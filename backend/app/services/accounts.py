"""Cuentas: registro, verificación, login, sesión y recuperación (diseno-tecnico.md §2)."""

import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app import security
from app.config import get_settings
from app.errors import ApiError
from app.models import EmailCode, User
from app.repositories import (
    AllowedEmailRepository,
    EmailCodeRepository,
    RateLimitRepository,
    SessionRepository,
    UserRepository,
)
from app.repositories.sessions import delete_by_token_hash, find_active_by_token_hash
from app.services.email import (
    EmailMessage,
    EmailProvider,
    already_registered_email,
    reset_password_email,
    verification_email,
)

logger = logging.getLogger("compabook.accounts")

PURPOSE_VERIFY = "verify_email"
PURPOSE_RESET = "reset_password"
CODE_TTL = timedelta(minutes=15)
CODE_MAX_ATTEMPTS = 5

HOUR = timedelta(hours=1)
REGISTER_IP_LIMIT = 10  # registros por hora e IP
EMAIL_SEND_LIMIT = 5  # envíos de código por hora y correo
LOGIN_IP_LIMIT = 30  # logins (cualquier resultado) por hora e IP

# Login fallido por correo + IP: 5 fallos en 15 minutos abren una espera de 15 minutos; la
# espera se duplica en cada bloqueo siguiente (30 min, y 1 h como máximo). La cuenta nunca se
# bloquea: el límite es por correo + IP, así que el dueño puede entrar desde otra red.
LOGIN_FAIL_THRESHOLD = 5
LOGIN_FAIL_WINDOW = timedelta(minutes=15)
LOGIN_BASE_WAIT = timedelta(minutes=15)
LOGIN_MAX_WAIT = timedelta(hours=1)
LOGIN_LOCK_MEMORY = timedelta(hours=24)  # los bloqueos se "olvidan" tras un día sin ninguno

SESSION_RENEW_AFTER = timedelta(hours=24)
USER_AGENT_MAX = 300

INVALID_CODE = ("invalid_code", "Código incorrecto o caducado")
UNAUTHORIZED = ("unauthorized", "No has iniciado sesión")


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


def _api_error(status_code: int, pair: tuple[str, str], **extra: object) -> ApiError:
    return ApiError(status_code, pair[0], pair[1], **extra)


def enforce_rate_limit(
    db: DbSession, bucket: str, key: str, limit: int, window: timedelta, now: datetime
) -> None:
    """Cuenta los intentos de la ventana; si ya se alcanzó el límite responde 429.

    Solo se anotan los intentos permitidos: los bloqueados no alargan la espera. El intento se
    guarda (commit) enseguida para que cuente aunque la petición falle más adelante.
    """
    repository = RateLimitRepository(db)
    count, oldest = repository.count_and_oldest(bucket, key, now, window)
    if count >= limit and oldest is not None:
        retry_after = max(1, math.ceil((oldest + window - now).total_seconds()))
        raise ApiError(
            429, "rate_limited", "Demasiados intentos; inténtalo más tarde", retry_after=retry_after
        )
    repository.add(bucket, key, now)
    db.commit()


# --- Códigos por correo -------------------------------------------------------------------


def _send(mailer: EmailProvider, message: EmailMessage) -> None:
    # Si el correo falla la API responde igual (no revela nada); el usuario puede reenviar.
    try:
        mailer.send(message)
    except Exception as error:
        logger.error("No se pudo enviar un correo: %s", type(error).__name__)


def _issue_code(
    db: DbSession, mailer: EmailProvider, user: User, purpose: str, now: datetime
) -> None:
    code = security.new_code()
    code_hash = security.hash_code(code, user.id, purpose)
    EmailCodeRepository(db).replace(user.id, purpose, code_hash, now + CODE_TTL)
    db.commit()
    template = verification_email if purpose == PURPOSE_VERIFY else reset_password_email
    _send(mailer, template(user.email, code, user.language))


def _consume_code(db: DbSession, user: User, purpose: str, code: str, now: datetime) -> EmailCode:
    """Comprueba el código; lo marca como usado (el commit lo hace quien llama).

    Todos los fallos son el mismo 400 `invalid_code`. Cada fallo gasta un intento del código.
    """
    record = EmailCodeRepository(db).latest_active(user.id, purpose, now)
    if record is None or record.attempts >= CODE_MAX_ATTEMPTS:
        raise _api_error(400, INVALID_CODE)
    if not security.verify_code(code, user.id, purpose, record.code_hash):
        record.attempts += 1
        db.commit()
        raise _api_error(400, INVALID_CODE)
    record.used_at = now
    return record


# --- Registro y verificación ----------------------------------------------------------------


def register(
    db: DbSession,
    mailer: EmailProvider,
    *,
    email: str,
    password: str,
    language: str,
    timezone: str,
    ip: str,
    now: datetime | None = None,
) -> None:
    now = now or utcnow()
    email = normalize_email(email)

    enforce_rate_limit(db, "register_ip", ip, REGISTER_IP_LIMIT, HOUR, now)

    if not AllowedEmailRepository(db).is_allowed(email):
        raise ApiError(403, "registration_not_allowed", "El registro es solo por invitación")

    try:
        security.validate_password(password)
    except security.WeakPassword as error:
        raise ApiError(422, "weak_password", "Contraseña no válida", reason=error.code) from error

    # Se hashea siempre, exista o no la cuenta, para que el tiempo no delate cuáles existen.
    password_hash = security.hash_password(password)

    enforce_rate_limit(db, "email_send", email, EMAIL_SEND_LIMIT, HOUR, now)

    users = UserRepository(db)
    user = users.get_by_email(email)
    if user is None:
        try:
            user = users.create(email, password_hash, language, timezone)
        except IntegrityError:
            # Otro registro del mismo correo se coló a la vez; ya recibirá su código.
            db.rollback()
            return
        _issue_code(db, mailer, user, PURPOSE_VERIFY, now)
    elif user.disabled_at is not None:
        db.commit()  # cuenta suspendida: no se envía nada
    elif user.email_verified_at is not None:
        db.commit()
        _send(mailer, already_registered_email(user.email, user.language))
    else:
        # Cuenta sin verificar: se actualizan los datos y se envía un código nuevo. No hay
        # riesgo de toma de control: sin el código de ese correo no se puede verificar.
        user.password_hash = password_hash
        user.language = language
        user.timezone = timezone
        _issue_code(db, mailer, user, PURPOSE_VERIFY, now)


def _open_session(db: DbSession, user: User, user_agent: str | None, now: datetime) -> str:
    """Crea la sesión y devuelve el token para la cookie (en la base solo va su hash)."""
    token, token_hash = security.new_session_token()
    expires_at = now + timedelta(days=get_settings().session_days)
    agent = user_agent[:USER_AGENT_MAX] if user_agent else None
    SessionRepository(db, user.id).create(token_hash, expires_at, agent, last_used_at=now)
    return token


def verify_email(
    db: DbSession,
    *,
    email: str,
    code: str,
    user_agent: str | None,
    now: datetime | None = None,
) -> tuple[User, str]:
    """Verifica el código e inicia sesión. Devuelve el usuario y el token para la cookie."""
    now = now or utcnow()
    user = UserRepository(db).get_by_email(normalize_email(email))
    if user is None or user.disabled_at is not None or user.email_verified_at is not None:
        raise _api_error(400, INVALID_CODE)

    _consume_code(db, user, PURPOSE_VERIFY, code, now)
    UserRepository(db).mark_verified(user, now)
    token = _open_session(db, user, user_agent, now)
    db.commit()
    return user, token


def resend_code(
    db: DbSession,
    mailer: EmailProvider,
    *,
    email: str,
    now: datetime | None = None,
) -> None:
    """Reenvía el código de verificación. El límite cuenta por correo exista o no la cuenta."""
    now = now or utcnow()
    email = normalize_email(email)
    enforce_rate_limit(db, "email_send", email, EMAIL_SEND_LIMIT, HOUR, now)

    user = UserRepository(db).get_by_email(email)
    if (
        user is not None
        and user.disabled_at is None
        and user.email_verified_at is None
        and AllowedEmailRepository(db).is_allowed(email)
    ):
        _issue_code(db, mailer, user, PURPOSE_VERIFY, now)


# --- Login, sesión y logout ------------------------------------------------------------------


def _login_wait_remaining(db: DbSession, key: str, now: datetime) -> int | None:
    """Segundos que faltan para poder reintentar el login con esta clave, o None si puede."""
    locks, last_lock = RateLimitRepository(db).window_stats(
        "login_lock", key, now, LOGIN_LOCK_MEMORY
    )
    if last_lock is None:
        return None
    wait = min(LOGIN_BASE_WAIT * 2 ** (locks - 1), LOGIN_MAX_WAIT)
    remaining = (last_lock + wait - now).total_seconds()
    return math.ceil(remaining) if remaining > 0 else None


def _record_login_failure(db: DbSession, key: str, now: datetime) -> None:
    """Anota un fallo; al quinto en 15 minutos (desde el último bloqueo) abre un bloqueo."""
    repository = RateLimitRepository(db)
    repository.add("login_fail", key, now)
    _, last_lock = repository.window_stats("login_lock", key, now, LOGIN_LOCK_MEMORY)
    since = now - LOGIN_FAIL_WINDOW
    if last_lock is not None and last_lock > since:
        since = last_lock
    if repository.count_since("login_fail", key, since) >= LOGIN_FAIL_THRESHOLD:
        repository.add("login_lock", key, now)
    db.commit()


def login(
    db: DbSession,
    *,
    email: str,
    password: str,
    ip: str,
    user_agent: str | None,
    now: datetime | None = None,
) -> tuple[User, str]:
    now = now or utcnow()
    email = normalize_email(email)

    enforce_rate_limit(db, "login_ip", ip, LOGIN_IP_LIMIT, HOUR, now)
    key = f"{email}|{ip}"
    remaining = _login_wait_remaining(db, key, now)
    if remaining is not None:
        raise ApiError(
            429, "rate_limited", "Demasiados intentos; inténtalo más tarde", retry_after=remaining
        )

    user = UserRepository(db).get_by_email(email)
    # Con usuario inexistente se verifica contra un hash ficticio: mismo tiempo y mismo error.
    valid = security.verify_password(password, user.password_hash if user else None)
    if user is None or not valid or user.disabled_at is not None:
        _record_login_failure(db, key, now)
        raise ApiError(401, "invalid_credentials", "Email o contraseña incorrectos")

    if user.email_verified_at is None:
        # La contraseña era correcta, así que no se castiga: se ofrece reenviar el código.
        raise ApiError(403, "email_not_verified", "Verifica tu correo para poder entrar")

    RateLimitRepository(db).clear("login_fail", key)
    RateLimitRepository(db).clear("login_lock", key)
    token = _open_session(db, user, user_agent, now)
    db.commit()
    return user, token


def authenticate(
    db: DbSession, token: str | None, now: datetime | None = None
) -> tuple[User, bool]:
    """Usuario de la cookie de sesión y si hay que reenviar la cookie (renovación deslizante).

    Pasadas 24 h desde el último uso, la sesión se renueva 30 días más: quien usa la app no
    vuelve a entrar y una sesión sin uso caduca a los 30 días.
    """
    now = now or utcnow()
    found = find_active_by_token_hash(db, security.hash_token(token), now) if token else None
    if found is None:
        raise _api_error(401, UNAUTHORIZED)
    session, user = found
    renewed = session.last_used_at is None or now - session.last_used_at > SESSION_RENEW_AFTER
    if renewed:
        session.last_used_at = now
        session.expires_at = now + timedelta(days=get_settings().session_days)
        db.commit()
    return user, renewed


def logout(db: DbSession, token: str | None) -> None:
    if token:
        delete_by_token_hash(db, security.hash_token(token))
        db.commit()


# --- Recuperar contraseña --------------------------------------------------------------------


def forgot_password(
    db: DbSession,
    mailer: EmailProvider,
    *,
    email: str,
    now: datetime | None = None,
) -> None:
    """Envía un código si la cuenta existe y está verificada. El límite cuenta siempre."""
    now = now or utcnow()
    email = normalize_email(email)
    enforce_rate_limit(db, "email_send", email, EMAIL_SEND_LIMIT, HOUR, now)

    user = UserRepository(db).get_by_email(email)
    if user is not None and user.disabled_at is None and user.email_verified_at is not None:
        _issue_code(db, mailer, user, PURPOSE_RESET, now)


def reset_password(
    db: DbSession,
    *,
    email: str,
    code: str,
    new_password: str,
    now: datetime | None = None,
) -> None:
    """Cambia la contraseña con el código y cierra todas las sesiones de la cuenta."""
    now = now or utcnow()
    try:
        security.validate_password(new_password)
    except security.WeakPassword as error:
        # Antes de mirar el código, para no gastar un intento por una contraseña floja.
        raise ApiError(422, "weak_password", "Contraseña no válida", reason=error.code) from error

    user = UserRepository(db).get_by_email(normalize_email(email))
    if user is None or user.disabled_at is not None or user.email_verified_at is None:
        raise _api_error(400, INVALID_CODE)

    _consume_code(db, user, PURPOSE_RESET, code, now)
    user.password_hash = security.hash_password(new_password)
    SessionRepository(db, user.id).revoke_all()
    db.commit()


# --- Mi cuenta -------------------------------------------------------------------------------

PASSWORD_CHECK_LIMIT = 5  # comprobaciones de la contraseña actual cada 15 minutos y usuario
PASSWORD_CHECK_WINDOW = timedelta(minutes=15)


def update_profile(
    db: DbSession, user: User, *, language: str | None, timezone: str | None
) -> User:
    if language is not None:
        user.language = language
    if timezone is not None:
        user.timezone = timezone
    db.commit()
    return user


def _check_current_password(db: DbSession, user: User, password: str, now: datetime) -> None:
    """Pide la contraseña actual antes de una acción delicada, con límite de intentos.

    Sin límite, quien robara una sesión podría adivinar la contraseña desde aquí.
    """
    enforce_rate_limit(
        db, "password_check", str(user.id), PASSWORD_CHECK_LIMIT, PASSWORD_CHECK_WINDOW, now
    )
    if not security.verify_password(password, user.password_hash):
        raise ApiError(400, "wrong_password", "La contraseña actual no es correcta")


def change_password(
    db: DbSession,
    user: User,
    *,
    current_token: str | None,
    current_password: str,
    new_password: str,
    now: datetime | None = None,
) -> None:
    """Cambia la contraseña y cierra las demás sesiones; la actual sigue abierta."""
    now = now or utcnow()
    _check_current_password(db, user, current_password, now)
    try:
        security.validate_password(new_password)
    except security.WeakPassword as error:
        raise ApiError(422, "weak_password", "Contraseña no válida", reason=error.code) from error

    user.password_hash = security.hash_password(new_password)
    keep = security.hash_token(current_token) if current_token else ""
    SessionRepository(db, user.id).revoke_others(keep)
    db.commit()


def delete_account(
    db: DbSession, user: User, *, password: str, now: datetime | None = None
) -> None:
    """Borra el usuario y, en cascada, sus sesiones y códigos (y más adelante sus conceptos).

    No toca `allowed_emails`: la invitación es del administrador, no del usuario.
    """
    now = now or utcnow()
    _check_current_password(db, user, password, now)
    db.delete(user)
    db.commit()
