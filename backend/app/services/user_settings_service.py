"""Per-user settings business logic: read the current user's settings and
apply partial updates. `ai_enabled` changes take effect immediately - the AI
tool layer (app.services.ai_assistant_service) re-reads this same row on
every request rather than caching it, so there is no separate place that
also needs to be told the setting changed."""

import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.user_settings import UserSettingsRead, UserSettingsUpdate


async def get_settings(db: AsyncSession, *, user_id: uuid.UUID) -> UserSettingsRead:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    if settings is None:
        # Every user gets a UserSettings row at registration
        # (see UserRepository.create) - this should be unreachable in practice.
        raise NotFoundError("Settings not found.")
    return UserSettingsRead.model_validate(settings)


async def update_settings(
    db: AsyncSession, *, user_id: uuid.UUID, data: UserSettingsUpdate
) -> UserSettingsRead:
    repo = UserSettingsRepository(db)
    settings = await repo.get_by_user_id(user_id)
    if settings is None:
        raise NotFoundError("Settings not found.")

    if data.currency is not None:
        settings.currency = data.currency
    if data.theme is not None:
        settings.theme = data.theme
    if data.ai_enabled is not None:
        settings.ai_enabled = data.ai_enabled

    await repo.flush()
    return UserSettingsRead.model_validate(settings)
