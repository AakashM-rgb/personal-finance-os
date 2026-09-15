"""Financial calendar endpoint. Authenticated and scoped to the caller's
own data via app.services.calendar_service."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import calendar_service

router = APIRouter(prefix="/calendar", tags=["calendar"])


@router.get("", response_model=None)
async def get_calendar_month(
    year: int = Query(..., ge=1900, le=3000),
    month: int = Query(..., ge=1, le=12),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    calendar_month = await calendar_service.get_calendar_month(
        db, user_id=current_user.id, year=year, month=month
    )
    return {"data": calendar_month, "error": None, "meta": None}
