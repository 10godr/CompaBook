import base64
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, require_csrf_header
from app.db import get_db
from app.errors import ApiError
from app.models import Concept, User
from app.repositories import ConceptRepository, VideoCacheRepository
from app.services import concepts as service
from app.services import jobs
from app.services.ai import AIProvider, get_ai_provider
from app.services.youtube import VideoProvider, get_video_provider

router = APIRouter(prefix="/concepts")

LIST_DEFAULT = 20
LIST_MAX = 50
QUERY_MAX = 200


class CreateBody(BaseModel):
    # La longitud se valida en el servicio: el máximo sale de la configuración.
    title: str


def _encode_cursor(concept: Concept) -> str:
    raw = f"{concept.created_at.isoformat()}|{concept.id}"
    return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[datetime, uuid.UUID]:
    try:
        raw = base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)).decode()
        created_at, concept_id = raw.split("|")
        return datetime.fromisoformat(created_at), uuid.UUID(concept_id)
    except ValueError:
        raise ApiError(
            422,
            "validation_error",
            "Datos no válidos",
            fields=[{"field": "cursor", "type": "invalid"}],
        ) from None


def _summary(concept: Concept, now: datetime) -> dict[str, object]:
    return {
        "id": concept.id,
        "title": concept.title,
        "language": concept.language,
        "created_at": concept.created_at,
        "card_title": concept.card.canonical_title if concept.card else None,
        **service.job_state(concept, now),
    }


def _card(concept: Concept) -> dict[str, object] | None:
    card = concept.card
    if card is None:
        return None
    return {
        "canonical_title": card.canonical_title,
        "what_is": card.what_is,
        "what_for": card.what_for,
        "example": card.example,
        "example_code": card.example_code,
        "example_code_language": card.example_code_language,
    }


def _videos(db: DbSession, concept: Concept) -> list[dict[str, object]]:
    """Los videos de la ficha, leídos al pedir el concepto (no se copian a cada concepto)."""
    card = concept.card
    if card is None:
        return []
    found = VideoCacheRepository(db).get(card.cache_slug, card.language)
    return [
        {
            "youtube_id": video.youtube_id,
            "title": video.title,
            "channel": video.channel,
            "thumbnail_url": video.thumbnail_url,
        }
        for video in found
    ]


@router.post("", status_code=201, dependencies=[Depends(require_csrf_header)])
def create_concept(
    body: CreateBody,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, object]:
    concept = service.create_concept(db, user, body.title)
    return {"id": concept.id, "status": concept.job.status}


@router.get("")
def list_concepts(
    q: str | None = Query(default=None, max_length=QUERY_MAX),
    limit: int = Query(default=LIST_DEFAULT, ge=1, le=LIST_MAX),
    cursor: str | None = Query(default=None, max_length=200),
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, object]:
    before = _decode_cursor(cursor) if cursor else None
    # Se pide uno de más para saber si hay otra página.
    found = ConceptRepository(db, user.id).list_page(
        limit + 1, query=(q or "").strip() or None, before=before
    )
    page = found[:limit]
    now = service.utcnow()
    return {
        "items": [_summary(concept, now) for concept in page],
        "next_cursor": _encode_cursor(page[-1]) if len(found) > limit else None,
    }


@router.get("/{concept_id}")
def get_concept(
    concept_id: uuid.UUID,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, object]:
    concept = ConceptRepository(db, user.id).get(concept_id)
    if concept is None:
        raise ApiError(404, "not_found", "No existe")
    return {
        **_summary(concept, service.utcnow()),
        "source": concept.source,
        "card": _card(concept),
        "videos": _videos(db, concept),
    }


@router.get("/{concept_id}/status")
def concept_status(
    concept_id: uuid.UUID,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, object]:
    concept = ConceptRepository(db, user.id).get(concept_id)
    if concept is None:
        raise ApiError(404, "not_found", "No existe")
    return service.job_state(concept, service.utcnow())


@router.post("/{concept_id}/process", dependencies=[Depends(require_csrf_header)])
def process_concept(
    concept_id: uuid.UUID,
    response: Response,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
    ai: AIProvider = Depends(get_ai_provider),
    videos: VideoProvider = Depends(get_video_provider),
) -> dict[str, object]:
    state, finished = jobs.process_concept(db, ai, videos, user, concept_id)
    if not finished:
        response.status_code = 202  # otro proceso lo está haciendo
    return state


@router.post("/{concept_id}/retry", status_code=202, dependencies=[Depends(require_csrf_header)])
def retry_concept(
    concept_id: uuid.UUID,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, object]:
    return service.retry_concept(db, user, concept_id)


@router.delete("/{concept_id}", dependencies=[Depends(require_csrf_header)])
def delete_concept(
    concept_id: uuid.UUID,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, bool]:
    if not ConceptRepository(db, user.id).delete(concept_id):
        raise ApiError(404, "not_found", "No existe")
    db.commit()
    return {"ok": True}
