"""Conceptos, fichas compartidas y cola de trabajos (diseno-tecnico.md §3)."""

import uuid
from datetime import datetime

from sqlalchemy import (
    CheckConstraint,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base
from app.models.accounts import UUID_PK


class ConceptCard(Base):
    """Ficha COMPARTIDA entre usuarios: una por (cache_slug, language). No guarda datos de nadie."""

    __tablename__ = "concept_cards"
    __table_args__ = (
        UniqueConstraint("cache_slug", "language", name="concept_cards_slug_language_key"),
        CheckConstraint("language in ('es', 'en')", name="concept_cards_language_check"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, **UUID_PK)
    # Nombre para mostrar que devuelve la IA: «CI/CD (Continuous Integration / ...)».
    canonical_title: Mapped[str] = mapped_column(Text)
    # Clave estable de la ficha y de los videos, en inglés: «ci-cd».
    cache_slug: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(2))
    what_is: Mapped[str] = mapped_column(Text)
    what_for: Mapped[str] = mapped_column(Text)
    example: Mapped[str] = mapped_column(Text)
    example_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    example_code_language: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Concept(Base):
    __tablename__ = "concepts"
    __table_args__ = (
        CheckConstraint("char_length(title) between 1 and 200", name="concepts_title_length_check"),
        CheckConstraint("language in ('es', 'en')", name="concepts_language_check"),
        CheckConstraint("source in ('app', 'siri')", name="concepts_source_check"),
        Index("ix_concepts_user_created", "user_id", text("created_at desc")),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, **UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Lo que escribió el usuario: «CI/CD».
    title: Mapped[str] = mapped_column(Text)
    # Idioma de la ficha: el del usuario al crear el concepto.
    language: Mapped[str] = mapped_column(String(2))
    source: Mapped[str] = mapped_column(Text, server_default="app")
    # Nulo hasta que hay ficha. Si la ficha compartida se borra (por SQL), el concepto se queda.
    card_id: Mapped[uuid.UUID | None] = mapped_column(
        ForeignKey("concept_cards.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    card: Mapped[ConceptCard | None] = relationship()
    job: Mapped["ProcessingJob"] = relationship(back_populates="concept", uselist=False)


class ProcessingJob(Base):
    """Un trabajo por concepto: dice en qué punto va la generación de la ficha."""

    __tablename__ = "processing_jobs"
    __table_args__ = (
        CheckConstraint(
            "status in ('pending', 'processing', 'completed', 'failed')",
            name="processing_jobs_status_check",
        ),
        CheckConstraint(
            "stage in ('queued', 'writing', 'finding_videos', 'done')",
            name="processing_jobs_stage_check",
        ),
        Index("ix_processing_jobs_status_next_run", "status", "next_run_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, **UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    concept_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("concepts.id", ondelete="CASCADE"), unique=True
    )
    status: Mapped[str] = mapped_column(Text, server_default="pending")
    stage: Mapped[str] = mapped_column(Text, server_default="queued")
    attempts: Mapped[int] = mapped_column(server_default="0")
    max_attempts: Mapped[int] = mapped_column(server_default="3")
    next_run_at: Mapped[datetime] = mapped_column(server_default=func.now())
    # Cuándo lo reclamó un proceso; un bloqueo viejo significa que la función murió a medias.
    locked_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Solo el tipo de error, nunca el contenido del concepto ni de la respuesta de la IA.
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    concept: Mapped[Concept] = relationship(back_populates="job")
