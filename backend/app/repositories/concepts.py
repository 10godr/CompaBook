import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import and_, delete, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from app.models import Concept, ConceptAlias, ConceptCard, ProcessingJob, VideoCache


def _like_pattern(text: str) -> str:
    """Texto del buscador como patrón de `ILIKE`: `%`, `_` y `\\` valen como letras normales."""
    escaped = text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


class ConceptRepository:
    """Conceptos y sus trabajos de UN usuario.

    Recibe el `user_id` de la sesión y lo aplica en cada consulta; nunca se acepta uno del
    cliente. Un concepto ajeno es, para este repositorio, un concepto que no existe.
    """

    def __init__(self, db: DbSession, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def create(self, title: str, language: str, source: str, now: datetime) -> Concept:
        """Guarda el concepto y su trabajo `pending` juntos: el concepto nunca queda sin trabajo."""
        concept = Concept(
            user_id=self.user_id, title=title, language=language, source=source, created_at=now
        )
        concept.job = ProcessingJob(user_id=self.user_id, next_run_at=now, created_at=now)
        self.db.add(concept)
        self.db.flush()
        return concept

    def get(self, concept_id: uuid.UUID) -> Concept | None:
        return self.db.scalar(
            select(Concept)
            .where(Concept.id == concept_id, Concept.user_id == self.user_id)
            .options(joinedload(Concept.card), joinedload(Concept.job))
            # Los cambios del trabajo se hacen con UPDATE directo: al volver a leer, que la
            # sesión no devuelva el objeto viejo que ya tenía.
            .execution_options(populate_existing=True)
        )

    def list_page(
        self,
        limit: int,
        query: str | None = None,
        before: tuple[datetime, uuid.UUID] | None = None,
    ) -> list[Concept]:
        """Del más nuevo al más viejo. `before` es (fecha, id) del último que ya se mostró."""
        statement = (
            select(Concept)
            .where(Concept.user_id == self.user_id)
            .options(joinedload(Concept.card), joinedload(Concept.job))
            .order_by(Concept.created_at.desc(), Concept.id.desc())
            .limit(limit)
        )
        if query:
            statement = statement.where(Concept.title.ilike(_like_pattern(query), escape="\\"))
        if before:
            created_at, concept_id = before
            statement = statement.where(
                or_(
                    Concept.created_at < created_at,
                    and_(Concept.created_at == created_at, Concept.id < concept_id),
                )
            )
        return list(self.db.scalars(statement).unique())

    def delete(self, concept_id: uuid.UUID) -> bool:
        """Elimina el concepto (y su trabajo, en cascada). False si no existe o es de otro."""
        result = self.db.execute(
            delete(Concept).where(Concept.id == concept_id, Concept.user_id == self.user_id)
        )
        return result.rowcount > 0

    def attach_card(self, concept_id: uuid.UUID, card_id: uuid.UUID) -> None:
        self.db.execute(
            update(Concept)
            .where(Concept.id == concept_id, Concept.user_id == self.user_id)
            .values(card_id=card_id)
        )

    # --- Trabajos -------------------------------------------------------------------------

    def claim_job(self, concept_id: uuid.UUID, now: datetime) -> bool:
        """Toma el trabajo `pending` del concepto. False si no lo está o ya lo tiene otro proceso.

        `SKIP LOCKED` hace que un segundo proceso no espere: pasa de largo y se entera de que
        el trabajo ya no está libre.
        """
        job_id = self.db.scalar(
            select(ProcessingJob.id)
            .where(
                ProcessingJob.concept_id == concept_id,
                ProcessingJob.user_id == self.user_id,
                ProcessingJob.status == "pending",
            )
            .with_for_update(skip_locked=True)
        )
        if job_id is None:
            return False
        self.db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.id == job_id)
            .values(status="processing", stage="writing", locked_at=now, updated_at=now)
        )
        return True

    def complete_job(self, concept_id: uuid.UUID, now: datetime) -> None:
        self._update_job(
            concept_id,
            status="completed",
            stage="done",
            locked_at=None,
            last_error=None,
            updated_at=now,
        )

    def fail_job(self, concept_id: uuid.UUID, error: str, now: datetime) -> None:
        """Marca el trabajo como fallido. `error` es solo el tipo, nunca contenido."""
        self.db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.concept_id == concept_id, ProcessingJob.user_id == self.user_id)
            .values(
                status="failed",
                locked_at=None,
                last_error=error,
                attempts=ProcessingJob.attempts + 1,
                updated_at=now,
            )
        )

    def reset_job(self, concept_id: uuid.UUID, now: datetime) -> None:
        """Vuelve a dejar el trabajo en cola (Reintentar)."""
        self._update_job(
            concept_id,
            status="pending",
            stage="queued",
            attempts=0,
            next_run_at=now,
            locked_at=None,
            updated_at=now,
        )

    def _update_job(self, concept_id: uuid.UUID, **values: object) -> None:
        self.db.execute(
            update(ProcessingJob)
            .where(ProcessingJob.concept_id == concept_id, ProcessingJob.user_id == self.user_id)
            .values(**values)
        )


class ConceptCardRepository:
    """Fichas compartidas entre usuarios, por eso este repositorio no lleva `user_id`.

    Una ficha no guarda datos de nadie: se llega a ella desde un concepto propio.
    """

    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get_by_slug(self, cache_slug: str, language: str) -> ConceptCard | None:
        return self.db.scalar(
            select(ConceptCard).where(
                ConceptCard.cache_slug == cache_slug, ConceptCard.language == language
            )
        )

    def insert_if_absent(
        self,
        *,
        canonical_title: str,
        cache_slug: str,
        language: str,
        what_is: str,
        what_for: str,
        example: str,
        example_code: str | None,
        example_code_language: str | None,
        model: str,
        now: datetime,
        youtube_search_query: str | None = None,
    ) -> tuple[ConceptCard, bool]:
        """Guarda la ficha, o devuelve la que ya existía para ese (cache_slug, language).

        Si dos usuarios la crean a la vez gana la primera y la otra se descarta; ambos usan la
        misma. Devuelve la ficha y si fue esta llamada quien la creó.
        """
        inserted = self.db.execute(
            pg_insert(ConceptCard)
            .values(
                canonical_title=canonical_title,
                cache_slug=cache_slug,
                language=language,
                what_is=what_is,
                what_for=what_for,
                example=example,
                example_code=example_code,
                example_code_language=example_code_language,
                model=model,
                youtube_search_query=youtube_search_query,
                created_at=now,
            )
            .on_conflict_do_nothing(constraint="concept_cards_slug_language_key")
            .returning(ConceptCard.id)
        ).scalar_one_or_none()
        card = self.get_by_slug(cache_slug, language)
        assert card is not None  # o la acabamos de crear o ya existía
        return card, inserted is not None


class ConceptAliasRepository:
    """Alias de conceptos: compartidos entre usuarios, por eso no llevan `user_id`.

    Un alias es un texto ya visto («integracion continua») que lleva a una ficha existente. No
    guarda quién lo escribió.
    """

    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get_card(self, language: str, alias: str) -> ConceptCard | None:
        """La ficha a la que lleva el alias, o None si ese texto no se había visto."""
        return self.db.scalar(
            select(ConceptCard)
            .join(
                ConceptAlias,
                and_(
                    ConceptAlias.cache_slug == ConceptCard.cache_slug,
                    ConceptAlias.language == ConceptCard.language,
                ),
            )
            .where(ConceptAlias.language == language, ConceptAlias.alias == alias)
        )

    def add_if_absent(self, language: str, alias: str, cache_slug: str, now: datetime) -> bool:
        """Guarda el alias. Si ya existía (lo guardó otro antes) no lo toca: gana el primero.

        Devuelve si fue esta llamada quien lo creó. La ficha (`cache_slug`, `language`) tiene que
        existir ya.
        """
        created = self.db.execute(
            pg_insert(ConceptAlias)
            .values(language=language, alias=alias, cache_slug=cache_slug, created_at=now)
            .on_conflict_do_nothing(index_elements=["language", "alias"])
            .returning(ConceptAlias.alias)
        ).scalar_one_or_none()
        return created is not None


@dataclass(frozen=True)
class NewVideo:
    """Un video listo para guardar en la caché."""

    youtube_id: str
    title: str
    channel: str | None
    thumbnail_url: str


class VideoCacheRepository:
    """Videos de un concepto, compartidos entre usuarios por (cache_slug, language)."""

    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get(self, cache_slug: str, language: str) -> list[VideoCache]:
        """Los videos guardados, en su orden (el 1 primero). Vacío si aún no se buscaron."""
        return list(
            self.db.scalars(
                select(VideoCache)
                .where(VideoCache.cache_slug == cache_slug, VideoCache.language == language)
                .order_by(VideoCache.position)
            )
        )

    def save_if_absent(
        self, cache_slug: str, language: str, videos: Sequence[NewVideo], now: datetime
    ) -> None:
        """Guarda hasta 2 videos. Si ya había (los buscó otro a la vez), se queda lo primero.

        Se insertan todos en una sola sentencia y por orden de posición: dos búsquedas simultáneas
        no pueden quedarse cada una con un video distinto.
        """
        rows = [
            {
                "cache_slug": cache_slug,
                "language": language,
                "position": position,
                "youtube_id": video.youtube_id,
                "title": video.title,
                "channel": video.channel,
                "thumbnail_url": video.thumbnail_url,
                "fetched_at": now,
            }
            for position, video in enumerate(videos[:2], start=1)
        ]
        if not rows:
            return
        self.db.execute(
            pg_insert(VideoCache)
            .values(rows)
            .on_conflict_do_nothing(constraint="video_cache_slug_language_position_key")
        )
