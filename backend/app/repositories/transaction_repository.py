"""Data access for transactions. Every query is scoped to a user_id so a
caller can never read or mutate another user's transaction by guessing an id."""

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Literal

from sqlalchemy import ColumnExpressionArgument, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionType

SortField = Literal["occurred_at", "amount_minor", "created_at"]
SortDirection = Literal["asc", "desc"]


@dataclass
class TransactionFilters:
    search: str | None = None
    category_id: uuid.UUID | None = None
    account_id: uuid.UUID | None = None
    type: TransactionType | None = None
    date_from: datetime | None = None
    date_to: datetime | None = None
    amount_min: int | None = None
    amount_max: int | None = None
    is_recurring: bool | None = None
    tags: list[str] = field(default_factory=list)
    sort_by: SortField = "occurred_at"
    sort_dir: SortDirection = "desc"
    limit: int = 50
    offset: int = 0


class TransactionRepository:
    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    def _base_query(
        self, user_id: uuid.UUID, filters: TransactionFilters
    ) -> list[ColumnExpressionArgument[bool]]:
        conditions: list[ColumnExpressionArgument[bool]] = [Transaction.user_id == user_id]

        if filters.search:
            pattern = f"%{filters.search.lower()}%"
            conditions.append(
                or_(
                    func.lower(Transaction.description).like(pattern),
                    func.lower(Transaction.merchant).like(pattern),
                    func.lower(Transaction.notes).like(pattern),
                )
            )
        if filters.category_id is not None:
            conditions.append(Transaction.category_id == filters.category_id)
        if filters.account_id is not None:
            conditions.append(
                or_(
                    Transaction.account_id == filters.account_id,
                    Transaction.transfer_account_id == filters.account_id,
                )
            )
        if filters.type is not None:
            conditions.append(Transaction.type == filters.type)
        if filters.date_from is not None:
            conditions.append(Transaction.occurred_at >= filters.date_from)
        if filters.date_to is not None:
            conditions.append(Transaction.occurred_at <= filters.date_to)
        if filters.amount_min is not None:
            conditions.append(Transaction.amount_minor >= filters.amount_min)
        if filters.amount_max is not None:
            conditions.append(Transaction.amount_minor <= filters.amount_max)
        if filters.is_recurring is not None:
            conditions.append(Transaction.is_recurring == filters.is_recurring)
        if filters.tags:
            # overlap: matches if the transaction has ANY of the requested tags
            conditions.append(Transaction.tags.overlap(filters.tags))

        return conditions

    async def list_for_user(
        self, user_id: uuid.UUID, filters: TransactionFilters
    ) -> tuple[list[Transaction], int]:
        conditions = self._base_query(user_id, filters)

        count_stmt = select(func.count()).select_from(Transaction).where(*conditions)
        total = (await self._db.execute(count_stmt)).scalar_one()

        sort_column = getattr(Transaction, filters.sort_by)
        order = sort_column.asc() if filters.sort_dir == "asc" else sort_column.desc()

        stmt = (
            select(Transaction)
            .where(*conditions)
            .order_by(order, Transaction.id.desc())
            .limit(filters.limit)
            .offset(filters.offset)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all()), total

    async def get_by_id_for_user(
        self, transaction_id: uuid.UUID, user_id: uuid.UUID
    ) -> Transaction | None:
        stmt = select(Transaction).where(
            Transaction.id == transaction_id, Transaction.user_id == user_id
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_idempotency_key(
        self, user_id: uuid.UUID, idempotency_key: str
    ) -> Transaction | None:
        stmt = select(Transaction).where(
            Transaction.user_id == user_id, Transaction.idempotency_key == idempotency_key
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, transaction: Transaction) -> None:
        self._db.add(transaction)

    async def flush(self) -> None:
        await self._db.flush()

    async def delete(self, transaction: Transaction) -> None:
        await self._db.delete(transaction)
