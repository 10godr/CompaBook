"""Prueba de concepto de la cookie de sesión (Fase 4). Se elimina al cerrar la fase.

Reproduce las opciones de la cookie `cb_session` de diseno-tecnico.md §2.1 para
comprobar cómo se comportan en Safari y en la PWA instalada en iPhone.
"""

import time

from fastapi import APIRouter, Header, HTTPException, Request, Response

from app.config import get_settings

router = APIRouter(prefix="/poc/cookie")

COOKIE_NAME = "cb_poc"
MAX_AGE = 30 * 24 * 3600
RENEW_AFTER = 24 * 3600


def _set_cookie(response: Response) -> None:
    response.set_cookie(
        COOKIE_NAME,
        str(int(time.time())),
        max_age=MAX_AGE,
        path="/",
        httponly=True,
        secure=get_settings().cookie_secure,
        samesite="lax",
    )


def _require_header(x_requested_with: str | None) -> None:
    if x_requested_with != "compabook":
        raise HTTPException(status_code=403, detail="Falta la cabecera X-Requested-With")


@router.post("")
def create(response: Response, x_requested_with: str | None = Header(default=None)) -> dict:
    _require_header(x_requested_with)
    _set_cookie(response)
    return {"created": True}


@router.get("")
def status(request: Request, response: Response) -> dict:
    value = request.cookies.get(COOKIE_NAME)
    if value is None or not value.isdigit():
        return {"present": False}
    age = int(time.time()) - int(value)
    # Renovación deslizante como en la sesión real: pasadas 24 h se reenvía la cookie.
    renewed = age > RENEW_AFTER
    if renewed:
        _set_cookie(response)
    return {"present": True, "age_seconds": age, "renewed": renewed}


@router.delete("")
def delete(response: Response, x_requested_with: str | None = Header(default=None)) -> dict:
    _require_header(x_requested_with)
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"deleted": True}
