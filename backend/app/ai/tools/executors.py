"""Executors for the eight allowlisted AI tools. Every function here takes
the authenticated `user_id` from its caller (see app.ai.tools.registry -
NEVER from a tool argument) and does nothing but call the same
service/repository functions the regular REST endpoints already use. There
is no second, divergent calculation path for any number an executor
returns, and none of these functions ever builds a raw SQL string or
accepts an AI-generated query expression.
"""

import uuid
from datetime import UTC, date, datetime, time, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.tools.calculations import safe_percent_change, safe_percent_of
from app.ai.tools.period_resolution import resolve_period, validate_custom_range
from app.ai.tools.schemas import (
    AccountBalancesArgs,
    AccountBalancesResult,
    BudgetStatusArgs,
    BudgetStatusResult,
    CategorySpendingArgs,
    CategorySpendingResult,
    ComparePeriodsArgs,
    ComparePeriodsResult,
    MonthlySpendingArgs,
    MonthlySpendingResult,
    PeriodTotals,
    RecurringExpensesArgs,
    RecurringExpensesResult,
    SavingsGoalsArgs,
    SavingsGoalsResult,
    TransactionsArgs,
    TransactionsResult,
    TransactionSummary,
)
from app.models.transaction import TransactionType
from app.repositories.account_repository import AccountRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.transaction_repository import TransactionFilters, TransactionRepository
from app.repositories.user_settings_repository import UserSettingsRepository
from app.services import (
    account_service,
    analytics_service,
    budget_service,
    category_service,
    savings_goal_service,
    transaction_service,
)
from app.services.account_service import calculate_net_worth


async def _get_base_currency(db: AsyncSession, user_id: uuid.UUID) -> str:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    return settings.currency if settings is not None else "INR"


def _inclusive_end_date(date_to_exclusive: datetime) -> date:
    return (date_to_exclusive - timedelta(days=1)).date()


async def _monthly_income_and_expense(
    txn_repo: TransactionRepository,
    user_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    currency: str,
) -> tuple[int, int]:
    """(total_income_minor, total_expense_minor) for [date_from, date_to) -
    transfers are excluded by construction (sum_income_and_expense_by_month
    only ever groups INCOME/EXPENSE rows)."""
    rows = await txn_repo.sum_income_and_expense_by_month(
        user_id, date_from=date_from, date_to=date_to, currency=currency
    )
    total_income_minor = sum(amount for _period, t, amount in rows if t == TransactionType.INCOME)
    total_expense_minor = sum(amount for _period, t, amount in rows if t == TransactionType.EXPENSE)
    return total_income_minor, total_expense_minor


async def execute_get_monthly_spending(
    db: AsyncSession, *, user_id: uuid.UUID, args: MonthlySpendingArgs
) -> MonthlySpendingResult:
    date_from, date_to, label = resolve_period(args.period, now=datetime.now(UTC))
    currency = await _get_base_currency(db, user_id)
    txn_repo = TransactionRepository(db)

    total_income_minor, total_expense_minor = await _monthly_income_and_expense(
        txn_repo, user_id, date_from=date_from, date_to=date_to, currency=currency
    )
    net_minor = total_income_minor - total_expense_minor

    return MonthlySpendingResult(
        period_label=label,
        date_from=date_from.date(),
        date_to=_inclusive_end_date(date_to),
        currency=currency,
        total_income_minor=total_income_minor,
        total_expense_minor=total_expense_minor,
        net_minor=net_minor,
        savings_rate_percent=safe_percent_of(net_minor, total_income_minor),
    )


async def execute_get_category_spending(
    db: AsyncSession, *, user_id: uuid.UUID, args: CategorySpendingArgs
) -> CategorySpendingResult:
    date_from, date_to, label = resolve_period(args.period, now=datetime.now(UTC))
    currency = await _get_base_currency(db, user_id)
    txn_repo = TransactionRepository(db)

    breakdown = await analytics_service.build_category_breakdown(
        db, txn_repo, user_id, date_from, date_to, currency
    )
    return CategorySpendingResult(
        period_label=label,
        date_from=date_from.date(),
        date_to=_inclusive_end_date(date_to),
        currency=currency,
        total_expense_minor=breakdown.total_expense_minor,
        categories=breakdown.items,
    )


async def execute_get_transactions(
    db: AsyncSession, *, user_id: uuid.UUID, args: TransactionsArgs
) -> TransactionsResult:
    date_from = datetime.combine(args.date_from, time.min, tzinfo=UTC) if args.date_from else None
    date_to = datetime.combine(args.date_to, time.max, tzinfo=UTC) if args.date_to else None

    filters = TransactionFilters(
        category_id=args.category_id,
        type=args.type,
        date_from=date_from,
        date_to=date_to,
        limit=args.limit,
        offset=0,
        sort_by="occurred_at",
        sort_dir="desc",
    )
    transactions, total = await transaction_service.list_transactions(
        db, user_id=user_id, filters=filters
    )

    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    categories_by_id = {c.id: c for c in categories}

    summaries = [
        TransactionSummary(
            id=t.id,
            occurred_at=t.occurred_at,
            type=t.type,
            amount_minor=t.amount_minor,
            currency=t.currency,
            category_name=category_service.display_name(
                categories_by_id.get(t.category_id) if t.category_id is not None else None
            ),
            merchant=t.merchant,
            description=t.description,
        )
        for t in transactions
    ]
    return TransactionsResult(
        total_matching=total,
        returned_count=len(summaries),
        limit=args.limit,
        transactions=summaries,
    )


async def execute_get_budget_status(
    db: AsyncSession, *, user_id: uuid.UUID, args: BudgetStatusArgs
) -> BudgetStatusResult:
    items = await budget_service.list_budget_items(db, user_id=user_id)
    currency = await _get_base_currency(db, user_id)
    return BudgetStatusResult(currency=currency, items=items)


async def execute_get_savings_goals(
    db: AsyncSession, *, user_id: uuid.UUID, args: SavingsGoalsArgs
) -> SavingsGoalsResult:
    goals = await savings_goal_service.list_savings_goals(db, user_id=user_id)
    return SavingsGoalsResult(goals=goals)


async def execute_get_recurring_expenses(
    db: AsyncSession, *, user_id: uuid.UUID, args: RecurringExpensesArgs
) -> RecurringExpensesResult:
    date_from, date_to, label = resolve_period(args.period, now=datetime.now(UTC))
    currency = await _get_base_currency(db, user_id)
    txn_repo = TransactionRepository(db)

    total_expense_minor = await txn_repo.sum_expense_in_range(
        user_id, date_from=date_from, date_to=date_to, currency=currency
    )
    breakdown = await analytics_service.build_recurring_expense_breakdown(
        db, txn_repo, user_id, date_from, date_to, currency, total_expense_minor
    )
    return RecurringExpensesResult(
        period_label=label,
        currency=currency,
        items=breakdown.items,
        total_scheduled_monthly_minor=breakdown.total_scheduled_monthly_minor,
        total_actual_paid_minor=breakdown.total_actual_paid_minor,
        recurring_share_of_expense_percent=breakdown.recurring_share_of_expense_percent,
    )


async def execute_get_account_balances(
    db: AsyncSession, *, user_id: uuid.UUID, args: AccountBalancesArgs
) -> AccountBalancesResult:
    currency = await _get_base_currency(db, user_id)

    accounts_read = await account_service.list_accounts(db, user_id=user_id, include_inactive=False)
    same_currency_read = [a for a in accounts_read if a.currency == currency]
    excluded = len(accounts_read) - len(same_currency_read)

    # A second, cheap query for the ORM rows calculate_net_worth expects -
    # reuses the one canonical net-worth formula (app.services.account_service)
    # rather than re-deriving assets-minus-liabilities here.
    orm_accounts = await AccountRepository(db).list_for_user(user_id, include_inactive=False)
    same_currency_orm = [a for a in orm_accounts if a.currency == currency]
    net_worth = calculate_net_worth(same_currency_orm)

    return AccountBalancesResult(
        currency=currency,
        accounts=same_currency_read,
        total_assets_minor=net_worth.total_assets_minor,
        total_liabilities_minor=net_worth.total_liabilities_minor,
        net_worth_minor=net_worth.net_worth_minor,
        excluded_other_currency_accounts=excluded,
    )


async def _period_totals(
    txn_repo: TransactionRepository,
    user_id: uuid.UUID,
    *,
    date_from: datetime,
    date_to: datetime,
    currency: str,
    label: str,
) -> PeriodTotals:
    total_income_minor, total_expense_minor = await _monthly_income_and_expense(
        txn_repo, user_id, date_from=date_from, date_to=date_to, currency=currency
    )
    return PeriodTotals(
        label=label,
        date_from=date_from.date(),
        date_to=_inclusive_end_date(date_to),
        total_income_minor=total_income_minor,
        total_expense_minor=total_expense_minor,
        net_minor=total_income_minor - total_expense_minor,
    )


def _resolve_side(
    *,
    now: datetime,
    period: str | None,
    date_from_raw: date | None,
    date_to_raw: date | None,
) -> tuple[datetime, datetime, str]:
    if date_from_raw is not None:
        assert date_to_raw is not None  # enforced by ComparePeriodsArgs' validator
        date_from = datetime.combine(date_from_raw, time.min, tzinfo=UTC)
        date_to = datetime.combine(date_to_raw + timedelta(days=1), time.min, tzinfo=UTC)
        validate_custom_range(date_from, date_to)
        label = f"{date_from_raw.isoformat()} to {date_to_raw.isoformat()}"
        return date_from, date_to, label
    return resolve_period(period, now=now)


async def execute_compare_periods(
    db: AsyncSession, *, user_id: uuid.UUID, args: ComparePeriodsArgs
) -> ComparePeriodsResult:
    now = datetime.now(UTC)
    currency = await _get_base_currency(db, user_id)
    txn_repo = TransactionRepository(db)

    date_from_a, date_to_a, label_a = _resolve_side(
        now=now, period=args.period_a, date_from_raw=args.date_from_a, date_to_raw=args.date_to_a
    )
    date_from_b, date_to_b, label_b = _resolve_side(
        now=now, period=args.period_b, date_from_raw=args.date_from_b, date_to_raw=args.date_to_b
    )

    period_a = await _period_totals(
        txn_repo,
        user_id,
        date_from=date_from_a,
        date_to=date_to_a,
        currency=currency,
        label=label_a,
    )
    period_b = await _period_totals(
        txn_repo,
        user_id,
        date_from=date_from_b,
        date_to=date_to_b,
        currency=currency,
        label=label_b,
    )

    return ComparePeriodsResult(
        currency=currency,
        period_a=period_a,
        period_b=period_b,
        expense_diff_minor=period_a.total_expense_minor - period_b.total_expense_minor,
        expense_percent_change=safe_percent_change(
            period_b.total_expense_minor, period_a.total_expense_minor
        ),
        income_diff_minor=period_a.total_income_minor - period_b.total_income_minor,
        income_percent_change=safe_percent_change(
            period_b.total_income_minor, period_a.total_income_minor
        ),
        net_diff_minor=period_a.net_minor - period_b.net_minor,
    )
