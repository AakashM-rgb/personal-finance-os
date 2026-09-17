"""Data access for per-user settings.

Queried directly rather than via `User.settings` - the current-user
dependency loads a bare `User` row, and traversing an unloaded relationship
on it later would trigger an async-incompatible lazy load.
"""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user_settings import UserSettings


class UserSettingsRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_by_user_id(self, user_id: uuid.UUID) -> UserSettings | None:
        result = await self._db.execute(
            select(UserSettings).where(UserSettings.user_id == user_id)
        )
        return result.scalar_one_or_none()

    async def flush(self) -> None:
        await self._db.flush()
