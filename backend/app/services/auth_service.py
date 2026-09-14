"""Authentication business logic: registration, login, session/refresh management.

Refresh tokens are opaque strings of the form "<session_id>.<secret>". The
session_id allows O(1) lookup of the session row; only a hash of the secret is
ever persisted (see app.core.security), so a leaked database cannot be used to
forge a session, and revoking the row immediately invalidates the token.
"""

import uuid
from datetime import UTC, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_settings
from app.core.errors import AuthenticationError, ConflictError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
    verify_refresh_token,
)
from app.models.session import Session
from app.models.user import User
from app.repositories.session_repository import SessionRepository
from app.repositories.user_repository import UserRepository
from app.services.audit_service import log_action

settings = get_settings()

_GENERIC_LOGIN_ERROR = "Incorrect email or password."


class AuthResult:
    def __init__(self, user: User, access_token: str, raw_refresh_token: str) -> None:
        self.user = user
        self.access_token = access_token
        self.raw_refresh_token = raw_refresh_token


def _encode_refresh_token(session_id: uuid.UUID, secret: str) -> str:
    return f"{session_id}.{secret}"


def _decode_refresh_token(raw_token: str) -> tuple[uuid.UUID, str]:
    try:
        session_id_str, secret = raw_token.split(".", 1)
        return uuid.UUID(session_id_str), secret
    except ValueError as exc:
        raise AuthenticationError("Invalid or expired session. Please log in again.") from exc


async def _issue_session(
    db: AsyncSession,
    *,
    user: User,
    user_agent: str | None,
    ip_address: str | None,
) -> AuthResult:
    session_repo = SessionRepository(db)

    session_id = uuid.uuid4()
    secret = generate_refresh_token()
    expires_at = datetime.now(UTC) + timedelta(days=settings.refresh_token_expire_days)

    await session_repo.create(
        session_id=session_id,
        user_id=user.id,
        refresh_token_hash=hash_refresh_token(secret),
        expires_at=expires_at,
        user_agent=user_agent,
        ip_address=ip_address,
    )

    access_token = create_access_token(user.id)
    raw_refresh_token = _encode_refresh_token(session_id, secret)
    return AuthResult(user=user, access_token=access_token, raw_refresh_token=raw_refresh_token)


async def register(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    full_name: str,
    user_agent: str | None,
    ip_address: str | None,
) -> AuthResult:
    user_repo = UserRepository(db)

    existing = await user_repo.get_by_email(email)
    if existing is not None:
        # Deliberately generic: do not reveal via a different message that the
        # email is already registered on this specific field vs. elsewhere.
        raise ConflictError("An account with this email already exists.")

    user = await user_repo.create(
        email=email, password_hash=hash_password(password), full_name=full_name
    )
    await log_action(
        db,
        user_id=user.id,
        action="user.register",
        entity_type="user",
        entity_id=str(user.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return await _issue_session(db, user=user, user_agent=user_agent, ip_address=ip_address)


async def login(
    db: AsyncSession,
    *,
    email: str,
    password: str,
    user_agent: str | None,
    ip_address: str | None,
) -> AuthResult:
    user_repo = UserRepository(db)
    user = await user_repo.get_by_email(email)

    if user is None or not verify_password(password, user.password_hash):
        await log_action(
            db,
            user_id=user.id if user else None,
            action="user.login_failed",
            ip_address=ip_address,
            user_agent=user_agent,
        )
        raise AuthenticationError(_GENERIC_LOGIN_ERROR)

    if not user.is_active:
        raise AuthenticationError(_GENERIC_LOGIN_ERROR)

    await log_action(
        db,
        user_id=user.id,
        action="user.login",
        entity_type="user",
        entity_id=str(user.id),
        ip_address=ip_address,
        user_agent=user_agent,
    )
    return await _issue_session(db, user=user, user_agent=user_agent, ip_address=ip_address)


async def refresh_session(
    db: AsyncSession,
    *,
    raw_refresh_token: str,
    user_agent: str | None,
    ip_address: str | None,
) -> AuthResult:
    session_id, secret = _decode_refresh_token(raw_refresh_token)

    session_repo = SessionRepository(db)
    session: Session | None = await session_repo.get_by_id(session_id)

    invalid = (
        session is None
        or not session.is_active
        or not verify_refresh_token(secret, session.refresh_token_hash)
    )
    if invalid:
        raise AuthenticationError("Invalid or expired session. Please log in again.")

    assert session is not None  # narrowed by `invalid` check above
    user_repo = UserRepository(db)
    user = await user_repo.get_by_id(session.user_id)
    if user is None or not user.is_active:
        raise AuthenticationError("Invalid or expired session. Please log in again.")

    # Rotate: revoke the used token and issue a fresh one, so a stolen-and-replayed
    # refresh token stops working the moment the legitimate client rotates it.
    await session_repo.revoke(session)
    return await _issue_session(db, user=user, user_agent=user_agent, ip_address=ip_address)


async def logout(db: AsyncSession, *, raw_refresh_token: str) -> None:
    try:
        session_id, _secret = _decode_refresh_token(raw_refresh_token)
    except AuthenticationError:
        return  # Already unusable; nothing to revoke.

    session_repo = SessionRepository(db)
    session = await session_repo.get_by_id(session_id)
    if session is not None and session.revoked_at is None:
        await session_repo.revoke(session)


async def logout_all(db: AsyncSession, *, user_id: uuid.UUID) -> None:
    session_repo = SessionRepository(db)
    await session_repo.revoke_all_for_user(user_id)
    await log_action(
        db,
        user_id=user_id,
        action="user.logout_all",
        entity_type="user",
        entity_id=str(user_id),
    )
