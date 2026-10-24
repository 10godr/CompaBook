"""Ayudantes compartidos por los tests de cuentas."""

import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.models import AllowedEmail, User
from app.services.email import EmailMessage

HEADERS = {"X-Requested-With": "compabook"}
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=UTC)
PASSWORD = "caballo-grapa-azul"
EMAIL = "ana@example.com"


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


def invite(orm: DbSession, email: str = EMAIL) -> None:
    orm.add(AllowedEmail(email=email))
    orm.flush()


def body(**override: object) -> dict[str, object]:
    data: dict[str, object] = {
        "email": EMAIL,
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


def verify(client: TestClient, code: str, email: str = EMAIL):
    return client.post(
        "/api/v1/auth/verify-email", json={"email": email, "code": code}, headers=HEADERS
    )


def resend(client: TestClient, email: str = EMAIL):
    return client.post("/api/v1/auth/resend-code", json={"email": email}, headers=HEADERS)


def login(client: TestClient, password: str = PASSWORD, email: str = EMAIL, ip: str = "1.1.1.1"):
    return client.post(
        "/api/v1/auth/login",
        json={"email": email, "password": password},
        headers={**HEADERS, "x-forwarded-for": ip},
    )


def forgot(client: TestClient, email: str = EMAIL):
    return client.post("/api/v1/auth/forgot-password", json={"email": email}, headers=HEADERS)


def reset(client: TestClient, code: str, new_password: str, email: str = EMAIL):
    return client.post(
        "/api/v1/auth/reset-password",
        json={"email": email, "code": code, "new_password": new_password},
        headers=HEADERS,
    )


def find_user(orm: DbSession, email: str = EMAIL) -> User | None:
    return orm.query(User).filter(User.email == email).one_or_none()


def token_of(response) -> str:
    """El token de la cookie `cb_session` que puso la respuesta."""
    match = re.search(r"cb_session=([^;]+)", response.headers["set-cookie"])
    assert match, "la respuesta no puso la cookie de sesión"
    return match.group(1)


def signup(client: TestClient, orm: DbSession, mailer: FakeEmailProvider, email: str = EMAIL):
    """Invita, registra y verifica una cuenta. Devuelve la respuesta de la verificación."""
    invite(orm, email)
    register(client, email=email)
    response = verify(client, mailer.last_code(), email)
    assert response.status_code == 200
    return response
