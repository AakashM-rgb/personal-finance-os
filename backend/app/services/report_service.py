"""Report business logic: every report is a different presentation of
numbers computed by the same services/repositories the rest of the app
already uses - app.services.analytics_service (spending, category,
income/expense, savings), app.services.budget_service (budgets),
app.services.savings_goal_service (goals), and
app.services.account_service (net worth). Reports never re-derive a
calculation that module already owns.
"""

import uuid
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import ValidationAppError
from app.models.account import Account, AccountType
from app.models.category import Category
from app.models.transaction import TransactionType
from app.repositories.account_repository import AccountRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.analytics import AnalyticsRangePreset, AnalyticsRequest
from app.schemas.reports import (
    BudgetReport,
    CategoryReport,
    CategoryReportItem,
    ExpenseReport,
    IncomeReport,
    MonthlyAmount,
    MonthlyReport,
    NetWorthAccountItem,
    NetWorthReport,
    NetWorthTrendPoint,
    SavingsReport,
    SavingsTrendPoint,
    TimeSeriesPoint,
    YearlyReport,
)
from app.schemas.transaction import TransactionRead
from app.services import analytics_service, budget_service, category_service, savings_goal_service
from app.services.account_service import calculate_net_worth
from app.services.analytics_calculations import (
    Granularity,
    generate_day_periods,
    generate_month_periods,
    resolve_date_range,
    resolve_granularity,
)
from app.services.month_bounds import current_month_bounds, month_start, month_start_n_months_ago

_LARGEST_TRANSACTIONS_LIMIT = 10
_NET_WORTH_TREND_MONTHS = 12


async def _get_base_currency(db: AsyncSession, user_id: uuid.UUID) -> str:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    return settings.currency if settings is not None else "INR"


def _resolve_range(
    range_preset: AnalyticsRangePreset, *, custom_from: date | None, custom_to: date | None
) -> tuple[datetime, datetime]:
    try:
        return resolve_date_range(
            range_preset, now=datetime.now(UTC), custom_from=custom_from, custom_to=custom_to
        )
    except ValueError as exc:
        raise ValidationAppError(str(exc), field_errors={"range": "invalid"}) from exc


def _category_items(
    rows: list[tuple[uuid.UUID | None, int, int]],
    total_minor: int,
    categories_by_id: dict[uuid.UUID, Category],
) -> list[CategoryReportItem]:
    ranked = sorted(rows, key=lambda row: row[1], reverse=True)
    items = []
    for category_id, amount_minor, count in ranked:
        category = categories_by_id.get(category_id) if category_id is not None else None
        items.append(
            CategoryReportItem(
                category_id=category_id,
                name=category_service.display_name(category),
                icon=category_service.display_icon(category),
                color=category_service.display_color(category),
                amount_minor=amount_minor,
                percent=round(amount_minor / total_minor * 100, 1) if total_minor > 0 else 0.0,
                transaction_count=count,
            )
        )
    return items


# --- Monthly report -------------------------------------------------------------------


async def get_monthly_report(
    db: AsyncSession, *, user_id: uuid.UUID, year: int, month: int
) -> MonthlyReport:
    date_from = month_start(year, month)
    date_to = month_start(year, month + 1)

    analytics = await analytics_service.get_analytics(
        db,
        user_id=user_id,
        request=AnalyticsRequest(
            range=AnalyticsRangePreset.CUSTOM,
            custom_from=date_from.date(),
            custom_to=(date_to - timedelta(days=1)).date(),
        ),
    )

    # A single-month custom range always yields exactly one savings-trend
    # point (see app.services.analytics_calculations.generate_month_periods).
    savings_point = analytics.savings_trend.points[0] if analytics.savings_trend.points else None

    return MonthlyReport(
        year=year,
        month=month,
        currency=analytics.currency,
        date_from=analytics.date_from,
        date_to=analytics.date_to,
        total_income_minor=analytics.income_vs_expense.total_income_minor,
        total_expense_minor=analytics.income_vs_expense.total_expense_minor,
        net_cash_flow_minor=analytics.income_vs_expense.net_minor,
        savings_minor=savings_point.savings_minor if savings_point else 0,
        savings_rate=savings_point.savings_rate if savings_point else None,
        category_breakdown=analytics.category_breakdown,
        budget_performance=analytics.budget_performance,
        recurring_expense_breakdown=analytics.recurring_expense_breakdown,
    )


# --- Yearly report --------------------------------------------------------------------


async def get_yearly_report(db: AsyncSession, *, user_id: uuid.UUID, year: int) -> YearlyReport:
    year_start = month_start(year, 1)
    year_end = month_start(year + 1, 1)

    analytics = await analytics_service.get_analytics(
        db,
        user_id=user_id,
        request=AnalyticsRequest(
            range=AnalyticsRangePreset.CUSTOM,
            custom_from=year_start.date(),
            custom_to=(year_end - timedelta(days=1)).date(),
        ),
    )

    monthly_income_trend = [
        MonthlyAmount(month=p.period, amount_minor=p.income_minor)
        for p in analytics.savings_trend.points
    ]
    monthly_expense_trend = [
        MonthlyAmount(month=p.period, amount_minor=p.expense_minor)
        for p in analytics.savings_trend.points
    ]
    monthly_savings_trend = [
        MonthlyAmount(month=p.period, amount_minor=p.savings_minor)
        for p in analytics.savings_trend.points
    ]

    total_income = analytics.income_vs_expense.total_income_minor
    net_cash_flow = analytics.income_vs_expense.net_minor
    savings_rate = round(net_cash_flow / total_income * 100, 1) if total_income > 0 else None

    return YearlyReport(
        year=year,
        currency=analytics.currency,
        total_income_minor=total_income,
        total_expense_minor=analytics.income_vs_expense.total_expense_minor,
        net_cash_flow_minor=net_cash_flow,
        savings_minor=net_cash_flow,
        savings_rate=savings_rate,
        monthly_income_trend=monthly_income_trend,
        monthly_expense_trend=monthly_expense_trend,
        monthly_savings_trend=monthly_savings_trend,
        category_totals=analytics.category_breakdown,
    )


# --- Category report -------------------------------------------------------------------


async def get_category_report(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    range_preset: AnalyticsRangePreset,
    custom_from: date | None,
    custom_to: date | None,
) -> CategoryReport:
    date_from, date_to = _resolve_range(range_preset, custom_from=custom_from, custom_to=custom_to)
    currency = await _get_base_currency(db, user_id)

    rows = await TransactionRepository(db).sum_and_count_by_category(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    total_expense_minor = sum(amount for _cid, amount, _count in rows)
    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    categories_by_id = {c.id: c for c in categories}

    return CategoryReport(
        currency=currency,
        date_from=date_from.date(),
        date_to=(date_to - timedelta(days=1)).date(),
        total_expense_minor=total_expense_minor,
        items=_category_items(rows, total_expense_minor, categories_by_id),
    )


# --- Income report -----------------------------------------------------------------------


async def get_income_report(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    range_preset: AnalyticsRangePreset,
    custom_from: date | None,
    custom_to: date | None,
) -> IncomeReport:
    date_from, date_to = _resolve_range(range_preset, custom_from=custom_from, custom_to=custom_to)
    currency = await _get_base_currency(db, user_id)
    txn_repo = TransactionRepository(db)

    rows = await txn_repo.sum_and_count_by_category(
        user_id,
        transaction_type=TransactionType.INCOME,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    total_income_minor = sum(amount for _cid, amount, _count in rows)
    transaction_count = sum(count for _cid, _amount, count in rows)
    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    categories_by_id = {c.id: c for c in categories}

    granularity = resolve_granularity(date_from, date_to)
    period_sums = dict(
        await txn_repo.sum_by_type_and_period(
            user_id,
            transaction_type=TransactionType.INCOME,
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
    over_time = [TimeSeriesPoint(period=p, amount_minor=period_sums.get(p, 0)) for p in periods]

    largest = await txn_repo.list_top_by_amount(
        user_id,
        transaction_type=TransactionType.INCOME,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
        limit=_LARGEST_TRANSACTIONS_LIMIT,
    )

    return IncomeReport(
        currency=currency,
        date_from=date_from.date(),
        date_to=(date_to - timedelta(days=1)).date(),
        total_income_minor=total_income_minor,
        transaction_count=transaction_count,
        by_source=_category_items(rows, total_income_minor, categories_by_id),
        over_time=over_time,
        largest_transactions=[TransactionRead.model_validate(t) for t in largest],
    )


# --- Expense report ----------------------------------------------------------------------


async def get_expense_report(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    range_preset: AnalyticsRangePreset,
    custom_from: date | None,
    custom_to: date | None,
) -> ExpenseReport:
    date_from, date_to = _resolve_range(range_preset, custom_from=custom_from, custom_to=custom_to)
    currency = await _get_base_currency(db, user_id)
    txn_repo = TransactionRepository(db)

    rows = await txn_repo.sum_and_count_by_category(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
    )
    total_expense_minor = sum(amount for _cid, amount, _count in rows)
    transaction_count = sum(count for _cid, _amount, count in rows)
    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    categories_by_id = {c.id: c for c in categories}

    granularity = resolve_granularity(date_from, date_to)
    period_sums = dict(
        await txn_repo.sum_by_type_and_period(
            user_id,
            transaction_type=TransactionType.EXPENSE,
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
    over_time = [TimeSeriesPoint(period=p, amount_minor=period_sums.get(p, 0)) for p in periods]

    largest = await txn_repo.list_top_by_amount(
        user_id,
        transaction_type=TransactionType.EXPENSE,
        date_from=date_from,
        date_to=date_to,
        currency=currency,
        limit=_LARGEST_TRANSACTIONS_LIMIT,
    )

    recurring_split = await txn_repo.sum_by_recurring_flag(
        user_id, date_from=date_from, date_to=date_to, currency=currency
    )

    return ExpenseReport(
        currency=currency,
        date_from=date_from.date(),
        date_to=(date_to - timedelta(days=1)).date(),
        total_expense_minor=total_expense_minor,
        transaction_count=transaction_count,
        by_category=_category_items(rows, total_expense_minor, categories_by_id),
        over_time=over_time,
        largest_transactions=[TransactionRead.model_validate(t) for t in largest],
        recurring_expense_minor=recurring_split.get(True, 0),
        non_recurring_expense_minor=recurring_split.get(False, 0),
    )


# --- Budget report -----------------------------------------------------------------------


async def get_budget_report(db: AsyncSession, *, user_id: uuid.UUID) -> BudgetReport:
    items = await budget_service.list_budget_items(db, user_id=user_id)
    currency = items[0].currency if items else await _get_base_currency(db, user_id)

    return BudgetReport(
        currency=currency,
        items=items,
        total_budgeted_minor=sum(i.amount_minor for i in items),
        total_spent_minor=sum(i.spent_minor for i in items),
        at_risk_count=sum(1 for i in items if i.status != "healthy"),
        exceeded_count=sum(1 for i in items if i.status == "exceeded"),
    )


# --- Savings report ----------------------------------------------------------------------


async def get_savings_report(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    range_preset: AnalyticsRangePreset,
    custom_from: date | None,
    custom_to: date | None,
) -> SavingsReport:
    analytics = await analytics_service.get_analytics(
        db,
        user_id=user_id,
        request=AnalyticsRequest(range=range_preset, custom_from=custom_from, custom_to=custom_to),
    )
    goals = await savings_goal_service.list_savings_goals(db, user_id=user_id)

    total_income = analytics.income_vs_expense.total_income_minor
    savings_minor = analytics.income_vs_expense.net_minor
    savings_rate = round(savings_minor / total_income * 100, 1) if total_income > 0 else None

    trend = [
        SavingsTrendPoint(
            period=p.period,
            income_minor=p.income_minor,
            expense_minor=p.expense_minor,
            savings_minor=p.savings_minor,
            savings_rate=p.savings_rate,
        )
        for p in analytics.savings_trend.points
    ]

    return SavingsReport(
        currency=analytics.currency,
        date_from=analytics.date_from,
        date_to=analytics.date_to,
        total_income_minor=total_income,
        total_expense_minor=analytics.income_vs_expense.total_expense_minor,
        savings_minor=savings_minor,
        savings_rate=savings_rate,
        trend=trend,
        trend_direction=analytics.savings_trend.trend,
        goals=goals,
    )


# --- Net worth report --------------------------------------------------------------------


async def _build_net_worth_trend(
    db: AsyncSession,
    *,
    user_id: uuid.UUID,
    accounts: list[Account],
    current_net_worth_minor: int,
    currency: str,
) -> list[NetWorthTrendPoint]:
    """Reconstructs a historical net-worth trend from the CURRENT account
    balances and the real transaction ledger - there is no stored
    historical balance snapshot anywhere in this schema. For each of the
    last _NET_WORTH_TREND_MONTHS month-starts m (oldest to newest):

        net_worth(start of m) = current_net_worth
                                 - SUM(each real transaction's net effect on
                                   total net worth) for every transaction
                                   with occurred_at >= start of m

    A transaction's net-worth effect is derived per account from the same
    balance delta app.services.transaction_service._apply_balance_effect
    actually applies (income/expense on their one account, a transfer's
    -amount/+amount split across its two accounts) - NOT assumed to be
    "income adds, expense subtracts, transfer is always zero". A transfer
    is exactly net-worth-neutral when both its accounts are assets, but
    NOT when either leg is a credit-card account (a liability, subtracted
    rather than added in net worth) - e.g. paying a card from checking is a
    real, common transfer that this app allows and that does change net
    worth under the existing balance convention, so treating every
    transfer as zero would silently misreport the trend for exactly that
    routine action.

    One grouped query (month, account) covers the whole trend window; the
    walk-backward subtraction happens as a Python suffix sum over its
    results, never one query per month.

    Documented assumptions: (1) this assumes no account's balance_minor has
    been changed by anything other than a recorded transaction since that
    account was created (e.g. no manual correction outside the ledger) -
    the trend is only meaningful back to whenever the earliest included
    account was created; (2) it is restricted to the same accounts
    get_net_worth_report used for the CURRENT figure (active, base-currency)
    - a transaction against an account excluded from that figure (inactive,
    or a different currency) correctly contributes nothing, keeping every
    trend point consistent with the current total it walks backward from.
    """
    now = datetime.now(UTC)
    _, this_month_start, next_month_start = current_month_bounds(now)
    trend_start = month_start_n_months_ago(this_month_start, _NET_WORTH_TREND_MONTHS - 1)

    account_ids = [a.id for a in accounts]
    is_liability_by_id = {a.id: a.type == AccountType.CREDIT_CARD for a in accounts}

    delta_rows = await TransactionRepository(db).sum_balance_delta_by_month_for_accounts(
        user_id,
        account_ids=account_ids,
        date_from=trend_start,
        date_to=next_month_start,
        currency=currency,
    )
    net_delta_by_month: dict[date, int] = defaultdict(int)
    for period, account_id, delta in delta_rows:
        # A liability account's balance is SUBTRACTED in net worth, so an
        # increase in what it owes (+delta) DECREASES net worth.
        net_delta_by_month[period] += -delta if is_liability_by_id.get(account_id, False) else delta

    month_starts = generate_month_periods(trend_start, next_month_start)  # ascending
    net_worth_by_month: dict[date, int] = {}
    suffix_sum = 0
    for m in reversed(month_starts):
        suffix_sum += net_delta_by_month.get(m, 0)
        net_worth_by_month[m] = current_net_worth_minor - suffix_sum

    return [
        NetWorthTrendPoint(month=m, net_worth_minor=net_worth_by_month[m]) for m in month_starts
    ]


async def get_net_worth_report(db: AsyncSession, *, user_id: uuid.UUID) -> NetWorthReport:
    base_currency = await _get_base_currency(db, user_id)
    all_accounts = await AccountRepository(db).list_for_user(user_id, include_inactive=False)
    accounts: list[Account] = [a for a in all_accounts if a.currency == base_currency]

    net_worth = calculate_net_worth(accounts)
    account_items = [
        NetWorthAccountItem(
            account_id=a.id,
            name=a.name,
            type=a.type.value,
            balance_minor=a.balance_minor,
            currency=a.currency,
            is_liability=(a.type == AccountType.CREDIT_CARD),
        )
        for a in accounts
    ]
    trend = await _build_net_worth_trend(
        db,
        user_id=user_id,
        accounts=accounts,
        current_net_worth_minor=net_worth.net_worth_minor,
        currency=base_currency,
    )

    return NetWorthReport(
        currency=base_currency,
        total_assets_minor=net_worth.total_assets_minor,
        total_liabilities_minor=net_worth.total_liabilities_minor,
        net_worth_minor=net_worth.net_worth_minor,
        accounts=account_items,
        trend=trend,
    )
