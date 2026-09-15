from datetime import date

from app.services.savings_goal_calculations import (
    calculate_days_remaining,
    calculate_progress_percent,
    calculate_remaining_minor,
    calculate_required_savings,
)

# --- progress percent --------------------------------------------------------------


def test_progress_is_zero_with_no_savings_yet() -> None:
    assert calculate_progress_percent(0, 15000000) == 0.0


def test_progress_matches_spec_example() -> None:
    # Target 1,50,000 / current 45,000 -> 30%
    assert calculate_progress_percent(4500000, 15000000) == 30.0


def test_progress_is_a_hundred_when_current_equals_target() -> None:
    assert calculate_progress_percent(15000000, 15000000) == 100.0


def test_progress_rounds_to_one_decimal_place() -> None:
    assert calculate_progress_percent(1, 3) == 33.3


def test_progress_guards_against_a_non_positive_target() -> None:
    assert calculate_progress_percent(100, 0) == 0.0


# --- remaining amount --------------------------------------------------------------


def test_remaining_matches_spec_example() -> None:
    # Target 1,50,000 / current 45,000 -> remaining 1,05,000
    assert calculate_remaining_minor(4500000, 15000000) == 10500000


def test_remaining_is_zero_when_goal_is_complete() -> None:
    assert calculate_remaining_minor(15000000, 15000000) == 0


def test_remaining_never_goes_negative() -> None:
    # Defensive only - overfunding is rejected upstream by schema/DB validation.
    assert calculate_remaining_minor(20000, 10000) == 0


# --- days remaining ------------------------------------------------------------------


def test_days_remaining_is_positive_for_a_future_target_date() -> None:
    assert calculate_days_remaining(date(2026, 1, 10), date(2026, 1, 1)) == 9


def test_days_remaining_is_zero_when_target_date_is_today() -> None:
    assert calculate_days_remaining(date(2026, 1, 1), date(2026, 1, 1)) == 0


def test_days_remaining_is_negative_for_a_past_target_date() -> None:
    assert calculate_days_remaining(date(2025, 12, 25), date(2026, 1, 1)) == -7


# --- required monthly / weekly savings --------------------------------------------


def test_required_savings_is_zero_when_goal_already_completed() -> None:
    assert calculate_required_savings(0, 100) == (0, 0)


def test_completed_goal_is_zero_even_with_a_past_target_date() -> None:
    # A completed goal needs nothing further, regardless of the date.
    assert calculate_required_savings(0, -30) == (0, 0)


def test_required_savings_is_undefined_when_target_date_is_today() -> None:
    assert calculate_required_savings(10000, 0) == (None, None)


def test_required_savings_is_undefined_for_a_past_target_date() -> None:
    assert calculate_required_savings(10000, -10) == (None, None)


def test_required_savings_matches_spec_style_example() -> None:
    # Remaining 1,05,000 over 300 days (~10 months) -> clean divisors.
    monthly, weekly = calculate_required_savings(10500000, 300)
    assert monthly == 1050000  # 10,500/month
    assert weekly == 245000  # 2,450/week


def test_required_savings_rounds_to_the_nearest_minor_unit() -> None:
    # 1000 * 30 / 7 = 4285.71... -> 4286; 1000 * 7 / 7 = 1000.0 exactly.
    monthly, weekly = calculate_required_savings(1000, 7)
    assert monthly == 4286
    assert weekly == 1000


def test_required_savings_handles_a_very_small_remaining_amount() -> None:
    # 1 minor unit spread over a year rounds down to 0 for both periods.
    monthly, weekly = calculate_required_savings(1, 365)
    assert monthly == 0
    assert weekly == 0
