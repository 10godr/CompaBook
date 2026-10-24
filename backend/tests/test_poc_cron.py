import logging

import pytest
from fastapi.testclient import TestClient

from app.config import get_settings
from app.main import app

SECRET = "secreto-de-prueba"


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "internal_secret", SECRET)


def test_sin_configurar(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "internal_secret", None)
    response = client.post("/api/v1/internal/ping", headers={"X-Internal-Secret": SECRET})
    assert response.status_code == 503


def test_sin_cabecera(client: TestClient, secret: None) -> None:
    assert client.post("/api/v1/internal/ping").status_code == 401


def test_secreto_incorrecto(client: TestClient, secret: None) -> None:
    response = client.post("/api/v1/internal/ping", headers={"X-Internal-Secret": "otro"})
    assert response.status_code == 401


def test_secreto_correcto(
    client: TestClient, secret: None, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="compabook.internal"):
        response = client.post("/api/v1/internal/ping", headers={"X-Internal-Secret": SECRET})
    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "internal_ping" in caplog.text
    assert SECRET not in caplog.text
