"""Per-user application settings.

`ai_enabled` is enforced inside the AI tool layer itself (once the AI module
exists) - not just used to hide UI - so disabling it actually blocks the
assistant's access to the user's data.

`ai_categorization_enabled` is a SEPARATE opt-in for background AI-assisted
transaction categorization during automatic sync (see app.services.sync_service)
- deliberately not reused from `ai_enabled`, which only governs the
conversational assistant/NL search. Defaults to False (an external-provider
data flow must be opt-in, never on by default) and is enforced the same
way: inside the sync pipeline itself, read fresh from this row on every
sync run, never just hidden in the UI.
"""

import uuid
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class UserSettings(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "user_settings"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    currency: Mapped[str] = mapped_column(String(3), nullable=False, default="INR")
    theme: Mapped[str] = mapped_column(String(10), nullable=False, default="system")
    ai_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    ai_categorization_enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    notification_preferences: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)

    user: Mapped["User"] = relationship(back_populates="settings")
