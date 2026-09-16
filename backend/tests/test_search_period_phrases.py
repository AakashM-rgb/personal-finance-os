from datetime import UTC, date, datetime

import pytest

from app.search.period_phrases import (
    resolve_month_keyword,
    resolve_named_month,
    resolve_relative_period,
)

_NOW = datetime(2026, 3, 15, tzinfo=UTC)  # a Sunday


def test_today() -> None:
    result = resolve_relative_period("today", now=_NOW)
    assert result is not None
    assert result.start_date == result.end_date == date(2026, 3, 15)


def test_yesterday() -> None:
    result = resolve_relative_period("yesterday", now=_NOW)
    assert result is not None
    assert result.start_date == result.end_date == date(2026, 3, 14)


def test_yesterday_across_month_boundary() -> None:
    result = resolve_relative_period("yesterday", now=datetime(2026, 3, 1, tzinfo=UTC))
    assert result is not None
    assert result.start_date == date(2026, 2, 28)


def test_this_week_monday_to_sunday() -> None:
    result = resolve_relative_period("this week", now=_NOW)
    assert result is not None
    # 2026-03-15 is a Sunday; the week is Mon 03-09 to Sun 03-15.
    assert result.start_date == date(2026, 3, 9)
    assert result.end_date == date(2026, 3, 15)


def test_last_week() -> None:
    result = resolve_relative_period("last week", now=_NOW)
    assert result is not None
    assert result.start_date == date(2026, 3, 2)
    assert result.end_date == date(2026, 3, 8)


def test_this_month() -> None:
    result = resolve_relative_period("this month", now=_NOW)
    assert result is not None
    assert result.start_date == date(2026, 3, 1)
    assert result.end_date == date(2026, 3, 31)


def test_last_month() -> None:
    result = resolve_relative_period("last month", now=_NOW)
    assert result is not None
    assert result.start_date == date(2026, 2, 1)
    assert result.end_date == date(2026, 2, 28)


def test_last_month_across_year_boundary() -> None:
    result = resolve_relative_period("last month", now=datetime(2026, 1, 15, tzinfo=UTC))
    assert result is not None
    assert result.start_date == date(2025, 12, 1)
    assert result.end_date == date(2025, 12, 31)


def test_this_year_is_year_to_date() -> None:
    result = resolve_relative_period("this year", now=_NOW)
    assert result is not None
    assert result.start_date == date(2026, 1, 1)
    assert result.end_date == date(2026, 3, 15)


def test_last_year_is_full_calendar_year() -> None:
    result = resolve_relative_period("last year", now=_NOW)
    assert result is not None
    assert result.start_date == date(2025, 1, 1)
    assert result.end_date == date(2025, 12, 31)


def test_unrecognized_keyword_returns_none() -> None:
    assert resolve_relative_period("next tuesday", now=_NOW) is None


def test_leap_year_february_last_month() -> None:
    # 2024 is a leap year - "last month" from March 2024 must resolve to
    # Feb 1-29, not Feb 1-28.
    result = resolve_relative_period("last month", now=datetime(2024, 3, 10, tzinfo=UTC))
    assert result is not None
    assert result.end_date == date(2024, 2, 29)


# --- named months -------------------------------------------------------------------


def test_named_month_already_passed_this_year_uses_current_year() -> None:
    # "now" is March 2026; January has already happened this year.
    result = resolve_named_month(1, now=_NOW)
    assert result.start_date == date(2026, 1, 1)
    assert result.end_date == date(2026, 1, 31)
    assert result.label == "January 2026"


def test_named_month_is_current_month_uses_current_year() -> None:
    result = resolve_named_month(3, now=_NOW)
    assert result.start_date == date(2026, 3, 1)


def test_named_month_not_yet_happened_this_year_uses_previous_year() -> None:
    # "now" is March 2026; August hasn't happened yet this year.
    result = resolve_named_month(8, now=_NOW)
    assert result.start_date == date(2025, 8, 1)
    assert result.end_date == date(2025, 8, 31)
    assert result.label == "August 2025"


def test_named_month_december_from_january() -> None:
    result = resolve_named_month(12, now=datetime(2026, 1, 5, tzinfo=UTC))
    assert result.start_date == date(2025, 12, 1)
    assert result.end_date == date(2025, 12, 31)


@pytest.mark.parametrize(
    "keyword,expected_month",
    [
        ("aug", 8),
        ("August", 8),
        ("  august  ", 8),
        ("AUGUST", 8),
        ("jan", 1),
        ("sept", 9),
        ("dec", 12),
    ],
)
def test_month_keyword_case_and_whitespace_insensitive(keyword: str, expected_month: int) -> None:
    result = resolve_month_keyword(keyword, now=_NOW)
    assert result is not None
    assert result.start_date.month == expected_month


def test_unrecognized_month_keyword_returns_none() -> None:
    assert resolve_month_keyword("smarch", now=_NOW) is None
