"""Financial AI Assistant endpoint. Authenticated, rate-limited, and scoped
to the caller's own data via app.services.ai_assistant_service - the AI
model itself never receives a database session or an unauthenticated
user_id; see app.ai for the full architecture. Nothing here exposes
internal tool execution details, provider credentials, or configuration -
only the final answer, a safe tools-used summary (name + success only),
and the provider's own non-secret label (e.g. "mock" or "anthropic").
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.config import get_settings
from app.core.database import get_db
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.ai import AssistantRequest
from app.services import ai_assistant_service

router = APIRouter(prefix="/ai", tags=["ai"])
settings = get_settings()


@router.post("/assistant", response_model=None)
@limiter.limit(settings.ai_rate_limit)
async def ask_assistant(
    request: Request,
    body: AssistantRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    response = await ai_assistant_service.ask(
        db, user_id=current_user.id, message=body.message, history=body.history
    )
    return {"data": response, "error": None, "meta": None}
