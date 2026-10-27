"""Recordatorios: ajustes por usuario y dispositivos suscritos a notificaciones push.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

TABLES = ["reminder_settings", "push_subscriptions"]


def upgrade() -> None:
    op.create_table(
        "reminder_settings",
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("false"), nullable=False),
        # Hora LOCAL del usuario (la zona horaria vive en users.timezone).
        sa.Column("local_time", sa.Time(), server_default=sa.text("'20:00'"), nullable=False),
        # ISO: 1 = lunes … 7 = domingo.
        sa.Column(
            "weekdays",
            postgresql.ARRAY(sa.SmallInteger()),
            server_default=sa.text("'{1,2,3,4,5,6,7}'"),
            nullable=False,
        ),
        # Fecha LOCAL del último envío: evita mandar dos veces el mismo día.
        sa.Column("last_sent_on", sa.Date(), nullable=True),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "weekdays <@ array[1, 2, 3, 4, 5, 6, 7]::smallint[] "
            "and cardinality(weekdays) between 1 and 7",
            name="reminder_settings_weekdays_check",
        ),
    )

    op.create_table(
        "push_subscriptions",
        sa.Column(
            "id",
            postgresql.UUID(as_uuid=True),
            server_default=sa.func.gen_random_uuid(),
            primary_key=True,
        ),
        sa.Column(
            "user_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # La URL del servicio de push del dispositivo: identifica al dispositivo.
        sa.Column("endpoint", sa.Text(), nullable=False),
        sa.Column("p256dh", sa.Text(), nullable=False),
        sa.Column("auth", sa.Text(), nullable=False),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        # Cuándo se (re)registró este dispositivo.
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.UniqueConstraint("endpoint", name="push_subscriptions_endpoint_key"),
        sa.CheckConstraint(
            "char_length(endpoint) between 1 and 2048", name="push_subscriptions_endpoint_check"
        ),
        sa.CheckConstraint(
            "char_length(p256dh) between 1 and 512", name="push_subscriptions_p256dh_check"
        ),
        sa.CheckConstraint(
            "char_length(auth) between 1 and 512", name="push_subscriptions_auth_check"
        ),
        sa.CheckConstraint(
            "user_agent is null or char_length(user_agent) <= 512",
            name="push_subscriptions_user_agent_check",
        ),
    )
    op.create_index(
        "ix_push_subscriptions_user_active", "push_subscriptions", ["user_id", "active"]
    )

    # Sin políticas: nada es accesible salvo desde el backend, que se conecta como propietario.
    for table in TABLES:
        op.execute(f"alter table {table} enable row level security")


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
