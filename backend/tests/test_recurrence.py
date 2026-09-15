from datetime import date

from app.models.recurring_transaction import RecurrenceFrequency
from app.services.recurrence import add_months_clamped, next_occurrence_date

# --- daily / weekly -----------------------------------------------------------------


def test_daily_advances_by_one_day() -> None:
    assert next_occurrence_date(
        date(2026, 3, 15), RecurrenceFrequency.DAILY, day_of_month=15
    ) == date(2026, 3, 16)


def test_daily_crosses_a_month_boundary() -> None:
    assert next_occurrence_date(
        date(2026, 3, 31), RecurrenceFrequency.DAILY, day_of_month=31
    ) == date(2026, 4, 1)


def test_weekly_advances_by_seven_days() -> None:
    assert next_occurrence_date(
        date(2026, 3, 15), RecurrenceFrequency.WEEKLY, day_of_month=15
    ) == date(2026, 3, 22)


def test_weekly_crosses_a_year_boundary() -> None:
    assert next_occurrence_date(
        date(2026, 12, 28), RecurrenceFrequency.WEEKLY, day_of_month=28
    ) == date(2027, 1, 4)


# --- monthly --------------------------------------------------------------------------


def test_monthly_same_day_next_month() -> None:
    assert next_occurrence_date(
        date(2026, 3, 15), RecurrenceFrequency.MONTHLY, day_of_month=15
    ) == date(2026, 4, 15)


def test_monthly_january_31_clamps_to_february_28_in_a_non_leap_year() -> None:
    assert next_occurrence_date(
        date(2026, 1, 31), RecurrenceFrequency.MONTHLY, day_of_month=31
    ) == date(2026, 2, 28)


def test_monthly_january_31_clamps_to_february_29_in_a_leap_year() -> None:
    assert next_occurrence_date(
        date(2028, 1, 31), RecurrenceFrequency.MONTHLY, day_of_month=31
    ) == date(2028, 2, 29)


def test_monthly_stays_anchored_to_31_after_a_clamped_february() -> None:
    # Jan 31 -> Feb 28 (clamped) -> Mar 31 (back to the real anchor, not
    # drifted to the 28th).
    stepped_to_feb = next_occurrence_date(
        date(2026, 1, 31), RecurrenceFrequency.MONTHLY, day_of_month=31
    )
    assert stepped_to_feb == date(2026, 2, 28)
    stepped_to_mar = next_occurrence_date(
        stepped_to_feb, RecurrenceFrequency.MONTHLY, day_of_month=31
    )
    assert stepped_to_mar == date(2026, 3, 31)


def test_monthly_crosses_a_year_boundary() -> None:
    assert next_occurrence_date(
        date(2026, 12, 15), RecurrenceFrequency.MONTHLY, day_of_month=15
    ) == date(2027, 1, 15)


# --- quarterly --------------------------------------------------------------------------


def test_quarterly_advances_by_three_months() -> None:
    assert next_occurrence_date(
        date(2026, 1, 15), RecurrenceFrequency.QUARTERLY, day_of_month=15
    ) == date(2026, 4, 15)


def test_quarterly_november_30_clamps_correctly_across_february() -> None:
    # Nov 30 -> Feb 28 (2026 is not a leap year).
    assert next_occurrence_date(
        date(2025, 11, 30), RecurrenceFrequency.QUARTERLY, day_of_month=30
    ) == date(2026, 2, 28)


def test_quarterly_crosses_a_year_boundary() -> None:
    assert next_occurrence_date(
        date(2026, 11, 15), RecurrenceFrequency.QUARTERLY, day_of_month=15
    ) == date(2027, 2, 15)


# --- yearly / leap years ---------------------------------------------------------------


def test_yearly_advances_by_twelve_months() -> None:
    assert next_occurrence_date(
        date(2026, 6, 15), RecurrenceFrequency.YEARLY, day_of_month=15
    ) == date(2027, 6, 15)


def test_yearly_feb_29_clamps_to_feb_28_in_a_non_leap_target_year() -> None:
    # 2028 is a leap year; 2029 is not.
    assert next_occurrence_date(
        date(2028, 2, 29), RecurrenceFrequency.YEARLY, day_of_month=29
    ) == date(2029, 2, 28)


def test_yearly_feb_29_returns_to_feb_29_on_the_next_leap_year() -> None:
    # Anchored to day_of_month=29 always - the non-leap years in between
    # never permanently shift the schedule to the 28th.
    year = date(2028, 2, 29)
    for expected in [date(2029, 2, 28), date(2030, 2, 28), date(2031, 2, 28), date(2032, 2, 29)]:
        year = next_occurrence_date(year, RecurrenceFrequency.YEARLY, day_of_month=29)
        assert year == expected


def test_yearly_across_a_non_leap_to_leap_transition() -> None:
    assert next_occurrence_date(
        date(2027, 3, 1), RecurrenceFrequency.YEARLY, day_of_month=1
    ) == date(2028, 3, 1)


# --- add_months_clamped (direct) --------------------------------------------------------


def test_add_months_clamped_handles_a_full_year_of_month_lengths() -> None:
    base = date(2026, 1, 31)
    assert add_months_clamped(base, 1, day_of_month=31) == date(2026, 2, 28)
    assert add_months_clamped(base, 2, day_of_month=31) == date(2026, 3, 31)
    assert add_months_clamped(base, 3, day_of_month=31) == date(2026, 4, 30)
    assert add_months_clamped(base, 4, day_of_month=31) == date(2026, 5, 31)


def test_add_months_clamped_zero_months_is_the_clamped_same_month() -> None:
    assert add_months_clamped(date(2026, 2, 5), 0, day_of_month=31) == date(2026, 2, 28)
