"""Pure, DB-free text-parsing helpers behind the mock OCR provider (see
app.ocr.mock) - kept separate and pure so every extraction rule is
unit-testable with plain strings, the same pattern as
app.services.budget_calculations / app.services.recurrence.

These are deliberately simple, documented heuristics over REAL text (never
fabricated) - a mock provider's job is to be honest about what it can and
cannot find, not to simulate a real OCR/ML engine's sophistication.
"""

import re
from datetime import date, datetime

from app.ocr.base import OcrItem

_MONTH_NAMES = (
    "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
    "|january|february|march|april|june|july|august|september|october|november|december"
)
_DATE_PATTERNS = [
    (re.compile(r"\b(\d{4})-(\d{1,2})-(\d{1,2})\b"), "ymd"),
    (re.compile(r"\b(\d{1,2})/(\d{1,2})/(\d{4})\b"), "dmy_slash"),
    (re.compile(r"\b(\d{1,2})-(\d{1,2})-(\d{4})\b"), "dmy_dash"),
    (
        re.compile(rf"\b(\d{{1,2}})\s+({_MONTH_NAMES})[a-z]*\s+(\d{{4}})\b", re.IGNORECASE),
        "d_month_y",
    ),
]
_MONEY_TOKEN = re.compile(r"(?:Rs\.?|INR|₹|\$)?\s*([\d,]+\.\d{2}|[\d,]+)")
_ITEM_WITH_QTY = re.compile(
    r"^(?P<desc>[A-Za-z][A-Za-z0-9 '&/-]*?)\s{2,}(?P<qty>\d+(?:\.\d+)?)\s*x\s*"
    r"(?P<unit>[\d,]+\.\d{2})\s*each\s*=\s*(?P<total>[\d,]+\.\d{2})\s*$",
    re.IGNORECASE,
)
_ITEM_SIMPLE = re.compile(
    r"^(?P<desc>[A-Za-z][A-Za-z0-9 '&/-]*?)\s{2,}(?P<total>[\d,]+\.\d{2})\s*$"
)


def parse_money_to_minor(text: str) -> int | None:
    """Converts a money-looking token ("1,234.50", "999", "₹45.00") to
    integer minor units using only string/integer arithmetic - never
    `float(text) * 100`, which can misround exact monetary values."""
    match = _MONEY_TOKEN.search(text)
    if not match:
        return None
    cleaned = match.group(1).replace(",", "")
    if "." in cleaned:
        whole, _, fraction = cleaned.partition(".")
        fraction = (fraction + "00")[:2]
    else:
        whole, fraction = cleaned, "00"
    if not whole:
        return None
    try:
        return int(whole) * 100 + int(fraction)
    except ValueError:
        return None


def find_line_amount(lines: list[str], *, keyword_pattern: re.Pattern[str]) -> int | None:
    for line in lines:
        if keyword_pattern.search(line):
            amount = parse_money_to_minor(line)
            if amount is not None:
                return amount
    return None


def extract_merchant(lines: list[str]) -> str | None:
    """The merchant name is conventionally the first meaningful line on a
    printed receipt - the first non-empty line that isn't itself a
    date/total/tax label or a bare number."""
    label_pattern = re.compile(r"^(date|total|tax|gst|vat|items?|subtotal)\b", re.IGNORECASE)
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if label_pattern.match(stripped):
            continue
        if parse_money_to_minor(stripped) is not None and len(stripped) < 15:
            continue  # a bare amount, not a name
        return stripped
    return None


def extract_date(text: str) -> date | None:
    for pattern, kind in _DATE_PATTERNS:
        match = pattern.search(text)
        if not match:
            continue
        try:
            if kind == "ymd":
                year, month, day = match.groups()
                return date(int(year), int(month), int(day))
            if kind == "dmy_slash" or kind == "dmy_dash":
                day, month, year = match.groups()
                return date(int(year), int(month), int(day))
            if kind == "d_month_y":
                day, month_name, year = match.groups()
                parsed = datetime.strptime(f"{day} {month_name[:3]} {year}", "%d %b %Y")
                return parsed.date()
        except ValueError:
            continue
    return None


def extract_total_minor(lines: list[str]) -> int | None:
    """Prefers an explicit "grand total" line, then any "total" line that
    is not itself a "subtotal" line, taking the LAST such match - on a real
    receipt with multiple total-like lines (subtotal, tax, grand total),
    the grand total conventionally appears last."""
    grand_total_pattern = re.compile(r"grand\s*total", re.IGNORECASE)
    total_pattern = re.compile(r"(?<!sub)\btotal\b", re.IGNORECASE)

    amount = find_line_amount(lines, keyword_pattern=grand_total_pattern)
    if amount is not None:
        return amount

    last_amount = None
    for line in lines:
        if total_pattern.search(line):
            found = parse_money_to_minor(line)
            if found is not None:
                last_amount = found
    return last_amount


def extract_tax_minor(lines: list[str]) -> int | None:
    tax_pattern = re.compile(r"\b(tax|gst|vat)\b", re.IGNORECASE)
    return find_line_amount(lines, keyword_pattern=tax_pattern)


def extract_items(lines: list[str]) -> list[OcrItem]:
    """Recognizes exactly two deliberately simple, documented line shapes:
    "Description  2 x 45.00 each = 90.00" and "Description  45.00". Any
    line not matching either shape is simply not treated as an item -
    never guessed at."""
    items: list[OcrItem] = []
    for line in lines:
        match = _ITEM_WITH_QTY.match(line)
        if match:
            items.append(
                OcrItem(
                    description=match["desc"].strip(),
                    quantity=match["qty"],
                    unit_price_minor=parse_money_to_minor(match["unit"]),
                    line_total_minor=parse_money_to_minor(match["total"]),
                )
            )
            continue
        match = _ITEM_SIMPLE.match(line)
        if match:
            items.append(
                OcrItem(
                    description=match["desc"].strip(),
                    quantity=None,
                    unit_price_minor=None,
                    line_total_minor=parse_money_to_minor(match["total"]),
                )
            )
    return items
