"""Prueba de concepto de pg_cron → pg_net → Vercel (Fase 4). Se elimina al cerrar la fase.

Es el esqueleto de los endpoints /internal/*: los protege un secreto compartido que
pg_cron envía en la cabecera X-Internal-Secret. No toca la base de datos.
"""

import logging
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, Header, HTTPException

from app.config import get_settings

router = APIRouter(prefix="/internal")
logger = logging.getLogger("compabook.internal")


@router.post("/ping")
def ping(x_internal_secret: str | None = Header(default=None)) -> dict[str, object]:
    expected = get_settings().internal_secret
    if not expected:
        raise HTTPException(status_code=503, detail="INTERNAL_SECRET no configurado")
    # Comparación en tiempo constante; el secreto nunca se registra ni se devuelve.
    if x_internal_secret is None or not secrets.compare_digest(x_internal_secret, expected):
        raise HTTPException(status_code=401, detail="No autorizado")
    now = datetime.now(UTC).isoformat()
    logger.info("internal_ping recibido a las %s", now)
    return {"ok": True, "at": now}
