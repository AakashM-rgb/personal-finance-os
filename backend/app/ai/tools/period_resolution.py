"""Pure, DB-free resolution of an AI tool's "period" argument into a
concrete half-open [date_from, date_to) UTC range plus a human-readable
label - same pattern as app.services.analytics_calculations /
app.services.month_bounds, so every branch is unit-testable with plain
dates and nothing here ever queries the database.

A period argument accepts exactly three shapes, and nothing else:
- None or "current_month": the calendar month `now` falls in.
- "previous_month": the calendar month immediately before that.
- "YYYY-MM": one explicit calendar month.

Anything else raises ValueError, which the tool registry (app.ai.tools.
registry) turns into a rejected ("invalid_arguments") tool call - a period
is always a real, resolvable calendar month, never a guess.
"""

import re
from datetime import datetime

from app.services.month_bounds import current_month_bounds, month_start

_MONTH_PATTERN = re.compile(r"^(\d{4})-(\d{2})$")
_MIN_YEAR = 2000
_MAX_YEAR = 2100

# A custom date range wider than this would be an unbounded query - the
# same "bounded query parameters" rule applies to a date range as to a
# result-row limit.
MAX_CUSTOM_RANGE_DAYS = 366


def _label(month_start_dt: datetime) -> str:
    return month_start_dt.strftime("%B %Y")


def resolve_period(period: str | None, *, now: datetime) -> tuple[datetime, datetime, str]:
    """Returns (date_from, date_to_exclusive, label) for a single named or
    explicit calendar month."""
    previous_month_start, this_month_start, next_month_start = current_month_bounds(now)

    if period is None or period == "current_month":
        return this_month_start, next_month_start, _label(this_month_start)
    if period == "previous_month":
        return previous_month_start, this_month_start, _label(previous_month_start)

    match = _MONTH_PATTERN.match(period)
    if not match:
        raise ValueError(
            f"Invalid period {period!r}. Use 'current_month', 'previous_month', or 'YYYY-MM'."
        )
    year, month = int(match.group(1)), int(match.group(2))
    if not (_MIN_YEAR <= year <= _MAX_YEAR):
        raise ValueError(f"Invalid period {period!r}: year out of supported range.")
    if not (1 <= month <= 12):
        # month_start() normalizes an out-of-range month instead of raising
        # (e.g. month=13 silently rolls into next January) - reject here so
        # an invalid month string is never silently reinterpreted as a
        # different, valid one.
        raise ValueError(f"Invalid period {period!r}: month must be 01-12.")

    start = month_start(year, month)
    end = month_start(year, month + 1)
    return start, end, _label(start)


def validate_custom_range(date_from: datetime, date_to: datetime) -> None:
    """Raises ValueError for a backwards or unbounded custom date range -
    used wherever a tool accepts explicit date_from/date_to arguments
    instead of a named period."""
    if date_from >= date_to:
        raise ValueError("date_from must be before date_to.")
    if (date_to - date_from).days > MAX_CUSTOM_RANGE_DAYS:
        raise ValueError(f"A date range can span at most {MAX_CUSTOM_RANGE_DAYS} days.")
