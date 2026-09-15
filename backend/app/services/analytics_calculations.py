"""Analytics date-range resolution, period generation, and trend math.
Pure and DB-free (same pattern as app.services.budget_calculations /
app.services.recurrence) so every boundary and rounding decision is
unit-testable with plain dates and numbers - nothing here queries the
database or fabricates a data point.

Date ranges reuse app.services.month_bounds' existing calendar-month
arithmetic rather than re-deriving it, so "current month" means exactly
the same thing here as it does on the dashboard and in budgets.
"""

import enum
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta

from app.services.month_bounds import current_month_bounds, month_start_n_months_ago

# A range at or under this span uses daily granularity; anything longer
# uses monthly - deliberately tied to the actual resolved span (not the
# preset name) so a custom range is classified the same way a preset
# range would be. ~2 months, comfortably covering "current month" and
# "previous month" while classifying every multi-month preset as monthly.
_SHORT_RANGE_GRANULARITY_THRESHOLD_DAYS = 62

# "Flat" trend threshold: a period-over-period change smaller than this
# (in percent) is noise, not a real trend - a deliberate, documented
# policy choice, not a fabricated one.
_FLAT_TREND_THRESHOLD_PERCENT = 1.0


class AnalyticsRangePreset(enum.StrEnum):
    CURRENT_MONTH = "current_month"
    PREVIOUS_MONTH = "previous_month"
    LAST_3_MONTHS = "last_3_months"
    LAST_6_MONTHS = "last_6_months"
    LAST_12_MONTHS = "last_12_months"
    CUSTOM = "custom"


class Granularity(enum.StrEnum):
    DAY = "day"
    MONTH = "month"


class TrendDirection(enum.StrEnum):
    INCREASING = "increasing"
    DECREASING = "decreasing"
    FLAT = "flat"


_MONTHS_BACK_FOR_PRESET: dict[AnalyticsRangePreset, int] = {
    # "Last N months" includes the current, in-progress month as the most
    # recent one - so LAST_3_MONTHS spans back 2 further months before it.
    AnalyticsRangePreset.LAST_3_MONTHS: 2,
    AnalyticsRangePreset.LAST_6_MONTHS: 5,
    AnalyticsRangePreset.LAST_12_MONTHS: 11,
}


def resolve_date_range(
    preset: AnalyticsRangePreset,
    *,
    now: datetime,
    custom_from: date | None = None,
    custom_to: date | None = None,
) -> tuple[datetime, datetime]:
    """Returns (date_from, date_to_exclusive), both UTC - a half-open
    [date_from, date_to) range, so callers never double-count the
    boundary day between two adjacent ranges."""
    previous_month_start, this_month_start, next_month_start = current_month_bounds(now)

    if preset == AnalyticsRangePreset.CURRENT_MONTH:
        return this_month_start, next_month_start
    if preset == AnalyticsRangePreset.PREVIOUS_MONTH:
        return previous_month_start, this_month_start
    if preset == AnalyticsRangePreset.CUSTOM:
        if custom_from is None or custom_to is None:
            raise ValueError("custom_from and custom_to are required for a custom range.")
        if custom_from > custom_to:
            raise ValueError("custom_from must not be after custom_to.")
        date_from = datetime.combine(custom_from, time.min, tzinfo=UTC)
        # custom_to is inclusive of its whole calendar day.
        date_to = datetime.combine(custom_to + timedelta(days=1), time.min, tzinfo=UTC)
        return date_from, date_to

    months_back = _MONTHS_BACK_FOR_PRESET[preset]
    return month_start_n_months_ago(this_month_start, months_back), next_month_start


def resolve_granularity(date_from: datetime, date_to: datetime) -> Granularity:
    span_days = (date_to - date_from).days
    return (
        Granularity.DAY
        if span_days <= _SHORT_RANGE_GRANULARITY_THRESHOLD_DAYS
        else Granularity.MONTH
    )


def generate_day_periods(date_from: datetime, date_to: datetime) -> list[date]:
    """Every calendar day in the half-open [date_from, date_to) range."""
    days: list[date] = []
    current = date_from.date()
    end = date_to.date()
    while current < end:
        days.append(current)
        current += timedelta(days=1)
    return days


def generate_month_periods(date_from: datetime, date_to: datetime) -> list[date]:
    """The first day of every calendar month in the half-open
    [date_from, date_to) range."""
    months: list[date] = []
    year, month = date_from.year, date_from.month
    end_year, end_month = date_to.year, date_to.month
    while (year, month) < (end_year, end_month):
        months.append(date(year, month, 1))
        month += 1
        if month > 12:
            month = 1
            year += 1
    return months


@dataclass(frozen=True)
class TrendResult:
    # None only when there are fewer than 2 data points to compare -
    # insufficient data, never a guessed direction.
    direction: TrendDirection | None
    percent_change: float | None


def determine_trend(amounts: list[int]) -> TrendResult:
    """Compares the average of the first half of `amounts` against the
    average of the second half (split by count, not by date) - a simple,
    deterministic, noise-resistant trend signal. Works for any ordered
    series of period totals, including one that can go negative (a
    savings-trend point can be a deficit) - direction is always judged
    from the raw difference between the two averages, never from the
    sign of a percent-change ratio, which would invert when the baseline
    itself is negative (e.g. a deficit of -100 improving to -50 is a real
    increase, even though (-50 - -100) / -100 is a NEGATIVE percentage).
    `percent_change` is reported only when the first-half average is a
    genuine positive baseline to express a percentage of; otherwise it is
    None even though `direction` is still known from the raw difference."""
    if len(amounts) < 2:
        return TrendResult(None, None)

    mid = len(amounts) // 2
    first_half = amounts[:mid]
    second_half = amounts[mid:]
    first_avg = sum(first_half) / len(first_half)
    second_avg = sum(second_half) / len(second_half)
    diff = second_avg - first_avg

    if first_avg == 0 and second_avg == 0:
        return TrendResult(TrendDirection.FLAT, 0.0)

    percent_change = round(diff / first_avg * 100, 1) if first_avg > 0 else None

    if percent_change is not None and abs(percent_change) < _FLAT_TREND_THRESHOLD_PERCENT:
        return TrendResult(TrendDirection.FLAT, percent_change)
    if percent_change is None and diff == 0:
        return TrendResult(TrendDirection.FLAT, None)

    direction = TrendDirection.INCREASING if diff > 0 else TrendDirection.DECREASING
    return TrendResult(direction, percent_change)
