"""app.services.export_formatting: the money strings every CSV/PDF export and
the demo AI assistant print.

`minor_to_major` divides integer paise as a float, which is only safe because
of the bound on what can be stored: at MAX_MONEY_MINOR (Rs 1,00,00,00,00,000)
a double's error is ~1e-5 of a rupee while a paise value is always >= 0.005
from a 2-decimal rounding boundary. These tests pin that, with exact Decimal
arithmetic as the oracle, so a change to either side can't silently start
printing the wrong paisa."""

from decimal import Decimal

import pytest

from app.schemas.money import MAX_MONEY_MINOR
from app.services.export_formatting import decimals_for, format_money, minor_to_major


def _exact(amount_minor: int, currency: str) -> str:
    places = decimals_for(currency)
    major = Decimal(amount_minor).scaleb(-places)
    return f"{major:.{places}f} {currency}"


@pytest.mark.parametrize(
    ("amount_minor", "expected"),
    [
        (0, "0.00 INR"),
        (1, "0.01 INR"),  # one paisa
        (64900, "649.00 INR"),  # a monthly subscription
        (240_100, "2401.00 INR"),  # the CLAUDE.md split example
        (-500_000, "-5000.00 INR"),  # a card in credit
        (12_345_67, "12345.67 INR"),
        (MAX_MONEY_MINOR, "100000000000.00 INR"),
        (-MAX_MONEY_MINOR, "-100000000000.00 INR"),
        (MAX_MONEY_MINOR - 1, "99999999999.99 INR"),
    ],
)
def test_inr_amounts_print_to_the_exact_paisa(amount_minor: int, expected: str) -> None:
    assert format_money(amount_minor, "INR") == expected


def test_jpy_has_no_minor_digits() -> None:
    assert format_money(1500, "JPY") == "1500 JPY"


@pytest.mark.parametrize(
    "amount_minor",
    [
        # Values whose /100 is a non-terminating binary fraction, spread across
        # the whole accepted range, plus the edges.
        *[value + cents for value in (0, 10**6, 10**9, 10**12) for cents in (1, 5, 10, 33, 99)],
        MAX_MONEY_MINOR - 1,
        MAX_MONEY_MINOR - 99,
        -(MAX_MONEY_MINOR - 1),
    ],
)
def test_float_formatting_matches_exact_decimal_across_the_accepted_range(
    amount_minor: int,
) -> None:
    assert format_money(amount_minor, "INR") == _exact(amount_minor, "INR")


def test_minor_to_major_is_only_a_display_value() -> None:
    """It feeds spreadsheet cells, which are doubles anyway; the integer
    value round-trips at the bound."""
    assert round(minor_to_major(MAX_MONEY_MINOR - 1, "INR") * 100) == MAX_MONEY_MINOR - 1
