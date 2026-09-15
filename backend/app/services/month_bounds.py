"""Shared month-boundary math - used by the dashboard, budgets, analytics,
the financial calendar, and reports so "this month" (or any other month)
means exactly the same thing everywhere in the app. Pure date arithmetic,
no rounding ambiguity, so sharing it carries none of the regression risk
a shared *money-rounding* formula would."""

import calendar
from datetime import UTC, datetime


def month_start(year: int, month: int) -> datetime:
    """The first instant of the given calendar month, UTC. `month` may be
    any integer, not just 1-12 - it is normalized first (0 rolls back into
    December of the previous year, 13 rolls into January of the next),
    so callers can shift by an arbitrary number of months (month + n or
    month - n) without hand-rolling year-rollover logic themselves."""
    total_months = year * 12 + (month - 1)
    normalized_year, normalized_month0 = divmod(total_months, 12)
    return datetime(normalized_year, normalized_month0 + 1, 1, tzinfo=UTC)


def current_month_bounds(now: datetime) -> tuple[datetime, datetime, datetime]:
    """Returns (previous_month_start, this_month_start, next_month_start), all UTC."""
    this_month_start = month_start(now.year, now.month)
    next_month_start = month_start(now.year, now.month + 1)
    previous_month_start = month_start(now.year, now.month - 1)
    return previous_month_start, this_month_start, next_month_start


def days_in_month(now: datetime) -> int:
    return calendar.monthrange(now.year, now.month)[1]


def days_elapsed_in_month(now: datetime, this_month_start: datetime) -> int:
    return (now.date() - this_month_start.date()).days + 1


def month_start_n_months_ago(this_month_start: datetime, n: int) -> datetime:
    """The start of the month that is `n` months before `this_month_start`."""
    return month_start(this_month_start.year, this_month_start.month - n)
