from datetime import date

from app.models.recurring_transaction import RecurrenceFrequency
from app.services.subscription_calculations import (
    LOOKBACK_DAYS,
    MIN_SUBSCRIPTION_AGE_DAYS,
    calculate_monthly_cost_minor,
    calculate_yearly_cost_minor,
    evaluate_unused_evidence,
)

# --- monthly / yearly cost: every frequency ----------------------------------------


def test_monthly_frequency_monthly_cost_is_the_amount_itself() -> None:
    assert calculate_monthly_cost_minor(64900, RecurrenceFrequency.MONTHLY) == 64900


def test_monthly_frequency_yearly_cost_is_twelve_times() -> None:
    assert calculate_yearly_cost_minor(64900, RecurrenceFrequency.MONTHLY) == 778800


def test_spec_worked_example_four_monthly_subscriptions() -> None:
    # Netflix 649 + Spotify 119 + Adobe 1675 + GitHub 400 = 2843/month,
    # 34116/year - the spec's own worked totals.
    amounts = [64900, 11900, 167500, 40000]
    monthly_total = sum(
        calculate_monthly_cost_minor(a, RecurrenceFrequency.MONTHLY) for a in amounts
    )
    yearly_total = sum(calculate_yearly_cost_minor(a, RecurrenceFrequency.MONTHLY) for a in amounts)
    assert monthly_total == 284300
    assert yearly_total == 3411600


def test_yearly_frequency_yearly_cost_is_the_amount_itself() -> None:
    assert calculate_yearly_cost_minor(120000, RecurrenceFrequency.YEARLY) == 120000


def test_yearly_frequency_monthly_cost_is_one_twelfth() -> None:
    assert calculate_monthly_cost_minor(120000, RecurrenceFrequency.YEARLY) == 10000


def test_yearly_frequency_monthly_cost_rounds() -> None:
    # 100000 / 12 = 8333.33... -> 8333
    assert calculate_monthly_cost_minor(100000, RecurrenceFrequency.YEARLY) == 8333


def test_quarterly_frequency_yearly_cost_is_four_times() -> None:
    assert calculate_yearly_cost_minor(30000, RecurrenceFrequency.QUARTERLY) == 120000


def test_quarterly_frequency_monthly_cost_is_one_third() -> None:
    assert calculate_monthly_cost_minor(30000, RecurrenceFrequency.QUARTERLY) == 10000


def test_quarterly_frequency_monthly_cost_rounds() -> None:
    # 10000 / 3 = 3333.33... -> 3333
    assert calculate_monthly_cost_minor(10000, RecurrenceFrequency.QUARTERLY) == 3333


def test_weekly_frequency_yearly_cost_is_fifty_two_times() -> None:
    assert calculate_yearly_cost_minor(10000, RecurrenceFrequency.WEEKLY) == 520000


def test_weekly_frequency_monthly_cost() -> None:
    # 10000 * 52 / 12 = 43333.33... -> 43333
    assert calculate_monthly_cost_minor(10000, RecurrenceFrequency.WEEKLY) == 43333


def test_daily_frequency_yearly_cost_is_365_times() -> None:
    assert calculate_yearly_cost_minor(500, RecurrenceFrequency.DAILY) == 182500


def test_daily_frequency_monthly_cost() -> None:
    # 500 * 365 / 12 = 15208.33... -> 15208
    assert calculate_monthly_cost_minor(500, RecurrenceFrequency.DAILY) == 15208


# --- unused-subscription evidence rule ----------------------------------------------


def test_no_billing_history_is_insufficient_data() -> None:
    result = evaluate_unused_evidence(
        own_billing_dates=[], other_category_activity_dates=[], today=date(2026, 6, 1)
    )
    assert result.is_possibly_unused is None
    assert "hasn't been billed yet" in result.reason


def test_recently_created_subscription_is_insufficient_data_even_with_no_other_activity() -> None:
    today = date(2026, 6, 1)
    first_billed = today  # billed today - zero days of history
    result = evaluate_unused_evidence(
        own_billing_dates=[first_billed],
        other_category_activity_dates=[],
        today=today,
    )
    assert result.is_possibly_unused is None
    assert str(MIN_SUBSCRIPTION_AGE_DAYS) in result.reason


def test_just_under_the_minimum_age_is_still_insufficient_data() -> None:
    today = date(2026, 6, 1)
    first_billed = today.fromordinal(today.toordinal() - (MIN_SUBSCRIPTION_AGE_DAYS - 1))
    result = evaluate_unused_evidence(
        own_billing_dates=[first_billed], other_category_activity_dates=[], today=today
    )
    assert result.is_possibly_unused is None


def test_exactly_the_minimum_age_with_no_recent_activity_is_flagged_unused() -> None:
    today = date(2026, 6, 1)
    first_billed = today.fromordinal(today.toordinal() - MIN_SUBSCRIPTION_AGE_DAYS)
    result = evaluate_unused_evidence(
        own_billing_dates=[first_billed], other_category_activity_dates=[], today=today
    )
    assert result.is_possibly_unused is True
    assert str(LOOKBACK_DAYS) in result.reason


def test_old_enough_subscription_with_recent_category_activity_is_not_flagged() -> None:
    today = date(2026, 6, 1)
    first_billed = today.fromordinal(today.toordinal() - 200)
    recent_activity = today.fromordinal(today.toordinal() - 10)
    result = evaluate_unused_evidence(
        own_billing_dates=[first_billed],
        other_category_activity_dates=[recent_activity],
        today=today,
    )
    assert result.is_possibly_unused is False
    assert "Found 1 other transaction" in result.reason


def test_activity_exactly_at_the_lookback_boundary_counts() -> None:
    today = date(2026, 6, 1)
    first_billed = today.fromordinal(today.toordinal() - 200)
    boundary_activity = today.fromordinal(today.toordinal() - LOOKBACK_DAYS)
    result = evaluate_unused_evidence(
        own_billing_dates=[first_billed],
        other_category_activity_dates=[boundary_activity],
        today=today,
    )
    assert result.is_possibly_unused is False


def test_activity_just_outside_the_lookback_window_does_not_count() -> None:
    today = date(2026, 6, 1)
    first_billed = today.fromordinal(today.toordinal() - 200)
    old_activity = today.fromordinal(today.toordinal() - (LOOKBACK_DAYS + 1))
    result = evaluate_unused_evidence(
        own_billing_dates=[first_billed],
        other_category_activity_dates=[old_activity],
        today=today,
    )
    assert result.is_possibly_unused is True


def test_multiple_own_billing_dates_uses_the_earliest_for_age() -> None:
    today = date(2026, 6, 1)
    older = today.fromordinal(today.toordinal() - 200)
    newer = today.fromordinal(today.toordinal() - 30)
    result = evaluate_unused_evidence(
        own_billing_dates=[newer, older], other_category_activity_dates=[], today=today
    )
    # Age is judged from the earliest (200 days), not the newest (30 days),
    # so this is old enough to draw a conclusion.
    assert result.is_possibly_unused is True
