"""Authentication endpoints: register, login, refresh, logout, logout-all, me."""

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.cookies import REFRESH_COOKIE_NAME, clear_session_cookies, set_session_cookies
from app.auth.dependencies import get_current_user, verify_csrf
from app.core.config import get_settings
from app.core.database import get_db
from app.core.errors import AuthenticationError
from app.core.rate_limit import limiter
from app.models.user import User
from app.schemas.auth import AccessTokenResponse, LoginRequest, RegisterRequest
from app.schemas.user import UserRead
from app.services import auth_service

router = APIRouter(prefix="/auth", tags=["auth"])
settings = get_settings()


def _client_context(request: Request) -> tuple[str | None, str | None]:
    ip_address = request.client.host if request.client else None
    user_agent = request.headers.get("user-agent")
    return ip_address, user_agent


def _to_response(result: auth_service.AuthResult) -> AccessTokenResponse:
    return AccessTokenResponse(
        access_token=result.access_token,
        expires_in=settings.access_token_expire_minutes * 60,
        user=UserRead.model_validate(result.user),
    )


@router.post("/register", response_model=None)
@limiter.limit(settings.register_rate_limit)
async def register(
    request: Request,
    body: RegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ip_address, user_agent = _client_context(request)
    result = await auth_service.register(
        db,
        email=body.email,
        password=body.password,
        full_name=body.full_name,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    set_session_cookies(response, raw_refresh_token=result.raw_refresh_token)
    return {"data": _to_response(result), "error": None, "meta": None}


@router.post("/login", response_model=None)
@limiter.limit(settings.login_rate_limit)
async def login(
    request: Request,
    body: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    ip_address, user_agent = _client_context(request)
    result = await auth_service.login(
        db,
        email=body.email,
        password=body.password,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    set_session_cookies(response, raw_refresh_token=result.raw_refresh_token)
    return {"data": _to_response(result), "error": None, "meta": None}


@router.post("/refresh", response_model=None, dependencies=[Depends(verify_csrf)])
async def refresh(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    raw_refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if not raw_refresh_token:
        raise AuthenticationError("Invalid or expired session. Please log in again.")

    ip_address, user_agent = _client_context(request)
    result = await auth_service.refresh_session(
        db,
        raw_refresh_token=raw_refresh_token,
        ip_address=ip_address,
        user_agent=user_agent,
    )
    await db.commit()
    set_session_cookies(response, raw_refresh_token=result.raw_refresh_token)
    return {"data": _to_response(result), "error": None, "meta": None}


@router.post("/logout", response_model=None, dependencies=[Depends(verify_csrf)])
async def logout(
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
) -> dict:
    raw_refresh_token = request.cookies.get(REFRESH_COOKIE_NAME)
    if raw_refresh_token:
        await auth_service.logout(db, raw_refresh_token=raw_refresh_token)
        await db.commit()
    clear_session_cookies(response)
    return {"data": {"success": True}, "error": None, "meta": None}


@router.post("/logout-all", response_model=None)
async def logout_all(
    response: Response,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await auth_service.logout_all(db, user_id=current_user.id)
    await db.commit()
    clear_session_cookies(response)
    return {"data": {"success": True}, "error": None, "meta": None}


@router.get("/me", response_model=None)
async def me(current_user: User = Depends(get_current_user)) -> dict:
    return {"data": UserRead.model_validate(current_user), "error": None, "meta": None}
