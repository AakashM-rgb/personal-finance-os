"""Dashboard aggregation: everything here is computed from the current
user's own accounts and transactions - never fabricated, never another
user's data (every query is scoped by user_id from the authenticated
caller, exactly like every other service in this app).

Query budget: this view issues a fixed, small number of queries regardless
of how much history the user has - one settings lookup, one accounts list,
one current-month transaction fetch (aggregated in Python into totals,
category breakdown, recurring ratio, and the daily series all at once
rather than four separate SQL aggregates), one previous-month SUM, one
"recent transactions" fetch, and one categories list for labeling. All are
backed by existing indexes (`ix_transactions_user_occurred_at`,
`ix_accounts_user_id`, `ix_categories_user_id`).
"""

import calendar
import uuid
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.account import Account, AccountType
from app.models.category import Category
from app.models.transaction import Transaction, TransactionType
from app.repositories.account_repository import AccountRepository
from app.repositories.category_repository import CategoryRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.dashboard import (
    CategoryBreakdownItem,
    DashboardRead,
    HealthScore,
    HealthScoreFactor,
    MonthlySpending,
    UpcomingPayment,
)
from app.schemas.transaction import TransactionRead
from app.services.account_service import calculate_credit_utilization_percent
from app.services.health_score import calculate_health_score
from app.services.month_bounds import current_month_bounds

_RECENT_TRANSACTIONS_LIMIT = 8


def _next_occurrence_of_day(today: date, day_of_month: int) -> date:
    """The next calendar date (today or later) whose day-of-month is
    `day_of_month`, clamped to the last day of a shorter month."""

    def _clamped(year: int, month: int) -> date:
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, min(day_of_month, last_day))

    candidate = _clamped(today.year, today.month)
    if candidate >= today:
        return candidate

    year, month = today.year, today.month + 1
    if month > 12:
        month = 1
        year += 1
    return _clamped(year, month)


async def get_dashboard(db: AsyncSession, *, user_id: uuid.UUID) -> DashboardRead:
    now = datetime.now(UTC)

    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    base_currency = settings.currency if settings is not None else "INR"

    all_accounts = await AccountRepository(db).list_for_user(user_id, include_inactive=False)
    accounts = [a for a in all_accounts if a.currency == base_currency]
    excluded_other_currency_accounts = len(all_accounts) - len(accounts)

    total_balance_minor = sum(
        a.balance_minor for a in accounts if a.type != AccountType.CREDIT_CARD
    )
    total_credit_debt_minor = sum(
        a.balance_minor for a in accounts if a.type == AccountType.CREDIT_CARD
    )
    net_worth_minor = total_balance_minor - total_credit_debt_minor

    previous_month_start, this_month_start, next_month_start = current_month_bounds(now)

    txn_repo = TransactionRepository(db)
    this_month_transactions = await txn_repo.list_in_range(
        user_id, date_from=this_month_start, date_to=next_month_start, currency=base_currency
    )
    previous_month_expense_minor = await txn_repo.sum_expense_in_range(
        user_id, date_from=previous_month_start, date_to=this_month_start, currency=base_currency
    )

    month_aggregate = _aggregate_month(this_month_transactions)
    total_income_minor = month_aggregate.total_income_minor
    total_expense_minor = month_aggregate.total_expense_minor
    category_sums = month_aggregate.category_sums
    recurring_expense_minor = month_aggregate.recurring_expense_minor
    daily_totals = month_aggregate.daily_totals

    savings_minor = total_income_minor - total_expense_minor
    savings_rate = (
        round(savings_minor / total_income_minor * 100, 1) if total_income_minor > 0 else None
    )

    days_elapsed = (now.date() - this_month_start.date()).days + 1
    days_in_month = calendar.monthrange(now.year, now.month)[1]
    daily_average_minor = round(total_expense_minor / days_elapsed) if days_elapsed > 0 else 0
    projected_month_expense_minor = daily_average_minor * days_in_month
    expense_delta_minor = total_expense_minor - previous_month_expense_minor
    percent_change = (
        round(expense_delta_minor / previous_month_expense_minor * 100, 1)
        if previous_month_expense_minor > 0
        else None
    )

    categories = await CategoryRepository(db).list_visible_for_user(user_id, include_inactive=True)
    categories_by_id = {c.id: c for c in categories}
    category_breakdown = _build_category_breakdown(
        category_sums, total_expense_minor, categories_by_id
    )

    recent_transactions = await txn_repo.list_recent(
        user_id, limit=_RECENT_TRANSACTIONS_LIMIT, currency=base_currency
    )

    month_start_date = this_month_start.date()
    daily_series = [
        daily_totals.get(month_start_date + timedelta(days=i), 0) for i in range(days_elapsed)
    ]

    upcoming_payments = _build_upcoming_payments(accounts, now.date())

    credit_card_utilizations = [
        calculate_credit_utilization_percent(a.balance_minor, a.credit_card.credit_limit_minor)
        for a in accounts
        if a.type == AccountType.CREDIT_CARD and a.credit_card is not None
    ]
    health_result = calculate_health_score(
        total_income_minor=total_income_minor,
        total_expense_minor=total_expense_minor,
        credit_card_utilizations_percent=credit_card_utilizations,
        recurring_expense_minor=recurring_expense_minor,
        daily_expense_series=daily_series,
        days_elapsed=days_elapsed,
    )

    return DashboardRead(
        currency=base_currency,
        generated_at=now,
        total_balance_minor=total_balance_minor,
        net_worth_minor=net_worth_minor,
        total_income_minor=total_income_minor,
        total_expense_minor=total_expense_minor,
        savings_minor=savings_minor,
        savings_rate=savings_rate,
        monthly_spending=MonthlySpending(
            current_month_expense_minor=total_expense_minor,
            previous_month_expense_minor=previous_month_expense_minor,
            percent_change=percent_change,
            daily_average_minor=daily_average_minor,
            projected_month_expense_minor=projected_month_expense_minor,
            days_elapsed=days_elapsed,
            days_in_month=days_in_month,
        ),
        category_breakdown=category_breakdown,
        recent_transactions=[
            TransactionRead.model_validate(t) for t in recent_transactions
        ],
        upcoming_payments=upcoming_payments,
        health_score=HealthScore(
            score=health_result.score,
            label=health_result.label,
            factors=[
                HealthScoreFactor(
                    key=f.key,
                    label=f.label,
                    weight=f.weight,
                    score=f.score,
                    detail=f.detail,
                    is_positive=f.is_positive,
                )
                for f in health_result.factors
            ],
        ),
        excluded_other_currency_accounts=excluded_other_currency_accounts,
    )


@dataclass
class _MonthAggregate:
    total_income_minor: int
    total_expense_minor: int
    category_sums: dict[uuid.UUID | None, int]
    recurring_expense_minor: int
    daily_totals: dict[date, int]


def _aggregate_month(transactions: list[Transaction]) -> _MonthAggregate:
    total_income_minor = 0
    total_expense_minor = 0
    category_sums: dict[uuid.UUID | None, int] = defaultdict(int)
    recurring_expense_minor = 0
    daily_totals: dict[date, int] = defaultdict(int)

    for txn in transactions:
        if txn.type == TransactionType.INCOME:
            total_income_minor += txn.amount_minor
        elif txn.type == TransactionType.EXPENSE:
            total_expense_minor += txn.amount_minor
            category_sums[txn.category_id] += txn.amount_minor
            daily_totals[txn.occurred_at.date()] += txn.amount_minor
            if txn.is_recurring:
                recurring_expense_minor += txn.amount_minor

    return _MonthAggregate(
        total_income_minor=total_income_minor,
        total_expense_minor=total_expense_minor,
        category_sums=category_sums,
        recurring_expense_minor=recurring_expense_minor,
        daily_totals=daily_totals,
    )


def _build_category_breakdown(
    category_sums: dict[uuid.UUID | None, int],
    total_expense_minor: int,
    categories_by_id: dict[uuid.UUID, Category],
) -> list[CategoryBreakdownItem]:
    items = []
    ranked = sorted(category_sums.items(), key=lambda kv: kv[1], reverse=True)
    for category_id, amount_minor in ranked:
        category = categories_by_id.get(category_id) if category_id is not None else None
        items.append(
            CategoryBreakdownItem(
                category_id=category_id,
                name=category.name if category is not None else "Uncategorized",
                icon=category.icon if category is not None else "🏷️",
                color=category.color if category is not None else "#9CA3AF",
                amount_minor=amount_minor,
                percent=round(amount_minor / total_expense_minor * 100, 1)
                if total_expense_minor > 0
                else 0.0,
            )
        )
    return items


def _build_upcoming_payments(accounts: list[Account], today: date) -> list[UpcomingPayment]:
    """Only ever built from real, structured data - a credit card's own
    `payment_due_day` and current balance owed. No prediction is made for
    plain recurring transactions, since there is no recurring-schedule
    model yet to derive a real next date from (see CLAUDE.md phase plan) -
    fabricating one would violate "never build fake functionality"."""
    payments = []
    for account in accounts:
        if account.type != AccountType.CREDIT_CARD or account.credit_card is None:
            continue
        due_date = _next_occurrence_of_day(today, account.credit_card.payment_due_day)
        amount_minor = account.credit_card.minimum_payment_minor or account.balance_minor
        payments.append(
            UpcomingPayment(
                account_id=account.id,
                account_name=account.name,
                kind="credit_card_due",
                due_date=due_date,
                amount_minor=amount_minor,
                description=f"{account.name} payment due",
            )
        )
    payments.sort(key=lambda p: p.due_date)
    return payments
