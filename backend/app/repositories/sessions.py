import uuid
from datetime import datetime

from sqlalchemy import delete, select
from sqlalchemy.orm import Session as DbSession

from app.models import Session, User


class SessionRepository:
    """Sesiones de UN usuario.

    Recibe siempre el `user_id` de la sesión autenticada y lo aplica en cada consulta; nunca
    se acepta un `user_id` del cliente. Un recurso ajeno se comporta como si no existiera.
    """

    def __init__(self, db: DbSession, user_id: uuid.UUID) -> None:
        self.db = db
        self.user_id = user_id

    def create(
        self,
        token_hash: str,
        expires_at: datetime,
        user_agent: str | None = None,
        last_used_at: datetime | None = None,
    ) -> Session:
        session = Session(
            user_id=self.user_id,
            token_hash=token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            last_used_at=last_used_at,
        )
        self.db.add(session)
        self.db.flush()
        return session

    def list_active(self, now: datetime) -> list[Session]:
        query = (
            select(Session)
            .where(Session.user_id == self.user_id, Session.expires_at > now)
            .order_by(Session.created_at.desc())
        )
        return list(self.db.scalars(query))

    def revoke(self, session_id: uuid.UUID) -> bool:
        """Cierra una sesión propia. Devuelve False si no existe o es de otro usuario."""
        result = self.db.execute(
            delete(Session).where(Session.id == session_id, Session.user_id == self.user_id)
        )
        return result.rowcount == 1

    def revoke_all(self) -> int:
        result = self.db.execute(delete(Session).where(Session.user_id == self.user_id))
        return result.rowcount

    def revoke_others(self, keep_token_hash: str) -> int:
        """Cierra todas las sesiones propias salvo la del token indicado (la actual)."""
        result = self.db.execute(
            delete(Session).where(
                Session.user_id == self.user_id, Session.token_hash != keep_token_hash
            )
        )
        return result.rowcount


# --- Búsquedas por token: se usan ANTES de saber quién es el usuario -------------------------
# La cookie es la credencial; por eso estas funciones no reciben `user_id`. Ningún endpoint
# las expone: solo las usan la dependencia de autenticación y el cierre de sesión.


def find_active_by_token_hash(
    db: DbSession, token_hash: str, now: datetime
) -> tuple[Session, User] | None:
    """La sesión vigente de un usuario verificado y no suspendido, o None."""
    row = db.execute(
        select(Session, User)
        .join(User, User.id == Session.user_id)
        .where(
            Session.token_hash == token_hash,
            Session.expires_at > now,
            User.disabled_at.is_(None),
            User.email_verified_at.is_not(None),
        )
    ).first()
    return (row[0], row[1]) if row else None


def delete_by_token_hash(db: DbSession, token_hash: str) -> None:
    db.execute(delete(Session).where(Session.token_hash == token_hash))
