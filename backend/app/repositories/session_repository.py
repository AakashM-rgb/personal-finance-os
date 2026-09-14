"""Data access for refresh-token sessions.

Every read/write here is explicitly scoped to a user_id where applicable, so a
caller can never revoke or read another user's session by guessing a session id.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session


class SessionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def create(
        self,
        *,
        session_id: uuid.UUID,
        user_id: uuid.UUID,
        refresh_token_hash: str,
        expires_at: datetime,
        user_agent: str | None,
        ip_address: str | None,
    ) -> Session:
        session = Session(
            id=session_id,
            user_id=user_id,
            refresh_token_hash=refresh_token_hash,
            expires_at=expires_at,
            user_agent=user_agent,
            ip_address=ip_address,
        )
        self._db.add(session)
        await self._db.flush()
        return session

    async def get_by_id(self, session_id: uuid.UUID) -> Session | None:
        return await self._db.get(Session, session_id)

    async def get_active_by_user(self, user_id: uuid.UUID) -> list[Session]:
        now = datetime.now(UTC)
        result = await self._db.execute(
            select(Session).where(
                Session.user_id == user_id,
                Session.revoked_at.is_(None),
                Session.expires_at > now,
            )
        )
        return list(result.scalars().all())

    async def get_by_id_for_user(self, session_id: uuid.UUID, user_id: uuid.UUID) -> Session | None:
        result = await self._db.execute(
            select(Session).where(Session.id == session_id, Session.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def revoke(self, session: Session) -> None:
        session.revoked_at = datetime.now(UTC)
        await self._db.flush()

    async def revoke_all_for_user(self, user_id: uuid.UUID) -> None:
        await self._db.execute(
            update(Session)
            .where(Session.user_id == user_id, Session.revoked_at.is_(None))
            .values(revoked_at=datetime.now(UTC))
        )
