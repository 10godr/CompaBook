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
    invite,
    login,
    register,
    signup,
    token_of,
)

WRONG = "otra-clave-distinta"


def fail(client: TestClient, times: int, ip: str = "1.1.1.1", email: str = EMAIL) -> None:
    for _ in range(times):
        assert login(client, WRONG, email=email, ip=ip).status_code == 401


def sessions(orm: DbSession) -> int:
    return orm.execute(text("select count(*) from sessions")).scalar_one()


# --- Credenciales ---


def test_login_correcto(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> None:
    signup(client, orm, mailer)
    response = login(client)
    assert response.status_code == 200
    assert response.json() == {
        "user": {"email": EMAIL, "language": "es", "timezone": "America/Santo_Domingo"}
    }
    cookie = response.headers["set-cookie"].lower()
    for option in (
        "cb_session=",
        "httponly",
        "secure",
        "samesite=lax",
        "path=/",
        "max-age=2592000",
    ):
        assert option in cookie
    assert sessions(orm) == 2  # la del registro y la del login


def test_el_token_no_se_guarda_en_claro(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)
    token = token_of(login(client))
    hashes = orm.execute(text("select token_hash from sessions")).scalars().all()
    assert token not in hashes


def test_login_sin_distinguir_mayusculas(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)
    assert login(client, email="ANA@Example.com").status_code == 200


def test_contrasena_incorrecta_y_correo_desconocido_responden_igual(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)
    wrong_password = login(client, WRONG)
    unknown_email = login(client, WRONG, email="nadie@example.com")
    assert wrong_password.status_code == unknown_email.status_code == 401
    assert wrong_password.json() == unknown_email.json()
    assert wrong_password.json()["error"]["code"] == "invalid_credentials"
    assert "set-cookie" not in wrong_password.headers


def test_cuenta_sin_verificar(client: TestClient, orm: DbSession) -> None:
    invite(orm)
    register(client)
    right = login(client)
    assert right.status_code == 403
    assert right.json()["error"]["code"] == "email_not_verified"
    assert login(client, WRONG).status_code == 401  # con contraseña mala no se revela nada


def test_cuenta_suspendida_no_entra_ni_con_la_contrasena_buena(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)
    orm.execute(text("update users set disabled_at = now()"))
    response = login(client)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "invalid_credentials"


def test_login_exige_la_cabecera_csrf(client: TestClient) -> None:
    response = client.post("/api/v1/auth/login", json={"email": EMAIL, "password": PASSWORD})
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf"


# --- Límites de intentos ---


def test_cinco_fallos_abren_una_espera_de_15_minutos(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)
    fail(client, 4)
    assert login(client).status_code == 200  # el 5.º intento, correcto, todavía entra
    fail(client, 5)
    blocked = login(client)  # ni con la contraseña buena
    assert blocked.status_code == 429
    assert blocked.json()["error"]["code"] == "rate_limited"
    assert blocked.json()["error"]["retry_after"] == 15 * 60


def test_la_espera_baja_con_el_tiempo_y_los_intentos_bloqueados_no_la_alargan(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    signup(client, orm, mailer)
    fail(client, 5)
    clock["now"] = NOW + timedelta(minutes=5)
    for _ in range(8):
        assert login(client).status_code == 429
    assert login(client).json()["error"]["retry_after"] == 10 * 60


def test_pasada_la_espera_se_puede_volver_a_entrar(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    signup(client, orm, mailer)
    fail(client, 5)
    clock["now"] = NOW + timedelta(minutes=15, seconds=1)
    assert login(client).status_code == 200


def test_la_espera_se_duplica_en_cada_bloqueo_con_tope_de_una_hora(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    signup(client, orm, mailer)
    now = NOW
    for expected in (15 * 60, 30 * 60, 60 * 60, 60 * 60):
        fail(client, 5)
        assert login(client).json()["error"]["retry_after"] == expected
        now += timedelta(seconds=expected + 1)
        clock["now"] = now


def test_entrar_bien_reinicia_los_fallos_y_los_bloqueos(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    signup(client, orm, mailer)
    fail(client, 5)  # primer bloqueo: 15 min
    clock["now"] = NOW + timedelta(minutes=16)
    assert login(client).status_code == 200  # entra y se olvida todo
    fail(client, 4)
    assert login(client).status_code == 200  # 4 fallos no bastan
    fail(client, 5)
    assert login(client).json()["error"]["retry_after"] == 15 * 60  # vuelve a ser el primero


def test_los_fallos_viejos_no_cuentan(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    signup(client, orm, mailer)
    fail(client, 4)
    clock["now"] = NOW + timedelta(minutes=16)  # los 4 fallos salen de la ventana de 15 min
    fail(client, 4)
    assert login(client).status_code == 200


def test_el_bloqueo_es_por_correo_e_ip_no_por_cuenta(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)
    fail(client, 5, ip="1.1.1.1")
    assert login(client, ip="1.1.1.1").status_code == 429
    assert login(client, ip="8.8.8.8").status_code == 200  # el dueño entra desde otra red


def test_un_atacante_no_bloquea_a_otro_correo_en_su_ip(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)
    fail(client, 5, ip="6.6.6.6", email="otra@example.com")
    assert login(client, ip="6.6.6.6").status_code == 200


def test_limite_de_30_logins_por_hora_e_ip(client: TestClient) -> None:
    for number in range(30):
        assert login(client, WRONG, email=f"x{number}@example.com", ip="3.3.3.3").status_code == 401
    response = login(client, WRONG, email="x31@example.com", ip="3.3.3.3")
    assert response.status_code == 429
    assert login(client, WRONG, email="x31@example.com", ip="4.4.4.4").status_code == 401


def test_headers_de_prueba_son_los_del_contrato() -> None:
    assert HEADERS == {"X-Requested-With": "compabook"}
