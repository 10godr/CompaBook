"""Limpieza programada (diseno-tecnico.md §4.4). La dispara pg_cron una vez al día."""

from datetime import datetime, timedelta

from sqlalchemy import delete
from sqlalchemy.orm import Session as DbSession

from app.models import EmailCode, RateLimitEvent, Session, User

RATE_LIMIT_KEEP = timedelta(days=2)
UNVERIFIED_KEEP = timedelta(days=7)


def cleanup(db: DbSession, now: datetime) -> dict[str, int]:
    """Borra lo que ya no sirve y devuelve cuántas filas quitó de cada cosa."""
    sessions = db.execute(delete(Session).where(Session.expires_at < now)).rowcount
    codes = db.execute(delete(EmailCode).where(EmailCode.expires_at < now)).rowcount
    events = db.execute(
        delete(RateLimitEvent).where(RateLimitEvent.created_at < now - RATE_LIMIT_KEEP)
    ).rowcount
    # Sus sesiones y códigos caen en cascada.
    unverified = db.execute(
        delete(User).where(
            User.email_verified_at.is_(None), User.created_at < now - UNVERIFIED_KEEP
        )
    ).rowcount
    db.commit()
    return {
        "sessions": sessions,
        "email_codes": codes,
        "rate_limit_events": events,
        "unverified_users": unverified,
    }
