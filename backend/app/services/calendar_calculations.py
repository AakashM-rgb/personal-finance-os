"""Financial calendar date math: projecting a recurring transaction's
still-unbilled occurrence dates into a requested calendar range. Pure and
DB-free (same pattern as app.services.recurrence /
app.services.analytics_calculations) - reuses recurrence.py's
next_occurrence_date rather than a second definition of "what's the next
date," so a bill projected here can never disagree with what the
recurring-transaction engine would actually generate.
"""

from datetime import date

from app.models.recurring_transaction import RecurrenceFrequency
from app.services.recurrence import next_occurrence_date

# A generous, purely defensive bound - the loop always advances strictly
# forward each iteration, so it terminates on its own; this only guards
# against an unforeseen bug turning that into an infinite loop.
_MAX_PROJECTION_ITERATIONS = 10_000


def project_bill_dates_in_range(
    *,
    last_real_occurrence: date | None,
    start_date: date,
    frequency: RecurrenceFrequency,
    day_of_month: int,
    date_from: date,
    date_to: date,
) -> list[date]:
    """Every occurrence date in the half-open [date_from, date_to) range
    that has NOT yet been generated as a real transaction - i.e. every
    date strictly after `last_real_occurrence` (or, if nothing has ever
    been generated, `start_date` itself). These are scheduled bills, not
    paid ones - a date already covered by a real transaction is never
    included here, since the caller derives that from the real ledger
    separately (see app.services.calendar_service)."""
    if last_real_occurrence is None:
        current = start_date
    else:
        current = next_occurrence_date(last_real_occurrence, frequency, day_of_month=day_of_month)

    dates: list[date] = []
    for _ in range(_MAX_PROJECTION_ITERATIONS):
        if current >= date_to:
            break
        if current >= date_from:
            dates.append(current)
        current = next_occurrence_date(current, frequency, day_of_month=day_of_month)
    return dates
