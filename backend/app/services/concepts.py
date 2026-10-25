"""Conceptos: crear, estado, reintentar y los límites diarios (diseno-tecnico.md §4).

Regla central: el concepto se guarda ANTES de llamar a la IA. Si Gemini falla, el usuario
conserva lo que escribió y puede reintentar. Procesar un trabajo está en `services/jobs.py`.
"""

import logging
import math
import uuid
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.errors import ApiError
from app.models import Concept, User
from app.repositories import ConceptRepository, RateLimitRepository

logger = logging.getLogger("compabook.concepts")

BUCKET_CREATE = "concept_create"
BUCKET_RETRY = "retry"
# Un trabajo `processing` más viejo que esto es de una función que murió a medias.
STALE_AFTER = timedelta(minutes=5)
TITLE_HARD_MAX = 200  # lo fija un check de la base de datos

NOT_FOUND = ("not_found", "No existe")


def utcnow() -> datetime:
    return datetime.now(UTC)


def title_max() -> int:
    return min(get_settings().concept_title_max, TITLE_HARD_MAX)


def _not_found() -> ApiError:
    return ApiError(404, NOT_FOUND[0], NOT_FOUND[1])


# --- Límites diarios ------------------------------------------------------------------------


def _local_day_start(user: User, now: datetime) -> datetime:
    """Medianoche local del usuario, en UTC: el «día» de los límites (contexto.md §5.5)."""
    try:
        zone = ZoneInfo(user.timezone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        zone = ZoneInfo("UTC")
    local = now.astimezone(zone)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(UTC)


def _used_today(db: DbSession, user: User, bucket: str, now: datetime) -> int:
    return RateLimitRepository(db).count_since(bucket, str(user.id), _local_day_start(user, now))


def usage(db: DbSession, user: User, now: datetime | None = None) -> dict[str, int]:
    now = now or utcnow()
    return {
        "concepts_today": _used_today(db, user, BUCKET_CREATE, now),
        "daily_limit": get_settings().daily_concept_limit,
    }


def _check_daily_limit(db: DbSession, user: User, bucket: str, limit: int, now: datetime) -> None:
    """429 `daily_limit_reached` si el usuario ya gastó su cupo del día local.

    El tope es blando: dos peticiones simultáneas pueden pasar una de más. No importa, porque
    el límite protege la cuota de la IA, no es una cuenta exacta.
    """
    if _used_today(db, user, bucket, now) >= limit:
        next_day = _local_day_start(user, now) + timedelta(days=1)
        retry_after = max(1, math.ceil((next_day - now).total_seconds()))
        raise ApiError(
            429,
            "daily_limit_reached",
            "Has llegado al límite de hoy",
            limit=limit,
            retry_after=retry_after,
        )


# --- Estado ---------------------------------------------------------------------------------


def job_state(concept: Concept, now: datetime) -> dict[str, object]:
    """`status`, `stage` y `attempts`; un trabajo `processing` abandonado se ve como en cola.

    Nadie lo está haciendo, pero el reloj (o un `/process`) lo recogerá solo: el usuario no
    tiene que pulsar Reintentar.
    """
    job = concept.job
    abandoned = (
        job.status == "processing"
        and job.locked_at is not None
        and now - job.locked_at > STALE_AFTER
    )
    if abandoned:
        return {"status": "pending", "stage": "queued", "attempts": job.attempts}
    return {"status": job.status, "stage": job.stage, "attempts": job.attempts}


# --- Crear ----------------------------------------------------------------------------------


def create_concept(db: DbSession, user: User, title: str, now: datetime | None = None) -> Concept:
    """Guarda el concepto y su trabajo (y el uso del día) en una sola transacción."""
    now = now or utcnow()
    title = title.strip()
    if not 1 <= len(title) <= title_max():
        raise ApiError(
            422,
            "validation_error",
            "Datos no válidos",
            fields=[{"field": "title", "type": "string_length"}],
        )
    _check_daily_limit(db, user, BUCKET_CREATE, get_settings().daily_concept_limit, now)
    concept = ConceptRepository(db, user.id).create(title, user.language, "app", now)
    RateLimitRepository(db).add(BUCKET_CREATE, str(user.id), now)
    db.commit()
    return concept


# --- Reintentar ----------------------------------------------------------------------------


def reload_concept(concepts: ConceptRepository, concept_id: uuid.UUID) -> Concept:
    concept = concepts.get(concept_id)
    assert concept is not None  # acabamos de leerlo; si lo borraron en medio, es un 500 honesto
    return concept


def retry_concept(
    db: DbSession, user: User, concept_id: uuid.UUID, now: datetime | None = None
) -> dict[str, object]:
    """Deja en cola un trabajo fallido. El frontend llama a /process después."""
    now = now or utcnow()
    concepts = ConceptRepository(db, user.id)
    concept = concepts.get(concept_id)
    if concept is None:
        raise _not_found()
    if job_state(concept, now)["status"] != "failed":
        raise ApiError(409, "not_retryable", "Solo se reintenta un concepto que falló")
    _check_daily_limit(db, user, BUCKET_RETRY, get_settings().daily_retry_limit, now)
    RateLimitRepository(db).add(BUCKET_RETRY, str(user.id), now)
    concepts.reset_job(concept_id, now)
    db.commit()
    return job_state(reload_concept(concepts, concept_id), now)
