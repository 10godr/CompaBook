from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, EmailStr, Field, field_validator
from sqlalchemy.orm import Session as DbSession

from app.api.deps import client_ip, require_csrf_header
from app.db import get_db
from app.services import accounts
from app.services.email import EmailProvider, get_email_provider
from app.session_cookie import set_session_cookie

router = APIRouter(prefix="/auth", dependencies=[Depends(require_csrf_header)])

MESSAGES = {
    "es": "Si el email es válido, te enviamos un código.",
    "en": "If the email is valid, we sent you a code.",
}


class RegisterBody(BaseModel):
    email: EmailStr
    # El tope solo protege a argon2 de entradas enormes; la política real va en el servicio.
    password: str = Field(max_length=256)
    language: Literal["es", "en"]
    timezone: str = Field(max_length=64)
    accept_terms: bool

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except (ZoneInfoNotFoundError, ValueError, OSError) as error:
            raise ValueError("zona horaria desconocida") from error
        return value

    @field_validator("accept_terms")
    @classmethod
    def terms_accepted(cls, value: bool) -> bool:
        if not value:
            raise ValueError("hay que aceptar los términos")
        return value


class VerifyBody(BaseModel):
    email: EmailStr
    code: str = Field(pattern=r"^\d{6}$")


class ResendBody(BaseModel):
    email: EmailStr
    purpose: Literal["verify_email"] = "verify_email"
    language: Literal["es", "en"] = "es"


@router.post("/register", status_code=202)
def register(
    body: RegisterBody,
    request: Request,
    db: DbSession = Depends(get_db),
    mailer: EmailProvider = Depends(get_email_provider),
) -> dict[str, str]:
    accounts.register(
        db,
        mailer,
        email=body.email,
        password=body.password,
        language=body.language,
        timezone=body.timezone,
        ip=client_ip(request),
    )
    return {"message": MESSAGES[body.language]}


@router.post("/verify-email")
def verify_email(
    body: VerifyBody,
    request: Request,
    response: Response,
    db: DbSession = Depends(get_db),
) -> dict[str, object]:
    user, token = accounts.verify_email(
        db,
        email=body.email,
        code=body.code,
        user_agent=request.headers.get("user-agent"),
    )
    set_session_cookie(response, token)
    return {"user": {"email": user.email, "language": user.language, "timezone": user.timezone}}


@router.post("/resend-code", status_code=202)
def resend_code(
    body: ResendBody,
    db: DbSession = Depends(get_db),
    mailer: EmailProvider = Depends(get_email_provider),
) -> dict[str, str]:
    accounts.resend_code(db, mailer, email=body.email)
    return {"message": MESSAGES[body.language]}
