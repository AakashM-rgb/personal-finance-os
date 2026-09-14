"""Data access for accounts. Every query is scoped to a user_id so a caller
can never read or mutate another user's account by guessing an id."""

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.account import Account


class AccountRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def list_for_user(self, user_id: uuid.UUID, *, include_inactive: bool) -> list[Account]:
        stmt = (
            select(Account)
            .where(Account.user_id == user_id)
            .options(selectinload(Account.credit_card))
            .order_by(Account.created_at.asc())
        )
        if not include_inactive:
            stmt = stmt.where(Account.is_active.is_(True))
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_by_id_for_user(self, account_id: uuid.UUID, user_id: uuid.UUID) -> Account | None:
        stmt = (
            select(Account)
            .where(Account.id == account_id, Account.user_id == user_id)
            .options(selectinload(Account.credit_card))
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, account: Account) -> None:
        self._db.add(account)

    async def flush(self) -> None:
        await self._db.flush()
