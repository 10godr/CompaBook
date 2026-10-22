import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.config import get_settings
from app.db import get_engine
from app.main import app

client = TestClient(app)

needs_db = pytest.mark.skipif(not get_settings().database_url, reason="DATABASE_URL no definida")


def test_health_db_sin_configurar(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "database_url", None)
    get_engine.cache_clear()
    response = client.get("/api/v1/health/db")
    assert response.status_code == 503
    assert response.json() == {"detail": "Base de datos no disponible"}


@needs_db
def test_health_db() -> None:
    get_engine.cache_clear()
    response = client.get("/api/v1/health/db")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@needs_db
def test_conexion_con_nullpool() -> None:
    get_engine.cache_clear()
    with get_engine().connect() as connection:
        assert connection.execute(text("select 1")).scalar() == 1
