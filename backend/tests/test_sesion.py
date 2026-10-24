from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from tests.helpers import (
    EMAIL,
    HEADERS,
    NOW,
    FakeEmailProvider,
    login,
    signup,
    token_of,
)


def me(client: TestClient, token: str | None):
    headers = {"Cookie": f"cb_session={token}"} if token else {}
    return client.get("/api/v1/me", headers=headers)


def session_row(orm: DbSession):
    return orm.execute(
        text("select expires_at, last_used_at from sessions order by created_at desc limit 1")
    ).one()


# --- Quién soy ---


def test_sin_cookie_no_hay_sesion(client: TestClient) -> None:
    response = me(client, None)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


def test_con_la_cookie_del_registro(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    response = me(client, token)
    assert response.status_code == 200
    assert response.json()["user"]["email"] == EMAIL


def test_token_inventado(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> None:
    signup(client, orm, mailer)
    assert me(client, "inventado").status_code == 401


def test_sesion_caducada(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    token = token_of(signup(client, orm, mailer))
    clock["now"] = NOW + timedelta(days=30, seconds=1)
    assert me(client, token).status_code == 401


def test_cuenta_suspendida_pierde_la_sesion_al_instante(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    assert me(client, token).status_code == 200
    orm.execute(text("update users set disabled_at = now()"))
    assert me(client, token).status_code == 401


# --- Renovación deslizante ---


def test_dentro_de_las_24_horas_no_se_renueva(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    token = token_of(signup(client, orm, mailer))
    clock["now"] = NOW + timedelta(hours=23)
    response = me(client, token)
    assert response.status_code == 200
    assert "set-cookie" not in response.headers
    expires_at, last_used_at = session_row(orm)
    assert expires_at == NOW + timedelta(days=30)
    assert last_used_at == NOW


def test_pasadas_24_horas_se_renueva_y_se_reenvia_la_cookie(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    token = token_of(signup(client, orm, mailer))
    later = NOW + timedelta(hours=25)
    clock["now"] = later
    response = me(client, token)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert f"cb_session={token}".lower() in cookie  # el mismo token, con nueva caducidad
    assert "max-age=2592000" in cookie
    expires_at, last_used_at = session_row(orm)
    assert expires_at == later + timedelta(days=30)
    assert last_used_at == later


def test_quien_usa_la_app_no_vuelve_a_entrar(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    token = token_of(signup(client, orm, mailer))
    for day in range(1, 41):
        clock["now"] = NOW + timedelta(days=day)
        assert me(client, token).status_code == 200, f"falló el día {day}"


def test_una_sesion_sin_uso_caduca_a_los_30_dias(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    token = token_of(signup(client, orm, mailer))
    clock["now"] = NOW + timedelta(days=15)
    assert me(client, token).status_code == 200  # renueva hasta el día 45
    clock["now"] = NOW + timedelta(days=45, seconds=1)
    assert me(client, token).status_code == 401


# --- Logout ---


def test_logout_cierra_la_sesion_y_borra_la_cookie(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    response = client.post(
        "/api/v1/auth/logout", headers={**HEADERS, "Cookie": f"cb_session={token}"}
    )
    assert response.status_code == 200
    cleared = response.headers["set-cookie"].lower()
    assert "cb_session=" in cleared
    assert "max-age=0" in cleared
    assert me(client, token).status_code == 401
    assert orm.execute(text("select count(*) from sessions")).scalar_one() == 0


def test_logout_sin_sesion_responde_igual(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout", headers=HEADERS)
    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_logout_solo_cierra_la_sesion_actual(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    first = token_of(signup(client, orm, mailer))
    second = token_of(login(client))
    client.post("/api/v1/auth/logout", headers={**HEADERS, "Cookie": f"cb_session={first}"})
    assert me(client, first).status_code == 401
    assert me(client, second).status_code == 200


def test_logout_de_una_cuenta_no_toca_la_de_otra(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    ana = token_of(signup(client, orm, mailer, "ana@example.com"))
    beto = token_of(signup(client, orm, mailer, "beto@example.com"))
    client.post("/api/v1/auth/logout", headers={**HEADERS, "Cookie": f"cb_session={ana}"})
    assert me(client, ana).status_code == 401
    assert me(client, beto).status_code == 200
    assert me(client, beto).json()["user"]["email"] == "beto@example.com"


def test_logout_exige_la_cabecera_csrf(client: TestClient) -> None:
    response = client.post("/api/v1/auth/logout")
    assert response.status_code == 403
