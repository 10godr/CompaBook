import logging
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session as DbSession

from app.config import get_settings
from tests.helpers import NOW

SECRET = "secreto-interno-de-prueba"
DAY = timedelta(days=1)


@pytest.fixture
def secret(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "internal_secret", SECRET)


def cleanup(client: TestClient, secret_value: str | None = SECRET):
    headers = {"X-Internal-Secret": secret_value} if secret_value else {}
    return client.post("/api/v1/internal/cleanup", headers=headers)


def add_user(orm: DbSession, email: str, created: object, verified: bool) -> str:
    return orm.execute(
        text(
            "insert into users (email, password_hash, language, timezone, created_at, "
            "email_verified_at) values (:email, 'h', 'es', 'UTC', :created, :verified) returning id"
        ),
        {"email": email, "created": created, "verified": created if verified else None},
    ).scalar_one()


def add_session(orm: DbSession, user_id: str, token: str, expires: object) -> None:
    orm.execute(
        text("insert into sessions (user_id, token_hash, expires_at) values (:u, :t, :e)"),
        {"u": user_id, "t": token, "e": expires},
    )


def add_code(orm: DbSession, user_id: str, expires: object) -> None:
    orm.execute(
        text(
            "insert into email_codes (user_id, purpose, code_hash, expires_at) "
            "values (:u, 'verify_email', 'h', :e)"
        ),
        {"u": user_id, "e": expires},
    )


def add_event(orm: DbSession, created: object, key: str) -> None:
    orm.execute(
        text("insert into rate_limit_events (bucket, key, created_at) values ('login_ip', :k, :c)"),
        {"k": key, "c": created},
    )


def total(orm: DbSession, table: str) -> int:
    return orm.execute(text(f"select count(*) from {table}")).scalar_one()


# --- Protección del endpoint ---


def test_sin_secreto_configurado(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(get_settings(), "internal_secret", None)
    assert cleanup(client).status_code == 503


def test_sin_cabecera_o_con_secreto_incorrecto(client: TestClient, secret: None) -> None:
    assert cleanup(client, None).status_code == 401
    assert cleanup(client, "otro").status_code == 401


def test_no_hace_falta_la_cabecera_csrf_porque_lo_llama_pg_cron(
    client: TestClient, secret: None
) -> None:
    assert cleanup(client).status_code == 200


# --- Qué borra ---


def test_borra_lo_caducado_y_conserva_lo_vigente(
    client: TestClient, orm: DbSession, secret: None
) -> None:
    user = add_user(orm, "ana@example.com", NOW - 30 * DAY, verified=True)
    add_session(orm, user, "caducada", NOW - timedelta(seconds=1))
    add_session(orm, user, "vigente", NOW + DAY)
    add_code(orm, user, NOW - timedelta(minutes=1))
    add_code(orm, user, NOW + timedelta(minutes=10))
    add_event(orm, NOW - 3 * DAY, "viejo")
    add_event(orm, NOW - DAY, "reciente")

    response = cleanup(client)

    assert response.json() == {
        "sessions": 1,
        "email_codes": 1,
        "rate_limit_events": 1,
        "unverified_users": 0,
    }
    assert total(orm, "sessions") == 1
    assert orm.execute(text("select token_hash from sessions")).scalar_one() == "vigente"
    assert total(orm, "email_codes") == 1
    assert orm.execute(text("select key from rate_limit_events")).scalar_one() == "reciente"


def test_borra_las_cuentas_sin_verificar_de_mas_de_7_dias_con_sus_datos(
    client: TestClient, orm: DbSession, secret: None
) -> None:
    viejo = add_user(orm, "viejo@example.com", NOW - 8 * DAY, verified=False)
    add_code(orm, viejo, NOW + DAY)
    add_user(orm, "reciente@example.com", NOW - 6 * DAY, verified=False)
    add_user(orm, "verificado@example.com", NOW - 30 * DAY, verified=True)

    response = cleanup(client)

    assert response.json()["unverified_users"] == 1
    emails = orm.execute(text("select email from users order by email")).scalars().all()
    assert emails == ["reciente@example.com", "verificado@example.com"]
    assert total(orm, "email_codes") == 0  # cayó en cascada con su cuenta


def test_no_toca_a_los_usuarios_verificados_aunque_sean_viejos(
    client: TestClient, orm: DbSession, secret: None
) -> None:
    user = add_user(orm, "ana@example.com", NOW - 365 * DAY, verified=True)
    add_session(orm, user, "vigente", NOW + DAY)
    cleanup(client)
    assert total(orm, "users") == 1
    assert total(orm, "sessions") == 1


def test_es_idempotente(client: TestClient, orm: DbSession, secret: None) -> None:
    user = add_user(orm, "ana@example.com", NOW - 30 * DAY, verified=True)
    add_session(orm, user, "caducada", NOW - DAY)
    assert cleanup(client).json()["sessions"] == 1
    assert cleanup(client).json() == {
        "sessions": 0,
        "email_codes": 0,
        "rate_limit_events": 0,
        "unverified_users": 0,
    }


def test_solo_registra_numeros(
    client: TestClient, orm: DbSession, secret: None, caplog: pytest.LogCaptureFixture
) -> None:
    add_user(orm, "secreto@example.com", NOW - 8 * DAY, verified=False)
    with caplog.at_level(logging.INFO, logger="compabook.internal"):
        cleanup(client)
    assert "cleanup:" in caplog.text
    assert "@" not in caplog.text
    assert SECRET not in caplog.text
