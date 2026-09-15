"""Data access for transactions. Every query is scoped to a user_id so a
caller can never read or mutate another user's transaction by guessing an id."""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
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

    async def list_in_range(
        self,
        user_id: uuid.UUID,
        *,
        date_from: datetime,
        date_to: datetime,
        currency: str,
        exclude_transfer: bool = True,
    ) -> list[Transaction]:
        """Fetches every matching row so the caller can derive several
        aggregates (totals, category breakdown, daily series, ...) from one
        query instead of issuing a separate SQL aggregate for each - cheap
        at personal-finance transaction volumes and backed by the existing
        (user_id, occurred_at) index."""
        conditions: list[ColumnExpressionArgument[bool]] = [
            Transaction.user_id == user_id,
            Transaction.occurred_at >= date_from,
            Transaction.occurred_at < date_to,
            Transaction.currency == currency,
        ]
        if exclude_transfer:
            conditions.append(Transaction.type != TransactionType.TRANSFER)
        stmt = select(Transaction).where(*conditions)
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def sum_expense_in_range(
        self,
        user_id: uuid.UUID,
        *,
        date_from: datetime,
        date_to: datetime,
        currency: str,
        category_id: uuid.UUID | None = None,
    ) -> int:
        """A single SQL SUM - used where we only need one number and don't
        need the individual rows (the dashboard's previous-month total, and
        a single budget item's current-month spend)."""
        conditions: list[ColumnExpressionArgument[bool]] = [
            Transaction.user_id == user_id,
            Transaction.type == TransactionType.EXPENSE,
            Transaction.occurred_at >= date_from,
            Transaction.occurred_at < date_to,
            Transaction.currency == currency,
        ]
        if category_id is not None:
            conditions.append(Transaction.category_id == category_id)
        stmt = select(func.coalesce(func.sum(Transaction.amount_minor), 0)).where(*conditions)
        result = await self._db.execute(stmt)
        return int(result.scalar_one())

    async def list_recent(
        self, user_id: uuid.UUID, *, limit: int, currency: str | None = None
    ) -> list[Transaction]:
        conditions: list[ColumnExpressionArgument[bool]] = [Transaction.user_id == user_id]
        if currency is not None:
            conditions.append(Transaction.currency == currency)
        stmt = (
            select(Transaction)
            .where(*conditions)
            .order_by(Transaction.occurred_at.desc(), Transaction.id.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_occurrence_date_for_recurring(
        self, recurring_transaction_id: uuid.UUID
    ) -> date | None:
        """The date of the most recently generated occurrence for this
        recurring transaction, or None if it has never generated one yet -
        the basis for computing the next occurrence date idempotently (see
        app.services.recurring_transaction_service). Not scoped by user_id:
        callers already own the recurring_transaction_id after an ownership
        check upstream, and this id uniquely identifies one user's schedule."""
        stmt = select(func.max(Transaction.occurred_at)).where(
            Transaction.recurring_transaction_id == recurring_transaction_id
        )
        result = await self._db.execute(stmt)
        latest = result.scalar_one_or_none()
        return latest.date() if latest is not None else None

    async def list_occurrence_dates_for_recurring(
        self, recurring_transaction_id: uuid.UUID
    ) -> list[date]:
        """Every real generated billing date for this recurring transaction
        - the evidence a subscription's unused-detection rule is judged
        against (see app.services.subscription_calculations). Not scoped by
        user_id, for the same reason as get_latest_occurrence_date_for_recurring."""
        stmt = select(Transaction.occurred_at).where(
            Transaction.recurring_transaction_id == recurring_transaction_id
        )
        result = await self._db.execute(stmt)
        return [occurred_at.date() for occurred_at in result.scalars().all()]

    async def list_category_activity_dates(
        self,
        user_id: uuid.UUID,
        *,
        category_id: uuid.UUID,
        exclude_recurring_transaction_id: uuid.UUID,
        date_from: datetime,
    ) -> list[date]:
        """Every OTHER transaction's date in this category since `date_from`
        - "other" meaning anything but this specific subscription's own
        generated charges (a different recurring transaction's charges in
        the same category, or a manual transaction, both count as real
        category activity). The evidence side of the unused-subscription
        check that isn't the subscription's own billing history."""
        stmt = select(Transaction.occurred_at).where(
            Transaction.user_id == user_id,
            Transaction.category_id == category_id,
            Transaction.occurred_at >= date_from,
            or_(
                Transaction.recurring_transaction_id.is_(None),
                Transaction.recurring_transaction_id != exclude_recurring_transaction_id,
            ),
        )
        result = await self._db.execute(stmt)
        return [occurred_at.date() for occurred_at in result.scalars().all()]

    async def sum_expense_by_period(
        self,
        user_id: uuid.UUID,
        *,
        date_from: datetime,
        date_to: datetime,
        currency: str,
        granularity: Literal["day", "month"],
    ) -> list[tuple[date, int]]:
        """Real expense totals grouped by calendar day or month, computed
        entirely in the database (date_trunc + SUM + GROUP BY) rather than
        fetching every row into Python - the basis for the analytics
        spending-over-time and daily-spending charts. Periods with zero
        expense are simply absent from the result; callers zero-fill them
        against app.services.analytics_calculations.generate_day_periods /
        generate_month_periods."""
        # The 3-arg form pins the truncation to UTC explicitly - Postgres's
        # 2-arg date_trunc truncates in the *session's* TimeZone setting
        # (e.g. Asia/Calcutta, UTC+5:30), which can shift a period's date
        # by a full day once the truncated timestamp is converted back to
        # UTC for Python's .date() - a real bug caught by testing this
        # against a non-UTC-configured database, not a style preference.
        period = func.date_trunc(granularity, Transaction.occurred_at, "UTC").label("period")
        stmt = (
            select(period, func.sum(Transaction.amount_minor))
            .where(
                Transaction.user_id == user_id,
                Transaction.type == TransactionType.EXPENSE,
                Transaction.occurred_at >= date_from,
                Transaction.occurred_at < date_to,
                Transaction.currency == currency,
            )
            .group_by(period)
            .order_by(period)
        )
        result = await self._db.execute(stmt)
        return [(period_start.date(), int(total)) for period_start, total in result.all()]

    async def sum_income_and_expense_by_month(
        self, user_id: uuid.UUID, *, date_from: datetime, date_to: datetime, currency: str
    ) -> list[tuple[date, TransactionType, int]]:
        """Real income and expense totals grouped by calendar month and
        type, computed in the database - transfers are excluded by the
        type filter, not by post-processing. The basis for both the
        income-vs-expense and savings-trend analytics (a savings-trend
        point is just this month's income minus its expense)."""
        # Pinned to UTC explicitly - see sum_expense_by_period's comment.
        period = func.date_trunc("month", Transaction.occurred_at, "UTC").label("period")
        stmt = (
            select(period, Transaction.type, func.sum(Transaction.amount_minor))
            .where(
                Transaction.user_id == user_id,
                Transaction.type.in_([TransactionType.INCOME, TransactionType.EXPENSE]),
                Transaction.occurred_at >= date_from,
                Transaction.occurred_at < date_to,
                Transaction.currency == currency,
            )
            .group_by(period, Transaction.type)
            .order_by(period)
        )
        result = await self._db.execute(stmt)
        return [
            (period_start.date(), txn_type, int(total))
            for period_start, txn_type, total in result.all()
        ]

    async def sum_expense_by_category(
        self, user_id: uuid.UUID, *, date_from: datetime, date_to: datetime, currency: str
    ) -> list[tuple[uuid.UUID | None, int]]:
        """Real expense totals grouped by category (NULL included, for
        uncategorized spending) - the basis for the analytics category
        breakdown."""
        stmt = (
            select(Transaction.category_id, func.sum(Transaction.amount_minor))
            .where(
                Transaction.user_id == user_id,
                Transaction.type == TransactionType.EXPENSE,
                Transaction.occurred_at >= date_from,
                Transaction.occurred_at < date_to,
                Transaction.currency == currency,
            )
            .group_by(Transaction.category_id)
        )
        result = await self._db.execute(stmt)
        return [(category_id, int(total)) for category_id, total in result.all()]

    async def sum_by_recurring_transaction_ids(
        self,
        user_id: uuid.UUID,
        *,
        recurring_transaction_ids: list[uuid.UUID],
        date_from: datetime,
        date_to: datetime,
        currency: str,
    ) -> dict[uuid.UUID, int]:
        """Real amounts actually paid, grouped by recurring_transaction_id,
        for the analytics recurring-expense breakdown - one query for every
        schedule at once rather than one query per item. Returns only the
        ids that have at least one matching transaction; callers treat a
        missing id as 0 (nothing paid yet in this range)."""
        if not recurring_transaction_ids:
            return {}
        stmt = (
            select(Transaction.recurring_transaction_id, func.sum(Transaction.amount_minor))
            .where(
                Transaction.user_id == user_id,
                Transaction.recurring_transaction_id.in_(recurring_transaction_ids),
                Transaction.occurred_at >= date_from,
                Transaction.occurred_at < date_to,
                Transaction.currency == currency,
            )
            .group_by(Transaction.recurring_transaction_id)
        )
        result = await self._db.execute(stmt)
        return {recurring_id: int(total) for recurring_id, total in result.all() if recurring_id}

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
