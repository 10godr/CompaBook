from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient
from pywebpush import WebPushException

from app import poc_push
from app.config import get_settings
from app.main import app

HEADERS = {"X-Requested-With": "compabook"}
APPLE = "https://web.push.apple.com/abc123"


def body(endpoint: str = APPLE, delay: int = 0) -> dict:
    return {
        "subscription": {"endpoint": endpoint, "keys": {"p256dh": "p", "auth": "a"}},
        "delay": delay,
    }


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture
def vapid(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "vapid_public_key", "publica")
    monkeypatch.setattr(settings, "vapid_private_key", "privada")


def test_clave_sin_configurar(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "vapid_public_key", None)
    assert client.get("/api/v1/poc/push/key").status_code == 503


def test_clave_publica(client: TestClient, vapid: None) -> None:
    assert client.get("/api/v1/poc/push/key").json() == {"publicKey": "publica"}


def test_enviar_exige_cabecera(client: TestClient, vapid: None) -> None:
    assert client.post("/api/v1/poc/push/send", json=body()).status_code == 403


def test_enviar_sin_configurar(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "vapid_private_key", None)
    response = client.post("/api/v1/poc/push/send", json=body(), headers=HEADERS)
    assert response.status_code == 503


@pytest.mark.parametrize(
    "endpoint",
    [
        "http://web.push.apple.com/abc",
        "https://evil.example.com/abc",
        "https://web.push.apple.com.evil.example.com/abc",
        "https://127.0.0.1/abc",
    ],
)
def test_rechaza_servicios_no_admitidos(client: TestClient, vapid: None, endpoint: str) -> None:
    response = client.post("/api/v1/poc/push/send", json=body(endpoint), headers=HEADERS)
    assert response.status_code == 400


def test_envia_con_las_claves_del_servidor(
    client: TestClient, vapid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(poc_push, "webpush", lambda **kwargs: calls.append(kwargs))
    response = client.post("/api/v1/poc/push/send", json=body(), headers=HEADERS)
    assert response.json() == {"sent": True}
    assert calls[0]["subscription_info"]["endpoint"] == APPLE
    assert calls[0]["vapid_private_key"] == "privada"


def test_limita_la_espera(client: TestClient, vapid: None, monkeypatch: pytest.MonkeyPatch) -> None:
    waits: list[float] = []
    monkeypatch.setattr(poc_push, "webpush", lambda **kwargs: None)
    monkeypatch.setattr(poc_push.time, "sleep", waits.append)
    client.post("/api/v1/poc/push/send", json=body(delay=999), headers=HEADERS)
    assert waits == [poc_push.MAX_DELAY]


def test_suscripcion_caducada(
    client: TestClient, vapid: None, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(**kwargs: object) -> None:
        raise WebPushException("gone", response=SimpleNamespace(status_code=410))

    monkeypatch.setattr(poc_push, "webpush", fail)
    response = client.post("/api/v1/poc/push/send", json=body(), headers=HEADERS)
    assert response.json() == {"sent": False, "status": 410, "expired": True}
