"""Cuentas, sesiones, códigos por correo y límites de intentos (diseno-tecnico.md §3)."""

import uuid
from datetime import datetime

from sqlalchemy import BigInteger, CheckConstraint, ForeignKey, Identity, Index, String, Text, func
from sqlalchemy.dialects.postgresql import CITEXT, UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base

# Los identificadores se generan en la base de datos para que sirvan también desde SQL.
UUID_PK = {"server_default": func.gen_random_uuid()}


class User(Base):
    __tablename__ = "users"
    __table_args__ = (CheckConstraint("language in ('es', 'en')", name="users_language_check"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, **UUID_PK)
    email: Mapped[str] = mapped_column(CITEXT, unique=True)
    password_hash: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(2))
    timezone: Mapped[str] = mapped_column(Text)
    email_verified_at: Mapped[datetime | None] = mapped_column(nullable=True)
    # Cuenta suspendida por el administrador: se comprueba en cada petición.
    disabled_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class AllowedEmail(Base):
    """Correos que pueden registrarse (registro por invitación). Se gestiona con SQL."""

    __tablename__ = "allowed_emails"

    email: Mapped[str] = mapped_column(CITEXT, primary_key=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class Session(Base):
    __tablename__ = "sessions"
    __table_args__ = (Index("ix_sessions_expires_at", "expires_at"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, **UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    # Solo se guarda el hash SHA-256 del token; el token va en la cookie.
    token_hash: Mapped[str] = mapped_column(Text, unique=True)
    user_agent: Mapped[str | None] = mapped_column(Text, nullable=True)
    expires_at: Mapped[datetime]
    last_used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class EmailCode(Base):
    __tablename__ = "email_codes"
    __table_args__ = (
        CheckConstraint(
            "purpose in ('verify_email', 'reset_password')", name="email_codes_purpose_check"
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, **UUID_PK)
    user_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    purpose: Mapped[str] = mapped_column(Text)
    code_hash: Mapped[str] = mapped_column(Text)
    attempts: Mapped[int] = mapped_column(server_default="0")
    expires_at: Mapped[datetime]
    used_at: Mapped[datetime | None] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())


class RateLimitEvent(Base):
    """Un intento por fila; los límites cuentan las filas de la ventana (sirve en serverless)."""

    __tablename__ = "rate_limit_events"
    __table_args__ = (
        Index("ix_rate_limit_events_bucket_key_created", "bucket", "key", "created_at"),
    )

    id: Mapped[int] = mapped_column(BigInteger, Identity(always=True), primary_key=True)
    bucket: Mapped[str] = mapped_column(Text)
    key: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
