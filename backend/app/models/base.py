"""Shared mixins for ORM models."""

import enum
import uuid
from datetime import UTC, datetime
from typing import TypeVar

from sqlalchemy import DateTime, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

_E = TypeVar("_E", bound=enum.Enum)


def str_enum_column(enum_cls: type[_E], *, name: str, length: int = 20) -> SAEnum:
    """A VARCHAR-backed enum column that stores each member's `.value`
    ("bank_account") rather than SQLAlchemy's default of its `.name`
    ("BANK_ACCOUNT") - without this, any raw SQL (check constraints,
    reports, ad hoc queries) written against the lowercase values a client
    actually sends would silently never match what's in the database."""
    return SAEnum(
        enum_cls,
        name=name,
        native_enum=False,
        length=length,
        values_callable=lambda cls: [member.value for member in cls],
    )


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
