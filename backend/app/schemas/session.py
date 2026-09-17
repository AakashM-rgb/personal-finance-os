"""Read schema for a user's own active login sessions/devices.

There is no `is_current` field: an access token carries only `sub`/`type`/
`iat`/`exp` (see app.core.security.create_access_token) - no session id - so
the backend has no reliable way to know which row issued the request that's
asking. Guessing from IP/user-agent would be misleading (multiple sessions
can share both), so this is deliberately left out rather than faked."""

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
