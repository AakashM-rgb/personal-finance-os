"""Data access for sync runs - an audit/observability record of one attempt
to pull transactions for a linked account (see app.models.sync_run). Scoped
by linked_account_id, never by user_id directly: callers already own the
linked_account_id after an ownership check upstream (see
app.services.sync_service), the same convention
TransactionRepository.get_latest_occurrence_date_for_recurring uses for
recurring_transaction_id."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sync_run import SyncRun


class SyncRunRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_linked_account(self, linked_account_id: uuid.UUID) -> list[SyncRun]:
        stmt = (
            select(SyncRun)
            .where(SyncRun.linked_account_id == linked_account_id)
            .order_by(SyncRun.started_at.desc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    def add(self, sync_run: SyncRun) -> None:
        self._db.add(sync_run)

    async def flush(self) -> None:
        await self._db.flush()
