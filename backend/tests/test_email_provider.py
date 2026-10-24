import pytest

from app.config import get_settings
from app.errors import ApiError
from app.services import email
from app.services.email import (
    ConsoleEmailProvider,
    EmailMessage,
    GmailSmtpProvider,
    already_registered_email,
    get_email_provider,
    verification_email,
)


def configure(monkeypatch: pytest.MonkeyPatch, **values: object) -> None:
    settings = get_settings()
    for name, value in values.items():
        monkeypatch.setattr(settings, name, value)


def test_con_smtp_usa_gmail(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch, smtp_user="compabook@gmail.com", smtp_app_password="abcd efgh")
    assert isinstance(get_email_provider(), GmailSmtpProvider)


def test_sin_smtp_en_local_usa_la_consola(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch, smtp_user=None, smtp_app_password=None, cookie_secure=False)
    assert isinstance(get_email_provider(), ConsoleEmailProvider)


def test_sin_smtp_en_produccion_no_imprime_codigos(monkeypatch: pytest.MonkeyPatch) -> None:
    configure(monkeypatch, smtp_user=None, smtp_app_password=None, cookie_secure=True)
    with pytest.raises(ApiError) as error:
        get_email_provider()
    assert error.value.status_code == 503


def test_gmail_envia_por_starttls_con_tiempo_maximo(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple] = []

    class FakeSMTP:
        def __init__(self, host: str, port: int, timeout: float) -> None:
            calls.append(("conectar", host, port, timeout))

        def __enter__(self) -> "FakeSMTP":
            return self

        def __exit__(self, *args: object) -> None:
            calls.append(("cerrar",))

        def starttls(self) -> None:
            calls.append(("starttls",))

        def login(self, user: str, password: str) -> None:
            calls.append(("login", user, password))

        def send_message(self, message) -> None:  # noqa: ANN001
            calls.append(("enviar", message["From"], message["To"], message["Subject"]))

    monkeypatch.setattr(email.smtplib, "SMTP", FakeSMTP)
    provider = GmailSmtpProvider("smtp.gmail.com", 587, "compabook@gmail.com", "clave", "CompaBook")
    provider.send(EmailMessage(to="ana@example.com", subject="Hola", body="Cuerpo"))

    assert calls[0] == ("conectar", "smtp.gmail.com", 587, 10)
    assert [call[0] for call in calls] == ["conectar", "starttls", "login", "enviar", "cerrar"]
    assert calls[2] == ("login", "compabook@gmail.com", "clave")
    assert calls[3] == ("enviar", "CompaBook <compabook@gmail.com>", "ana@example.com", "Hola")


def test_plantillas_en_los_dos_idiomas() -> None:
    assert "123456" in verification_email("a@b.c", "123456", "es").body
    assert "15 minutos" in verification_email("a@b.c", "123456", "es").body
    assert "15 minutes" in verification_email("a@b.c", "123456", "en").body
    assert "Ya tienes" in already_registered_email("a@b.c", "es").subject
    assert "already have" in already_registered_email("a@b.c", "en").subject
