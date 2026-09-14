"""Transaction endpoints. Every route is authenticated and scoped to the
caller's own transactions via app.services.transaction_service - the
frontend never supplies a user_id, only the resource ids it wants to act on."""

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Header, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.transaction import TransactionType
from app.models.user import User
from app.repositories.transaction_repository import SortDirection, SortField, TransactionFilters
from app.schemas.transaction import QuickAddParseRequest, TransactionCreate, TransactionUpdate
from app.services import transaction_service

router = APIRouter(prefix="/transactions", tags=["transactions"])

_MAX_PAGE_SIZE = 200


@router.get("", response_model=None)
async def list_transactions(
    q: str | None = None,
    category_id: UUID | None = None,
    account_id: UUID | None = None,
    type: TransactionType | None = None,  # noqa: A002 - matches the public query param name
    date_from: datetime | None = None,
    date_to: datetime | None = None,
    amount_min: int | None = None,
    amount_max: int | None = None,
    is_recurring: bool | None = None,
    tags: list[str] = Query(default_factory=list),
    sort_by: SortField = "occurred_at",
    sort_dir: SortDirection = "desc",
    limit: int = Query(default=50, ge=1, le=_MAX_PAGE_SIZE),
    offset: int = Query(default=0, ge=0),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    filters = TransactionFilters(
        search=q,
        category_id=category_id,
        account_id=account_id,
        type=type,
        date_from=date_from,
        date_to=date_to,
        amount_min=amount_min,
        amount_max=amount_max,
        is_recurring=is_recurring,
        tags=tags,
        sort_by=sort_by,
        sort_dir=sort_dir,
        limit=limit,
        offset=offset,
    )
    transactions, total = await transaction_service.list_transactions(
        db, user_id=current_user.id, filters=filters
    )
    return {
        "data": transactions,
        "error": None,
        "meta": {"count": total, "limit": limit, "offset": offset},
    }


@router.post("", response_model=None, status_code=201)
async def create_transaction(
    body: TransactionCreate,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    transaction = await transaction_service.create_transaction(
        db, user_id=current_user.id, data=body, idempotency_key=idempotency_key
    )
    await db.commit()
    return {"data": transaction, "error": None, "meta": None}


@router.post("/quick-add/parse", response_model=None)
async def quick_add_parse(
    body: QuickAddParseRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    result = await transaction_service.quick_add_parse(db, user_id=current_user.id, text=body.text)
    return {"data": result, "error": None, "meta": None}


@router.get("/{transaction_id}", response_model=None)
async def get_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    transaction = await transaction_service.get_transaction(
        db, user_id=current_user.id, transaction_id=transaction_id
    )
    return {"data": transaction, "error": None, "meta": None}


@router.put("/{transaction_id}", response_model=None)
async def update_transaction(
    transaction_id: UUID,
    body: TransactionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    transaction = await transaction_service.update_transaction(
        db, user_id=current_user.id, transaction_id=transaction_id, data=body
    )
    await db.commit()
    return {"data": transaction, "error": None, "meta": None}


@router.delete("/{transaction_id}", response_model=None, status_code=200)
async def delete_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await transaction_service.delete_transaction(
        db, user_id=current_user.id, transaction_id=transaction_id
    )
    await db.commit()
    return {"data": {"success": True}, "error": None, "meta": None}


@router.post("/{transaction_id}/duplicate", response_model=None, status_code=201)
async def duplicate_transaction(
    transaction_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    transaction = await transaction_service.duplicate_transaction(
        db, user_id=current_user.id, transaction_id=transaction_id
    )
    await db.commit()
    return {"data": transaction, "error": None, "meta": None}
