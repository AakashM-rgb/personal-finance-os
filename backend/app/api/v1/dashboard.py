"""Dashboard endpoint. Authenticated and scoped to the caller's own data via
app.services.dashboard_service - every number returned is computed from
that user's own accounts and transactions."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.services import dashboard_service

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("", response_model=None)
async def get_dashboard(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    dashboard = await dashboard_service.get_dashboard(db, user_id=current_user.id)
    return {"data": dashboard, "error": None, "meta": None}
