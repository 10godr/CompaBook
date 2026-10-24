import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.models import EmailCode


class EmailCodeRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def replace(
        self, user_id: uuid.UUID, purpose: str, code_hash: str, expires_at: datetime
    ) -> EmailCode:
        """Un código nuevo invalida los anteriores sin usar del mismo propósito."""
        self.db.execute(
            delete(EmailCode).where(
                EmailCode.user_id == user_id,
                EmailCode.purpose == purpose,
                EmailCode.used_at.is_(None),
            )
        )
        code = EmailCode(
            user_id=user_id, purpose=purpose, code_hash=code_hash, expires_at=expires_at
        )
        self.db.add(code)
        self.db.flush()
        return code

    def latest_active(self, user_id: uuid.UUID, purpose: str, now: datetime) -> EmailCode | None:
        query = (
            select(EmailCode)
            .where(
                EmailCode.user_id == user_id,
                EmailCode.purpose == purpose,
                EmailCode.used_at.is_(None),
                EmailCode.expires_at > now,
            )
            .order_by(EmailCode.created_at.desc())
            .limit(1)
        )
        return self.db.scalar(query)
