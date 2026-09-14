"""Password hashing and JWT issuance/verification.

Passwords are hashed with Argon2id (never stored in plaintext, never logged).
Access tokens are short-lived JWTs; refresh tokens are opaque random strings
persisted (hashed) in the `sessions` table so they can be individually revoked.
"""

import secrets
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any
from uuid import UUID

import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()

_pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")


def hash_password(plain_password: str) -> str:
    return _pwd_context.hash(plain_password)


def verify_password(plain_password: str, password_hash: str) -> bool:
    return _pwd_context.verify(plain_password, password_hash)


class TokenType(StrEnum):
    ACCESS = "access"
    EMAIL_VERIFY = "email_verify"
    PASSWORD_RESET = "password_reset"


def create_access_token(user_id: UUID) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": TokenType.ACCESS.value,
        "iat": now,
        "exp": now + timedelta(minutes=settings.access_token_expire_minutes),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def create_purpose_token(user_id: UUID, token_type: TokenType, expires_in: timedelta) -> str:
    """Single-use-by-convention token for email verification / password reset flows."""
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": token_type.value,
        "jti": secrets.token_urlsafe(16),
        "iat": now,
        "exp": now + expires_in,
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """Raises jwt.PyJWTError (or subclasses) on invalid/expired tokens."""
    return jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])


def generate_refresh_token() -> str:
    """Opaque high-entropy refresh token. The raw value is only ever returned to
    the client once, in an httpOnly cookie; only its hash is persisted."""
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str) -> str:
    """Refresh tokens are hashed at rest like passwords, not encrypted/plaintext,
    so a database read alone can never yield a usable session token."""
    return _pwd_context.hash(raw_token)


def verify_refresh_token(raw_token: str, token_hash: str) -> bool:
    return _pwd_context.verify(raw_token, token_hash)
