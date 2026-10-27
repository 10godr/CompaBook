"""Envío de notificaciones push (diseno-tecnico.md §1.6).

El envío va detrás de `PushProvider`: en producción lo hace `WebPushProvider` (pywebpush, claves
VAPID) y en los tests una implementación falsa. Nunca se registra el endpoint, las claves ni el
texto del aviso: solo el tipo de fallo.
"""

import json
import logging
from dataclasses import dataclass
from typing import Literal, Protocol
from urllib.parse import urlparse

import requests
from pywebpush import WebPushException, webpush

from app.config import get_settings

logger = logging.getLogger("compabook.push")

# El servidor hace una petición a la URL que trae la suscripción: solo se aceptan los servicios
# de push de Apple, Google, Mozilla y Microsoft, para que no sirva de proxy hacia otros sitios.
ALLOWED_HOSTS = {
    "web.push.apple.com",
    "fcm.googleapis.com",
    "updates.push.services.mozilla.com",
}
ALLOWED_SUFFIXES = (".notify.windows.com",)

PushErrorKind = Literal["expired", "unavailable", "rejected", "not_configured"]


def is_allowed_endpoint(endpoint: str) -> bool:
    try:
        parsed = urlparse(endpoint)
        host = parsed.hostname or ""
    except ValueError:
        return False
    if parsed.scheme != "https":
        return False
    return host in ALLOWED_HOSTS or host.endswith(ALLOWED_SUFFIXES)


class PushError(Exception):
    """Fallo del envío. Solo lleva el tipo: nunca el endpoint, las claves ni el mensaje.

    - `expired`: el servicio dice que el dispositivo ya no existe (404/410): se da de baja.
    - `unavailable`: caída, límite de uso, tiempo agotado o error 5xx: se puede reintentar.
    - `rejected`: el servicio rechazó el envío (clave VAPID, datos o destino no válidos).
    - `not_configured`: faltan las claves VAPID.
    """

    def __init__(self, kind: PushErrorKind) -> None:
        super().__init__(kind)
        self.kind = kind


@dataclass(frozen=True)
class PushTarget:
    endpoint: str
    p256dh: str
    auth: str


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str
    # Ruta de la web que abre al tocar la notificación (p. ej. «/cuaderno/<id>»).
    url: str = "/"
    # Notificaciones con la misma etiqueta se sustituyen en lugar de apilarse.
    tag: str | None = None
    # Segundos que el servicio de push guarda el aviso si el dispositivo está apagado.
    ttl: int = 3600


class PushProvider(Protocol):
    def send(self, target: PushTarget, message: PushMessage) -> None:
        """Envía el aviso o lanza `PushError`."""


class WebPushProvider:
    def __init__(self, private_key: str | None, subject: str, timeout: float) -> None:
        self.private_key = private_key
        self.subject = subject
        self.timeout = timeout

    def send(self, target: PushTarget, message: PushMessage) -> None:
        if not self.private_key:
            raise PushError("not_configured")
        if not is_allowed_endpoint(target.endpoint):
            raise PushError("rejected")
        payload = {"title": message.title, "body": message.body, "url": message.url}
        if message.tag:
            payload["tag"] = message.tag
        try:
            webpush(
                subscription_info={
                    "endpoint": target.endpoint,
                    "keys": {"p256dh": target.p256dh, "auth": target.auth},
                },
                data=json.dumps(payload),
                vapid_private_key=self.private_key,
                vapid_claims={"sub": self.subject},
                ttl=message.ttl,
                timeout=self.timeout,
            )
        except WebPushException as error:
            # `str(error)` lleva el cuerpo de la respuesta: solo se mira el código.
            raise PushError(_kind_of(error.status_code)) from None
        except requests.RequestException:
            raise PushError("unavailable") from None
        except Exception:
            # Claves mal formadas u otro fallo local: el detalle puede incluir las claves.
            raise PushError("rejected") from None


def _kind_of(status: int | None) -> PushErrorKind:
    if status in (404, 410):
        return "expired"
    if status is None or status == 429 or status >= 500:
        return "unavailable"
    return "rejected"


def get_push_provider() -> PushProvider:
    settings = get_settings()
    return WebPushProvider(
        settings.vapid_private_key, settings.vapid_subject, settings.push_timeout_seconds
    )
