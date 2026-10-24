"""Registro por invitación y verificación por código (diseno-tecnico.md §2.3 a §2.5)."""

import logging
import math
from datetime import UTC, datetime, timedelta

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session as DbSession

from app import security
from app.config import get_settings
from app.errors import ApiError
from app.models import User
from app.repositories import (
    AllowedEmailRepository,
    EmailCodeRepository,
    RateLimitRepository,
    SessionRepository,
    UserRepository,
)
from app.services.email import (
    EmailMessage,
    EmailProvider,
    already_registered_email,
    verification_email,
)

logger = logging.getLogger("compabook.accounts")

PURPOSE_VERIFY = "verify_email"
CODE_TTL = timedelta(minutes=15)
CODE_MAX_ATTEMPTS = 5

HOUR = timedelta(hours=1)
REGISTER_IP_LIMIT = 10  # registros por hora e IP
EMAIL_SEND_LIMIT = 5  # envíos de código por hora y correo

USER_AGENT_MAX = 300


def utcnow() -> datetime:
    return datetime.now(UTC)


def normalize_email(email: str) -> str:
    return email.strip().lower()


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


def _issue_verification_code(
    db: DbSession, mailer: EmailProvider, user: User, now: datetime
) -> None:
    code = security.new_code()
    code_hash = security.hash_code(code, user.id, PURPOSE_VERIFY)
    EmailCodeRepository(db).replace(user.id, PURPOSE_VERIFY, code_hash, now + CODE_TTL)
    db.commit()
    _send(mailer, verification_email(user.email, code, user.language))


def _send(mailer: EmailProvider, message: EmailMessage) -> None:
    # Si el correo falla el registro responde igual (no revela nada); el usuario puede reenviar.
    try:
        mailer.send(message)
    except Exception as error:
        logger.error("No se pudo enviar un correo: %s", type(error).__name__)


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
        _issue_verification_code(db, mailer, user, now)
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
        _issue_verification_code(db, mailer, user, now)


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
    invalid = ApiError(400, "invalid_code", "Código incorrecto o caducado")

    user = UserRepository(db).get_by_email(normalize_email(email))
    if user is None or user.disabled_at is not None or user.email_verified_at is not None:
        raise invalid

    codes = EmailCodeRepository(db)
    record = codes.latest_active(user.id, PURPOSE_VERIFY, now)
    if record is None or record.attempts >= CODE_MAX_ATTEMPTS:
        raise invalid

    if not security.verify_code(code, user.id, PURPOSE_VERIFY, record.code_hash):
        record.attempts += 1
        db.commit()
        raise invalid

    record.used_at = now
    UserRepository(db).mark_verified(user, now)
    token, token_hash = security.new_session_token()
    expires_at = now + timedelta(days=get_settings().session_days)
    agent = user_agent[:USER_AGENT_MAX] if user_agent else None
    SessionRepository(db, user.id).create(token_hash, expires_at, agent)
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
        _issue_verification_code(db, mailer, user, now)
