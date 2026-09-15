"""Recurrence date math: given the date of an occurrence, deterministically
compute the date of the next one for a given frequency. Pure and DB-free
(same pattern as app.services.budget_calculations /
app.services.savings_goal_calculations) so every branch - including every
month-length and leap-year edge case - is unit-testable with plain dates.
Nothing here is randomly generated or approximated (no "+30 days" for
"monthly") - every step is exact calendar arithmetic.

Monthly/quarterly/yearly recurrences are always anchored to a fixed
`day_of_month` (the day of the schedule's original start_date) rather
than to whatever day the previous occurrence happened to land on - this
is what keeps a "31st of every month" schedule anchored to the 31st (or a
shorter month's last day) forever, instead of drifting to the 28th/30th
after passing through February and never recovering. The same anchor
governs yearly recurrences through a Feb 29 start date: a non-leap target
year clamps to Feb 28, and the next leap year returns to Feb 29 on its
own, with no drift accumulated in between.
"""

import calendar
from datetime import date, timedelta

from app.models.recurring_transaction import RecurrenceFrequency

_MONTHS_PER_STEP: dict[RecurrenceFrequency, int] = {
    RecurrenceFrequency.MONTHLY: 1,
    RecurrenceFrequency.QUARTERLY: 3,
    RecurrenceFrequency.YEARLY: 12,
}


def add_months_clamped(base: date, months: int, *, day_of_month: int) -> date:
    """`base`'s year/month, advanced by `months` calendar months, landing on
    `day_of_month` - clamped to the target month's last day if it's shorter
    (e.g. day_of_month=31 in a 30-day month, or =29 in a non-leap February)."""
    total_months = base.year * 12 + (base.month - 1) + months
    year, month0 = divmod(total_months, 12)
    month = month0 + 1
    last_day_of_month = calendar.monthrange(year, month)[1]
    return date(year, month, min(day_of_month, last_day_of_month))


def next_occurrence_date(
    current: date, frequency: RecurrenceFrequency, *, day_of_month: int
) -> date:
    """The date of the occurrence immediately after `current` for the given
    frequency. `day_of_month` is only consulted for monthly/quarterly/yearly
    frequencies - daily and weekly simply add a fixed number of days."""
    if frequency == RecurrenceFrequency.DAILY:
        return current + timedelta(days=1)
    if frequency == RecurrenceFrequency.WEEKLY:
        return current + timedelta(days=7)
    return add_months_clamped(current, _MONTHS_PER_STEP[frequency], day_of_month=day_of_month)
