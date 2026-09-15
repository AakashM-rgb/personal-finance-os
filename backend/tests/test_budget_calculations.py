from app.services.budget_calculations import (
    BudgetStatus,
    build_warning_message,
    determine_budget_status,
    project_monthly_amount,
)

# --- status thresholds ----------------------------------------------------------


def test_zero_percent_is_healthy() -> None:
    assert determine_budget_status(0.0) == BudgetStatus.HEALTHY


def test_just_under_warning_threshold_is_healthy() -> None:
    assert determine_budget_status(69.9) == BudgetStatus.HEALTHY


def test_exactly_seventy_percent_is_warning() -> None:
    assert determine_budget_status(70.0) == BudgetStatus.WARNING


def test_just_under_near_limit_threshold_is_warning() -> None:
    assert determine_budget_status(89.9) == BudgetStatus.WARNING


def test_exactly_ninety_percent_is_near_limit() -> None:
    assert determine_budget_status(90.0) == BudgetStatus.NEAR_LIMIT


def test_just_under_hundred_percent_is_near_limit() -> None:
    assert determine_budget_status(99.9) == BudgetStatus.NEAR_LIMIT


def test_exactly_hundred_percent_is_exceeded() -> None:
    assert determine_budget_status(100.0) == BudgetStatus.EXCEEDED


def test_over_hundred_percent_is_exceeded() -> None:
    assert determine_budget_status(150.0) == BudgetStatus.EXCEEDED


# --- warning messages -------------------------------------------------------------


def test_healthy_budget_has_no_warning_message() -> None:
    assert build_warning_message("Food", 40.0, BudgetStatus.HEALTHY) is None


def test_warning_status_produces_a_percent_message() -> None:
    message = build_warning_message("Food", 85.0, BudgetStatus.WARNING)
    assert message == "You've used 85% of your Food budget."


def test_near_limit_status_produces_a_percent_message() -> None:
    message = build_warning_message("Food", 92.0, BudgetStatus.NEAR_LIMIT)
    assert message == "You've used 92% of your Food budget."


def test_exceeded_status_uses_distinct_wording() -> None:
    message = build_warning_message("Food", 130.0, BudgetStatus.EXCEEDED)
    assert message == "You've exceeded your Food budget (130% used)."


# --- monthly projection ------------------------------------------------------------


def test_projection_is_daily_average_times_days_in_month() -> None:
    # 5000 spent over 10 days -> 500/day; 30-day month -> 15000 projected
    assert project_monthly_amount(5000, days_elapsed=10, days_in_month=30) == 15000


def test_projection_with_zero_spending_is_zero() -> None:
    assert project_monthly_amount(0, days_elapsed=10, days_in_month=30) == 0


def test_projection_guards_against_zero_days_elapsed() -> None:
    assert project_monthly_amount(5000, days_elapsed=0, days_in_month=30) == 0


def test_projection_on_the_last_day_equals_spending_so_far() -> None:
    assert project_monthly_amount(12345, days_elapsed=30, days_in_month=30) == 12345


def test_projection_rounds_to_the_nearest_minor_unit() -> None:
    # 1000 / 3 days = 333.33.../day * 31 days = 10333.33... -> rounds to 10333
    assert project_monthly_amount(1000, days_elapsed=3, days_in_month=31) == 10333
