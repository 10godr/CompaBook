"""Endpoints que solo llama pg_cron, protegidos por `X-Internal-Secret`."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.api.deps import require_internal_secret
from app.db import get_db
from app.services import accounts, maintenance

router = APIRouter(prefix="/internal", dependencies=[Depends(require_internal_secret)])
logger = logging.getLogger("compabook.internal")


@router.post("/cleanup")
def cleanup(db: DbSession = Depends(get_db)) -> dict[str, int]:
    counts = maintenance.cleanup(db, accounts.utcnow())
    logger.info("cleanup: %s", counts)  # solo números; nada de correos ni datos de usuarios
    return counts
