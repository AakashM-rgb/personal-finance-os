"""User-facing schemas (never expose password_hash or internal IDs beyond the UUID)."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    email: str
    full_name: str
    is_active: bool
    email_verified_at: datetime | None
    created_at: datetime
