from typing import Literal

from fastapi import APIRouter, Depends, Request, Response
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy.orm import Session as DbSession

from app.api.auth import user_payload
from app.api.deps import current_user, require_csrf_header
from app.api.validators import check_timezone
from app.db import get_db
from app.models import User
from app.services import accounts
from app.session_cookie import COOKIE_NAME, clear_session_cookie

router = APIRouter(prefix="/me")


class ProfileBody(BaseModel):
    language: Literal["es", "en"] | None = None
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str | None) -> str | None:
        return None if value is None else check_timezone(value)

    @model_validator(mode="after")
    def something_to_change(self) -> "ProfileBody":
        if self.language is None and self.timezone is None:
            raise ValueError("no hay nada que cambiar")
        return self


class ChangePasswordBody(BaseModel):
    current_password: str = Field(max_length=256)
    new_password: str = Field(max_length=256)


class DeleteBody(BaseModel):
    password: str = Field(max_length=256)


@router.get("")
def me(user: User = Depends(current_user)) -> dict[str, object]:
    return user_payload(user)


@router.patch("", dependencies=[Depends(require_csrf_header)])
def update_me(
    body: ProfileBody,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, object]:
    accounts.update_profile(db, user, language=body.language, timezone=body.timezone)
    return user_payload(user)


@router.post("/change-password", dependencies=[Depends(require_csrf_header)])
def change_password(
    body: ChangePasswordBody,
    request: Request,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, bool]:
    accounts.change_password(
        db,
        user,
        current_token=request.cookies.get(COOKIE_NAME),
        current_password=body.current_password,
        new_password=body.new_password,
    )
    return {"ok": True}


@router.delete("", dependencies=[Depends(require_csrf_header)])
def delete_me(
    body: DeleteBody,
    response: Response,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, bool]:
    accounts.delete_account(db, user, password=body.password)
    clear_session_cookie(response)
    return {"ok": True}
