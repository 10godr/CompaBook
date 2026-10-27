"""Ayudantes compartidos por los tests de cuentas."""

import re
from datetime import UTC, datetime

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session as DbSession

from app.models import AllowedEmail, User
from app.services.ai import CardContent, GeneratedCard, normalize_slug
from app.services.email import EmailMessage
from app.services.push import PushError, PushMessage, PushTarget
from app.services.youtube import Video

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


class FakePushProvider:
    """Push falso: anota cada envío y falla con el error que se le pida (uno o todos)."""

    def __init__(self) -> None:
        self.sent: list[tuple[PushTarget, PushMessage]] = []
        self.error: PushError | None = None  # falla todos los envíos
        self.errors: dict[str, PushError] = {}  # falla los de un endpoint concreto

    def send(self, target: PushTarget, message: PushMessage) -> None:
        if self.error:
            raise self.error
        if target.endpoint in self.errors:
            raise self.errors[target.endpoint]
        self.sent.append((target, message))


def make_content(title: str = "CI/CD", **override: object) -> CardContent:
    """Una ficha válida de ejemplo; el `cache_slug` sale del título."""
    values = {
        "canonical_title": title,
        "cache_slug": normalize_slug(title),
        "what_is": "Qué es.",
        "what_for": "Para qué sirve.",
        "example": "Un ejemplo.",
    }
    return CardContent(**{**values, **override})


class FakeAIProvider:
    """IA falsa: cuenta las llamadas y devuelve una ficha fija o lanza el error que se le pida."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # (título, idioma) de cada llamada
        self.error: Exception | None = None
        self.cards: dict[str, CardContent] = {}  # ficha a devolver para un título concreto

    def generate_card(self, title: str, language: str) -> GeneratedCard:
        self.calls.append((title, language))
        if self.error:
            raise self.error
        return GeneratedCard(self.cards.get(title) or make_content(title), "modelo-falso")


def make_videos() -> list[Video]:
    return [
        Video(f"abcdefghij{n}", f"Video {n}", f"Canal {n}", f"https://i.ytimg.com/vi/{n}/hq.jpg")
        for n in (1, 2)
    ]


class FakeVideoProvider:
    """YouTube falso: cuenta las búsquedas y devuelve 2 videos fijos o lanza el error pedido."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []  # (consulta, idioma) de cada búsqueda
        self.error: Exception | None = None
        self.videos: list[Video] = make_videos()

    def search(self, query: str, language: str) -> list[Video]:
        self.calls.append((query, language))
        if self.error:
            raise self.error
        return self.videos


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
