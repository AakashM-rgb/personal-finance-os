"""Subscription endpoints. Every route is authenticated and scoped to the
caller's own subscriptions via app.services.subscription_service."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.subscription import SubscriptionCreate, SubscriptionUpdate
from app.services import subscription_service

router = APIRouter(prefix="/subscriptions", tags=["subscriptions"])


@router.get("", response_model=None)
async def list_subscriptions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    items = await subscription_service.list_subscriptions(db, user_id=current_user.id)
    return {"data": items, "error": None, "meta": {"count": len(items)}}


@router.post("", response_model=None, status_code=201)
async def create_subscription(
    body: SubscriptionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    item = await subscription_service.create_subscription(db, user_id=current_user.id, data=body)
    await db.commit()
    return {"data": item, "error": None, "meta": None}


@router.get("/{subscription_id}", response_model=None)
async def get_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    item = await subscription_service.get_subscription(
        db, user_id=current_user.id, subscription_id=subscription_id
    )
    return {"data": item, "error": None, "meta": None}


@router.put("/{subscription_id}", response_model=None)
async def update_subscription(
    subscription_id: UUID,
    body: SubscriptionUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    item = await subscription_service.update_subscription(
        db, user_id=current_user.id, subscription_id=subscription_id, data=body
    )
    await db.commit()
    return {"data": item, "error": None, "meta": None}


@router.delete("/{subscription_id}", response_model=None, status_code=200)
async def deactivate_subscription(
    subscription_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await subscription_service.deactivate_subscription(
        db, user_id=current_user.id, subscription_id=subscription_id
    )
    await db.commit()
    return {"data": {"success": True}, "error": None, "meta": None}
