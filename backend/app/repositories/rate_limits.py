from datetime import datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session as DbSession

from app.models import RateLimitEvent


class RateLimitRepository:
    """Un intento por fila; se cuentan las de la ventana (sirve en serverless, sin memoria)."""

    def __init__(self, db: DbSession) -> None:
        self.db = db

    def add(self, bucket: str, key: str, now: datetime) -> None:
        self.db.add(RateLimitEvent(bucket=bucket, key=key, created_at=now))
        self.db.flush()

    def window_stats(
        self, bucket: str, key: str, now: datetime, window: timedelta
    ) -> tuple[int, datetime | None]:
        """Número de eventos de la ventana y fecha del más reciente."""
        row = self.db.execute(
            select(func.count(), func.max(RateLimitEvent.created_at)).where(
                RateLimitEvent.bucket == bucket,
                RateLimitEvent.key == key,
                RateLimitEvent.created_at > now - window,
            )
        ).one()
        return row[0], row[1]

    def count_since(self, bucket: str, key: str, since: datetime) -> int:
        return self.db.scalar(
            select(func.count()).where(
                RateLimitEvent.bucket == bucket,
                RateLimitEvent.key == key,
                RateLimitEvent.created_at > since,
            )
        )

    def clear(self, bucket: str, key: str) -> None:
        self.db.execute(
            delete(RateLimitEvent).where(RateLimitEvent.bucket == bucket, RateLimitEvent.key == key)
        )

    def count_and_oldest(
        self, bucket: str, key: str, now: datetime, window: timedelta
    ) -> tuple[int, datetime | None]:
        row = self.db.execute(
            select(func.count(), func.min(RateLimitEvent.created_at)).where(
                RateLimitEvent.bucket == bucket,
                RateLimitEvent.key == key,
                RateLimitEvent.created_at > now - window,
            )
        ).one()
        return row[0], row[1]
