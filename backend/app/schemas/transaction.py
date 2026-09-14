"""Transaction request/response schemas.

`amount_minor` is always integer minor units and always a positive
magnitude - the sign is implied by `type`. Currency is never accepted here;
it is always derived server-side from the account (see
app.services.transaction_service), so a transaction can never claim a
currency its account doesn't have.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.transaction import TransactionType

_MAX_TAGS = 10
_MAX_TAG_LENGTH = 50


def _validate_tags(tags: list[str]) -> list[str]:
    if len(tags) > _MAX_TAGS:
        raise ValueError(f"A transaction can have at most {_MAX_TAGS} tags.")
    cleaned = []
    for tag in tags:
        tag = tag.strip().lower()
        if not tag:
            continue
        if len(tag) > _MAX_TAG_LENGTH:
            raise ValueError(f"Each tag must be at most {_MAX_TAG_LENGTH} characters.")
        if tag not in cleaned:
            cleaned.append(tag)
    return cleaned


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID
    type: TransactionType
    amount_minor: int = Field(gt=0)
    transfer_account_id: UUID | None = None
    category_id: UUID | None = None

    merchant: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    payment_method: str | None = Field(default=None, max_length=50)
    tags: list[str] = Field(default_factory=list)

    occurred_at: datetime | None = None
    is_recurring: bool = False

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return _validate_tags(value)


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: UUID | None = None
    type: TransactionType | None = None
    amount_minor: int | None = Field(default=None, gt=0)
    transfer_account_id: UUID | None = None
    category_id: UUID | None = None
    clear_category: bool = False

    merchant: str | None = Field(default=None, max_length=200)
    description: str | None = Field(default=None, max_length=500)
    notes: str | None = Field(default=None, max_length=5000)
    payment_method: str | None = Field(default=None, max_length=50)
    tags: list[str] | None = None

    occurred_at: datetime | None = None
    is_recurring: bool | None = None

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str] | None) -> list[str] | None:
        return _validate_tags(value) if value is not None else None


class TransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    account_id: UUID
    transfer_account_id: UUID | None
    category_id: UUID | None
    type: TransactionType
    amount_minor: int
    currency: str

    merchant: str | None
    description: str | None
    notes: str | None
    payment_method: str | None
    tags: list[str]

    occurred_at: datetime
    is_recurring: bool

    created_at: datetime
    updated_at: datetime


class QuickAddParseRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=200)


class QuickAddParseResult(BaseModel):
    raw_text: str
    amount_minor: int | None
    category_id: UUID | None
    category_name: str | None
    description: str | None
    occurred_at: datetime
    confidence: str  # "high" | "medium" | "low"
    error: str | None
