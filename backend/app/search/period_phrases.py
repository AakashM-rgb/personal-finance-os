"""Deterministic resolution of a natural-language period phrase into a
concrete [start_date, end_date] inclusive range plus a human-readable
label. Pure, DB-free (same pattern as app.ai.tools.period_resolution,
which this reuses directly for calendar-month phrases) so every branch is
unit-testable with plain dates - nothing here ever queries the database or
invents a date, and "now" is always passed in explicitly rather than read
from the system clock inside this module, so tests can freeze it.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta

from app.ai.tools.period_resolution import resolve_period
from app.services.month_bounds import month_start

_MONTH_NAMES: dict[str, int] = {
    "january": 1,
    "jan": 1,
    "february": 2,
    "feb": 2,
    "march": 3,
    "mar": 3,
    "april": 4,
    "apr": 4,
    "may": 5,
    "june": 6,
    "jun": 6,
    "july": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "sept": 9,
    "october": 10,
    "oct": 10,
    "november": 11,
    "nov": 11,
    "december": 12,
    "dec": 12,
}

_RELATIVE_KEYWORDS = frozenset(
    {
        "today",
        "yesterday",
        "this week",
        "last week",
        "this month",
        "last month",
        "this year",
        "last year",
    }
)


@dataclass(frozen=True)
class ResolvedPeriod:
    start_date: date
    end_date: date  # inclusive
    label: str


def resolve_named_month(month_number: int, *, now: datetime) -> ResolvedPeriod:
    """Resolves a bare month name (e.g. "August") to a specific year using
    a deterministic rule: if that month has already started this year (it
    is the current month or an earlier one), use this year; otherwise
    (it's later in the calendar than the current month) it hasn't happened
    yet this year, so use last year - a bare month name in a transaction
    search almost always means the most recent occurrence of it, never a
    future one that can have no data yet."""
    year = now.year if month_number <= now.month else now.year - 1
    start = month_start(year, month_number)
    end_exclusive = month_start(year, month_number + 1)
    return ResolvedPeriod(
        start_date=start.date(),
        end_date=(end_exclusive - timedelta(days=1)).date(),
        label=start.strftime("%B %Y"),
    )


def resolve_month_keyword(keyword: str, *, now: datetime) -> ResolvedPeriod | None:
    month_number = _MONTH_NAMES.get(keyword.strip().lower())
    if month_number is None:
        return None
    return resolve_named_month(month_number, now=now)


def resolve_relative_period(keyword: str, *, now: datetime) -> ResolvedPeriod | None:
    """today / yesterday / this week / last week / this month / last month
    / this year / last year - the fixed, documented set of relative
    phrases this feature supports. "This week" is Monday-Sunday, the same
    ISO convention Python's own date.weekday() already uses."""
    normalized = keyword.strip().lower()
    if normalized not in _RELATIVE_KEYWORDS:
        return None

    today = now.date()

    if normalized == "today":
        return ResolvedPeriod(today, today, "Today")
    if normalized == "yesterday":
        yesterday = today - timedelta(days=1)
        return ResolvedPeriod(yesterday, yesterday, "Yesterday")
    if normalized == "this week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        return ResolvedPeriod(start, end, f"This week ({start.isoformat()} to {end.isoformat()})")
    if normalized == "last week":
        this_week_start = today - timedelta(days=today.weekday())
        start = this_week_start - timedelta(days=7)
        end = this_week_start - timedelta(days=1)
        return ResolvedPeriod(start, end, f"Last week ({start.isoformat()} to {end.isoformat()})")
    if normalized == "this month":
        date_from, date_to, label = resolve_period("current_month", now=now)
        return ResolvedPeriod(date_from.date(), (date_to - timedelta(days=1)).date(), label)
    if normalized == "last month":
        date_from, date_to, label = resolve_period("previous_month", now=now)
        return ResolvedPeriod(date_from.date(), (date_to - timedelta(days=1)).date(), label)
    if normalized == "this year":
        start = date(today.year, 1, 1)
        return ResolvedPeriod(start, today, f"{today.year} (year to date)")
    # last year
    start = date(today.year - 1, 1, 1)
    end = date(today.year - 1, 12, 31)
    return ResolvedPeriod(start, end, str(today.year - 1))
