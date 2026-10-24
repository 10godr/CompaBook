"""Conceptos: fichas compartidas, conceptos y cola de trabajos.

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

TABLES = ["concept_cards", "concepts", "processing_jobs"]


def uuid_pk() -> sa.Column:
    return sa.Column(
        "id",
        postgresql.UUID(as_uuid=True),
        server_default=sa.func.gen_random_uuid(),
        primary_key=True,
    )


def timestamp(name: str) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False)


def upgrade() -> None:
    op.create_table(
        "concept_cards",
        uuid_pk(),
        sa.Column("canonical_title", sa.Text(), nullable=False),
        sa.Column("cache_slug", sa.Text(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("what_is", sa.Text(), nullable=False),
        sa.Column("what_for", sa.Text(), nullable=False),
        sa.Column("example", sa.Text(), nullable=False),
        sa.Column("example_code", sa.Text(), nullable=True),
        sa.Column("example_code_language", sa.Text(), nullable=True),
        sa.Column("model", sa.Text(), nullable=False),
        timestamp("created_at"),
        sa.UniqueConstraint("cache_slug", "language", name="concept_cards_slug_language_key"),
        sa.CheckConstraint("language in ('es', 'en')", name="concept_cards_language_check"),
    )

    op.create_table(
        "concepts",
        uuid_pk(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("source", sa.Text(), server_default="app", nullable=False),
        sa.Column(
            "card_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concept_cards.id", ondelete="SET NULL"),
            nullable=True,
        ),
        timestamp("created_at"),
        sa.CheckConstraint(
            "char_length(title) between 1 and 200", name="concepts_title_length_check"
        ),
        sa.CheckConstraint("language in ('es', 'en')", name="concepts_language_check"),
        sa.CheckConstraint("source in ('app', 'siri')", name="concepts_source_check"),
    )
    op.create_index("ix_concepts_user_created", "concepts", ["user_id", sa.text("created_at desc")])

    op.create_table(
        "processing_jobs",
        uuid_pk(),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "concept_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("concepts.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.Text(), server_default="pending", nullable=False),
        sa.Column("stage", sa.Text(), server_default="queued", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_attempts", sa.Integer(), server_default="3", nullable=False),
        timestamp("next_run_at"),
        sa.Column("locked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        timestamp("created_at"),
        timestamp("updated_at"),
        sa.UniqueConstraint("concept_id", name="processing_jobs_concept_id_key"),
        sa.CheckConstraint(
            "status in ('pending', 'processing', 'completed', 'failed')",
            name="processing_jobs_status_check",
        ),
        sa.CheckConstraint(
            "stage in ('queued', 'writing', 'finding_videos', 'done')",
            name="processing_jobs_stage_check",
        ),
    )
    op.create_index(
        "ix_processing_jobs_status_next_run", "processing_jobs", ["status", "next_run_at"]
    )

    # Sin políticas: nada es accesible salvo desde el backend, que se conecta como propietario.
    for table in TABLES:
        op.execute(f"alter table {table} enable row level security")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
