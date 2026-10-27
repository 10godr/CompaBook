"""Recordatorios y dispositivos suscritos a notificaciones push (diseno-tecnico.md §3)."""

import uuid
from datetime import date, datetime, time

from sqlalchemy import Boolean, CheckConstraint, ForeignKey, Index, SmallInteger, Text, func, text
from sqlalchemy.dialects.postgresql import ARRAY, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base
from app.models.accounts import UUID_PK

ALL_WEEKDAYS = [1, 2, 3, 4, 5, 6, 7]


class ReminderSettings(Base):
    """Cuándo quiere el usuario su recordatorio. Una fila por usuario, creada al guardar."""

    __tablename__ = "reminder_settings"
    __table_args__ = (
        CheckConstraint(
            "weekdays <@ array[1, 2, 3, 4, 5, 6, 7]::smallint[] "
            "and cardinality(weekdays) between 1 and 7",
            name="reminder_settings_weekdays_check",
        ),
    )

    user_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), primary_key=True
    )
    enabled: Mapped[bool] = mapped_column(Boolean, server_default=text("false"))
    # Hora LOCAL del usuario; su zona horaria está en `users.timezone`.
    local_time: Mapped[time] = mapped_column(server_default=text("'20:00'"))
    # ISO: 1 = lunes … 7 = domingo.
    weekdays: Mapped[list[int]] = mapped_column(
        ARRAY(SmallInteger), server_default=text("'{1,2,3,4,5,6,7}'")
    )
    # Fecha LOCAL del último envío: evita mandar dos veces el mismo día.
    last_sent_on: Mapped[date | None] = mapped_column(nullable=True)
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class PushSubscription(Base):
    """Un dispositivo suscrito. El `endpoint` identifica al dispositivo, no a la persona."""

    __tablename__ = "push_subscriptions"
    __table_args__ = (
        CheckConstraint(
            "char_length(endpoint) between 1 and 2048", name="push_subscriptions_endpoint_check"
        ),
        CheckConstraint(
            "char_length(p256dh) between 1 and 512", name="push_subscriptions_p256dh_check"
        ),
        CheckConstraint(
            "char_length(auth) between 1 and 512", name="push_subscriptions_auth_check"
        ),
        CheckConstraint(
            "user_agent is null or char_length(user_agent) <= 512",
            name="push_subscriptions_user_agent_check",
        ),
        Index("ix_push_subscriptions_user_active", "user_id", "active"),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, **UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    endpoint: Mapped[str] = mapped_column(Text, unique=True)
    p256dh: Mapped[str] = mapped_column(Text)
    auth: Mapped[str] = mapped_column(Text)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Pasa a false cuando el servicio de push responde 404/410 (el dispositivo ya no existe).
    active: Mapped[bool] = mapped_column(Boolean, server_default=text("true"))
    # Cuándo se (re)registró este dispositivo.
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
