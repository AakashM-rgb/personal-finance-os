"""The one shared money-formatting convention for exports (CSV/Excel/PDF)
- mirrors frontend/lib/money.ts's DECIMALS_BY_CURRENCY table exactly, so
an exported amount always matches what the same figure shows as on
screen. Pure, no I/O."""

_DECIMALS_BY_CURRENCY = {
    "INR": 2,
    "USD": 2,
    "EUR": 2,
    "GBP": 2,
    "JPY": 0,
}


def decimals_for(currency: str) -> int:
    return _DECIMALS_BY_CURRENCY.get(currency, 2)


def minor_to_major(amount_minor: int, currency: str) -> float:
    """Integer minor units to a plain float major-unit amount - used only
    for display/export rendering, never for stored or summed money."""
    return amount_minor / (10 ** decimals_for(currency))


def format_money(amount_minor: int, currency: str) -> str:
    """A plain decimal string with the currency code, e.g. "649.00 INR" -
    used in CSV/PDF cells where a locale-aware symbol isn't worth the
    ambiguity a plain code avoids."""
    decimals = decimals_for(currency)
    return f"{minor_to_major(amount_minor, currency):.{decimals}f} {currency}"
