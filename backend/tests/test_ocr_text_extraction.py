from app.ocr.text_extraction import (
    extract_date,
    extract_items,
    extract_merchant,
    extract_tax_minor,
    extract_total_minor,
    parse_money_to_minor,
)


def test_parse_money_to_minor_handles_thousands_separator_and_decimals() -> None:
    assert parse_money_to_minor("1,234.50") == 123450


def test_parse_money_to_minor_defaults_missing_fraction_to_zero_paise() -> None:
    assert parse_money_to_minor("999") == 99900


def test_parse_money_to_minor_strips_currency_symbols() -> None:
    assert parse_money_to_minor("Rs. 45.00") == 4500
    assert parse_money_to_minor("₹600.00") == 60000


def test_parse_money_to_minor_never_misrounds_exact_paise() -> None:
    # A float-based `int(float(x) * 100)` implementation can misround this
    # to 233649 due to binary floating-point representation error.
    assert parse_money_to_minor("2336.50") == 233650


def test_parse_money_to_minor_returns_none_for_no_number() -> None:
    assert parse_money_to_minor("no amount here") is None


def test_extract_total_minor_prefers_grand_total_over_subtotal() -> None:
    lines = ["Subtotal    500.00", "Tax    50.00", "Grand Total    550.00"]
    assert extract_total_minor(lines) == 55000


def test_extract_total_minor_ignores_subtotal_when_no_grand_total_present() -> None:
    lines = ["Subtotal    500.00", "Total    550.00"]
    assert extract_total_minor(lines) == 55000


def test_extract_tax_minor_finds_gst_line() -> None:
    assert extract_tax_minor(["GST    18.00", "Total    118.00"]) == 1800


def test_extract_merchant_skips_label_lines_and_bare_amounts() -> None:
    lines = ["", "Total", "42.00", "Corner Cafe", "Date: 2026-03-05"]
    assert extract_merchant(lines) == "Corner Cafe"


def test_extract_date_supports_iso_and_slash_and_named_month_formats() -> None:
    assert extract_date("Date: 2026-03-05").isoformat() == "2026-03-05"
    assert extract_date("05/03/2026").isoformat() == "2026-03-05"
    assert extract_date("5 March 2026").isoformat() == "2026-03-05"


def test_extract_items_recognizes_quantity_and_simple_lines_only() -> None:
    lines = [
        "Sandwich  2 x 150.00 each = 300.00",
        "Coffee            250.00",
        "not an item line",
    ]
    items = extract_items(lines)
    assert len(items) == 2

    sandwich = next(i for i in items if i.description == "Sandwich")
    assert sandwich.quantity == "2"
    assert sandwich.unit_price_minor == 15000
    assert sandwich.line_total_minor == 30000

    coffee = next(i for i in items if i.description == "Coffee")
    assert coffee.quantity is None
    assert coffee.line_total_minor == 25000
