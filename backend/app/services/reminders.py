"""Ajustes de recordatorio y dispositivos suscritos (diseno-tecnico.md §4.6 y §7)."""

import logging
import re
from datetime import datetime, time, timedelta

from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.errors import ApiError
from app.models import User
from app.models.reminders import ALL_WEEKDAYS
from app.repositories import PushSubscriptionRepository, ReminderRepository
from app.services import accounts
from app.services.push import PushError, PushMessage, PushProvider, PushTarget

logger = logging.getLogger("compabook.reminders")

HOUR = timedelta(hours=1)
TEST_LIMIT = 5  # notificaciones de prueba por hora y usuario: cada una toca los servicios de push
USER_AGENT_MAX = 512

TEST_TEXT = {
    "es": "Las notificaciones funcionan en este dispositivo.",
    "en": "Notifications are working on this device.",
}

TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


def parse_local_time(value: str) -> time:
    match = TIME_PATTERN.match(value)
    if not match:
        raise ValueError("hora no válida")
    return time(int(match.group(1)), int(match.group(2)))


def reminder_state(db: DbSession, user: User) -> dict[str, object]:
    """Los ajustes del usuario (o los de fábrica si aún no guardó nada) y cuántos dispositivos."""
    settings = ReminderRepository(db, user.id).get()
    devices = len(PushSubscriptionRepository(db, user.id).list_active())
    return {
        "enabled": settings.enabled if settings else False,
        "local_time": (settings.local_time if settings else time(20, 0)).strftime("%H:%M"),
        "weekdays": list(settings.weekdays) if settings else list(ALL_WEEKDAYS),
        "timezone": user.timezone,
        "devices": devices,
    }


def save_reminders(
    db: DbSession,
    user: User,
    *,
    enabled: bool,
    local_time: time,
    weekdays: list[int],
    timezone: str | None,
    now: datetime,
) -> dict[str, object]:
    """Guarda los ajustes. Si llega la zona horaria del dispositivo y cambió, se actualiza."""
    if timezone is not None and timezone != user.timezone:
        user.timezone = timezone
    ReminderRepository(db, user.id).save(enabled, local_time, weekdays, now)
    db.commit()
    return reminder_state(db, user)


def subscribe(
    db: DbSession,
    user: User,
    *,
    endpoint: str,
    p256dh: str,
    auth: str,
    user_agent: str | None,
    now: datetime,
) -> None:
    agent = user_agent[:USER_AGENT_MAX] if user_agent else None
    PushSubscriptionRepository(db, user.id).upsert(endpoint, p256dh, auth, agent, now)
    db.commit()


def unsubscribe(db: DbSession, user: User, endpoint: str) -> None:
    if not PushSubscriptionRepository(db, user.id).delete(endpoint):
        raise ApiError(404, "not_found", "No encontrado")
    db.commit()


def send_test(
    db: DbSession,
    push: PushProvider,
    user: User,
    endpoint: str | None,
    now: datetime,
) -> dict[str, int]:
    """Manda una notificación de prueba a un dispositivo del usuario (o a todos los suyos)."""
    repository = PushSubscriptionRepository(db, user.id)
    if endpoint is not None:
        found = repository.get(endpoint)
        if found is None or not found.active:
            raise ApiError(404, "not_found", "No encontrado")
        targets = [found]
    else:
        targets = repository.list_active()
        if not targets:
            raise ApiError(409, "no_devices", "No hay dispositivos con las notificaciones activas")
    accounts.enforce_rate_limit(db, "push_test", str(user.id), TEST_LIMIT, HOUR, now)

    message = PushMessage(
        title="CompaBook",
        body=TEST_TEXT.get(user.language, TEST_TEXT["es"]),
        tag="test",
        ttl=60,
    )
    counts = {"sent": 0, "expired": 0, "failed": 0}
    sendable = [PushTarget(t.endpoint, t.p256dh, t.auth) for t in targets]
    db.commit()  # sin transacción abierta mientras se espera a los servicios de push
    for target in sendable:
        try:
            push.send(target, message)
        except PushError as error:
            logger.warning("aviso de prueba fallido: %s", error.kind)
            if error.kind == "not_configured":
                raise ApiError(
                    503, "push_unavailable", "Las notificaciones no están disponibles"
                ) from None
            if error.kind == "expired":
                repository.deactivate(target.endpoint)
                counts["expired"] += 1
            else:
                counts["failed"] += 1
        else:
            counts["sent"] += 1
    db.commit()
    return counts


def public_key() -> str:
    key = get_settings().vapid_public_key
    if not key:
        raise ApiError(503, "push_unavailable", "Las notificaciones no están disponibles")
    return key
