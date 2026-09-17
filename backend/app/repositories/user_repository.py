"""Data access for users. No business logic here - see app.services.auth_service."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User
from app.models.user_settings import UserSettings


class UserRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_id(self, user_id: uuid.UUID) -> User | None:
        return await self._db.get(User, user_id)

    async def get_by_email(self, email: str) -> User | None:
        result = await self._db.execute(select(User).where(User.email == email.lower()))
        return result.scalar_one_or_none()

    async def create(self, *, email: str, password_hash: str, full_name: str) -> User:
        user = User(email=email.lower(), password_hash=password_hash, full_name=full_name)
        user.settings = UserSettings()
        self._db.add(user)
        await self._db.flush()
        return user

    async def list_all_ids(self) -> list[uuid.UUID]:
        """Every user's id, active or not - used only by
        app.services.notification_service's system-wide generation sweep,
        which runs each user's detectors independently rather than a single
        cross-user query (unlike the recurring-transaction sweep, there is
        no single underlying table this could batch across, since budgets/
        goals/subscriptions/recurring/transactions are five different
        sources)."""
        result = await self._db.execute(select(User.id))
        return list(result.scalars().all())
