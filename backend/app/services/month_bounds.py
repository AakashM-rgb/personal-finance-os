"""Shared current-month boundary math - used by both the dashboard and the
budgets module so "this month" means exactly the same thing everywhere in
the app. Pure date arithmetic, no rounding ambiguity, so sharing it carries
none of the regression risk a shared *money-rounding* formula would."""

import calendar
from datetime import UTC, datetime


def current_month_bounds(now: datetime) -> tuple[datetime, datetime, datetime]:
    """Returns (previous_month_start, this_month_start, next_month_start), all UTC."""
    this_month_start = datetime(now.year, now.month, 1, tzinfo=UTC)

    if now.month == 12:
        next_month_start = datetime(now.year + 1, 1, 1, tzinfo=UTC)
    else:
        next_month_start = datetime(now.year, now.month + 1, 1, tzinfo=UTC)

    if now.month == 1:
        previous_month_start = datetime(now.year - 1, 12, 1, tzinfo=UTC)
    else:
        previous_month_start = datetime(now.year, now.month - 1, 1, tzinfo=UTC)

    return previous_month_start, this_month_start, next_month_start


def days_in_month(now: datetime) -> int:
    return calendar.monthrange(now.year, now.month)[1]


def days_elapsed_in_month(now: datetime, this_month_start: datetime) -> int:
    return (now.date() - this_month_start.date()).days + 1


def month_start_n_months_ago(this_month_start: datetime, n: int) -> datetime:
    """The start of the month that is `n` months before `this_month_start`."""
    total_months = (this_month_start.year * 12 + (this_month_start.month - 1)) - n
    year, month0 = divmod(total_months, 12)
    return datetime(year, month0 + 1, 1, tzinfo=UTC)
