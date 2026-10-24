from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from tests.helpers import (
    EMAIL,
    HEADERS,
    NOW,
    PASSWORD,
    FakeEmailProvider,
    find_user,
    login,
    register,
    signup,
    token_of,
)
from tests.test_sesion import me

NEW = "nueva-clave-segura-9"
WRONG = "otra-clave-distinta"


def auth(token: str) -> dict[str, str]:
    return {**HEADERS, "Cookie": f"cb_session={token}"}


def patch_me(client: TestClient, token: str | None, **body: object):
    headers = auth(token) if token else HEADERS
    return client.patch("/api/v1/me", json=body, headers=headers)


def change_password(client: TestClient, token: str | None, current: str, new: str):
    headers = auth(token) if token else HEADERS
    body = {"current_password": current, "new_password": new}
    return client.post("/api/v1/me/change-password", json=body, headers=headers)


def delete_me(client: TestClient, token: str | None, password: str):
    headers = auth(token) if token else HEADERS
    return client.request("DELETE", "/api/v1/me", json={"password": password}, headers=headers)


def count(orm: DbSession, table: str) -> int:
    return orm.execute(text(f"select count(*) from {table}")).scalar_one()


# --- Perfil ---


def test_cambiar_idioma_y_zona_horaria(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    response = patch_me(client, token, language="en", timezone="Europe/Madrid")
    assert response.status_code == 200
    assert response.json() == {
        "user": {"email": EMAIL, "language": "en", "timezone": "Europe/Madrid"}
    }
    user = find_user(orm)
    assert user is not None
    assert (user.language, user.timezone) == ("en", "Europe/Madrid")
    assert me(client, token).json()["user"]["language"] == "en"


def test_cambiar_solo_el_idioma_no_toca_la_zona_horaria(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    patch_me(client, token, language="en")
    assert find_user(orm).timezone == "America/Santo_Domingo"  # type: ignore[union-attr]


def test_perfil_con_datos_no_validos(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    for body in ({}, {"language": "fr"}, {"timezone": "Marte/Olimpo"}, {"timezone": "x" * 100}):
        response = patch_me(client, token, **body)
        assert response.status_code == 422, body
        assert response.json()["error"]["code"] == "validation_error"
    assert find_user(orm).language == "es"  # type: ignore[union-attr]


def test_perfil_exige_sesion_y_cabecera_csrf(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    assert patch_me(client, None, language="en").status_code == 401  # con cabecera, pero sin cookie
    sin_csrf = client.patch(
        "/api/v1/me", json={"language": "en"}, headers={"Cookie": f"cb_session={token}"}
    )
    assert sin_csrf.status_code == 403


def test_cada_usuario_solo_cambia_su_perfil(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    ana = token_of(signup(client, orm, mailer, "ana@example.com"))
    signup(client, orm, mailer, "beto@example.com")
    patch_me(client, ana, language="en")
    assert find_user(orm, "ana@example.com").language == "en"  # type: ignore[union-attr]
    assert find_user(orm, "beto@example.com").language == "es"  # type: ignore[union-attr]


# --- Cambiar la contraseña ---


def test_cambiar_la_contrasena(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    response = change_password(client, token, PASSWORD, NEW)
    assert response.status_code == 200
    assert login(client, PASSWORD, ip="2.2.2.2").status_code == 401
    assert login(client, NEW, ip="3.3.3.3").status_code == 200
    stored = find_user(orm).password_hash  # type: ignore[union-attr]
    assert stored.startswith("$argon2id$")
    assert NEW not in stored


def test_la_sesion_actual_sigue_y_las_demas_se_cierran(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    actual = token_of(signup(client, orm, mailer))
    otro_dispositivo = token_of(login(client))
    change_password(client, actual, PASSWORD, NEW)
    assert me(client, actual).status_code == 200
    assert me(client, otro_dispositivo).status_code == 401


def test_cambiar_la_contrasena_no_toca_las_sesiones_de_otra_cuenta(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    ana = token_of(signup(client, orm, mailer, "ana@example.com"))
    beto = token_of(signup(client, orm, mailer, "beto@example.com"))
    change_password(client, ana, PASSWORD, NEW)
    assert me(client, beto).status_code == 200


def test_contrasena_actual_incorrecta(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    response = change_password(client, token, WRONG, NEW)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "wrong_password"
    assert login(client, PASSWORD).status_code == 200  # no cambió


def test_contrasena_nueva_debil(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    response = change_password(client, token, PASSWORD, "password123")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "weak_password"
    assert login(client, PASSWORD).status_code == 200


def test_comprobar_la_contrasena_actual_tiene_limite(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    for _ in range(5):
        assert change_password(client, token, WRONG, NEW).status_code == 400
    bloqueado = change_password(client, token, PASSWORD, NEW)  # ni acertando
    assert bloqueado.status_code == 429
    assert bloqueado.json()["error"]["code"] == "rate_limited"
    assert login(client, PASSWORD).status_code == 200  # la contraseña sigue siendo la vieja


def test_el_limite_se_libera_con_el_tiempo(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    token = token_of(signup(client, orm, mailer))
    for _ in range(5):
        change_password(client, token, WRONG, NEW)
    clock["now"] = NOW + timedelta(minutes=16)
    assert me(client, token).status_code == 200
    assert change_password(client, token, PASSWORD, NEW).status_code == 200


def test_cambiar_la_contrasena_exige_sesion_y_cabecera_csrf(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    body = {"current_password": PASSWORD, "new_password": NEW}
    assert client.post("/api/v1/me/change-password", json=body, headers=HEADERS).status_code == 401
    sin_csrf = client.post(
        "/api/v1/me/change-password", json=body, headers={"Cookie": f"cb_session={token}"}
    )
    assert sin_csrf.status_code == 403


# --- Eliminar la cuenta ---


def test_eliminar_la_cuenta_borra_todo(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    login(client)  # una segunda sesión
    response = delete_me(client, token, PASSWORD)
    assert response.status_code == 200
    cookie = response.headers["set-cookie"].lower()
    assert "cb_session=" in cookie and "max-age=0" in cookie
    assert find_user(orm) is None
    assert count(orm, "sessions") == 0
    assert count(orm, "email_codes") == 0
    assert me(client, token).status_code == 401
    assert login(client).status_code == 401


def test_eliminar_la_cuenta_no_toca_a_otra(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    ana = token_of(signup(client, orm, mailer, "ana@example.com"))
    beto = token_of(signup(client, orm, mailer, "beto@example.com"))
    delete_me(client, ana, PASSWORD)
    assert find_user(orm, "ana@example.com") is None
    assert find_user(orm, "beto@example.com") is not None
    assert me(client, beto).status_code == 200
    assert count(orm, "sessions") == 1


def test_eliminar_exige_la_contrasena(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    response = delete_me(client, token, WRONG)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "wrong_password"
    assert find_user(orm) is not None
    assert me(client, token).status_code == 200


def test_eliminar_comparte_el_limite_de_comprobaciones(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    for _ in range(5):
        assert delete_me(client, token, WRONG).status_code == 400
    assert delete_me(client, token, PASSWORD).status_code == 429
    assert find_user(orm) is not None


def test_eliminar_exige_sesion_cuerpo_y_cabecera_csrf(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    assert delete_me(client, None, PASSWORD).status_code == 401
    sin_csrf = client.request(
        "DELETE",
        "/api/v1/me",
        json={"password": PASSWORD},
        headers={"Cookie": f"cb_session={token}"},
    )
    assert sin_csrf.status_code == 403
    sin_cuerpo = client.delete("/api/v1/me", headers=auth(token))
    assert sin_cuerpo.status_code == 422
    assert find_user(orm) is not None


def test_la_invitacion_sobrevive_y_se_puede_volver_a_registrar(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    token = token_of(signup(client, orm, mailer))
    delete_me(client, token, PASSWORD)
    assert count(orm, "allowed_emails") == 1  # la invitación es del administrador
    mailer.sent.clear()
    assert register(client, ip="9.9.9.9").status_code == 202
    assert find_user(orm) is not None
    assert len(mailer.sent) == 1
