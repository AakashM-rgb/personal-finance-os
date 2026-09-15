from datetime import date

from app.models.recurring_transaction import RecurrenceFrequency
from app.services.calendar_calculations import project_bill_dates_in_range


def test_never_billed_with_start_date_inside_the_range() -> None:
    dates = project_bill_dates_in_range(
        last_real_occurrence=None,
        start_date=date(2026, 9, 5),
        frequency=RecurrenceFrequency.MONTHLY,
        day_of_month=5,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 10, 1),
    )
    assert dates == [date(2026, 9, 5)]


def test_never_billed_with_start_date_before_the_range_fast_forwards() -> None:
    # Started Jan 5, monthly - by September it should show only the
    # September occurrence, not every missed month since January.
    dates = project_bill_dates_in_range(
        last_real_occurrence=None,
        start_date=date(2026, 1, 5),
        frequency=RecurrenceFrequency.MONTHLY,
        day_of_month=5,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 10, 1),
    )
    assert dates == [date(2026, 9, 5)]


def test_never_billed_with_start_date_after_the_range_is_empty() -> None:
    dates = project_bill_dates_in_range(
        last_real_occurrence=None,
        start_date=date(2027, 1, 1),
        frequency=RecurrenceFrequency.MONTHLY,
        day_of_month=1,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 10, 1),
    )
    assert dates == []


def test_weekly_frequency_can_have_multiple_bills_in_one_month() -> None:
    dates = project_bill_dates_in_range(
        last_real_occurrence=date(2026, 8, 29),
        start_date=date(2026, 8, 1),
        frequency=RecurrenceFrequency.WEEKLY,
        day_of_month=1,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 10, 1),
    )
    assert dates == [date(2026, 9, 5), date(2026, 9, 12), date(2026, 9, 19), date(2026, 9, 26)]


def test_already_billed_date_is_never_repeated_as_a_bill() -> None:
    # Last real occurrence was Sept 1 - the next scheduled bill is Oct 1,
    # not Sept 1 again.
    dates = project_bill_dates_in_range(
        last_real_occurrence=date(2026, 9, 1),
        start_date=date(2026, 1, 1),
        frequency=RecurrenceFrequency.MONTHLY,
        day_of_month=1,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 10, 1),
    )
    assert dates == []


def test_range_end_boundary_is_exclusive() -> None:
    dates = project_bill_dates_in_range(
        last_real_occurrence=date(2026, 8, 1),
        start_date=date(2026, 1, 1),
        frequency=RecurrenceFrequency.MONTHLY,
        day_of_month=1,
        date_from=date(2026, 8, 1),
        date_to=date(2026, 9, 1),  # Sept 1's occurrence must NOT be included
    )
    assert dates == []


def test_range_start_boundary_is_inclusive() -> None:
    dates = project_bill_dates_in_range(
        last_real_occurrence=date(2026, 8, 1),
        start_date=date(2026, 1, 1),
        frequency=RecurrenceFrequency.MONTHLY,
        day_of_month=1,
        date_from=date(2026, 9, 1),
        date_to=date(2026, 10, 1),
    )
    assert dates == [date(2026, 9, 1)]


def test_monthly_month_end_clamping_is_reused_correctly() -> None:
    # day_of_month=31 anchored - January's occurrence clamps into a
    # shorter February exactly as app.services.recurrence dictates.
    dates = project_bill_dates_in_range(
        last_real_occurrence=date(2026, 1, 31),
        start_date=date(2026, 1, 31),
        frequency=RecurrenceFrequency.MONTHLY,
        day_of_month=31,
        date_from=date(2026, 2, 1),
        date_to=date(2026, 3, 1),
    )
    assert dates == [date(2026, 2, 28)]
