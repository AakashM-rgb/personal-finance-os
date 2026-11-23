"""Unit tests for the canonical credit-card figures in
app.services.account_service: utilization, available credit and the
over-limit amount.

These are the numbers every card view shows, so they are pinned here with
plain values rather than only through the API, and in one place because the
account response, the dashboard and the health score all read the same
functions (CLAUDE.md §13: one canonical formula, reused everywhere).
"""

import pytest

from app.services.account_service import (
    calculate_available_credit_minor,
    calculate_credit_utilization_percent,
    calculate_over_limit_minor,
)

LIMIT = 100_000_00


@pytest.mark.parametrize(
    ("owed", "expected"),
    [
        (0, 0.0),
        (25_000_00, 25.0),
        (LIMIT, 100.0),
        (120_000_00, 120.0),  # over limit is reported, never clamped or hidden
        (-5_000_00, 0.0),  # a credit balance owes nothing
    ],
)
def test_utilization_reflects_the_amount_owed(owed: int, expected: float) -> None:
    assert calculate_credit_utilization_percent(owed, LIMIT) == expected


def test_utilization_guards_a_zero_or_missing_limit() -> None:
    """Division by zero would otherwise crash every card view."""
    assert calculate_credit_utilization_percent(5_000_00, 0) == 0.0
    assert calculate_credit_utilization_percent(5_000_00, -1) == 0.0


@pytest.mark.parametrize(
    ("owed", "expected"),
    [
        (0, LIMIT),
        (25_000_00, 75_000_00),
        (LIMIT, 0),
        (120_000_00, 0),  # over limit: nothing available, never a negative figure
        (-5_000_00, LIMIT + 5_000_00),  # overpaid: the overpayment is real spending power
    ],
)
def test_available_credit_is_never_negative(owed: int, expected: int) -> None:
    assert calculate_available_credit_minor(owed, LIMIT) == expected


@pytest.mark.parametrize(
    ("owed", "expected"),
    [
        (0, 0),
        (LIMIT, 0),  # exactly on the limit is not over it
        (120_000_00, 20_000_00),
        (-5_000_00, 0),
    ],
)
def test_over_limit_reports_only_the_overshoot(owed: int, expected: int) -> None:
    assert calculate_over_limit_minor(owed, LIMIT) == expected


def test_over_limit_guards_a_zero_or_missing_limit() -> None:
    assert calculate_over_limit_minor(5_000_00, 0) == 0
    assert calculate_over_limit_minor(5_000_00, -1) == 0


@pytest.mark.parametrize("owed", [-5_000_00, 0, 25_000_00, LIMIT, 120_000_00])
def test_available_and_over_limit_are_never_both_non_zero(owed: int) -> None:
    """They describe the same gap from opposite sides, so a view can show one
    or the other without ever contradicting itself."""
    available = calculate_available_credit_minor(owed, LIMIT)
    over = calculate_over_limit_minor(owed, LIMIT)

    assert available >= 0 and over >= 0
    assert available == 0 or over == 0
    if over:
        assert owed - LIMIT == over
