import uuid
from datetime import datetime

from sqlalchemy import and_, delete, or_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession
from sqlalchemy.orm import joinedload

from app.models import Concept, ConceptCard, ProcessingJob


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
                created_at=now,
            )
            .on_conflict_do_nothing(constraint="concept_cards_slug_language_key")
            .returning(ConceptCard.id)
        ).scalar_one_or_none()
        card = self.get_by_slug(cache_slug, language)
        assert card is not None  # o la acabamos de crear o ya existía
        return card, inserted is not None
