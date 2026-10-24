import logging

from fastapi import APIRouter, FastAPI, HTTPException
from sqlalchemy import text

from app import poc, poc_cron, poc_push
from app.api import auth, concepts, internal, me
from app.config import get_settings
from app.db import get_engine
from app.errors import register_error_handlers

# Vercel recoge la salida estándar; sin esto los mensajes INFO no se ven.
logging.basicConfig(level=get_settings().log_level)

app = FastAPI(title="CompaBook API")
register_error_handlers(app)

router = APIRouter(prefix="/api/v1")
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(concepts.router)
router.include_router(internal.router)
router.include_router(poc.router)
router.include_router(poc_push.router)
router.include_router(poc_cron.router)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/db")
def health_db() -> dict[str, str]:
    try:
        with get_engine().connect() as connection:
            connection.execute(text("select 1"))
    except Exception as error:
        # Sin detalles al cliente: el mensaje de la base de datos puede incluir la conexión.
        raise HTTPException(status_code=503, detail="Base de datos no disponible") from error
    return {"status": "ok"}


app.include_router(router)
