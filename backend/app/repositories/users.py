from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session as DbSession

from app.models import AllowedEmail, User


class UserRepository:
    """Usuarios, sin `user_id`: se usa ANTES de autenticar (registro, verificación, login).

    Nunca se expone a un endpoint con sesión; ahí se usan repositorios con `user_id`.
    """

    def __init__(self, db: DbSession) -> None:
        self.db = db

    def get_by_email(self, email: str) -> User | None:
        # La columna es citext: la comparación no distingue mayúsculas.
        return self.db.scalar(select(User).where(User.email == email))

    def create(self, email: str, password_hash: str, language: str, timezone: str) -> User:
        user = User(email=email, password_hash=password_hash, language=language, timezone=timezone)
        self.db.add(user)
        self.db.flush()
        return user

    def mark_verified(self, user: User, now: datetime) -> None:
        user.email_verified_at = now


class AllowedEmailRepository:
    def __init__(self, db: DbSession) -> None:
        self.db = db

    def is_allowed(self, email: str) -> bool:
        return self.db.get(AllowedEmail, email) is not None
