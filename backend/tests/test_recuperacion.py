from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.models import EmailCode
from tests.helpers import (
    EMAIL,
    NOW,
    PASSWORD,
    FakeEmailProvider,
    forgot,
    invite,
    login,
    register,
    reset,
    signup,
    token_of,
)
from tests.test_sesion import me

NEW_PASSWORD = "nueva-clave-segura-9"


def wrong_code(code: str) -> str:
    return "000000" if code != "000000" else "111111"


def request_reset(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider, email: str = EMAIL
) -> str:
    """Crea la cuenta, pide el código de recuperación y lo devuelve."""
    signup(client, orm, mailer, email)
    mailer.sent.clear()
    assert forgot(client, email).status_code == 200
    return mailer.last_code()


# --- Pedir el código ---


def test_cuenta_verificada_recibe_el_codigo(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    request_reset(client, orm, mailer)
    assert len(mailer.sent) == 1
    assert "Restablece" in mailer.sent[0].subject


def test_el_correo_sale_en_el_idioma_de_la_cuenta(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client, language="en")
    from tests.helpers import verify

    verify(client, mailer.last_code())
    mailer.sent.clear()
    forgot(client)
    assert "Reset your CompaBook password" in mailer.sent[0].subject


def test_correo_desconocido_responde_igual_y_no_envia(
    client: TestClient, mailer: FakeEmailProvider
) -> None:
    response = forgot(client, "nadie@example.com")
    assert response.status_code == 200
    assert mailer.sent == []


def test_cuenta_sin_verificar_no_recibe_codigo_de_recuperacion(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    mailer.sent.clear()
    assert forgot(client).status_code == 200
    assert mailer.sent == []


def test_cuenta_suspendida_no_recibe_codigo(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)
    orm.execute(text("update users set disabled_at = now()"))
    mailer.sent.clear()
    assert forgot(client).status_code == 200
    assert mailer.sent == []


def test_la_respuesta_es_la_misma_exista_o_no_la_cuenta(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)
    assert forgot(client).json() == forgot(client, "nadie@example.com").json()


def test_limite_de_envios_por_correo(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    signup(client, orm, mailer)  # 1.er envío (verificación)
    for _ in range(4):
        assert forgot(client).status_code == 200
    assert forgot(client).status_code == 429
    for _ in range(5):
        assert forgot(client, "nadie@example.com").status_code == 200
    assert forgot(client, "nadie@example.com").status_code == 429


def test_un_codigo_nuevo_invalida_el_anterior(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    first = request_reset(client, orm, mailer)
    forgot(client)
    second = mailer.last_code()
    assert orm.query(EmailCode).filter(EmailCode.purpose == "reset_password").count() == 1
    if first != second:
        assert reset(client, first, NEW_PASSWORD).status_code == 400
    assert reset(client, second, NEW_PASSWORD).status_code == 200


# --- Cambiar la contraseña ---


def test_restablecer_cambia_la_contrasena(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    code = request_reset(client, orm, mailer)
    response = reset(client, code, NEW_PASSWORD)
    assert response.status_code == 200
    assert response.json() == {"ok": True}
    assert login(client, PASSWORD).status_code == 401
    assert login(client, NEW_PASSWORD).status_code == 200


def test_restablecer_cierra_todas_las_sesiones(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    first = token_of(signup(client, orm, mailer))
    second = token_of(login(client))
    mailer.sent.clear()
    forgot(client)
    reset(client, mailer.last_code(), NEW_PASSWORD)
    assert me(client, first).status_code == 401
    assert me(client, second).status_code == 401


def test_restablecer_no_toca_las_sesiones_de_otra_cuenta(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    beto = token_of(signup(client, orm, mailer, "beto@example.com"))
    code = request_reset(client, orm, mailer, "ana@example.com")
    assert reset(client, code, NEW_PASSWORD, "ana@example.com").status_code == 200
    assert me(client, beto).status_code == 200


def test_el_codigo_solo_vale_una_vez(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    code = request_reset(client, orm, mailer)
    assert reset(client, code, NEW_PASSWORD).status_code == 200
    assert reset(client, code, "otra-clave-nueva-7").status_code == 400
    assert login(client, NEW_PASSWORD).status_code == 200


def test_codigo_incorrecto(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> None:
    code = request_reset(client, orm, mailer)
    response = reset(client, wrong_code(code), NEW_PASSWORD)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_code"
    assert login(client, PASSWORD).status_code == 200  # la contraseña no cambió


def test_cinco_intentos_agotan_el_codigo(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    code = request_reset(client, orm, mailer)
    for _ in range(5):
        assert reset(client, wrong_code(code), NEW_PASSWORD).status_code == 400
    assert reset(client, code, NEW_PASSWORD).status_code == 400


def test_codigo_caducado(
    client: TestClient,
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
) -> None:
    code = request_reset(client, orm, mailer)
    clock["now"] = NOW + timedelta(minutes=16)
    assert reset(client, code, NEW_PASSWORD).status_code == 400


def test_contrasena_debil_no_gasta_el_codigo(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    code = request_reset(client, orm, mailer)
    response = reset(client, code, "password123")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "weak_password"
    assert orm.query(EmailCode).filter(EmailCode.purpose == "reset_password").one().attempts == 0
    assert reset(client, code, NEW_PASSWORD).status_code == 200


def test_correo_desconocido_responde_como_codigo_malo(client: TestClient) -> None:
    response = reset(client, "123456", NEW_PASSWORD, email="nadie@example.com")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_code"


def test_cuenta_sin_verificar_no_puede_restablecer(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    assert reset(client, mailer.last_code(), NEW_PASSWORD).status_code == 400


def test_cuenta_suspendida_no_puede_restablecer(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    code = request_reset(client, orm, mailer)
    orm.execute(text("update users set disabled_at = now()"))
    assert reset(client, code, NEW_PASSWORD).status_code == 400


def test_el_hash_nuevo_es_argon2id_y_no_se_guarda_la_contrasena(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    code = request_reset(client, orm, mailer)
    reset(client, code, NEW_PASSWORD)
    stored = orm.execute(text("select password_hash from users")).scalar_one()
    assert stored.startswith("$argon2id$")
    assert NEW_PASSWORD not in stored
