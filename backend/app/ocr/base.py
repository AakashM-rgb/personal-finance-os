"""OCR provider abstraction. Every provider returns the SAME structured
`OcrExtractionResult` shape regardless of how it actually extracted the
data - the rest of the application never depends on a specific OCR
vendor, and (critically) never treats this result as authoritative. It is
always a set of candidates a human must review and confirm; nothing here
is ever written directly into a Receipt's confirmed_* columns or used to
create a Transaction (see app.services.receipt_service).

Money fields are integer minor units, exactly like everywhere else in this
application - an OCR provider must never invent a fractional-paise value.
`quantity` is a plain string (not a float) since it is display-only
metadata, never itself a financial calculation input.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol


@dataclass(frozen=True)
class OcrItem:
    description: str
    quantity: str | None = None
    unit_price_minor: int | None = None
    line_total_minor: int | None = None


@dataclass(frozen=True)
class OcrExtractionResult:
    provider: str
    merchant: str | None = None
    occurred_on: date | None = None
    total_minor: int | None = None
    tax_minor: int | None = None
    items: list[OcrItem] = field(default_factory=list)
    suggested_category_name: str | None = None
    # 0.0-1.0, or None when the provider does not produce a confidence
    # score at all (never fabricated just to have a number).
    confidence: float | None = None
    # Set when extraction could not run at all (e.g. an unreadable file) -
    # distinct from "ran but found nothing", which just leaves the fields
    # above as None/empty.
    error: str | None = None


class OcrProvider(Protocol):
    async def extract(self, *, file_bytes: bytes, content_type: str) -> OcrExtractionResult: ...
