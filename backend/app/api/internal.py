"""Endpoints que solo llama pg_cron, protegidos por `X-Internal-Secret`."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session as DbSession

from app.api.deps import require_internal_secret
from app.config import get_settings
from app.db import get_db
from app.services import accounts, jobs, maintenance
from app.services.ai import AIProvider, get_ai_provider
from app.services.youtube import VideoProvider, get_video_provider

router = APIRouter(prefix="/internal", dependencies=[Depends(require_internal_secret)])
logger = logging.getLogger("compabook.internal")


@router.post("/cleanup")
def cleanup(db: DbSession = Depends(get_db)) -> dict[str, int]:
    counts = maintenance.cleanup(db, accounts.utcnow())
    logger.info("cleanup: %s", counts)  # solo números; nada de correos ni datos de usuarios
    return counts


@router.post("/jobs")
def process_jobs(
    db: DbSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
    videos: VideoProvider = Depends(get_video_provider),
) -> dict[str, int]:
    settings = get_settings()
    counts = jobs.run_due_jobs(
        db, ai, videos, settings.jobs_max_per_run, settings.jobs_budget_seconds
    )
    logger.info("jobs: %s", counts)  # solo números; nada de conceptos ni de usuarios
    return counts
