"""Data access for subscriptions. Subscription itself has no user_id
column (see app.models.subscription) - every ownership-scoped query joins
to RecurringTransaction.user_id instead, the same pattern
BudgetItemRepository uses to scope through its Budget parent."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recurring_transaction import RecurringTransaction
from app.models.subscription import Subscription


class SubscriptionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(
        self, user_id: uuid.UUID
    ) -> list[tuple[Subscription, RecurringTransaction]]:
        stmt = (
            select(Subscription, RecurringTransaction)
            .join(
                RecurringTransaction,
                Subscription.recurring_transaction_id == RecurringTransaction.id,
            )
            .where(RecurringTransaction.user_id == user_id)
            .order_by(Subscription.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return [(row[0], row[1]) for row in result.all()]

    async def get_by_id_for_user(
        self, subscription_id: uuid.UUID, user_id: uuid.UUID
    ) -> tuple[Subscription, RecurringTransaction] | None:
        stmt = (
            select(Subscription, RecurringTransaction)
            .join(
                RecurringTransaction,
                Subscription.recurring_transaction_id == RecurringTransaction.id,
            )
            .where(Subscription.id == subscription_id, RecurringTransaction.user_id == user_id)
        )
        result = await self._db.execute(stmt)
        row = result.first()
        return (row[0], row[1]) if row is not None else None

    def add(self, subscription: Subscription) -> None:
        self._db.add(subscription)

    async def flush(self) -> None:
        await self._db.flush()
