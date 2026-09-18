"""Sync run model - an audit/observability record of one attempt to pull
transactions for a `LinkedAccount` (see app.models.linked_account).

This table exists purely to record what happened (for the user-visible sync
history and for debugging), not to drive behavior - idempotency of the
transactions a run produces is enforced on `Transaction` itself (its
`idempotency_key` unique constraint), never here. Deleting a linked account
also removes its run history (`ondelete="CASCADE"`), since a run with no
link left to describe has no remaining meaning.

No ingestion/orchestration logic lives on this model - that belongs to a
later phase's service layer.
"""

import enum
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.base import TimestampMixin, UUIDPrimaryKeyMixin, str_enum_column


class SyncRunStatus(enum.StrEnum):
    SUCCESS = "success"
    PARTIAL = "partial"
    FAILED = "failed"


class SyncRun(UUIDPrimaryKeyMixin, TimestampMixin, Base):
    __tablename__ = "sync_runs"

    linked_account_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("linked_accounts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[SyncRunStatus] = mapped_column(
        str_enum_column(SyncRunStatus, name="sync_run_status"),
        nullable=False,
    )

    transactions_fetched: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transactions_created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    transactions_skipped_duplicate: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    error_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
