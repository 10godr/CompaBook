"""El trabajador de fichas y videos (diseno-tecnico.md §4.3 y §4.4).

Lo comparten `POST /concepts/{id}/process` (el usuario, al momento) y `POST /internal/jobs` (el
reloj): hacen exactamente lo mismo y solo cambia quién lo pide. Nunca se mantiene abierta una
transacción mientras se espera a Gemini o a YouTube: se reclama el trabajo y se confirma, se llama
al servicio externo y el resultado se guarda en otra transacción.
"""

import logging
import time
import uuid
from collections.abc import Callable
from datetime import datetime, timedelta

from sqlalchemy.orm import Session as DbSession

from app.errors import ApiError
from app.models import User
from app.repositories import (
    ConceptAliasRepository,
    ConceptCardRepository,
    ConceptRepository,
    JobQueueRepository,
    NewVideo,
    VideoCacheRepository,
)
from app.services import concepts
from app.services.ai import AIError, AIProvider
from app.services.aliases import normalize_title
from app.services.concepts import STALE_AFTER, job_state
from app.services.youtube import VideoProvider

logger = logging.getLogger("compabook.jobs")

# Espera antes del siguiente intento: tras el 1.º fallo 2 min, tras el 2.º 4 min. Con 3 intentos
# en total (`max_attempts`) no hace falta una tercera espera.
RETRY_BACKOFF = (timedelta(minutes=2), timedelta(minutes=4))
# Volver a preguntar no ayuda si el servicio se negó (clave o modelo mal, contenido bloqueado).
NOT_RETRYABLE = {"rejected", "not_configured"}


def _backoff(attempts: int) -> timedelta:
    return RETRY_BACKOFF[min(attempts, len(RETRY_BACKOFF)) - 1]


def process_concept(
    db: DbSession,
    ai: AIProvider,
    videos: VideoProvider,
    user: User,
    concept_id: uuid.UUID,
    now: datetime | None = None,
) -> tuple[dict[str, object], bool]:
    """`POST /process`: procesa el concepto del usuario. Devuelve el estado y si terminó."""
    result = run_job(db, ai, videos, user.id, concept_id, now)
    if result is None:
        raise ApiError(404, *concepts.NOT_FOUND)
    return result


def run_job(
    db: DbSession,
    ai: AIProvider,
    videos: VideoProvider,
    user_id: uuid.UUID,
    concept_id: uuid.UUID,
    now: datetime | None = None,
) -> tuple[dict[str, object], bool] | None:
    """Hace el trabajo del concepto. None si no existe (o es de otro usuario).

    Devuelve el estado y si esta llamada lo dejó resuelto (`completed`, `failed` o en cola para un
    reintento); False cuando no le tocaba — otro proceso lo tiene, o espera su turno de reintento —
    y el endpoint responde 202.
    """

    def moment() -> datetime:
        return now or concepts.utcnow()  # fresca en cada paso: Gemini puede tardar medio minuto

    repository = ConceptRepository(db, user_id)
    concept = repository.get(concept_id)
    if concept is None:
        return None
    # Se copia lo necesario antes de confirmar y de las llamadas largas.
    title, language = concept.title, concept.language
    card = concept.card
    card_slug = card.cache_slug if card else None
    claim_time = moment()
    claim = repository.claim_job(concept_id, claim_time, claim_time - STALE_AFTER)
    db.commit()
    if claim is None:
        state = job_state(concepts.reload_concept(repository, concept_id), claim_time)
        return state, state["status"] in ("completed", "failed")

    alias_result = "none"
    try:
        if card_slug is None:
            card_slug, alias_result = _ensure_card(
                db, ai, repository, concept_id, title, language, moment
            )
        query, canonical_title = _card_search_data(db, card_slug, language)
    except AIError as error:
        return _fail(db, repository, concept_id, error.kind, claim.attempts, moment())
    except Exception as error:  # un fallo nuestro no debe dejar el trabajo colgado
        db.rollback()
        logger.error("fallo inesperado al procesar el trabajo: %s", type(error).__name__)
        return _fail(db, repository, concept_id, "internal_error", claim.attempts, moment())

    repository.set_stage(concept_id, "finding_videos", moment())
    db.commit()
    try:
        video_result = _ensure_videos(
            db, videos, card_slug, language, query or canonical_title, moment
        )
    except Exception as error:  # los videos son un extra: la ficha ya está y se entrega igual
        db.rollback()
        logger.warning("sin videos: %s", type(error).__name__)
        video_result = "error"
    repository.complete_job(concept_id, moment())
    db.commit()
    # Solo contadores: nada del título ni de la respuesta (diseno-tecnico.md §5.5).
    logger.info("trabajo terminado alias=%s videos=%s", alias_result, video_result)
    return job_state(concepts.reload_concept(repository, concept_id), moment()), True


def _ensure_card(
    db: DbSession,
    ai: AIProvider,
    repository: ConceptRepository,
    concept_id: uuid.UUID,
    title: str,
    language: str,
    moment: Callable[[], datetime],
) -> tuple[str, str]:
    """Asigna la ficha al concepto: por alias si ese texto ya se vio, si no con Gemini.

    Devuelve el `cache_slug` y `hit` o `miss` (`none` si el título no admite alias).
    """
    aliases = ConceptAliasRepository(db)
    alias = normalize_title(title)
    found = aliases.get_card(language, alias) if alias else None
    db.commit()  # la lectura no deja una transacción abierta durante la llamada a Gemini
    if found is not None:
        repository.attach_card(concept_id, found.id)
        db.commit()
        return found.cache_slug, "hit"

    content = ai.generate_card(title, language)
    card, _ = ConceptCardRepository(db).insert_if_absent(
        canonical_title=content.content.canonical_title,
        cache_slug=content.content.cache_slug,
        language=language,
        what_is=content.content.what_is,
        what_for=content.content.what_for,
        example=content.content.example,
        example_code=content.content.example_code,
        example_code_language=content.content.example_code_language,
        youtube_search_query=content.content.youtube_search_query,
        model=content.model,
        now=moment(),
    )
    # El alias se guarda con la ficha ya guardada: así nunca apunta a algo que no existe.
    if alias:
        aliases.add_if_absent(language, alias, card.cache_slug, moment())
    repository.attach_card(concept_id, card.id)
    db.commit()
    return card.cache_slug, "miss" if alias else "none"


def _card_search_data(db: DbSession, cache_slug: str, language: str) -> tuple[str | None, str]:
    """La consulta de YouTube de la ficha (nula en las de la 6a) y su título, para buscar con él."""
    card = ConceptCardRepository(db).get_by_slug(cache_slug, language)
    assert card is not None  # la acabamos de asignar, o ya la tenía el concepto
    result = card.youtube_search_query, card.canonical_title
    db.commit()
    return result


def _ensure_videos(
    db: DbSession,
    provider: VideoProvider,
    cache_slug: str,
    language: str,
    query: str,
    moment: Callable[[], datetime],
) -> str:
    """Deja los videos del concepto en la caché. Devuelve el resultado, solo como contador.

    Si YouTube falla la ficha se entrega igual sin videos: no se marca `failed`, no se guarda nada
    en la caché (el fallo no se recuerda) y no se vuelve a intentar (decisión 2 de la 6b).
    """
    cache = VideoCacheRepository(db)
    cached = cache.get(cache_slug, language)
    db.commit()  # sin transacción abierta durante la llamada a YouTube
    if cached:
        return "hit"
    try:
        found = provider.search(query, language)
    except Exception as error:
        kind = getattr(error, "kind", type(error).__name__)
        logger.warning("sin videos: %s", kind)
        return "error"
    if not found:
        return "empty"
    cache.save_if_absent(
        cache_slug,
        language,
        [NewVideo(v.youtube_id, v.title, v.channel, v.thumbnail_url) for v in found],
        moment(),
    )
    db.commit()
    return "found"


def _fail(
    db: DbSession,
    repository: ConceptRepository,
    concept_id: uuid.UUID,
    kind: str,
    attempts: int,
    now: datetime,
) -> tuple[dict[str, object], bool]:
    """Cuenta el intento fallido: a la cola con espera, o `failed` si ya no quedan o no vale."""
    failed_attempts = attempts + 1
    max_attempts = concepts.reload_concept(repository, concept_id).job.max_attempts
    retry_at = None
    if kind not in NOT_RETRYABLE and failed_attempts < max_attempts:
        retry_at = now + _backoff(failed_attempts)
    repository.fail_job(concept_id, kind, now, retry_at)
    db.commit()
    logger.warning(
        "trabajo fallido: %s intento=%d reintento=%s", kind, failed_attempts, bool(retry_at)
    )
    return job_state(concepts.reload_concept(repository, concept_id), now), True


# --- El reloj -------------------------------------------------------------------------------


def run_due_jobs(
    db: DbSession,
    ai: AIProvider,
    videos: VideoProvider,
    max_jobs: int,
    budget_seconds: float,
    now: datetime | None = None,
    monotonic: Callable[[], float] = time.monotonic,
) -> dict[str, int]:
    """`POST /internal/jobs`: procesa hasta `max_jobs` trabajos a los que ya les toca.

    No empieza otro si ya pasaron `budget_seconds`: la función de Vercel muere a los 60 s, y un
    trabajo puede tardar medio minuto. Devuelve solo contadores.
    """
    started = monotonic()
    current = now or concepts.utcnow()
    due = JobQueueRepository(db).due(current, current - STALE_AFTER, max_jobs)
    db.commit()
    counts = {"due": len(due), "completed": 0, "retrying": 0, "failed": 0, "skipped": 0}
    for position, job in enumerate(due):
        if position and monotonic() - started >= budget_seconds:
            counts["skipped"] += len(due) - position
            break
        try:
            result = run_job(db, ai, videos, job.user_id, job.concept_id, now)
        except Exception as error:  # un trabajo roto no debe parar a los demás
            db.rollback()
            logger.error("fallo inesperado en el reloj: %s", type(error).__name__)
            counts["failed"] += 1
            continue
        status = result[0]["status"] if result else None
        if status == "completed":
            counts["completed"] += 1
        elif status == "pending" and result and result[1]:
            counts["retrying"] += 1
        elif status == "failed":
            counts["failed"] += 1
        else:
            counts["skipped"] += 1  # otro proceso lo tomó antes, o ya no existe
    return counts
