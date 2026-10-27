import uuid
from dataclasses import dataclass
from datetime import date, datetime, time

from sqlalchemy import delete, exists, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session as DbSession

from app.models import PushSubscription, ReminderSettings, User

# Más dispositivos que estos no tiene sentido: se descartan los registrados hace más tiempo.
MAX_SUBSCRIPTIONS = 5


class ReminderRepository:
    """Los ajustes de recordatorio de UN usuario (se aplica el `user_id` en cada consulta)."""

    def __init__(self, db: DbSession, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def get(self) -> ReminderSettings | None:
        """None si el usuario aún no ha guardado nada: valen los valores por defecto."""
        return self.db.scalar(
            select(ReminderSettings)
            .where(ReminderSettings.user_id == self.user_id)
            .execution_options(populate_existing=True)
        )

    def save(
        self, enabled: bool, local_time: time, weekdays: list[int], now: datetime
    ) -> ReminderSettings:
        """Crea o actualiza los ajustes. No toca `last_sent_on`: cambiar la hora no repite."""
        values = {
            "enabled": enabled,
            "local_time": local_time,
            "weekdays": sorted(set(weekdays)),
            "updated_at": now,
        }
        self.db.execute(
            pg_insert(ReminderSettings)
            .values(user_id=self.user_id, **values)
            .on_conflict_do_update(index_elements=[ReminderSettings.user_id], set_=values)
        )
        self.db.flush()
        settings = self.get()
        assert settings is not None  # acabamos de guardarlo
        return settings

    def claim_send(self, day: date) -> bool:
        """Se queda con el envío del día: True si este proceso es el primero en pedirlo.

        Es un solo `UPDATE`, así que dos ejecuciones del reloj a la vez no mandan el aviso dos
        veces. `updated_at` no cambia: es la fecha de los ajustes, no la del envío.
        """
        result = self.db.execute(
            update(ReminderSettings)
            .where(
                ReminderSettings.user_id == self.user_id,
                ReminderSettings.last_sent_on.is_distinct_from(day),
            )
            .values(last_sent_on=day, updated_at=ReminderSettings.updated_at)
        )
        return result.rowcount == 1

    def release_send(self, day: date, previous: date | None) -> None:
        """Devuelve el envío del día, como si no se hubiera pedido (nadie lo recibió)."""
        self.db.execute(
            update(ReminderSettings)
            .where(ReminderSettings.user_id == self.user_id, ReminderSettings.last_sent_on == day)
            .values(last_sent_on=previous, updated_at=ReminderSettings.updated_at)
        )


class PushSubscriptionRepository:
    """Los dispositivos suscritos de UN usuario."""

    def __init__(self, db: DbSession, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def upsert(
        self, endpoint: str, p256dh: str, auth: str, user_agent: str | None, now: datetime
    ) -> PushSubscription:
        """Registra el dispositivo; si ya estaba, pasa a ser de este usuario y queda activo.

        El `endpoint` identifica al dispositivo: si otra persona inicia sesión en él y se suscribe,
        el dispositivo deja de ser del usuario anterior (si no, sus avisos, con títulos de sus
        conceptos, saldrían en la pantalla de otra persona). Se conservan los más recientes.
        """
        values = {
            "user_id": self.user_id,
            "p256dh": p256dh,
            "auth": auth,
            "user_agent": user_agent,
            "active": True,
            "created_at": now,
        }
        self.db.execute(
            pg_insert(PushSubscription)
            .values(endpoint=endpoint, **values)
            .on_conflict_do_update(index_elements=[PushSubscription.endpoint], set_=values)
        )
        self.db.flush()
        self._keep_newest(endpoint)
        subscription = self.get(endpoint)
        assert subscription is not None  # es el más reciente: no se descarta
        return subscription

    def _keep_newest(self, registering: str) -> None:
        keep = (
            select(PushSubscription.id)
            .where(PushSubscription.user_id == self.user_id)
            .order_by(PushSubscription.active.desc(), PushSubscription.created_at.desc())
            .limit(MAX_SUBSCRIPTIONS)
        )
        self.db.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == self.user_id,
                PushSubscription.id.not_in(keep),
                PushSubscription.endpoint != registering,  # el que se acaba de registrar se queda
            )
        )

    def get(self, endpoint: str) -> PushSubscription | None:
        return self.db.scalar(
            select(PushSubscription)
            .where(PushSubscription.endpoint == endpoint, PushSubscription.user_id == self.user_id)
            .execution_options(populate_existing=True)
        )

    def list_active(self) -> list[PushSubscription]:
        return list(
            self.db.scalars(
                select(PushSubscription)
                .where(PushSubscription.user_id == self.user_id, PushSubscription.active)
                .order_by(PushSubscription.created_at.desc(), PushSubscription.id)
                .execution_options(populate_existing=True)
            )
        )

    def deactivate(self, endpoint: str) -> bool:
        """El servicio de push dijo 404/410: el dispositivo ya no existe. True si era suyo."""
        result = self.db.execute(
            update(PushSubscription)
            .where(PushSubscription.endpoint == endpoint, PushSubscription.user_id == self.user_id)
            .values(active=False)
        )
        return result.rowcount > 0

    def delete(self, endpoint: str) -> bool:
        """Da de baja el dispositivo. True si era de este usuario; uno ajeno no existe aquí."""
        result = self.db.execute(
            delete(PushSubscription).where(
                PushSubscription.endpoint == endpoint, PushSubscription.user_id == self.user_id
            )
        )
        return result.rowcount > 0


@dataclass(frozen=True)
class DueCandidate:
    """Un usuario con recordatorio activo y algún dispositivo. Sin nada de sus conceptos."""

    user_id: uuid.UUID
    timezone: str
    language: str
    local_time: time
    weekdays: tuple[int, ...]
    last_sent_on: date | None


class ReminderQueueRepository:
    """Los usuarios a los que quizá les toque el aviso, de TODAS las cuentas.

    Excepción documentada a la regla del `user_id` (como `JobQueueRepository`): el reloj no tiene
    sesión. Solo devuelve los ajustes; el envío se hace luego con los repositorios de siempre y el
    `user_id` de cada uno. No incluye cuentas suspendidas.
    """

    def __init__(self, db: DbSession) -> None:
        self.db = db

    def candidates(self) -> list[DueCandidate]:
        has_device = exists().where(
            PushSubscription.user_id == ReminderSettings.user_id, PushSubscription.active
        )
        rows = self.db.execute(
            select(
                ReminderSettings.user_id,
                User.timezone,
                User.language,
                ReminderSettings.local_time,
                ReminderSettings.weekdays,
                ReminderSettings.last_sent_on,
            )
            .join(User, User.id == ReminderSettings.user_id)
            .where(ReminderSettings.enabled, User.disabled_at.is_(None), has_device)
            .order_by(ReminderSettings.user_id)
        ).all()
        return [
            DueCandidate(
                user_id=row.user_id,
                timezone=row.timezone,
                language=row.language,
                local_time=row.local_time,
                weekdays=tuple(row.weekdays),
                last_sent_on=row.last_sent_on,
            )
            for row in rows
        ]
