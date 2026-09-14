"""FastAPI dependency for extracting and validating the current authenticated user.

This is the single choke point every protected route depends on - never parse
or trust the Authorization header anywhere else.
"""

import uuid

import jwt
from fastapi import Depends, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.errors import AuthenticationError
from app.core.security import TokenType, decode_token
from app.models.user import User
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

    try:
        user_id = uuid.UUID(payload["sub"])
    except (KeyError, ValueError) as exc:
        raise AuthenticationError("Invalid or expired session. Please log in again.") from exc

    user = await UserRepository(db).get_by_id(user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired session. Please log in again.")

    return user
