import secrets

from fastapi import Depends, Header, Request, Response
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import get_db
from app.errors import ApiError
from app.models import User
from app.services import accounts
from app.session_cookie import COOKIE_NAME, set_session_cookie


def require_csrf_header(x_requested_with: str | None = Header(default=None)) -> None:
    """Todo POST/PUT/PATCH/DELETE exige `X-Requested-With: compabook` (diseno-tecnico.md §2.4).

    Un formulario de otro sitio no puede añadir esa cabecera.
    """
    if x_requested_with != "compabook":
        raise ApiError(403, "csrf", "Falta la cabecera X-Requested-With")


def require_internal_secret(x_internal_secret: str | None = Header(default=None)) -> None:
    """Protege /internal/*: solo pg_cron, que envía el secreto en `X-Internal-Secret`."""
    expected = get_settings().internal_secret
    if not expected:
        raise ApiError(503, "internal_unavailable", "INTERNAL_SECRET no está configurado")
    # Comparación en tiempo constante; el secreto nunca se registra ni se devuelve.
    if x_internal_secret is None or not secrets.compare_digest(x_internal_secret, expected):
        raise ApiError(401, "unauthorized", "No autorizado")


def client_ip(request: Request) -> str:
    """IP del cliente: el primer valor de `x-forwarded-for`, que pone Vercel."""
    forwarded = request.headers.get("x-forwarded-for", "")
    first = forwarded.split(",")[0].strip()
    if first:
        return first
    return request.client.host if request.client else "desconocida"


def current_user(request: Request, response: Response, db: DbSession = Depends(get_db)) -> User:
    """Usuario de la sesión (cookie `cb_session`). 401 si no hay sesión vigente.

    Los endpoints con sesión usan este usuario y nunca un `user_id` enviado por el cliente.
    Si la sesión se renovó (pasadas 24 h), se reenvía la cookie con la nueva caducidad.
    """
    token = request.cookies.get(COOKIE_NAME)
    user, renewed = accounts.authenticate(db, token)
    if renewed and token:
        set_session_cookie(response, token)
    return user
