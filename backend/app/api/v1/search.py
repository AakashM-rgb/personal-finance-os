"""Natural-Language Financial Search endpoint. Authenticated, rate-limited,
and scoped to the caller's own data via app.search.service - the
interpreter never receives a database session or an unauthenticated
user_id; see app.search for the full architecture. Nothing here exposes
SQL, internal query-builder details, or another user's data.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.search import service as search_service
from app.search.schemas import SearchRequest

router = APIRouter(prefix="/search", tags=["search"])
settings = get_settings()


@router.post("/financial", response_model=None)
@limiter.limit(settings.search_rate_limit)
async def search_financial(
    request: Request,
    body: SearchRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    response = await search_service.search(db, user_id=current_user.id, request=body)
    return {"data": response, "error": None, "meta": None}
