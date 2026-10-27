from fastapi import APIRouter, Depends, Header
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, require_csrf_header
from app.db import get_db
from app.models import User
from app.services import accounts, reminders
from app.services.push import PushProvider, get_push_provider, is_allowed_endpoint

router = APIRouter(prefix="/push")

ENDPOINT_MAX = 2048
KEY_MAX = 512


def _allowed(value: str) -> str:
    if not is_allowed_endpoint(value):
        raise ValueError("servicio de push no admitido")
    return value


class Keys(BaseModel):
    p256dh: str = Field(min_length=1, max_length=KEY_MAX)
    auth: str = Field(min_length=1, max_length=KEY_MAX)


class SubscribeBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=ENDPOINT_MAX)
    keys: Keys

    @field_validator("endpoint")
    @classmethod
    def allowed_service(cls, value: str) -> str:
        return _allowed(value)


class EndpointBody(BaseModel):
    endpoint: str = Field(min_length=1, max_length=ENDPOINT_MAX)


class PushTestBody(BaseModel):
    # Sin endpoint se avisa a todos los dispositivos del usuario.
    endpoint: str | None = Field(default=None, min_length=1, max_length=ENDPOINT_MAX)


@router.get("/vapid-public-key")
def vapid_public_key() -> dict[str, str]:
    """Sin sesión: es la clave pública, la que el navegador necesita para suscribirse."""
    return {"public_key": reminders.public_key()}


@router.post("/subscriptions", dependencies=[Depends(require_csrf_header)])
def subscribe(
    body: SubscribeBody,
    user_agent: str | None = Header(default=None),
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, bool]:
    reminders.subscribe(
        db,
        user,
        endpoint=body.endpoint,
        p256dh=body.keys.p256dh,
        auth=body.keys.auth,
        user_agent=user_agent,
        now=accounts.utcnow(),
    )
    return {"ok": True}


@router.delete("/subscriptions", dependencies=[Depends(require_csrf_header)])
def unsubscribe(
    body: EndpointBody,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, bool]:
    reminders.unsubscribe(db, user, body.endpoint)
    return {"ok": True}


@router.post("/test", dependencies=[Depends(require_csrf_header)])
def send_test(
    body: PushTestBody,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
    push: PushProvider = Depends(get_push_provider),
) -> dict[str, int]:
    return reminders.send_test(db, push, user, body.endpoint, accounts.utcnow())
