"""Recurring transaction request/response schemas.

`amount_minor` is always a positive integer minor-unit amount. `type` is
restricted to income/expense - transfers are not supported for recurring
transactions (see app.models.recurring_transaction). `start_date` is
immutable after creation (RecurringTransactionUpdate has no such field):
it anchors `day_of_month` and the generation catch-up logic, and letting
it move after occurrences may already exist would make "what counts as
already generated" ambiguous.
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.models.recurring_transaction import RecurrenceFrequency
from app.models.transaction import TransactionType


def _reject_transfer(value: TransactionType | None) -> TransactionType | None:
    if value == TransactionType.TRANSFER:
        raise ValueError("Recurring transfers are not supported.")
    return value


class RecurringTransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    account_id: UUID
    category_id: UUID | None = None
    type: TransactionType
    amount_minor: int = Field(gt=0)
    frequency: RecurrenceFrequency
    start_date: date

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: TransactionType) -> TransactionType:
        if value == TransactionType.TRANSFER:
            raise ValueError("Recurring transfers are not supported.")
        return value


class RecurringTransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    account_id: UUID | None = None
    category_id: UUID | None = None
    clear_category: bool = False
    type: TransactionType | None = None
    amount_minor: int | None = Field(default=None, gt=0)
    frequency: RecurrenceFrequency | None = None

    @field_validator("type")
    @classmethod
    def _validate_type(cls, value: TransactionType | None) -> TransactionType | None:
        return _reject_transfer(value)


class RecurringTransactionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    account_id: UUID
    account_name: str
    category_id: UUID | None
    category_name: str | None
    category_icon: str | None
    category_color: str | None
    type: TransactionType
    amount_minor: int
    currency: str
    frequency: RecurrenceFrequency
    start_date: date
    # The date the next occurrence will be generated for - derived from the
    # already-generated ledger history, never stored. See
    # app.services.recurring_transaction_service.
    next_occurrence_date: date
    is_active: bool

    created_at: datetime
    updated_at: datetime
