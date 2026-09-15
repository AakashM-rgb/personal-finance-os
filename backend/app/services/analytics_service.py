"""Analytics business logic: every figure here is computed from the
authenticated caller's own real data via database-side aggregation
(GROUP BY / SUM in SQL - see the sum_* methods on TransactionRepository)
rather than fetching the whole ledger into Python. Nothing is randomly
generated; every number traces to a real, documented calculation in
app.services.analytics_calculations, app.services.subscription_calculations,
or the reused app.services.budget_service - never a second, divergent
implementation of a number that module already owns.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.models.transaction import TransactionType
from app.repositories.category_repository import CategoryRepository
from app.repositories.recurring_transaction_repository import RecurringTransactionRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.analytics import (
    AnalyticsRead,
    AnalyticsRequest,
    CategoryBreakdown,
    CategoryBreakdownItem,
    DailySpending,
    DailySpendingPoint,
    IncomeVsExpense,
    RecurringExpenseBreakdown,
    RecurringExpenseBreakdownItem,
    SavingsTrend,
    SavingsTrendPoint,
    SpendingOverTime,
    SpendingOverTimePoint,
    TrendInfo,
)
from app.services import budget_service, category_service
from app.services.analytics_calculations import (
    Granularity,
    determine_trend,
    generate_day_periods,
    generate_month_periods,
    resolve_date_range,
    resolve_granularity,
)
from app.services.subscription_calculations import calculate_monthly_cost_minor

MonthlyRow = tuple[date, TransactionType, int]


async def _get_base_currency(db: AsyncSession, user_id: uuid.UUID) -> str:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    return settings.currency if settings is not None else "INR"


def _trend_info(amounts: list[int]) -> TrendInfo:
    result = determine_trend(amounts)
    return TrendInfo(direction=result.direction, percent_change=result.percent_change)


async def _build_spending_over_time(
    txn_repo: TransactionRepository,
    user_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
    currency: str,
) -> SpendingOverTime:
    granularity = resolve_granularity(date_from, date_to)
    sums_by_period = dict(
        await txn_repo.sum_expense_by_period(
            user_id,
            date_from=date_from,
            date_to=date_to,
            currency=currency,
            granularity=granularity.value,
        )
    )
    periods = (
        generate_day_periods(date_from, date_to)
        if granularity == Granularity.DAY
        else generate_month_periods(date_from, date_to)
    )
    points = [
        SpendingOverTimePoint(period=p, amount_minor=sums_by_period.get(p, 0)) for p in periods
    ]
    return SpendingOverTime(
        granularity=granularity,
        points=points,
        trend=_trend_info([p.amount_minor for p in points]),
    )


async def _build_category_breakdown(
    db: AsyncSession,
    txn_repo: TransactionRepository,
    user_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
    currency: str,
) -> CategoryBreakdown:
    sums = await txn_repo.sum_expense_by_category(
        user_id, date_from=date_from, date_to=date_to, currency=currency
    )
    total_expense_minor = sum(amount for _category_id, amount in sums)

    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    categories_by_id = {c.id: c for c in categories}

    ranked = sorted(sums, key=lambda kv: kv[1], reverse=True)
    items = [
        CategoryBreakdownItem(
            category_id=category_id,
            name=category_service.display_name(
                categories_by_id.get(category_id) if category_id is not None else None
            ),
            icon=category_service.display_icon(
                categories_by_id.get(category_id) if category_id is not None else None
            ),
            color=category_service.display_color(
                categories_by_id.get(category_id) if category_id is not None else None
            ),
            amount_minor=amount_minor,
            percent=(
                round(amount_minor / total_expense_minor * 100, 1)
                if total_expense_minor > 0
                else 0.0
            ),
        )
        for category_id, amount_minor in ranked
    ]
    return CategoryBreakdown(items=items, total_expense_minor=total_expense_minor)


def _build_income_vs_expense(monthly_rows: list[MonthlyRow]) -> IncomeVsExpense:
    total_income_minor = sum(
        amount for _p, txn_type, amount in monthly_rows if txn_type == TransactionType.INCOME
    )
    total_expense_minor = sum(
        amount for _p, txn_type, amount in monthly_rows if txn_type == TransactionType.EXPENSE
    )
    net_minor = total_income_minor - total_expense_minor
    return IncomeVsExpense(
        total_income_minor=total_income_minor,
        total_expense_minor=total_expense_minor,
        net_minor=net_minor,
        is_spending_more_than_earning=net_minor < 0,
    )


def _build_savings_trend(
    monthly_rows: list[MonthlyRow], date_from: datetime, date_to: datetime
) -> SavingsTrend:
    income_by_period: dict[date, int] = defaultdict(int)
    expense_by_period: dict[date, int] = defaultdict(int)
    for period, txn_type, amount in monthly_rows:
        if txn_type == TransactionType.INCOME:
            income_by_period[period] += amount
        else:
            expense_by_period[period] += amount

    points = []
    for period in generate_month_periods(date_from, date_to):
        income_minor = income_by_period.get(period, 0)
        expense_minor = expense_by_period.get(period, 0)
        savings_minor = income_minor - expense_minor
        savings_rate = round(savings_minor / income_minor * 100, 1) if income_minor > 0 else None
        points.append(
            SavingsTrendPoint(
                period=period,
                income_minor=income_minor,
                expense_minor=expense_minor,
                savings_minor=savings_minor,
                savings_rate=savings_rate,
            )
        )

    return SavingsTrend(points=points, trend=_trend_info([p.savings_minor for p in points]))


async def _build_daily_spending(
    txn_repo: TransactionRepository,
    user_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
    currency: str,
    spending_over_time: SpendingOverTime,
) -> DailySpending:
    if spending_over_time.granularity == Granularity.DAY:
        # Identical to the query spending-over-time already ran for a
        # short range - reuse its result instead of re-querying.
        points = [
            DailySpendingPoint(day=p.period, amount_minor=p.amount_minor)
            for p in spending_over_time.points
        ]
    else:
        sums_by_day = dict(
            await txn_repo.sum_expense_by_period(
                user_id, date_from=date_from, date_to=date_to, currency=currency, granularity="day"
            )
        )
        points = [
            DailySpendingPoint(day=d, amount_minor=sums_by_day.get(d, 0))
            for d in generate_day_periods(date_from, date_to)
        ]

    if not points:
        return DailySpending(points=[], highest_day=None, highest_amount_minor=0)
    highest = max(points, key=lambda p: p.amount_minor)
    return DailySpending(
        points=points, highest_day=highest.day, highest_amount_minor=highest.amount_minor
    )


async def _build_recurring_expense_breakdown(
    db: AsyncSession,
    txn_repo: TransactionRepository,
    user_id: uuid.UUID,
    date_from: datetime,
    date_to: datetime,
    currency: str,
    total_expense_minor: int,
) -> RecurringExpenseBreakdown:
    all_recurring = await RecurringTransactionRepository(db).list_for_user(user_id)
    expense_recurring = [r for r in all_recurring if r.type == TransactionType.EXPENSE]
    if not expense_recurring:
        return RecurringExpenseBreakdown(
            items=[],
            total_scheduled_monthly_minor=0,
            total_actual_paid_minor=0,
            recurring_share_of_expense_percent=None,
        )

    recurring_ids = [r.id for r in expense_recurring]
    actual_paid_by_id = await txn_repo.sum_by_recurring_transaction_ids(
        user_id,
        recurring_transaction_ids=recurring_ids,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    subscription_rows = await SubscriptionRepository(db).list_for_user(user_id)
    subscription_recurring_ids = {sub.recurring_transaction_id for sub, _rec in subscription_rows}

    items = []
    total_scheduled_monthly_minor = 0
    total_actual_paid_minor = 0
    for recurring in expense_recurring:
        scheduled = calculate_monthly_cost_minor(recurring.amount_minor, recurring.frequency)
        actual_paid = actual_paid_by_id.get(recurring.id, 0)
        if recurring.is_active:
            total_scheduled_monthly_minor += scheduled
        total_actual_paid_minor += actual_paid
        items.append(
            RecurringExpenseBreakdownItem(
                recurring_transaction_id=recurring.id,
                name=recurring.name,
                frequency=recurring.frequency,
                amount_minor=recurring.amount_minor,
                currency=recurring.currency,
                is_active=recurring.is_active,
                is_subscription=recurring.id in subscription_recurring_ids,
                scheduled_monthly_cost_minor=scheduled,
                actual_paid_minor=actual_paid,
            )
        )
    items.sort(key=lambda it: it.actual_paid_minor, reverse=True)

    recurring_share_of_expense_percent = (
        round(total_actual_paid_minor / total_expense_minor * 100, 1)
        if total_expense_minor > 0
        else None
    )
    return RecurringExpenseBreakdown(
        items=items,
        total_scheduled_monthly_minor=total_scheduled_monthly_minor,
        total_actual_paid_minor=total_actual_paid_minor,
        recurring_share_of_expense_percent=recurring_share_of_expense_percent,
    )


async def get_analytics(
    db: AsyncSession, *, user_id: uuid.UUID, request: AnalyticsRequest
) -> AnalyticsRead:
    try:
        date_from, date_to = resolve_date_range(
            request.range,
            now=datetime.now(UTC),
            custom_from=request.custom_from,
            custom_to=request.custom_to,
        )
    except ValueError as exc:
        raise ValidationAppError(str(exc), field_errors={"range": "invalid"}) from exc

    currency = await _get_base_currency(db, user_id)
    txn_repo = TransactionRepository(db)

    spending_over_time = await _build_spending_over_time(
        txn_repo, user_id, date_from, date_to, currency
    )
    category_breakdown = await _build_category_breakdown(
        db, txn_repo, user_id, date_from, date_to, currency
    )
    monthly_rows = await txn_repo.sum_income_and_expense_by_month(
        user_id, date_from=date_from, date_to=date_to, currency=currency
    )
    income_vs_expense = _build_income_vs_expense(monthly_rows)
    savings_trend = _build_savings_trend(monthly_rows, date_from, date_to)
    budget_performance = await budget_service.list_budget_items(db, user_id=user_id)
    daily_spending = await _build_daily_spending(
        txn_repo, user_id, date_from, date_to, currency, spending_over_time
    )
    recurring_expense_breakdown = await _build_recurring_expense_breakdown(
        db,
        txn_repo,
        user_id,
        date_from,
        date_to,
        currency,
        income_vs_expense.total_expense_minor,
    )

    return AnalyticsRead(
        currency=currency,
        range=request.range,
        date_from=date_from.date(),
        date_to=(date_to - timedelta(days=1)).date(),
        spending_over_time=spending_over_time,
        category_breakdown=category_breakdown,
        income_vs_expense=income_vs_expense,
        savings_trend=savings_trend,
        budget_performance=budget_performance,
        daily_spending=daily_spending,
        recurring_expense_breakdown=recurring_expense_breakdown,
    )
