"""Shared mixins for ORM models."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, func
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column


class UUIDPrimaryKeyMixin:
    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    # onupdate is a Python-side callable (not a server function) so the new
    # value is known before the UPDATE is sent and never needs to be
    # re-fetched from the DB afterward - a server-side onupdate=func.now()
    # marks the attribute "expired", and refreshing an expired attribute via
    # plain attribute access triggers a synchronous reload that crashes
    # (MissingGreenlet) under the async engine.
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
