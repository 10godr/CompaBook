"""Prueba de concepto de las notificaciones push (Fase 4). Se elimina al cerrar la fase.

No guarda suscripciones: la página las envía en cada petición. Nunca se registran ni
se devuelven las claves de la suscripción.
"""

import json
import time
from urllib.parse import urlparse

from fastapi import APIRouter, Header, HTTPException
from pydantic import BaseModel
from pywebpush import WebPushException, webpush

from app.config import get_settings

router = APIRouter(prefix="/poc/push")

MAX_DELAY = 8

# El servidor hace una petición a la URL que trae la suscripción: solo se aceptan los
# servicios de push de Apple, Google, Mozilla y Microsoft para que no sirva de proxy.
ALLOWED_HOSTS = {
    "web.push.apple.com",
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
}
ALLOWED_SUFFIXES = (".notify.windows.com",)


class Keys(BaseModel):
    p256dh: str
    auth: str


class Subscription(BaseModel):
    endpoint: str
    keys: Keys


class SendRequest(BaseModel):
    subscription: Subscription
    delay: int = 0


def _allowed_endpoint(endpoint: str) -> bool:
    parsed = urlparse(endpoint)
    host = parsed.hostname or ""
    if parsed.scheme != "https":
        return False
    return host in ALLOWED_HOSTS or host.endswith(ALLOWED_SUFFIXES)


@router.get("/key")
def public_key() -> dict[str, str]:
    key = get_settings().vapid_public_key
    if not key:
        raise HTTPException(status_code=503, detail="VAPID no configurado")
    return {"publicKey": key}


@router.post("/send")
def send(
    body: SendRequest, x_requested_with: str | None = Header(default=None)
) -> dict[str, object]:
    if x_requested_with != "compabook":
        raise HTTPException(status_code=403, detail="Falta la cabecera X-Requested-With")
    settings = get_settings()
    if not settings.vapid_private_key:
        raise HTTPException(status_code=503, detail="VAPID no configurado")
    if not _allowed_endpoint(body.subscription.endpoint):
        raise HTTPException(status_code=400, detail="Servicio de push no admitido")

    # Margen para que dé tiempo a cerrar la app antes de que llegue el aviso.
    time.sleep(max(0, min(body.delay, MAX_DELAY)))
    try:
        webpush(
            subscription_info=body.subscription.model_dump(),
            data=json.dumps({"title": "CompaBook", "body": "Prueba de notificación"}),
            vapid_private_key=settings.vapid_private_key,
            vapid_claims={"sub": settings.vapid_subject},
            ttl=60,
        )
    except WebPushException as error:
        status = error.response.status_code if error.response is not None else None
        return {"sent": False, "status": status, "expired": status in (404, 410)}
    return {"sent": True}
