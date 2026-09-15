from datetime import UTC, date, datetime, timedelta

import pytest

from app.services.analytics_calculations import (
    AnalyticsRangePreset,
    Granularity,
    TrendDirection,
    determine_trend,
    generate_day_periods,
    generate_month_periods,
    resolve_date_range,
    resolve_granularity,
)

_NOW = datetime(2026, 9, 15, 12, 0, tzinfo=UTC)  # September 15, 2026

# --- resolve_date_range: presets -----------------------------------------------------


def test_current_month_range() -> None:
    date_from, date_to = resolve_date_range(AnalyticsRangePreset.CURRENT_MONTH, now=_NOW)
    assert date_from == datetime(2026, 9, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 10, 1, tzinfo=UTC)


def test_previous_month_range() -> None:
    date_from, date_to = resolve_date_range(AnalyticsRangePreset.PREVIOUS_MONTH, now=_NOW)
    assert date_from == datetime(2026, 8, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 9, 1, tzinfo=UTC)


def test_previous_month_range_across_a_year_boundary() -> None:
    date_from, date_to = resolve_date_range(
        AnalyticsRangePreset.PREVIOUS_MONTH, now=datetime(2026, 1, 15, tzinfo=UTC)
    )
    assert date_from == datetime(2025, 12, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 1, 1, tzinfo=UTC)


def test_last_3_months_includes_the_current_partial_month() -> None:
    date_from, date_to = resolve_date_range(AnalyticsRangePreset.LAST_3_MONTHS, now=_NOW)
    # July, August, September (current) - 3 calendar months total.
    assert date_from == datetime(2026, 7, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 10, 1, tzinfo=UTC)


def test_last_6_months() -> None:
    date_from, date_to = resolve_date_range(AnalyticsRangePreset.LAST_6_MONTHS, now=_NOW)
    assert date_from == datetime(2026, 4, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 10, 1, tzinfo=UTC)


def test_last_12_months_spans_a_year_boundary() -> None:
    date_from, date_to = resolve_date_range(AnalyticsRangePreset.LAST_12_MONTHS, now=_NOW)
    assert date_from == datetime(2025, 10, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 10, 1, tzinfo=UTC)


# --- resolve_date_range: custom -------------------------------------------------------


def test_custom_range_is_inclusive_of_the_end_date() -> None:
    date_from, date_to = resolve_date_range(
        AnalyticsRangePreset.CUSTOM,
        now=_NOW,
        custom_from=date(2026, 5, 1),
        custom_to=date(2026, 5, 31),
    )
    assert date_from == datetime(2026, 5, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 6, 1, tzinfo=UTC)  # exclusive, covers all of May 31


def test_custom_range_single_day() -> None:
    date_from, date_to = resolve_date_range(
        AnalyticsRangePreset.CUSTOM,
        now=_NOW,
        custom_from=date(2026, 5, 10),
        custom_to=date(2026, 5, 10),
    )
    assert date_from == datetime(2026, 5, 10, tzinfo=UTC)
    assert date_to == datetime(2026, 5, 11, tzinfo=UTC)


def test_custom_range_requires_both_dates() -> None:
    with pytest.raises(ValueError, match="required"):
        resolve_date_range(AnalyticsRangePreset.CUSTOM, now=_NOW, custom_from=date(2026, 5, 1))


def test_custom_range_rejects_from_after_to() -> None:
    with pytest.raises(ValueError, match="must not be after"):
        resolve_date_range(
            AnalyticsRangePreset.CUSTOM,
            now=_NOW,
            custom_from=date(2026, 5, 31),
            custom_to=date(2026, 5, 1),
        )


# --- resolve_granularity --------------------------------------------------------------


def test_granularity_is_daily_for_current_month() -> None:
    date_from, date_to = resolve_date_range(AnalyticsRangePreset.CURRENT_MONTH, now=_NOW)
    assert resolve_granularity(date_from, date_to) == Granularity.DAY


def test_granularity_is_monthly_for_last_3_months() -> None:
    date_from, date_to = resolve_date_range(AnalyticsRangePreset.LAST_3_MONTHS, now=_NOW)
    assert resolve_granularity(date_from, date_to) == Granularity.MONTH


def test_granularity_boundary_at_exactly_the_threshold_is_daily() -> None:
    date_from = datetime(2026, 1, 1, tzinfo=UTC)
    date_to = date_from + timedelta(days=62)
    assert resolve_granularity(date_from, date_to) == Granularity.DAY


def test_granularity_just_over_the_threshold_is_monthly() -> None:
    date_from = datetime(2026, 1, 1, tzinfo=UTC)
    date_to = date_from + timedelta(days=63)
    assert resolve_granularity(date_from, date_to) == Granularity.MONTH


# --- generate_day_periods / generate_month_periods ------------------------------------


def test_generate_day_periods_covers_every_day_in_a_short_range() -> None:
    date_from = datetime(2026, 9, 1, tzinfo=UTC)
    date_to = datetime(2026, 9, 4, tzinfo=UTC)
    assert generate_day_periods(date_from, date_to) == [
        date(2026, 9, 1),
        date(2026, 9, 2),
        date(2026, 9, 3),
    ]


def test_generate_day_periods_empty_range() -> None:
    same = datetime(2026, 9, 1, tzinfo=UTC)
    assert generate_day_periods(same, same) == []


def test_generate_month_periods_covers_every_month() -> None:
    date_from = datetime(2026, 7, 1, tzinfo=UTC)
    date_to = datetime(2026, 10, 1, tzinfo=UTC)
    assert generate_month_periods(date_from, date_to) == [
        date(2026, 7, 1),
        date(2026, 8, 1),
        date(2026, 9, 1),
    ]


def test_generate_month_periods_across_a_year_boundary() -> None:
    date_from = datetime(2025, 11, 1, tzinfo=UTC)
    date_to = datetime(2026, 2, 1, tzinfo=UTC)
    assert generate_month_periods(date_from, date_to) == [
        date(2025, 11, 1),
        date(2025, 12, 1),
        date(2026, 1, 1),
    ]


# --- determine_trend -------------------------------------------------------------------


def test_trend_is_none_with_fewer_than_two_points() -> None:
    assert determine_trend([]).direction is None
    assert determine_trend([100]).direction is None


def test_trend_is_flat_when_both_halves_are_zero() -> None:
    result = determine_trend([0, 0, 0, 0])
    assert result.direction == TrendDirection.FLAT
    assert result.percent_change == 0.0


def test_trend_is_increasing_from_zero() -> None:
    result = determine_trend([0, 0, 100, 100])
    assert result.direction == TrendDirection.INCREASING
    assert result.percent_change is None


def test_trend_is_increasing() -> None:
    result = determine_trend([1000, 1000, 2000, 2000])
    assert result.direction == TrendDirection.INCREASING
    assert result.percent_change == 100.0


def test_trend_is_decreasing() -> None:
    result = determine_trend([2000, 2000, 1000, 1000])
    assert result.direction == TrendDirection.DECREASING
    assert result.percent_change == -50.0


def test_trend_is_flat_within_the_threshold() -> None:
    # 1000 -> 1005 is 0.5% change, under the 1% flat threshold.
    result = determine_trend([1000, 1005])
    assert result.direction == TrendDirection.FLAT


def test_trend_just_outside_the_flat_threshold_is_increasing() -> None:
    # 1000 -> 1010 is exactly 1.0%, not < 1.0%, so it counts as a real trend.
    result = determine_trend([1000, 1010])
    assert result.direction == TrendDirection.INCREASING
    assert result.percent_change == 1.0


def test_trend_uses_averages_for_unequal_halves() -> None:
    # first half [100] avg=100; second half [100, 300] avg=200 -> +100%.
    result = determine_trend([100, 100, 300])
    assert result.direction == TrendDirection.INCREASING
    assert result.percent_change == 100.0


def test_trend_with_a_negative_baseline_improving_is_increasing_not_decreasing() -> None:
    # A deficit of -100 improving to -50 is a real increase (less
    # negative) - a naive percent-of-baseline calculation would get this
    # backwards, since (-50 - -100) / -100 * 100 = -50% (looks negative).
    result = determine_trend([-100, -100, -50, -50])
    assert result.direction == TrendDirection.INCREASING
    assert result.percent_change is None  # no meaningful % of a negative baseline


def test_trend_with_a_negative_baseline_worsening_is_decreasing() -> None:
    # A deficit of -50 worsening to -100 is a real decrease.
    result = determine_trend([-50, -50, -100, -100])
    assert result.direction == TrendDirection.DECREASING
    assert result.percent_change is None


def test_trend_crossing_from_negative_to_positive_is_increasing() -> None:
    result = determine_trend([-100, -100, 100, 100])
    assert result.direction == TrendDirection.INCREASING
    assert result.percent_change is None


def test_trend_flat_with_an_unchanged_negative_baseline() -> None:
    result = determine_trend([-100, -100, -100, -100])
    assert result.direction == TrendDirection.FLAT
    assert result.percent_change is None
