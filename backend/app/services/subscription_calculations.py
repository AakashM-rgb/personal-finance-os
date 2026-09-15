"""Subscription cost math and the unused-subscription evidence rule. Pure
and DB-free (same pattern as app.services.budget_calculations /
app.services.recurrence) so every branch is unit-testable with plain
numbers and dates - nothing here is randomly estimated.

Monthly/yearly cost convention (the one canonical normalization formula
for a subscription's amount, per CLAUDE.md §13 - reuse this everywhere a
monthly-equivalent subscription figure is needed, never a second
approximation of it): a year is treated as exactly 365 days and 52 weeks,
and a month as 1/12 of a year - the same convention a daily/weekly/
monthly/quarterly/yearly billing amount is annualized or monthlyized
under, everywhere in this module.

Unused-subscription evidence: this app can only ever observe money
movement, never actual service usage (it has no idea whether a video was
watched). Claiming "unused" from that data only ever means one narrow,
falsifiable thing - defined here and nowhere else: the subscription has
enough of its own billing history to judge from
(>= MIN_SUBSCRIPTION_AGE_DAYS since its first real generated charge), and
there is no other transaction in its category in the trailing
LOOKBACK_DAYS window. Absent either fact, no claim is made - the result
is `None` ("insufficient data"), never a guessed `False`.
"""

from dataclasses import dataclass
from datetime import date, timedelta

from app.models.recurring_transaction import RecurrenceFrequency

_DAYS_PER_YEAR = 365
_WEEKS_PER_YEAR = 52
_MONTHS_PER_YEAR = 12
_MONTHS_PER_QUARTER = 3

# Evidence-rule policy thresholds - deliberate, documented choices, not
# arbitrary magic numbers: two months of billing history before drawing
# any conclusion, and a full quarter of category activity to check against.
MIN_SUBSCRIPTION_AGE_DAYS = 60
LOOKBACK_DAYS = 90


def calculate_monthly_cost_minor(amount_minor: int, frequency: RecurrenceFrequency) -> int:
    """The amount's cost expressed as a monthly-equivalent figure."""
    if frequency == RecurrenceFrequency.DAILY:
        return round(amount_minor * _DAYS_PER_YEAR / _MONTHS_PER_YEAR)
    if frequency == RecurrenceFrequency.WEEKLY:
        return round(amount_minor * _WEEKS_PER_YEAR / _MONTHS_PER_YEAR)
    if frequency == RecurrenceFrequency.MONTHLY:
        return amount_minor
    if frequency == RecurrenceFrequency.QUARTERLY:
        return round(amount_minor / _MONTHS_PER_QUARTER)
    return round(amount_minor / _MONTHS_PER_YEAR)  # YEARLY


def calculate_yearly_cost_minor(amount_minor: int, frequency: RecurrenceFrequency) -> int:
    """The amount's cost expressed as a yearly-equivalent figure. Always an
    exact integer - every frequency's yearly multiplier is a whole number."""
    if frequency == RecurrenceFrequency.DAILY:
        return amount_minor * _DAYS_PER_YEAR
    if frequency == RecurrenceFrequency.WEEKLY:
        return amount_minor * _WEEKS_PER_YEAR
    if frequency == RecurrenceFrequency.MONTHLY:
        return amount_minor * _MONTHS_PER_YEAR
    if frequency == RecurrenceFrequency.QUARTERLY:
        return amount_minor * (_MONTHS_PER_YEAR // _MONTHS_PER_QUARTER)
    return amount_minor  # YEARLY


@dataclass(frozen=True)
class UnusedEvidence:
    # None = insufficient data, no claim made. True/False = evidence exists
    # either way - see the module docstring for exactly what each means.
    is_possibly_unused: bool | None
    reason: str


def evaluate_unused_evidence(
    *,
    own_billing_dates: list[date],
    other_category_activity_dates: list[date],
    today: date,
) -> UnusedEvidence:
    """`own_billing_dates` are this subscription's own real generated
    charges. `other_category_activity_dates` are every OTHER transaction
    (never this subscription's own) in the same category - already
    pre-filtered by the caller to the trailing LOOKBACK_DAYS window is not
    required; this function only uses dates >= (today - LOOKBACK_DAYS)."""
    if not own_billing_dates:
        return UnusedEvidence(None, "This subscription hasn't been billed yet.")

    first_billed = min(own_billing_dates)
    age_days = (today - first_billed).days
    if age_days < MIN_SUBSCRIPTION_AGE_DAYS:
        return UnusedEvidence(
            None,
            f"Only {age_days} day(s) of billing history - "
            f"need at least {MIN_SUBSCRIPTION_AGE_DAYS} to draw a conclusion.",
        )

    lookback_start = today - timedelta(days=LOOKBACK_DAYS)
    recent_activity = [d for d in other_category_activity_dates if d >= lookback_start]
    if recent_activity:
        return UnusedEvidence(
            False,
            f"Found {len(recent_activity)} other transaction(s) in this category in the "
            f"last {LOOKBACK_DAYS} days.",
        )
    return UnusedEvidence(
        True,
        f"No other transactions in this category in the last {LOOKBACK_DAYS} days, "
        f"despite {age_days} days of billing history.",
    )
