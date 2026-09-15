"""Data access for savings goals. Every query is scoped to a user_id so a
caller can never read or mutate another user's goal by guessing an id."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.savings_goal import SavingsGoal


class SavingsGoalRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(self, user_id: uuid.UUID) -> list[SavingsGoal]:
        stmt = (
            select(SavingsGoal)
            .where(SavingsGoal.user_id == user_id)
            .order_by(SavingsGoal.created_at.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self, goal_id: uuid.UUID, user_id: uuid.UUID
    ) -> SavingsGoal | None:
        stmt = select(SavingsGoal).where(SavingsGoal.id == goal_id, SavingsGoal.user_id == user_id)
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, goal: SavingsGoal) -> None:
        self._db.add(goal)

    async def flush(self) -> None:
        await self._db.flush()

    async def delete(self, goal: SavingsGoal) -> None:
        await self._db.delete(goal)
