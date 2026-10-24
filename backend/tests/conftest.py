from collections.abc import Iterator
from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import Connection
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import get_db, get_engine
from app.main import app
from app.services import accounts
from app.services.ai import get_ai_provider
from app.services.email import get_email_provider
from tests.helpers import NOW, FakeAIProvider, FakeEmailProvider


@pytest.fixture
def db() -> Iterator[Connection]:
    """Conexión a la base de datos de pruebas; todo lo que se haga se deshace al terminar."""
    if not get_settings().database_url:
        pytest.skip("DATABASE_URL no definida")
    get_engine.cache_clear()
    with get_engine().connect() as connection:
        transaction = connection.begin()
        try:
            yield connection
        finally:
            transaction.rollback()


@pytest.fixture
def orm(db: Connection) -> Iterator[DbSession]:
    """Sesión del ORM sobre la misma conexión, para probar repositorios."""
    with DbSession(bind=db, join_transaction_mode="create_savepoint") as session:
        yield session


@pytest.fixture
def mailer() -> FakeEmailProvider:
    return FakeEmailProvider()


@pytest.fixture
def ai() -> FakeAIProvider:
    return FakeAIProvider()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, datetime]:
    """Reloj controlable: `clock["now"] = ...` adelanta o atrasa el tiempo de los servicios."""
    state = {"now": NOW}
    monkeypatch.setattr(accounts, "utcnow", lambda: state["now"])
    return state


@pytest.fixture
def client(
    orm: DbSession,
    mailer: FakeEmailProvider,
    ai: FakeAIProvider,
    clock: dict[str, datetime],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    """Cliente de la API con la base de datos de pruebas y un correo falso."""
    monkeypatch.setattr(get_settings(), "secret_key", "clave-de-prueba")
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    app.dependency_overrides[get_db] = lambda: orm
    app.dependency_overrides[get_email_provider] = lambda: mailer
    app.dependency_overrides[get_ai_provider] = lambda: ai
    yield TestClient(app)
    app.dependency_overrides.clear()
