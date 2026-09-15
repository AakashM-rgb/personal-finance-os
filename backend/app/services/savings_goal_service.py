"""Savings goal business logic: ownership enforcement and the progress /
pacing figures shown to the user - every number here is computed from the
authenticated caller's own stored goal (never another user's, never a
caller-supplied user_id), and nothing is randomly generated.
"""

import uuid
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.models.savings_goal import SavingsGoal
from app.repositories.savings_goal_repository import SavingsGoalRepository
from app.schemas.savings_goal import SavingsGoalCreate, SavingsGoalRead, SavingsGoalUpdate
from app.services.savings_goal_calculations import (
    calculate_days_remaining,
    calculate_progress_percent,
    calculate_remaining_minor,
    calculate_required_savings,
)


def _to_read(goal: SavingsGoal) -> SavingsGoalRead:
    today = datetime.now(UTC).date()
    remaining_minor = calculate_remaining_minor(goal.current_amount_minor, goal.target_amount_minor)
    days_remaining = calculate_days_remaining(goal.target_date, today)
    required_monthly_minor, required_weekly_minor = calculate_required_savings(
        remaining_minor, days_remaining
    )

    return SavingsGoalRead(
        id=goal.id,
        name=goal.name,
        target_amount_minor=goal.target_amount_minor,
        current_amount_minor=goal.current_amount_minor,
        currency=goal.currency,
        target_date=goal.target_date,
        progress_percent=calculate_progress_percent(
            goal.current_amount_minor, goal.target_amount_minor
        ),
        remaining_minor=remaining_minor,
        is_completed=remaining_minor <= 0,
        days_remaining=days_remaining,
        required_monthly_savings_minor=required_monthly_minor,
        required_weekly_savings_minor=required_weekly_minor,
        created_at=goal.created_at,
        updated_at=goal.updated_at,
    )


async def list_savings_goals(db: AsyncSession, *, user_id: uuid.UUID) -> list[SavingsGoalRead]:
    goals = await SavingsGoalRepository(db).list_for_user(user_id)
    return [_to_read(goal) for goal in goals]


async def get_savings_goal(
    db: AsyncSession, *, user_id: uuid.UUID, goal_id: uuid.UUID
) -> SavingsGoalRead:
    goal = await SavingsGoalRepository(db).get_by_id_for_user(goal_id, user_id)
    if goal is None:
        raise NotFoundError("Savings goal not found.")
    return _to_read(goal)


async def create_savings_goal(
    db: AsyncSession, *, user_id: uuid.UUID, data: SavingsGoalCreate
) -> SavingsGoalRead:
    goal = SavingsGoal(
        user_id=user_id,
        name=data.name,
        target_amount_minor=data.target_amount_minor,
        current_amount_minor=data.current_amount_minor,
        currency=data.currency,
        target_date=data.target_date,
    )
    repo = SavingsGoalRepository(db)
    repo.add(goal)
    await repo.flush()
    return _to_read(goal)


async def update_savings_goal(
    db: AsyncSession, *, user_id: uuid.UUID, goal_id: uuid.UUID, data: SavingsGoalUpdate
) -> SavingsGoalRead:
    repo = SavingsGoalRepository(db)
    goal = await repo.get_by_id_for_user(goal_id, user_id)
    if goal is None:
        raise NotFoundError("Savings goal not found.")

    if data.name is not None:
        goal.name = data.name
    if data.target_amount_minor is not None:
        goal.target_amount_minor = data.target_amount_minor
    if data.current_amount_minor is not None:
        goal.current_amount_minor = data.current_amount_minor
    if data.currency is not None:
        goal.currency = data.currency
    if data.target_date is not None:
        goal.target_date = data.target_date

    # Re-validated here (not just at create) because a partial update can
    # change target_amount_minor or current_amount_minor independently of
    # each other - only the merged, final state can be checked.
    if goal.current_amount_minor > goal.target_amount_minor:
        raise ValidationAppError(
            "current_amount_minor must not exceed target_amount_minor",
            field_errors={"current_amount_minor": "cannot exceed the target amount"},
        )

    await repo.flush()
    return _to_read(goal)


async def delete_savings_goal(db: AsyncSession, *, user_id: uuid.UUID, goal_id: uuid.UUID) -> None:
    repo = SavingsGoalRepository(db)
    goal = await repo.get_by_id_for_user(goal_id, user_id)
    if goal is None:
        raise NotFoundError("Savings goal not found.")
    await repo.delete(goal)
    await repo.flush()
