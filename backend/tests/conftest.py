from collections.abc import Iterator

import pytest
from sqlalchemy import Connection
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import get_engine


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
