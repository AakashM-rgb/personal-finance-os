"""Savings goal endpoints. Every route is authenticated and scoped to the
caller's own goals via app.services.savings_goal_service."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.savings_goal import SavingsGoalCreate, SavingsGoalUpdate
from app.services import savings_goal_service

router = APIRouter(prefix="/goals", tags=["goals"])


@router.get("", response_model=None)
async def list_goals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    goals = await savings_goal_service.list_savings_goals(db, user_id=current_user.id)
    return {"data": goals, "error": None, "meta": {"count": len(goals)}}


@router.post("", response_model=None, status_code=201)
async def create_goal(
    body: SavingsGoalCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    goal = await savings_goal_service.create_savings_goal(db, user_id=current_user.id, data=body)
    await db.commit()
    return {"data": goal, "error": None, "meta": None}


@router.get("/{goal_id}", response_model=None)
async def get_goal(
    goal_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    goal = await savings_goal_service.get_savings_goal(
        db, user_id=current_user.id, goal_id=goal_id
    )
    return {"data": goal, "error": None, "meta": None}


@router.put("/{goal_id}", response_model=None)
async def update_goal(
    goal_id: UUID,
    body: SavingsGoalUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    goal = await savings_goal_service.update_savings_goal(
        db, user_id=current_user.id, goal_id=goal_id, data=body
    )
    await db.commit()
    return {"data": goal, "error": None, "meta": None}


@router.delete("/{goal_id}", response_model=None, status_code=200)
async def delete_goal(
    goal_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await savings_goal_service.delete_savings_goal(db, user_id=current_user.id, goal_id=goal_id)
    await db.commit()
    return {"data": {"success": True}, "error": None, "meta": None}
