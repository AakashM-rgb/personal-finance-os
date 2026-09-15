"""Recurring transaction endpoints. Every route is authenticated and
scoped to the caller's own schedules via
app.services.recurring_transaction_service. `generate` is a manual
trigger for app.jobs.recurring_transaction_generator - see that module
for why nothing schedules it automatically yet."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.jobs import recurring_transaction_generator
from app.models.user import User
from app.schemas.recurring_transaction import RecurringTransactionCreate, RecurringTransactionUpdate
from app.services import recurring_transaction_service

router = APIRouter(prefix="/recurring-transactions", tags=["recurring-transactions"])


@router.get("", response_model=None)
async def list_recurring_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    items = await recurring_transaction_service.list_recurring_transactions(
        db, user_id=current_user.id
    )
    return {"data": items, "error": None, "meta": {"count": len(items)}}


@router.post("", response_model=None, status_code=201)
async def create_recurring_transaction(
    body: RecurringTransactionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    item = await recurring_transaction_service.create_recurring_transaction(
        db, user_id=current_user.id, data=body
    )
    await db.commit()
    return {"data": item, "error": None, "meta": None}


@router.post("/generate", response_model=None)
async def generate_recurring_transactions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    generated = await recurring_transaction_generator.run_for_user(db, user_id=current_user.id)
    await db.commit()
    return {"data": generated, "error": None, "meta": {"count": len(generated)}}


@router.get("/{recurring_id}", response_model=None)
async def get_recurring_transaction(
    recurring_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    item = await recurring_transaction_service.get_recurring_transaction(
        db, user_id=current_user.id, recurring_id=recurring_id
    )
    return {"data": item, "error": None, "meta": None}


@router.put("/{recurring_id}", response_model=None)
async def update_recurring_transaction(
    recurring_id: UUID,
    body: RecurringTransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    item = await recurring_transaction_service.update_recurring_transaction(
        db, user_id=current_user.id, recurring_id=recurring_id, data=body
    )
    await db.commit()
    return {"data": item, "error": None, "meta": None}


@router.delete("/{recurring_id}", response_model=None, status_code=200)
async def deactivate_recurring_transaction(
    recurring_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await recurring_transaction_service.deactivate_recurring_transaction(
        db, user_id=current_user.id, recurring_id=recurring_id
    )
    await db.commit()
    return {"data": {"success": True}, "error": None, "meta": None}
