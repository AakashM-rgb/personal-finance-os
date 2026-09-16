"""Deterministic intent classification for app.ai.provider.mock.MockProvider
- pure, DB-free, unit-testable string matching (same pattern as
app.services.quick_add_parser), never a real NLU model.

This is honest about being a fixed set of recognized question shapes, not
a general language-understanding system: anything that doesn't match one
of them classifies as Intent.UNSUPPORTED, and the mock provider must say so
explicitly rather than guess (CLAUDE.md - "the assistant must explicitly
say that the available financial data/tools are insufficient").
"""

import enum
import re
from dataclasses import dataclass


class Intent(enum.StrEnum):
    TOP_SPENDING = "top_spending"
    CATEGORY_SPENDING = "category_spending"
    COMPARE_MONTHS = "compare_months"
    BIGGEST_RECURRING = "biggest_recurring"
    SAVINGS_RECOMMENDATION = "savings_recommendation"
    AFFORDABILITY = "affordability"
    BUDGET_STATUS = "budget_status"
    ACCOUNT_BALANCES = "account_balances"
    TRANSACTIONS_LOOKUP = "transactions_lookup"
    UNSUPPORTED = "unsupported"


@dataclass(frozen=True)
class ClassifiedIntent:
    intent: Intent
    # A category-name-ish keyword pulled out of a "how much did I spend on
    # X" question - matched against the real category names a tool call
    # later returns, never against a hardcoded category list.
    keyword: str | None = None
    # A parsed rupee amount, for AFFORDABILITY - None means "afford" was
    # mentioned but no amount could be found in the question.
    amount_minor: int | None = None


_AFFORD_RE = re.compile(r"\bafford\b", re.IGNORECASE)
_SPENT_ON_RE = re.compile(
    r"\bspen[dt]\b.*?\bon\b\s+([a-zA-Z][a-zA-Z &]*?)(?:\s+(?:this|last|in|during)\b|[?.!]|$)",
    re.IGNORECASE,
)
_TOP_SPENDING_RE = re.compile(r"\bwhere\b.*\bspend", re.IGNORECASE)
_COMPARE_RE = re.compile(r"\bcompar", re.IGNORECASE)
_RECURRING_RE = re.compile(r"\brecurring\b|\bsubscription", re.IGNORECASE)
_SAVINGS_RE = re.compile(r"\bhow much\b.*\bsave\b|\bshould i save\b", re.IGNORECASE)
_BUDGET_RE = re.compile(r"\bbudget", re.IGNORECASE)
_BALANCE_RE = re.compile(r"\bbalance\b|\bnet worth\b|\bhow much.*\bin my account", re.IGNORECASE)
_TRANSACTIONS_RE = re.compile(r"\btransactions?\b|\bpurchases?\b", re.IGNORECASE)

# The first money-looking number in the text - digits with optional comma
# grouping, optional decimal, optional trailing "k" shorthand (e.g. "70k").
_AMOUNT_RE = re.compile(r"([\d][\d,]*)(\.\d{1,2})?\s*(k\b)?", re.IGNORECASE)


def _extract_amount_minor(text: str) -> int | None:
    """Converts the first money-looking number in `text` to integer minor
    units using only string/integer arithmetic - never `float(x) * 100`,
    which can misround an exact rupee value. Returns None if no number is
    found (the caller must then treat the amount as genuinely unknown,
    never assume one)."""
    match = _AMOUNT_RE.search(text)
    if not match:
        return None
    whole_raw, frac_raw, k_suffix = match.groups()
    whole = int(whole_raw.replace(",", ""))
    if k_suffix:
        return whole * 1000 * 100
    frac = (frac_raw[1:] + "00")[:2] if frac_raw else "00"
    return whole * 100 + int(frac)


def classify_intent(text: str) -> ClassifiedIntent:
    stripped = text.strip()
    if not stripped:
        return ClassifiedIntent(Intent.UNSUPPORTED)

    if _AFFORD_RE.search(stripped):
        return ClassifiedIntent(Intent.AFFORDABILITY, amount_minor=_extract_amount_minor(stripped))

    spent_on_match = _SPENT_ON_RE.search(stripped)
    if spent_on_match:
        return ClassifiedIntent(Intent.CATEGORY_SPENDING, keyword=spent_on_match.group(1).strip())

    if _TOP_SPENDING_RE.search(stripped):
        return ClassifiedIntent(Intent.TOP_SPENDING)
    if _COMPARE_RE.search(stripped):
        return ClassifiedIntent(Intent.COMPARE_MONTHS)
    if _RECURRING_RE.search(stripped):
        return ClassifiedIntent(Intent.BIGGEST_RECURRING)
    if _SAVINGS_RE.search(stripped):
        return ClassifiedIntent(Intent.SAVINGS_RECOMMENDATION)
    if _BUDGET_RE.search(stripped):
        return ClassifiedIntent(Intent.BUDGET_STATUS)
    if _BALANCE_RE.search(stripped):
        return ClassifiedIntent(Intent.ACCOUNT_BALANCES)
    if _TRANSACTIONS_RE.search(stripped):
        return ClassifiedIntent(Intent.TRANSACTIONS_LOOKUP)

    return ClassifiedIntent(Intent.UNSUPPORTED)
