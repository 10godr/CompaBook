"""Envío de correos detrás de una interfaz (EmailProvider), con plantillas es/en."""

import smtplib
from dataclasses import dataclass
from email.message import EmailMessage as MimeMessage
from email.utils import formataddr
from typing import Protocol

from app.config import get_settings
from app.errors import ApiError

SMTP_TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class EmailMessage:
    to: str
    subject: str
    body: str


class EmailProvider(Protocol):
    def send(self, message: EmailMessage) -> None: ...


class ConsoleEmailProvider:
    """Solo para desarrollo local: escribe el correo, con su código, en la salida estándar."""

    def send(self, message: EmailMessage) -> None:
        print(
            f"\n--- Correo para {message.to} ---\n{message.subject}\n\n{message.body}\n---",
            flush=True,
        )


class GmailSmtpProvider:
    def __init__(self, host: str, port: int, user: str, app_password: str, from_name: str) -> None:
        self.host = host
        self.port = port
        self.user = user
        self.app_password = app_password
        self.from_name = from_name

    def send(self, message: EmailMessage) -> None:
        mime = MimeMessage()
        mime["From"] = formataddr((self.from_name, self.user))
        mime["To"] = message.to
        mime["Subject"] = message.subject
        mime.set_content(message.body)
        # Tiempo máximo de conexión de 10 s para no dejar colgada la petición de registro.
        with smtplib.SMTP(self.host, self.port, timeout=SMTP_TIMEOUT_SECONDS) as smtp:
            smtp.starttls()
            smtp.login(self.user, self.app_password)
            smtp.send_message(mime)


def get_email_provider() -> EmailProvider:
    settings = get_settings()
    if settings.smtp_user and settings.smtp_app_password:
        return GmailSmtpProvider(
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_user,
            settings.smtp_app_password,
            settings.email_from_name,
        )
    # Los códigos nunca deben salir por los logs de producción: ahí `Secure` está activo.
    if settings.cookie_secure:
        raise ApiError(503, "email_unavailable", "El envío de correos no está configurado")
    return ConsoleEmailProvider()


# --- Plantillas ----------------------------------------------------------------------------


def verification_email(to: str, code: str, language: str) -> EmailMessage:
    if language == "en":
        return EmailMessage(
            to=to,
            subject="Your CompaBook verification code",
            body=(
                f"Your CompaBook verification code is: {code}\n\n"
                "It expires in 15 minutes. If you didn't ask for it, you can ignore this email.\n"
            ),
        )
    return EmailMessage(
        to=to,
        subject="Tu código de verificación de CompaBook",
        body=(
            f"Tu código de verificación de CompaBook es: {code}\n\n"
            "Caduca en 15 minutos. Si no lo pediste, puedes ignorar este correo.\n"
        ),
    )


def reset_password_email(to: str, code: str, language: str) -> EmailMessage:
    if language == "en":
        return EmailMessage(
            to=to,
            subject="Reset your CompaBook password",
            body=(
                f"Your CompaBook password reset code is: {code}\n\n"
                "It expires in 15 minutes. If you didn't ask for it, ignore this email: "
                "your password won't change.\n"
            ),
        )
    return EmailMessage(
        to=to,
        subject="Restablece tu contraseña de CompaBook",
        body=(
            f"Tu código para restablecer la contraseña de CompaBook es: {code}\n\n"
            "Caduca en 15 minutos. Si no lo pediste, ignora este correo: "
            "tu contraseña no cambiará.\n"
        ),
    )


def already_registered_email(to: str, language: str) -> EmailMessage:
    app_url = get_settings().app_url
    if language == "en":
        return EmailMessage(
            to=to,
            subject="You already have a CompaBook account",
            body=(
                "Someone tried to sign up with this email, but you already have an account.\n"
                f"If it was you, sign in at {app_url} and use «Forgot my password» if you "
                "don't remember it.\n"
            ),
        )
    return EmailMessage(
        to=to,
        subject="Ya tienes una cuenta en CompaBook",
        body=(
            "Alguien intentó registrarse con este correo, pero ya tienes una cuenta.\n"
            f"Si fuiste tú, entra en {app_url} y usa «Olvidé mi contraseña» si no la recuerdas.\n"
        ),
    )
