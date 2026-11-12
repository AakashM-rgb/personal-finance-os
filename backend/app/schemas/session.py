"""Read schema for a user's own active login sessions/devices.

There is no `is_current` field. An access token's `sid` claim names a
session FAMILY (see app.models.session), not the row a request came from, and
guessing from IP/user-agent would be misleading (multiple sessions can share
both), so this is deliberately left out rather than faked."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class SessionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    user_agent: str | None
    ip_address: str | None
    created_at: datetime
    expires_at: datetime
