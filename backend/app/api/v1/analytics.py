"""Analytics endpoint. Authenticated and scoped to the caller's own data
via app.services.analytics_service - every figure returned is computed
from that user's own transactions, budgets, and recurring transactions."""

from datetime import date

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.analytics import AnalyticsRequest
from app.services import analytics_service
from app.services.analytics_calculations import AnalyticsRangePreset

router = APIRouter(prefix="/analytics", tags=["analytics"])


@router.get("", response_model=None)
async def get_analytics(
    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH,  # noqa: A002
    custom_from: date | None = None,
    custom_to: date | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    request = AnalyticsRequest(range=range, custom_from=custom_from, custom_to=custom_to)
    analytics = await analytics_service.get_analytics(db, user_id=current_user.id, request=request)
    return {"data": analytics, "error": None, "meta": None}
