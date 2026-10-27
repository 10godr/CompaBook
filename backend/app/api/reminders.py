from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session as DbSession

from app.api.deps import current_user, require_csrf_header
from app.api.validators import check_timezone
from app.db import get_db
from app.models import User
from app.services import accounts, reminders

router = APIRouter(prefix="/reminders")


class RemindersBody(BaseModel):
    enabled: bool
    local_time: str = Field(max_length=5)
    weekdays: list[int] = Field(min_length=1, max_length=7)
    # La del dispositivo (Intl): los recordatorios usan la zona horaria de la cuenta.
    timezone: str | None = Field(default=None, max_length=64)

    @field_validator("local_time")
    @classmethod
    def valid_time(cls, value: str) -> str:
        reminders.parse_local_time(value)
        return value

    @field_validator("weekdays")
    @classmethod
    def valid_weekdays(cls, value: list[int]) -> list[int]:
        if any(day < 1 or day > 7 for day in value):
            raise ValueError("los días van de 1 (lunes) a 7 (domingo)")
        return value

    @field_validator("timezone")
    @classmethod
    def known_timezone(cls, value: str | None) -> str | None:
        return None if value is None else check_timezone(value)


@router.get("")
def get_reminders(
    user: User = Depends(current_user), db: DbSession = Depends(get_db)
) -> dict[str, object]:
    return reminders.reminder_state(db, user)


@router.put("", dependencies=[Depends(require_csrf_header)])
def put_reminders(
    body: RemindersBody,
    user: User = Depends(current_user),
    db: DbSession = Depends(get_db),
) -> dict[str, object]:
    return reminders.save_reminders(
        db,
        user,
        enabled=body.enabled,
        local_time=reminders.parse_local_time(body.local_time),
        weekdays=body.weekdays,
        timezone=body.timezone,
        now=accounts.utcnow(),
    )
