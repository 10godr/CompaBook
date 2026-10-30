"""Ajustes de recordatorio y dispositivos suscritos (diseno-tecnico.md §4.6 y §7)."""

import logging
import re
import time as clock_time
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.errors import ApiError
from app.models import User
from app.models.reminders import ALL_WEEKDAYS
from app.repositories import (
    ConceptRepository,
    DueCandidate,
    PushSubscriptionRepository,
    ReminderQueueRepository,
    ReminderRepository,
)
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

# El aviso sale desde la hora elegida y durante 2 h: si una ejecución falla o se retrasa, la
# siguiente lo manda igual; pasado ese margen ya sería un aviso a deshora.
WINDOW = timedelta(hours=2)
REMINDER_TTL = 3600  # un aviso de repaso que llega pasada una hora ya no sirve
REMINDER_TAG = "reminder"
TITLE_MAX = 80  # el título de la ficha puede ser largo; en la pantalla de bloqueo no cabe
# Los fallos tras los cuales no merece la pena volver a intentarlo el mismo día.
GIVE_UP = {"expired", "not_configured"}

REMINDER_TEXT = {
    "es": (
        'Tienes {n} conceptos en tu Cuaderno — repasa "{title}"',
        'Tienes 1 concepto en tu Cuaderno — repasa "{title}"',
    ),
    "en": (
        'You have {n} concepts in your Notebook — review "{title}"',
        'You have 1 concept in your Notebook — review "{title}"',
    ),
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


# --- El reloj de recordatorios (diseno-tecnico.md §4.6) --------------------------------------


def reminder_day(candidate: DueCandidate, now: datetime) -> tuple[date, datetime] | None:
    """El día LOCAL al que pertenece el aviso que toca mandar ahora, y cuándo empezó su hora.

    Toca si la hora actual está entre `local_time` y `local_time + 2 h`, el día de la semana es
    uno de los elegidos y ese día aún no se envió. Un aviso pertenece al día en que cae su hora:
    con 23:30 elegido, a las 00:30 se mira el día de ayer (su día de la semana y su envío).
    Con un cambio de hora, una hora que no existe cuenta desde el instante equivalente y una que
    ocurre dos veces, desde la primera.
    """
    try:
        zone = ZoneInfo(candidate.timezone)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        return None
    today = now.astimezone(zone).date()
    for day in (today, today - timedelta(days=1)):
        if day.isoweekday() not in candidate.weekdays or candidate.last_sent_on == day:
            continue
        starts = datetime.combine(day, candidate.local_time, tzinfo=zone).astimezone(UTC)
        if starts <= now < starts + WINDOW:
            return day, starts
    return None


def reminder_message(language: str, total: int, title: str, concept_id: object) -> PushMessage:
    many, one = REMINDER_TEXT.get(language, REMINDER_TEXT["es"])
    shown = title if len(title) <= TITLE_MAX else title[: TITLE_MAX - 1].rstrip() + "…"
    body = (one if total == 1 else many).format(n=total, title=shown)
    return PushMessage(
        title="CompaBook",
        body=body,
        url=f"/cuaderno/{concept_id}",
        tag=REMINDER_TAG,
        ttl=REMINDER_TTL,
    )


def _remind(db: DbSession, push: PushProvider, candidate: DueCandidate, day: date) -> str:
    """Avisa a un usuario. Devuelve `sent`, `retrying`, `failed` o `skipped`.

    El envío del día se reclama antes de mandar nada (un `UPDATE` atómico): dos ejecuciones
    solapadas no duplican el aviso. Si ningún dispositivo lo recibe por un fallo que puede
    arreglarse solo, el reclamo se devuelve para volver a intentarlo el minuto siguiente.
    """
    user_id = candidate.user_id
    pick = ConceptRepository(db, user_id).pick_for_review()
    db.commit()
    if pick is None:  # Cuaderno vacío: no se manda nada, y si añade uno dentro de la ventana sí
        return "skipped"

    reminders = ReminderRepository(db, user_id)
    if not reminders.claim_send(day):
        db.rollback()
        return "skipped"  # otra ejecución del reloj se lo quedó
    db.commit()

    devices = PushSubscriptionRepository(db, user_id)
    targets = [PushTarget(d.endpoint, d.p256dh, d.auth) for d in devices.list_active()]
    db.commit()  # sin transacción abierta mientras se espera a los servicios de push
    if not targets:
        reminders.release_send(day, candidate.last_sent_on)
        db.commit()
        return "skipped"

    message = reminder_message(candidate.language, pick.total, pick.title, pick.concept_id)
    sent, failures, expired = 0, set(), []
    for target in targets:
        try:
            push.send(target, message)
        except PushError as error:
            failures.add(error.kind)
            if error.kind == "expired":
                expired.append(target.endpoint)
        else:
            sent += 1
    for endpoint in expired:
        devices.deactivate(endpoint)

    if sent:
        outcome = "sent"
    elif failures - GIVE_UP:
        reminders.release_send(day, candidate.last_sent_on)
        outcome = "retrying"
    else:
        outcome = "failed"
    db.commit()
    # Solo contadores: nada del concepto, del usuario ni de los dispositivos.
    logger.info(
        "recordatorio %s: recibidos=%d caducados=%d fallos=%s",
        outcome,
        sent,
        len(expired),
        ",".join(sorted(failures - {"expired"})) or "-",
    )
    return outcome


def run_due_reminders(
    db: DbSession,
    push: PushProvider,
    max_users: int,
    budget_seconds: float,
    now: datetime | None = None,
    monotonic: Callable[[], float] = clock_time.monotonic,
) -> dict[str, int]:
    """`POST /internal/reminders`: avisa a los usuarios a los que ya les toca.

    Atiende primero a quien lleva más tiempo esperando. No empieza con otro si ya pasaron
    `budget_seconds` (la función de Vercel muere a los 60 s) ni pasa de `max_users`; a quien
    quede sin atender le tocará en la siguiente ejecución, mientras siga en su ventana de 2 h.
    Devuelve solo contadores.
    """
    started = monotonic()
    current = now or accounts.utcnow()
    candidates = ReminderQueueRepository(db).candidates()
    db.commit()
    due: list[tuple[datetime, DueCandidate, date]] = []
    for candidate in candidates:
        found = reminder_day(candidate, current)
        if found is not None:
            due.append((found[1], candidate, found[0]))
    due.sort(key=lambda item: item[0])

    counts = {
        "checked": len(candidates),
        "due": len(due),
        "sent": 0,
        "retrying": 0,
        "failed": 0,
        "skipped": 0,
    }
    for position, (_, candidate, day) in enumerate(due):
        if position and (position >= max_users or monotonic() - started >= budget_seconds):
            counts["skipped"] += len(due) - position
            break
        try:
            outcome = _remind(db, push, candidate, day)
        except Exception as error:  # un usuario con problemas no debe parar a los demás
            db.rollback()
            logger.error("fallo inesperado en un recordatorio: %s", type(error).__name__)
            outcome = "failed"
        counts[outcome] += 1
    return counts
