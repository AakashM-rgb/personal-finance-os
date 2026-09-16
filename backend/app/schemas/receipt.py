"""Receipt request/response schemas.

`ReceiptItemData` is used for BOTH the OCR-extracted candidates and the
user-confirmed items - same shape, different columns (see
app.models.receipt). Money fields are always integer minor units;
`quantity` is a plain string (display-only, never itself a calculation
input, so it is never coerced to a float).

The maximum upload size lives here (not buried in the route) so both the
service (which enforces it) and any caller that wants to report it (the
frontend, via a constant it keeps in sync - see docs in
frontend/lib/receipts.ts) have one obvious place to look.
"""

from datetime import date as date_type
from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

# 10 MB: generous enough for a high-resolution phone photo of a paper
# receipt or a multi-page scanned PDF, while still bounded well below
# anything that could meaningfully strain request handling or storage at
# this application's scale (a personal-finance app's per-user receipt
# volume is small; nothing here needs to support bulk/enterprise uploads).
RECEIPT_MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024

ALLOWED_CONTENT_TYPES = {"image/jpeg", "image/png", "application/pdf"}
ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf"}


class ReceiptItemData(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=300)
    quantity: str | None = Field(default=None, max_length=30)
    unit_price_minor: int | None = Field(default=None, ge=0)
    line_total_minor: int | None = Field(default=None, ge=0)


class ReceiptExtraction(BaseModel):
    """Read-only OCR output - a set of candidates, never authoritative.
    Always present on a processed/failed receipt so the review screen can
    show exactly what (if anything) was found."""

    model_config = ConfigDict(from_attributes=True)

    provider: str | None
    confidence: float | None
    processed_at: datetime | None
    error: str | None

    merchant: str | None
    # `date_type`, not `date`: a field named `date` with a same-named type and
    # a `=` default would have Python bind the default value to the name
    # `date` in this class body before the annotation is evaluated, making
    # `date | None` resolve to `None | None` and raise a TypeError.
    date: date_type | None
    total_minor: int | None
    tax_minor: int | None
    items: list[ReceiptItemData]
    suggested_category_id: UUID | None
    suggested_category_name: str | None


class ReceiptConfirmRequest(BaseModel):
    """Exactly what the user reviewed and explicitly submitted - never
    merged with or defaulted from the OCR extraction server-side. A field
    left out here (None) means the user is confirming it as genuinely
    unknown/blank, not "keep whatever OCR said"."""

    model_config = ConfigDict(extra="forbid")

    merchant: str | None = Field(default=None, max_length=200)
    date: date_type | None = None
    total_minor: int | None = Field(default=None, ge=0)
    tax_minor: int | None = Field(default=None, ge=0)
    items: list[ReceiptItemData] = Field(default_factory=list)
    category_id: UUID | None = None


class ReceiptCreateTransactionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID


class ReceiptRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transaction_id: UUID | None
    original_filename: str | None
    content_type: str
    file_size_bytes: int
    status: str

    extraction: ReceiptExtraction | None

    confirmed_merchant: str | None
    confirmed_date: date_type | None
    confirmed_total_minor: int | None
    confirmed_tax_minor: int | None
    confirmed_items: list[ReceiptItemData]
    category_id: UUID | None
    category_name: str | None
    category_icon: str | None
    category_color: str | None
    confirmed_at: datetime | None

    created_at: datetime
    updated_at: datetime
