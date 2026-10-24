from fastapi import APIRouter, Depends

from app.api.auth import user_payload
from app.api.deps import current_user
from app.models import User

router = APIRouter(prefix="/me")


@router.get("")
def me(user: User = Depends(current_user)) -> dict[str, object]:
    return user_payload(user)
