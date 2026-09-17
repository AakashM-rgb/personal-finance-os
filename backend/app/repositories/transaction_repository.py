"""Data access for transactions. Every query is scoped to a user_id so a
caller can never read or mutate another user's transaction by guessing an id."""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal

from sqlalchemy import ColumnExpressionArgument, case, false, func, or_, select
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
    # Predefined, server-computed filters used by the natural-language
    # search feature (app.search) - never populated from raw AI/user text
    # directly. `days_of_week` uses Postgres's own EXTRACT(DOW) convention
    # (0=Sunday..6=Saturday); `recurring_transaction_ids` is the caller's
    # already-resolved set of a user's OWN subscription schedule ids (see
    # app.search.query_builder), not an arbitrary id list.
    days_of_week: list[int] | None = None
    recurring_transaction_ids: list[uuid.UUID] | None = None
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
        if filters.days_of_week:
            # Pinned to UTC explicitly, same reasoning as sum_expense_by_period's
            # date_trunc calls: Postgres's EXTRACT(DOW FROM timestamptz) uses the
            # session's TimeZone setting otherwise, which can shift a timestamp
            # near midnight onto the wrong day of week.
            day_of_week = func.extract("dow", func.timezone("UTC", Transaction.occurred_at))
            conditions.append(day_of_week.in_(filters.days_of_week))
        if filters.recurring_transaction_ids is not None:
            # An explicitly empty list (e.g. a user with zero subscriptions)
            # must match nothing - never silently fall back to "no filter".
            conditions.append(
                Transaction.recurring_transaction_id.in_(filters.recurring_transaction_ids)
                if filters.recurring_transaction_ids
                else false()
            )

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

    async def sum_by_type_and_period(
        self,
        user_id: uuid.UUID,
        *,
        transaction_type: TransactionType,
        date_from: datetime,
        date_to: datetime,
        currency: str,
        granularity: Literal["day", "month"],
    ) -> list[tuple[date, int]]:
        """Real totals of one transaction type grouped by calendar day or
        month, computed entirely in the database (date_trunc + SUM +
        GROUP BY) rather than fetching every row into Python - the basis
        for the analytics spending-over-time/daily-spending charts and
        the reports module's income/expense-over-time series. Periods
        with zero activity are simply absent from the result; callers
        zero-fill them against
        app.services.analytics_calculations.generate_day_periods /
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
                Transaction.type == transaction_type,
                Transaction.occurred_at >= date_from,
                Transaction.occurred_at < date_to,
                Transaction.currency == currency,
            )
            .group_by(period)
            .order_by(period)
        )
        result = await self._db.execute(stmt)
        return [(period_start.date(), int(total)) for period_start, total in result.all()]

    async def sum_expense_by_period(
        self,
        user_id: uuid.UUID,
        *,
        date_from: datetime,
        date_to: datetime,
        currency: str,
        granularity: Literal["day", "month"],
    ) -> list[tuple[date, int]]:
        """Thin wrapper over sum_by_type_and_period for EXPENSE - kept as
        its own method so existing callers (analytics_service) never had
        to change signatures when this was generalized."""
        return await self.sum_by_type_and_period(
            user_id,
            transaction_type=TransactionType.EXPENSE,
            date_from=date_from,
            date_to=date_to,
            currency=currency,
            granularity=granularity,
        )

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

    async def sum_and_count_by_category(
        self,
        user_id: uuid.UUID,
        *,
        transaction_type: TransactionType,
        date_from: datetime,
        date_to: datetime,
        currency: str,
    ) -> list[tuple[uuid.UUID | None, int, int]]:
        """Real totals AND transaction counts of one transaction type,
        grouped by category (NULL included, for uncategorized activity) -
        the basis for the reports module's category/income breakdowns.
        One query returns both figures rather than a separate COUNT query
        repeating the same GROUP BY."""
        stmt = (
            select(
                Transaction.category_id,
                func.sum(Transaction.amount_minor),
                func.count(),
            )
            .where(
                Transaction.user_id == user_id,
                Transaction.type == transaction_type,
                Transaction.occurred_at >= date_from,
                Transaction.occurred_at < date_to,
                Transaction.currency == currency,
            )
            .group_by(Transaction.category_id)
        )
        result = await self._db.execute(stmt)
        return [(category_id, int(total), int(count)) for category_id, total, count in result.all()]

    async def sum_by_recurring_flag(
        self, user_id: uuid.UUID, *, date_from: datetime, date_to: datetime, currency: str
    ) -> dict[bool, int]:
        """Real expense totals split by whether each transaction is
        recurring-linked or not (Transaction.is_recurring) - the basis for
        the expense report's recurring-vs-non-recurring breakdown. Keys
        missing from the result mean zero for that side, same convention
        as every other sum_* method here."""
        stmt = (
            select(Transaction.is_recurring, func.sum(Transaction.amount_minor))
            .where(
                Transaction.user_id == user_id,
                Transaction.type == TransactionType.EXPENSE,
                Transaction.occurred_at >= date_from,
                Transaction.occurred_at < date_to,
                Transaction.currency == currency,
            )
            .group_by(Transaction.is_recurring)
        )
        result = await self._db.execute(stmt)
        return {is_recurring: int(total) for is_recurring, total in result.all()}

    async def list_top_by_amount(
        self,
        user_id: uuid.UUID,
        *,
        transaction_type: TransactionType,
        date_from: datetime,
        date_to: datetime,
        currency: str,
        limit: int,
    ) -> list[Transaction]:
        """The `limit` largest transactions of one type in a range,
        ordered by amount descending - a single indexed range scan plus
        an ORDER BY/LIMIT the database itself applies, never a full fetch
        sorted in Python. The basis for the income/expense reports'
        "largest transactions" figures."""
        stmt = (
            select(Transaction)
            .where(
                Transaction.user_id == user_id,
                Transaction.type == transaction_type,
                Transaction.occurred_at >= date_from,
                Transaction.occurred_at < date_to,
                Transaction.currency == currency,
            )
            .order_by(Transaction.amount_minor.desc())
            .limit(limit)
        )
        result = await self._db.execute(stmt)
        return list(result.scalars().all())

    async def get_latest_occurrence_dates_for_recurring_ids(
        self, recurring_transaction_ids: list[uuid.UUID]
    ) -> dict[uuid.UUID, date]:
        """The most recently generated occurrence date for every id in
        `recurring_transaction_ids`, in one query - the bulk counterpart
        of get_latest_occurrence_date_for_recurring, used by the
        financial calendar to project each active recurring transaction's
        next due date without querying once per schedule (N+1)."""
        if not recurring_transaction_ids:
            return {}
        stmt = (
            select(Transaction.recurring_transaction_id, func.max(Transaction.occurred_at))
            .where(Transaction.recurring_transaction_id.in_(recurring_transaction_ids))
            .group_by(Transaction.recurring_transaction_id)
        )
        result = await self._db.execute(stmt)
        return {
            recurring_id: latest.date() for recurring_id, latest in result.all() if recurring_id
        }

    async def sum_balance_delta_by_month_for_accounts(
        self,
        user_id: uuid.UUID,
        *,
        account_ids: list[uuid.UUID],
        date_from: datetime,
        date_to: datetime,
        currency: str,
    ) -> list[tuple[date, uuid.UUID, int]]:
        """For every account in `account_ids`, the signed delta real
        transactions applied to that account's balance_minor, grouped by
        calendar month - mirrors app.services.transaction_service.
        _apply_balance_effect exactly (income +amount on its account,
        expense -amount on its account, transfer -amount on `account_id`
        and +amount on `transfer_account_id`), so a caller reconstructing a
        historical balance can never silently diverge from how balances are
        actually mutated. Unlike sum_income_and_expense_by_month, a transfer
        is NOT excluded here - restricted instead to `account_ids` on
        purpose, since a transfer crossing into/out of one of those accounts
        genuinely changes ITS balance and must be counted; a transfer
        between two accounts outside `account_ids` correctly contributes
        nothing. One query total (a UNION ALL of the transaction's two
        possible legs, grouped once), never one query per account."""
        if not account_ids:
            return []

        period = func.date_trunc("month", Transaction.occurred_at, "UTC").label("period")
        base_conditions: list[ColumnExpressionArgument[bool]] = [
            Transaction.user_id == user_id,
            Transaction.occurred_at >= date_from,
            Transaction.occurred_at < date_to,
            Transaction.currency == currency,
        ]

        # Leg 1: the effect on `account_id` - the account every transaction
        # type has (source account for a transfer, the only account for
        # income/expense).
        primary = select(
            period,
            Transaction.account_id.label("account_id"),
            func.sum(
                case(
                    (Transaction.type == TransactionType.INCOME, Transaction.amount_minor),
                    (
                        Transaction.type.in_([TransactionType.EXPENSE, TransactionType.TRANSFER]),
                        -Transaction.amount_minor,
                    ),
                    else_=0,
                )
            ).label("delta"),
        ).where(*base_conditions, Transaction.account_id.in_(account_ids))
        primary = primary.group_by(period, Transaction.account_id)

        # Leg 2: a transfer's destination account, which gains what the
        # source lost.
        secondary = select(
            period,
            Transaction.transfer_account_id.label("account_id"),
            func.sum(Transaction.amount_minor).label("delta"),
        ).where(
            *base_conditions,
            Transaction.type == TransactionType.TRANSFER,
            Transaction.transfer_account_id.in_(account_ids),
        )
        secondary = secondary.group_by(period, Transaction.transfer_account_id)

        combined = primary.union_all(secondary).subquery()
        stmt = select(
            combined.c.period, combined.c.account_id, func.sum(combined.c.delta)
        ).group_by(combined.c.period, combined.c.account_id)

        result = await self._db.execute(stmt)
        return [
            (period_start.date(), account_id, int(total))
            for period_start, account_id, total in result.all()
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

    async def get_by_recurring_occurrence(
        self, recurring_transaction_id: uuid.UUID, occurred_at: datetime
    ) -> Transaction | None:
        stmt = select(Transaction).where(
            Transaction.recurring_transaction_id == recurring_transaction_id,
            Transaction.occurred_at == occurred_at,
        )
        result = await self._db.execute(stmt)
        return result.scalar_one_or_none()

    def add(self, transaction: Transaction) -> None:
        self._db.add(transaction)

    async def flush(self) -> None:
        await self._db.flush()

    async def delete(self, transaction: Transaction) -> None:
        await self._db.delete(transaction)
