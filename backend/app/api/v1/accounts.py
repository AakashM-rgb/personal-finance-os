"""Account endpoints. Every route is authenticated and scoped to the caller's
own accounts via app.services.account_service."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.account import AccountCreate, AccountUpdate
from app.services import account_service

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", response_model=None)
async def list_accounts(
    include_inactive: bool = False,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    accounts = await account_service.list_accounts(
        db, user_id=current_user.id, include_inactive=include_inactive
    )
    return {"data": accounts, "error": None, "meta": {"count": len(accounts)}}


@router.post("", response_model=None, status_code=201)
async def create_account(
    body: AccountCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    account = await account_service.create_account(db, user_id=current_user.id, data=body)
    await db.commit()
    return {"data": account, "error": None, "meta": None}


@router.get("/{account_id}", response_model=None)
async def get_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    account = await account_service.get_account(db, user_id=current_user.id, account_id=account_id)
    return {"data": account, "error": None, "meta": None}


@router.put("/{account_id}", response_model=None)
async def update_account(
    account_id: UUID,
    body: AccountUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    account = await account_service.update_account(
        db, user_id=current_user.id, account_id=account_id, data=body
    )
    await db.commit()
    return {"data": account, "error": None, "meta": None}


@router.delete("/{account_id}", response_model=None, status_code=200)
async def archive_account(
    account_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await account_service.archive_account(db, user_id=current_user.id, account_id=account_id)
    await db.commit()
    return {"data": {"success": True}, "error": None, "meta": None}
