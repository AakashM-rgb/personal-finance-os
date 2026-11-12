"""Merchant category rule endpoints. Every route is authenticated and
scoped to the caller's own rules via app.services.merchant_rule_service -
a rule id alone is never enough to read, update, or delete one."""

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.dependencies import get_current_user
from app.core.database import get_db
from app.models.user import User
from app.schemas.merchant_category_rule import (
    MerchantCategoryRuleCreate,
    MerchantCategoryRuleUpdate,
)
from app.services import merchant_rule_service

router = APIRouter(prefix="/merchant-rules", tags=["merchant-rules"])


@router.get("", response_model=None)
async def list_merchant_rules(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rules = await merchant_rule_service.list_rules(db, user_id=current_user.id)
    return {"data": rules, "error": None, "meta": {"count": len(rules)}}


@router.post("", response_model=None, status_code=201)
async def create_merchant_rule(
    body: MerchantCategoryRuleCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rule = await merchant_rule_service.upsert_rule(
        db, user_id=current_user.id, raw_merchant=body.merchant, category_id=body.category_id
    )
    await db.commit()
    return {"data": rule, "error": None, "meta": None}


@router.get("/{rule_id}", response_model=None)
async def get_merchant_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rule = await merchant_rule_service.get_rule(db, user_id=current_user.id, rule_id=rule_id)
    return {"data": rule, "error": None, "meta": None}


@router.patch("/{rule_id}", response_model=None)
async def update_merchant_rule(
    rule_id: UUID,
    body: MerchantCategoryRuleUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    rule = await merchant_rule_service.update_rule_category(
        db, user_id=current_user.id, rule_id=rule_id, category_id=body.category_id
    )
    await db.commit()
    return {"data": rule, "error": None, "meta": None}


@router.delete("/{rule_id}", response_model=None, status_code=200)
async def delete_merchant_rule(
    rule_id: UUID,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
) -> dict:
    await merchant_rule_service.delete_rule(db, user_id=current_user.id, rule_id=rule_id)
    await db.commit()
    return {"data": {"success": True}, "error": None, "meta": None}
