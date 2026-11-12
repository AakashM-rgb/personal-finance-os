"""FastAPI dependency for extracting and validating the current authenticated user.

This is the single choke point every protected route depends on - never parse
or trust the Authorization header anywhere else.
"""

import uuid
from typing import Any

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AuthenticationError
from app.core.security import TokenType, decode_token
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository

_bearer_scheme = HTTPBearer(auto_error=False)

CSRF_COOKIE_NAME = "csrf_token"
CSRF_HEADER_NAME = "x-csrf-token"


def verify_csrf(request: Request) -> None:
    """Double-submit CSRF check for cookie-authenticated mutating endpoints
    (refresh/logout). The csrf cookie is deliberately NOT httpOnly so only
    same-origin JavaScript can read it and echo it back as a header - a
    cross-site form/fetch cannot read it to forge a matching header."""
    cookie_value = request.cookies.get(CSRF_COOKIE_NAME)
    header_value = request.headers.get(CSRF_HEADER_NAME)
    if not cookie_value or not header_value or cookie_value != header_value:
        raise AuthenticationError("Missing or invalid CSRF token.")


def _uuid_claim(payload: dict[str, Any], claim: str) -> uuid.UUID:
    # Signed but not schema-checked: a claim of the wrong JSON type must be a
    # 401, never an unhandled error from uuid.UUID.
    value = payload.get(claim)
    if not isinstance(value, str):
        raise AuthenticationError("Invalid or expired session. Please log in again.")
    try:
        return uuid.UUID(value)
    except ValueError as exc:
        raise AuthenticationError("Invalid or expired session. Please log in again.") from exc


async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    if credentials is None:
        raise AuthenticationError("Authentication required.")

    try:
        payload = decode_token(credentials.credentials)
    except jwt.PyJWTError as exc:
        raise AuthenticationError("Invalid or expired session. Please log in again.") from exc

    if payload.get("type") != TokenType.ACCESS.value:
        raise AuthenticationError("Invalid or expired session. Please log in again.")

    # A token without `sid` predates session-bound access tokens. It is
    # refused rather than trusted until expiry; the frontend answers the 401
    # with one silent refresh, which issues a token that has one.
    user_id = _uuid_claim(payload, "sub")
    session_family_id = _uuid_claim(payload, "sid")

    # A signature check alone would keep honoring a token for its whole
    # lifetime after its session was revoked (logout, logout-all, a password
    # change, refresh-token reuse). Its family must still have a live row.
    if not await SessionRepository(db).family_has_active_session(session_family_id, user_id):
        raise AuthenticationError("Invalid or expired session. Please log in again.")

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired session. Please log in again.")

    return user
