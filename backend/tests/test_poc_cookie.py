import pytest
from fastapi.testclient import TestClient

from app import poc
from app.config import get_settings
from app.main import app

HEADERS = {"X-Requested-With": "compabook"}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, base_url="https://testserver")


def test_crear_exige_cabecera(client: TestClient) -> None:
    assert client.post("/api/v1/poc/cookie").status_code == 403


def test_cookie_con_las_opciones_de_la_sesion(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    # En local el .env desactiva Secure; aquí se comprueba el valor de producción.
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    response = client.post("/api/v1/poc/cookie", headers=HEADERS)
    set_cookie = response.headers["set-cookie"].lower()
    for option in ("httponly", "secure", "samesite=lax", "path=/", f"max-age={poc.MAX_AGE}"):
        assert option in set_cookie


def test_estado_sin_cookie(client: TestClient) -> None:
    assert client.get("/api/v1/poc/cookie").json() == {"present": False}


def test_estado_con_cookie_reciente(client: TestClient) -> None:
    client.post("/api/v1/poc/cookie", headers=HEADERS)
    body = client.get("/api/v1/poc/cookie").json()
    assert body["present"] is True
    assert body["renewed"] is False


def test_se_renueva_pasadas_24_horas(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    client.post("/api/v1/poc/cookie", headers=HEADERS)
    now = poc.time.time()
    monkeypatch.setattr(poc.time, "time", lambda: now + poc.RENEW_AFTER + 60)
    response = client.get("/api/v1/poc/cookie")
    assert response.json()["renewed"] is True
    assert "set-cookie" in response.headers


def test_borrar(client: TestClient) -> None:
    client.post("/api/v1/poc/cookie", headers=HEADERS)
    assert client.delete("/api/v1/poc/cookie").status_code == 403
    assert client.delete("/api/v1/poc/cookie", headers=HEADERS).json() == {"deleted": True}
    assert client.get("/api/v1/poc/cookie").json() == {"present": False}
