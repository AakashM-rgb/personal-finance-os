"""Data access for recurring transactions. Every user-facing query is
scoped to a user_id so a caller can never read or mutate another user's
schedule by guessing an id. `list_active_all` is the one exception - it
has no user_id filter, since it exists only for the system-wide
generation sweep in app.jobs.recurring_transaction_generator, never for
a user-facing endpoint."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recurring_transaction import RecurringTransaction


class RecurringTransactionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(self, user_id: uuid.UUID) -> list[RecurringTransaction]:
        stmt = (
            select(RecurringTransaction)
            .where(RecurringTransaction.user_id == user_id)
            .order_by(RecurringTransaction.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_active_for_user(self, user_id: uuid.UUID) -> list[RecurringTransaction]:
        stmt = select(RecurringTransaction).where(
            RecurringTransaction.user_id == user_id,
            RecurringTransaction.is_active.is_(True),
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def list_active_all(self) -> list[RecurringTransaction]:
        stmt = select(RecurringTransaction).where(RecurringTransaction.is_active.is_(True))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self, recurring_id: uuid.UUID, user_id: uuid.UUID
    ) -> RecurringTransaction | None:
        stmt = select(RecurringTransaction).where(
            RecurringTransaction.id == recurring_id, RecurringTransaction.user_id == user_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, recurring: RecurringTransaction) -> None:
        self._db.add(recurring)

    async def flush(self) -> None:
        await self._db.flush()

    async def delete(self, recurring: RecurringTransaction) -> None:
        await self._db.delete(recurring)
