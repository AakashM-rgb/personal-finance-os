"""Budget endpoints. Every route is authenticated and scoped to the
caller's own budgets via app.services.budget_service - the frontend never
supplies a user_id, only the resource ids it wants to act on.

Route order matters: the literal "/suggestions" path must be registered
before "/{item_id}" so it is never swallowed by the path-parameter route.
"""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.budget import BudgetItemCreate, BudgetItemUpdate
from app.services import budget_service

router = APIRouter(prefix="/budgets", tags=["budgets"])


@router.get("", response_model=None)
async def list_budgets(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    items = await budget_service.list_budget_items(db, user_id=current_user.id)
    return {"data": items, "error": None, "meta": {"count": len(items)}}


@router.get("/suggestions", response_model=None)
async def get_budget_suggestions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    suggestions = await budget_service.list_budget_suggestions(db, user_id=current_user.id)
    return {"data": suggestions, "error": None, "meta": {"count": len(suggestions)}}


@router.post("", response_model=None, status_code=201)
async def create_budget(
    body: BudgetItemCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    item = await budget_service.create_budget_item(db, user_id=current_user.id, data=body)
    await db.commit()
    return {"data": item, "error": None, "meta": None}


@router.get("/{item_id}", response_model=None)
async def get_budget(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    item = await budget_service.get_budget_item(db, user_id=current_user.id, item_id=item_id)
    return {"data": item, "error": None, "meta": None}


@router.put("/{item_id}", response_model=None)
async def update_budget(
    item_id: UUID,
    body: BudgetItemUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    item = await budget_service.update_budget_item(
        db, user_id=current_user.id, item_id=item_id, data=body
    )
    await db.commit()
    return {"data": item, "error": None, "meta": None}


@router.delete("/{item_id}", response_model=None, status_code=200)
async def delete_budget(
    item_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await budget_service.delete_budget_item(db, user_id=current_user.id, item_id=item_id)
    await db.commit()
    return {"data": {"success": True}, "error": None, "meta": None}
