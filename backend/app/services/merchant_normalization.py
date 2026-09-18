"""Normalizes raw bank/UPI statement narration (e.g.
"UPI/DR/399/SWIGGY/paytm@ybl/Swiggy Order") into a canonical merchant name,
for app.services.sync_service. This is deliberately narration-text-only:
nothing here touches the database, calls a provider, or decides a category
- see app.services.keyword_categorization for that.

The approach is two steps, never a machine-learning guess:

1. Strip narration NOISE that carries no merchant identity - transfer
   mode/direction markers (UPI/NEFT/IMPS/RTGS, DR/CR), numeric reference
   and amount codes, and UPI VPA handles (anything containing "@").
2. Check what's left against a small, curated list of well-known merchant
   aliases (matched as a case-insensitive substring, so "SWIGGY",
   "SWIGGY INSTAMART", and "SWIGGY PVT LTD" all resolve to the same
   canonical "Swiggy"). If nothing matches, the cleaned text itself
   becomes the display name - an unknown merchant is never mapped to the
   wrong known one, and its own narration stays identifiable rather than
   being discarded.
"""

import re
from dataclasses import dataclass

_MODE_TOKEN_RE = re.compile(r"^(UPI|NEFT|IMPS|RTGS)$", re.IGNORECASE)
_DIRECTION_TOKEN_RE = re.compile(r"^(DR|CR)$", re.IGNORECASE)
# A reference/amount code: optional short letter prefix then 3+ digits
# (e.g. "399", "N123456789012", "987654321098") - never a merchant name,
# which is never purely numeric.
_REFERENCE_TOKEN_RE = re.compile(r"^[A-Z]{0,3}\d{3,}$", re.IGNORECASE)
# A UPI VPA handle (e.g. "paytm@ybl", "amazon@icici") - identifies a payment
# handle, never the merchant's own display name.
_VPA_TOKEN_RE = re.compile(r"^\S+@\S+$")

# Generic corporate-suffix words dropped only from an UNRECOGNIZED
# merchant's fallback display name - never applied when checking for a
# known alias, so "SWIGGY PVT LTD" still matches "SWIGGY" as a substring.
_GENERIC_SUFFIX_WORDS = {"PVT", "LTD", "LIMITED", "PRIVATE"}

# Ordered specific-before-generic; matched as a case-insensitive substring
# of the cleaned, noise-stripped narration. Deliberately small and curated
# - see the module docstring: an unmatched merchant must never be guessed
# at, only ever left identifiable as itself.
_MERCHANT_ALIASES: tuple[tuple[str, str], ...] = (
    ("AMZN MKTPLACE", "Amazon"),
    ("AMAZON", "Amazon"),
    ("FLIPKART", "Flipkart"),
    ("SWIGGY", "Swiggy"),
    ("ZOMATO", "Zomato"),
    ("NETFLIX", "Netflix"),
    ("SPOTIFY", "Spotify"),
    ("UBER", "Uber"),
    ("OLA", "Ola"),
)

_UNKNOWN_MERCHANT_DISPLAY_NAME = "Unknown Merchant"


@dataclass(frozen=True)
class NormalizedMerchant:
    """`recognized=True` only when `canonical_name` came from
    `_MERCHANT_ALIASES` - i.e. the merchant's identity is confidently known,
    not just noise-stripped free text. app.services.sync_service treats
    this as its strongest categorization/confidence signal."""

    canonical_name: str
    recognized: bool


def _clean_segments(narration: str) -> list[str]:
    segments = [segment.strip() for segment in narration.split("/") if segment.strip()]
    cleaned = []
    for segment in segments:
        if _MODE_TOKEN_RE.match(segment):
            continue
        if _DIRECTION_TOKEN_RE.match(segment):
            continue
        if _REFERENCE_TOKEN_RE.match(segment):
            continue
        if _VPA_TOKEN_RE.match(segment):
            continue
        cleaned.append(segment)
    return cleaned


def _fallback_display_name(cleaned_segments: list[str]) -> str:
    if not cleaned_segments:
        return _UNKNOWN_MERCHANT_DISPLAY_NAME
    primary = cleaned_segments[0]
    words = [word for word in primary.split() if word.upper() not in _GENERIC_SUFFIX_WORDS]
    if not words:
        words = primary.split()
    return " ".join(word.capitalize() for word in words)


def normalize_merchant(narration: str) -> NormalizedMerchant:
    if not narration or not narration.strip():
        return NormalizedMerchant(canonical_name=_UNKNOWN_MERCHANT_DISPLAY_NAME, recognized=False)

    cleaned_segments = _clean_segments(narration)
    haystack = " ".join(cleaned_segments).upper()

    for alias, canonical_name in _MERCHANT_ALIASES:
        if alias in haystack:
            return NormalizedMerchant(canonical_name=canonical_name, recognized=True)

    return NormalizedMerchant(
        canonical_name=_fallback_display_name(cleaned_segments), recognized=False
    )
