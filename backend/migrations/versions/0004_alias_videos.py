"""Alias de conceptos, caché de videos y la consulta de YouTube de la ficha.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

TABLES = ["concept_aliases", "video_cache"]


def upgrade() -> None:
    # Nula en las fichas de la Fase 6a: se rellena con las nuevas.
    op.add_column("concept_cards", sa.Column("youtube_search_query", sa.Text(), nullable=True))

    op.create_table(
        "concept_aliases",
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("alias", sa.Text(), nullable=False),
        sa.Column("cache_slug", sa.Text(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("language", "alias"),
        sa.ForeignKeyConstraint(
            ["cache_slug", "language"],
            ["concept_cards.cache_slug", "concept_cards.language"],
            name="concept_aliases_card_fkey",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint(
            "char_length(alias) between 1 and 60", name="concept_aliases_alias_check"
        ),
        sa.CheckConstraint("language in ('es', 'en')", name="concept_aliases_language_check"),
    )

    op.create_table(
        "video_cache",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.func.gen_random_uuid(),
            primary_key=True,
        ),
        sa.Column("cache_slug", sa.Text(), nullable=False),
        sa.Column("language", sa.String(2), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("youtube_id", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("channel", sa.Text(), nullable=True),
        sa.Column("thumbnail_url", sa.Text(), nullable=False),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint(
            "cache_slug", "language", "position", name="video_cache_slug_language_position_key"
        ),
        sa.CheckConstraint("position in (1, 2)", name="video_cache_position_check"),
        sa.CheckConstraint("language in ('es', 'en')", name="video_cache_language_check"),
    )

    # Sin políticas: nada es accesible salvo desde el backend, que se conecta como propietario.
    for table in TABLES:
        op.execute(f"alter table {table} enable row level security")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
    op.drop_column("concept_cards", "youtube_search_query")
