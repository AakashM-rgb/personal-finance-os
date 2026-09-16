from datetime import UTC, datetime

import pytest

from app.ai.tools.period_resolution import resolve_period, validate_custom_range


def test_current_month_default() -> None:
    now = datetime(2026, 3, 15, tzinfo=UTC)
    date_from, date_to, label = resolve_period(None, now=now)
    assert date_from == datetime(2026, 3, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 4, 1, tzinfo=UTC)
    assert label == "March 2026"


def test_current_month_explicit() -> None:
    now = datetime(2026, 3, 15, tzinfo=UTC)
    date_from, date_to, _label = resolve_period("current_month", now=now)
    assert date_from == datetime(2026, 3, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 4, 1, tzinfo=UTC)


def test_previous_month() -> None:
    now = datetime(2026, 3, 15, tzinfo=UTC)
    date_from, date_to, label = resolve_period("previous_month", now=now)
    assert date_from == datetime(2026, 2, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 3, 1, tzinfo=UTC)
    assert label == "February 2026"


def test_previous_month_across_year_boundary() -> None:
    now = datetime(2026, 1, 15, tzinfo=UTC)
    date_from, date_to, label = resolve_period("previous_month", now=now)
    assert date_from == datetime(2025, 12, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 1, 1, tzinfo=UTC)
    assert label == "December 2025"


def test_explicit_year_month() -> None:
    now = datetime(2026, 3, 15, tzinfo=UTC)
    date_from, date_to, label = resolve_period("2025-11", now=now)
    assert date_from == datetime(2025, 11, 1, tzinfo=UTC)
    assert date_to == datetime(2025, 12, 1, tzinfo=UTC)
    assert label == "November 2025"


def test_explicit_december_rolls_into_next_january() -> None:
    now = datetime(2026, 3, 15, tzinfo=UTC)
    date_from, date_to, _label = resolve_period("2025-12", now=now)
    assert date_from == datetime(2025, 12, 1, tzinfo=UTC)
    assert date_to == datetime(2026, 1, 1, tzinfo=UTC)


@pytest.mark.parametrize(
    "bad_period",
    ["2026-13", "2026-00", "not-a-period", "2026/03", "26-03", "", "2026-3"],
)
def test_invalid_period_strings_raise(bad_period: str) -> None:
    now = datetime(2026, 3, 15, tzinfo=UTC)
    with pytest.raises(ValueError):
        resolve_period(bad_period, now=now)


def test_month_out_of_range_never_silently_rolls_over() -> None:
    """month_start() itself normalizes an out-of-range month (13 rolls into
    next January) - resolve_period must reject this before that happens,
    never silently reinterpret an invalid month as a different one."""
    now = datetime(2026, 3, 15, tzinfo=UTC)
    with pytest.raises(ValueError):
        resolve_period("2026-13", now=now)


def test_year_out_of_supported_range_raises() -> None:
    now = datetime(2026, 3, 15, tzinfo=UTC)
    with pytest.raises(ValueError):
        resolve_period("1899-01", now=now)
    with pytest.raises(ValueError):
        resolve_period("2200-01", now=now)


def test_validate_custom_range_accepts_valid_range() -> None:
    validate_custom_range(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 2, 1, tzinfo=UTC))


def test_validate_custom_range_rejects_backwards_range() -> None:
    with pytest.raises(ValueError):
        validate_custom_range(datetime(2026, 2, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))


def test_validate_custom_range_rejects_equal_bounds() -> None:
    with pytest.raises(ValueError):
        validate_custom_range(datetime(2026, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))


def test_validate_custom_range_rejects_unbounded_span() -> None:
    with pytest.raises(ValueError):
        validate_custom_range(datetime(2020, 1, 1, tzinfo=UTC), datetime(2026, 1, 1, tzinfo=UTC))
