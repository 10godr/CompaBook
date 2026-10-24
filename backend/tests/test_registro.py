import logging
import re
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from app.db import get_db
from app.main import app
from app.models import AllowedEmail, EmailCode, User
from app.services import accounts
from app.services.email import EmailMessage, get_email_provider

HEADERS = {"X-Requested-With": "compabook"}
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
PASSWORD = "caballo-grapa-azul"


class FakeEmailProvider:
    def __init__(self) -> None:
        self.sent: list[EmailMessage] = []
        self.fail = False

    def send(self, message: EmailMessage) -> None:
        if self.fail:
            raise RuntimeError("SMTP caído")
        self.sent.append(message)

    def last_code(self) -> str:
        match = re.search(r"\b(\d{6})\b", self.sent[-1].body)
        assert match, "el correo no lleva código"
        return match.group(1)


@pytest.fixture
def mailer() -> FakeEmailProvider:
    return FakeEmailProvider()


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> dict[str, datetime]:
    state = {"now": NOW}
    monkeypatch.setattr(accounts, "utcnow", lambda: state["now"])
    return state


@pytest.fixture
def client(
    orm: DbSession,
    mailer: FakeEmailProvider,
    clock: dict[str, datetime],
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setattr(get_settings(), "secret_key", "clave-de-prueba")
    monkeypatch.setattr(get_settings(), "cookie_secure", True)
    app.dependency_overrides[get_db] = lambda: orm
    app.dependency_overrides[get_email_provider] = lambda: mailer
    yield TestClient(app)
    app.dependency_overrides.clear()


def invite(orm: DbSession, email: str = "ana@example.com") -> None:
    orm.add(AllowedEmail(email=email))
    orm.flush()


def body(**override: object) -> dict[str, object]:
    data: dict[str, object] = {
        "email": "ana@example.com",
        "password": PASSWORD,
        "language": "es",
        "timezone": "America/Santo_Domingo",
        "accept_terms": True,
    }
    return {**data, **override}


def register(client: TestClient, ip: str = "1.1.1.1", **override: object):
    return client.post(
        "/api/v1/auth/register", json=body(**override), headers={**HEADERS, "x-forwarded-for": ip}
    )


def verify(client: TestClient, code: str, email: str = "ana@example.com"):
    return client.post(
        "/api/v1/auth/verify-email", json={"email": email, "code": code}, headers=HEADERS
    )


def find_user(orm: DbSession, email: str = "ana@example.com") -> User | None:
    return orm.query(User).filter(User.email == email).one_or_none()


# --- Registro por invitación ---


def test_correo_no_invitado(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> None:
    response = register(client, email="intruso@example.com")
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "registration_not_allowed"
    assert find_user(orm, "intruso@example.com") is None
    assert mailer.sent == []


def test_correo_invitado_crea_usuario_sin_verificar(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    response = register(client)
    assert response.status_code == 202
    user = find_user(orm)
    assert user is not None
    assert user.email_verified_at is None
    assert user.password_hash.startswith("$argon2id$")
    assert PASSWORD not in user.password_hash
    assert len(mailer.sent) == 1
    assert mailer.sent[0].to == "ana@example.com"


def test_el_codigo_se_guarda_firmado_y_caduca_a_los_15_minutos(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    stored = orm.query(EmailCode).one()
    assert mailer.last_code() not in stored.code_hash
    assert stored.purpose == "verify_email"
    assert stored.expires_at == NOW + timedelta(minutes=15)


def test_la_invitacion_no_distingue_mayusculas(client: TestClient, orm: DbSession) -> None:
    invite(orm, "Ana@Example.com")
    assert register(client, email="ANA@example.com").status_code == 202


def test_correo_y_idioma_en_ingles(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    response = register(client, language="en")
    assert response.json()["message"] == "If the email is valid, we sent you a code."
    assert "verification code" in mailer.sent[0].subject


def test_correo_en_espanol(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> None:
    invite(orm)
    response = register(client)
    assert response.json()["message"] == "Si el email es válido, te enviamos un código."
    assert "código de verificación" in mailer.sent[0].subject


def test_cuenta_ya_verificada_responde_igual_y_avisa(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    first = register(client)
    verify(client, mailer.last_code())
    original_hash = find_user(orm).password_hash  # type: ignore[union-attr]
    mailer.sent.clear()

    second = register(client, ip="2.2.2.2", password="otra-clave-distinta")
    assert second.status_code == 202
    assert second.json() == first.json()
    assert len(mailer.sent) == 1
    assert "ya tienes una cuenta" in mailer.sent[0].subject.lower()
    assert find_user(orm).password_hash == original_hash  # type: ignore[union-attr]
    assert orm.query(User).count() == 1


def test_registrar_dos_veces_sin_verificar_invalida_el_codigo_anterior(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    old_code = mailer.last_code()
    register(client, ip="2.2.2.2")
    new_code = mailer.last_code()
    assert orm.query(EmailCode).count() == 1
    if old_code != new_code:
        assert verify(client, old_code).status_code == 400
    assert verify(client, new_code).status_code == 200


@pytest.mark.parametrize(
    "override",
    [
        {"accept_terms": False},
        {"email": "no-es-un-correo"},
        {"language": "fr"},
        {"timezone": "Marte/Olimpo"},
        {"password": "x" * 300},
    ],
)
def test_datos_no_validos(client: TestClient, orm: DbSession, override: dict) -> None:
    invite(orm)
    response = register(client, **override)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


def test_el_error_de_validacion_no_devuelve_la_contrasena(
    client: TestClient, orm: DbSession
) -> None:
    response = register(client, email="no-es-un-correo", password="mi-clave-secreta-123")
    assert "mi-clave-secreta-123" not in response.text


@pytest.mark.parametrize(
    ("password", "reason"),
    [("corta1", "too_short"), ("password123", "too_common"), ("aaaaaaaaaa", "too_common")],
)
def test_contrasena_debil(client: TestClient, orm: DbSession, password: str, reason: str) -> None:
    invite(orm)
    response = register(client, password=password)
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "weak_password"
    assert response.json()["error"]["reason"] == reason
    assert find_user(orm) is None


def test_cuenta_suspendida_no_recibe_nada(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    orm.execute(text("update users set disabled_at = now()"))
    mailer.sent.clear()
    assert register(client, ip="2.2.2.2").status_code == 202
    assert mailer.sent == []


def test_si_el_correo_falla_el_registro_responde_igual(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider, caplog: pytest.LogCaptureFixture
) -> None:
    invite(orm)
    mailer.fail = True
    with caplog.at_level(logging.INFO):
        response = register(client)
    assert response.status_code == 202
    assert "RuntimeError" in caplog.text


def test_no_se_registran_ni_codigos_ni_contrasenas(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider, caplog: pytest.LogCaptureFixture
) -> None:
    invite(orm)
    with caplog.at_level(logging.DEBUG):
        register(client)
        verify(client, mailer.last_code())
    assert PASSWORD not in caplog.text
    assert mailer.last_code() not in caplog.text


def test_exige_la_cabecera_csrf(client: TestClient, orm: DbSession) -> None:
    invite(orm)
    response = client.post("/api/v1/auth/register", json=body())
    assert response.status_code == 403
    assert response.json()["error"]["code"] == "csrf"


# --- Verificación ---


def test_verificar_inicia_sesion(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    response = verify(client, mailer.last_code())
    assert response.status_code == 200
    assert response.json() == {
        "user": {"email": "ana@example.com", "language": "es", "timezone": "America/Santo_Domingo"}
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
    user = find_user(orm)
    assert user is not None
    assert user.email_verified_at == NOW


def test_la_sesion_se_guarda_con_hash_y_no_el_token(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    response = verify(client, mailer.last_code())
    token = re.search(r"cb_session=([^;]+)", response.headers["set-cookie"]).group(1)  # type: ignore[union-attr]
    stored = orm.execute(text("select token_hash, expires_at from sessions")).one()
    assert stored.token_hash != token
    assert token not in stored.token_hash
    assert stored.expires_at == NOW + timedelta(days=30)


def test_un_codigo_solo_vale_una_vez(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    code = mailer.last_code()
    assert verify(client, code).status_code == 200
    assert verify(client, code).status_code == 400


def test_codigo_incorrecto(client: TestClient, orm: DbSession, mailer: FakeEmailProvider) -> None:
    invite(orm)
    register(client)
    wrong = "000000" if mailer.last_code() != "000000" else "111111"
    response = verify(client, wrong)
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_code"
    assert orm.query(EmailCode).one().attempts == 1


def test_cinco_intentos_agotan_el_codigo(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    right = mailer.last_code()
    wrong = "000000" if right != "000000" else "111111"
    for _ in range(5):
        assert verify(client, wrong).status_code == 400
    assert verify(client, right).status_code == 400  # ya no vale ni el correcto
    assert find_user(orm).email_verified_at is None  # type: ignore[union-attr]


def test_codigo_caducado(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider, clock: dict[str, datetime]
) -> None:
    invite(orm)
    register(client)
    clock["now"] = NOW + timedelta(minutes=16)
    assert verify(client, mailer.last_code()).status_code == 400


def test_un_codigo_justo_antes_de_caducar_vale(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider, clock: dict[str, datetime]
) -> None:
    invite(orm)
    register(client)
    clock["now"] = NOW + timedelta(minutes=14, seconds=59)
    assert verify(client, mailer.last_code()).status_code == 200


def test_correo_desconocido_responde_igual_que_codigo_malo(client: TestClient) -> None:
    response = verify(client, "123456", email="nadie@example.com")
    assert response.status_code == 400
    assert response.json()["error"]["code"] == "invalid_code"


def test_cuenta_suspendida_no_puede_verificar(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    orm.execute(text("update users set disabled_at = now()"))
    assert verify(client, mailer.last_code()).status_code == 400


def test_formato_del_codigo(client: TestClient) -> None:
    response = client.post(
        "/api/v1/auth/verify-email",
        json={"email": "ana@example.com", "code": "abc"},
        headers=HEADERS,
    )
    assert response.status_code == 422


# --- Reenviar código ---


def resend(client: TestClient, email: str = "ana@example.com"):
    return client.post("/api/v1/auth/resend-code", json={"email": email}, headers=HEADERS)


def test_reenviar_manda_un_codigo_nuevo(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    mailer.sent.clear()
    assert resend(client).status_code == 202
    assert len(mailer.sent) == 1
    assert verify(client, mailer.last_code()).status_code == 200


def test_reenviar_a_un_correo_desconocido_responde_igual_y_no_envia(
    client: TestClient, mailer: FakeEmailProvider
) -> None:
    assert resend(client, "nadie@example.com").status_code == 202
    assert mailer.sent == []


def test_reenviar_a_una_cuenta_verificada_no_envia(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)
    verify(client, mailer.last_code())
    mailer.sent.clear()
    assert resend(client).status_code == 202
    assert mailer.sent == []


# --- Límites de intentos ---


def test_limite_de_registros_por_ip(client: TestClient) -> None:
    for number in range(10):
        assert register(client, email=f"x{number}@example.com").status_code == 403
    response = register(client, email="x11@example.com")
    assert response.status_code == 429
    error = response.json()["error"]
    assert error["code"] == "rate_limited"
    assert 1 <= error["retry_after"] <= 3600
    # Otra IP no se ve afectada.
    assert register(client, ip="9.9.9.9", email="x12@example.com").status_code == 403


def test_el_limite_de_ip_se_libera_pasada_una_hora(
    client: TestClient, clock: dict[str, datetime]
) -> None:
    for number in range(10):
        register(client, email=f"x{number}@example.com")
    assert register(client, email="y@example.com").status_code == 429
    clock["now"] = NOW + timedelta(hours=1, seconds=1)
    assert register(client, email="y@example.com").status_code == 403


def test_limite_de_envios_por_correo(
    client: TestClient, orm: DbSession, mailer: FakeEmailProvider
) -> None:
    invite(orm)
    register(client)  # 1.er envío
    for _ in range(4):
        assert resend(client).status_code == 202
    response = resend(client)
    assert response.status_code == 429
    assert response.json()["error"]["code"] == "rate_limited"


def test_el_limite_de_envios_cuenta_aunque_el_correo_no_exista(client: TestClient) -> None:
    for _ in range(5):
        assert resend(client, "nadie@example.com").status_code == 202
    assert resend(client, "nadie@example.com").status_code == 429
