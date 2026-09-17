"""Notification request/response schemas.

`NotificationRead` never exposes `dedupe_key` - it is a purely internal
idempotency mechanism (see app.models.notification), not something a
client needs or should be able to see or set.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict

from app.models.notification import NotificationCategory


class NotificationRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category: NotificationCategory
    title: str
    message: str
    reference_type: str | None
    reference_id: str | None
    action_url: str | None
    is_read: bool
    created_at: datetime


class UnreadCountRead(BaseModel):
    unread_count: int


class MarkReadResult(BaseModel):
    updated_count: int
