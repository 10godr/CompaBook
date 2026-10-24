"""Contraseñas, tokens de sesión y códigos por correo (diseno-tecnico.md §2)."""

import hashlib
import hmac
import secrets
import uuid

from pwdlib import PasswordHash

from app.common_passwords import COMMON_PASSWORDS
from app.config import get_settings

PASSWORD_MIN = 8
PASSWORD_MAX = 128

# argon2id con los parámetros recomendados de pwdlib.
_hasher = PasswordHash.recommended()
# Se usa cuando el email no existe, para que el login tarde lo mismo y no revele qué cuentas hay.
_DUMMY_HASH = _hasher.hash("contraseña-ficticia-para-igualar-tiempos")


class WeakPassword(ValueError):
    """La contraseña no cumple la política. `code` identifica el motivo."""

    def __init__(self, code: str) -> None:
        super().__init__(code)
        self.code = code


def validate_password(password: str) -> None:
    if len(password) < PASSWORD_MIN:
        raise WeakPassword("too_short")
    if len(password) > PASSWORD_MAX:
        raise WeakPassword("too_long")
    if password.lower() in COMMON_PASSWORDS or len(set(password)) < 4:
        raise WeakPassword("too_common")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Con `password_hash=None` (usuario inexistente) verifica contra un hash ficticio y falla."""
    if password_hash is None:
        _hasher.verify(password, _DUMMY_HASH)
        return False
    return _hasher.verify(password, password_hash)


def verify_and_update_password(password: str, password_hash: str) -> tuple[bool, str | None]:
    """Como `verify_password`, y devuelve un hash nuevo si los parámetros de argon2 cambiaron."""
    return _hasher.verify_and_update(password, password_hash)


# --- Sesiones -----------------------------------------------------------------------------


def hash_token(token: str) -> str:
    """SHA-256 del token: basta porque el token tiene 256 bits de entropía."""
    return hashlib.sha256(token.encode()).hexdigest()


def new_session_token() -> tuple[str, str]:
    """Devuelve (token para la cookie, hash para guardar en la base de datos)."""
    token = secrets.token_urlsafe(32)
    return token, hash_token(token)


# --- Códigos por correo -------------------------------------------------------------------


def _secret_key() -> bytes:
    key = get_settings().secret_key
    if not key:
        raise RuntimeError("SECRET_KEY no está definida")
    return key.encode()


def new_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def hash_code(code: str, user_id: uuid.UUID, purpose: str) -> str:
    """HMAC-SHA256 con la clave del servidor, ligado al usuario y al propósito.

    Un código de 6 dígitos tiene solo un millón de combinaciones: con un hash simple se
    descubriría en segundos si se filtrara la base de datos. Sin `SECRET_KEY` no se puede.
    """
    message = f"{purpose}:{user_id}:{code}".encode()
    return hmac.new(_secret_key(), message, hashlib.sha256).hexdigest()


def verify_code(code: str, user_id: uuid.UUID, purpose: str, code_hash: str) -> bool:
    return hmac.compare_digest(hash_code(code, user_id, purpose), code_hash)
