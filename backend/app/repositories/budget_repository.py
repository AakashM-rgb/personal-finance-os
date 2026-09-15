"""Data access for budgets. Every query is scoped to a user_id (via the
one-per-user `Budget` container) so a caller can never read or mutate
another user's budget item by guessing an id."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.budget import Budget, BudgetItem


class BudgetRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def get_or_create_for_user(self, user_id: uuid.UUID) -> Budget:
        result = await self._db.execute(select(Budget).where(Budget.user_id == user_id))
        budget = result.scalar_one_or_none()
        if budget is None:
            budget = Budget(user_id=user_id)
            self._db.add(budget)
            await self._db.flush()
        return budget


class BudgetItemRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(self, user_id: uuid.UUID) -> list[BudgetItem]:
        stmt = (
            select(BudgetItem)
            .join(Budget, BudgetItem.budget_id == Budget.id)
            .where(Budget.user_id == user_id)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(self, item_id: uuid.UUID, user_id: uuid.UUID) -> BudgetItem | None:
        stmt = (
            select(BudgetItem)
            .join(Budget, BudgetItem.budget_id == Budget.id)
            .where(BudgetItem.id == item_id, Budget.user_id == user_id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_category_for_user(
        self, category_id: uuid.UUID, user_id: uuid.UUID
    ) -> BudgetItem | None:
        stmt = (
            select(BudgetItem)
            .join(Budget, BudgetItem.budget_id == Budget.id)
            .where(BudgetItem.category_id == category_id, Budget.user_id == user_id)
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, item: BudgetItem) -> None:
        self._db.add(item)

    async def flush(self) -> None:
        await self._db.flush()

    async def delete(self, item: BudgetItem) -> None:
        await self._db.delete(item)
