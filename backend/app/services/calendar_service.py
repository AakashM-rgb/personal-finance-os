"""Financial calendar business logic: a month's worth of real daily
income/expense totals, real transactions (including transfers, though
they never count toward a day's income_minor/expense_minor), and
scheduled-but-not-yet-generated bills projected from the recurring
transaction engine. One bounded fetch (never more than one calendar
month of transaction history) drives both the daily totals and the
transaction list, so the two can never disagree with each other.
"""

import uuid
from collections import defaultdict
from datetime import date, datetime

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.transaction import Transaction, TransactionType
from app.repositories.recurring_transaction_repository import RecurringTransactionRepository
from app.repositories.subscription_repository import SubscriptionRepository
from app.repositories.transaction_repository import TransactionRepository
from app.repositories.user_settings_repository import UserSettingsRepository
from app.schemas.calendar import CalendarBill, CalendarDay, CalendarMonth
from app.schemas.transaction import TransactionRead
from app.services.analytics_calculations import generate_day_periods
from app.services.calendar_calculations import project_bill_dates_in_range
from app.services.month_bounds import month_start


async def _get_base_currency(db: AsyncSession, user_id: uuid.UUID) -> str:
    settings = await UserSettingsRepository(db).get_by_user_id(user_id)
    return settings.currency if settings is not None else "INR"


async def _build_bills_by_day(
    db: AsyncSession, user_id: uuid.UUID, date_from: datetime, date_to: datetime
) -> dict[date, list[CalendarBill]]:
    recurring_list = await RecurringTransactionRepository(db).list_active_for_user(user_id)
    if not recurring_list:
        return {}

    recurring_ids = [r.id for r in recurring_list]
    # One bulk query for every schedule's latest real occurrence, never
    # one query per schedule (avoids an N+1 across the user's recurring
    # transactions).
    latest_by_id = await TransactionRepository(db).get_latest_occurrence_dates_for_recurring_ids(
        recurring_ids
    )
    subscription_rows = await SubscriptionRepository(db).list_for_user(user_id)
    subscription_ids = {sub.recurring_transaction_id for sub, _rec in subscription_rows}

    bills_by_day: dict[date, list[CalendarBill]] = defaultdict(list)
    for recurring in recurring_list:
        bill_dates = project_bill_dates_in_range(
            last_real_occurrence=latest_by_id.get(recurring.id),
            start_date=recurring.start_date,
            frequency=recurring.frequency,
            day_of_month=recurring.day_of_month,
            date_from=date_from.date(),
            date_to=date_to.date(),
        )
        for bill_date in bill_dates:
            bills_by_day[bill_date].append(
                CalendarBill(
                    recurring_transaction_id=recurring.id,
                    name=recurring.name,
                    type=recurring.type,
                    amount_minor=recurring.amount_minor,
                    currency=recurring.currency,
                    frequency=recurring.frequency,
                    is_subscription=recurring.id in subscription_ids,
                )
            )
    return bills_by_day


async def get_calendar_month(
    db: AsyncSession, *, user_id: uuid.UUID, year: int, month: int
) -> CalendarMonth:
    date_from = month_start(year, month)
    date_to = month_start(year, month + 1)
    currency = await _get_base_currency(db, user_id)

    # One bounded fetch - never more than one calendar month of
    # transactions - drives both the per-day totals and the per-day
    # transaction list below, so the two can never disagree.
    transactions = await TransactionRepository(db).list_in_range(
        user_id, date_from=date_from, date_to=date_to, currency=currency, exclude_transfer=False
    )

    transactions_by_day: dict[date, list[Transaction]] = defaultdict(list)
    income_by_day: dict[date, int] = defaultdict(int)
    expense_by_day: dict[date, int] = defaultdict(int)
    for txn in transactions:
        day = txn.occurred_at.date()
        transactions_by_day[day].append(txn)
        # Transfers are deliberately excluded here - they must never
        # appear as income or expense, only as visible entries in the
        # day's transaction list.
        if txn.type == TransactionType.INCOME:
            income_by_day[day] += txn.amount_minor
        elif txn.type == TransactionType.EXPENSE:
            expense_by_day[day] += txn.amount_minor

    bills_by_day = await _build_bills_by_day(db, user_id, date_from, date_to)

    days = []
    for day in generate_day_periods(date_from, date_to):
        day_transactions = sorted(transactions_by_day.get(day, []), key=lambda t: t.occurred_at)
        income_minor = income_by_day.get(day, 0)
        expense_minor = expense_by_day.get(day, 0)
        days.append(
            CalendarDay(
                date=day,
                income_minor=income_minor,
                expense_minor=expense_minor,
                net_minor=income_minor - expense_minor,
                transactions=[TransactionRead.model_validate(t) for t in day_transactions],
                bills=bills_by_day.get(day, []),
            )
        )

    return CalendarMonth(year=year, month=month, currency=currency, days=days)
