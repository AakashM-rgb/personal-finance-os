"""Data access for merchant category rules. Every query is scoped to a
user_id so a caller can never read, update, or delete another user's rule
by guessing an id."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.merchant_category_rule import MerchantCategoryRule


class MerchantCategoryRuleRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(self, user_id: uuid.UUID) -> list[MerchantCategoryRule]:
        stmt = (
            select(MerchantCategoryRule)
            .where(MerchantCategoryRule.user_id == user_id)
            .order_by(MerchantCategoryRule.merchant_key.asc())
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(
        self, rule_id: uuid.UUID, user_id: uuid.UUID
    ) -> MerchantCategoryRule | None:
        stmt = select(MerchantCategoryRule).where(
            MerchantCategoryRule.id == rule_id, MerchantCategoryRule.user_id == user_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_user_and_merchant_key(
        self, user_id: uuid.UUID, merchant_key: str
    ) -> MerchantCategoryRule | None:
        stmt = select(MerchantCategoryRule).where(
            MerchantCategoryRule.user_id == user_id,
            MerchantCategoryRule.merchant_key == merchant_key,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, rule: MerchantCategoryRule) -> None:
        self._db.add(rule)

    async def flush(self) -> None:
        await self._db.flush()

    async def delete(self, rule: MerchantCategoryRule) -> None:
        await self._db.delete(rule)
