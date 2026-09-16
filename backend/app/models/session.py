"""Refresh-token session model - backs revocable login sessions.

The raw refresh token is never persisted, only its hash (see app.core.security),
so a database read alone can never yield a usable session token. Revoking a row
here is what makes "logout from all devices" work server-side; rotation-reuse
detection (app.services.auth_service.refresh_session) revokes every row for a
user the moment an already-revoked token is presented again with a matching
secret - see that function's docstring for why.
"""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin

if TYPE_CHECKING:
    from app.models.user import User


class Session(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sessions"

    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    refresh_token_hash: Mapped[str] = mapped_column(String(255), nullable=False)

    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(64), nullable=True)

    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    user: Mapped["User"] = relationship(back_populates="sessions")

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None and self.expires_at > datetime.now(UTC)
