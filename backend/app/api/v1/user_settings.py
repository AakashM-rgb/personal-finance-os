"""Current user's settings endpoints. Always scoped to the authenticated
caller - there is no id in the URL because a user can only ever have one
settings row, and it is always their own (see app.services.user_settings_service)."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.user_settings import UserSettingsUpdate
from app.services import user_settings_service

router = APIRouter(prefix="/settings", tags=["settings"])


@router.get("", response_model=None)
async def get_settings(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    settings = await user_settings_service.get_settings(db, user_id=current_user.id)
    return {"data": settings, "error": None, "meta": None}


@router.patch("", response_model=None)
async def update_settings(
    body: UserSettingsUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    settings = await user_settings_service.update_settings(db, user_id=current_user.id, data=body)
    await db.commit()
    return {"data": settings, "error": None, "meta": None}
