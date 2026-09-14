"""Account request/response schemas.

Money fields are always integer minor units. `type` is immutable after
creation (AccountUpdate simply has no `type` field), so an account can never
silently jump between a bank account and a credit card.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.account import AccountType

# Kept small and explicit rather than open-ended, matching the spec's stated
# multi-currency roadmap (INR first-class today).
SUPPORTED_CURRENCIES = {"INR", "USD", "EUR", "GBP", "JPY"}


class CreditCardFields(BaseModel):
    model_config = ConfigDict(extra="forbid")

    credit_limit_minor: int = Field(gt=0)
    statement_day: int = Field(ge=1, le=31)
    payment_due_day: int = Field(ge=1, le=31)
    minimum_payment_minor: int | None = Field(default=None, ge=0)


class AccountCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    type: AccountType
    balance_minor: int = 0
    currency: str = "INR"
    institution_name: str | None = Field(default=None, max_length=200)
    credit_card: CreditCardFields | None = None

    @model_validator(mode="after")
    def _validate_currency_and_credit_card_fields(self) -> "AccountCreate":
        if self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(SUPPORTED_CURRENCIES)}")

        if self.type == AccountType.CREDIT_CARD and self.credit_card is None:
            raise ValueError("credit_card details are required for a credit_card account")
        if self.type != AccountType.CREDIT_CARD and self.credit_card is not None:
            raise ValueError("credit_card details are only valid for a credit_card account")
        return self


class AccountUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    balance_minor: int | None = None
    currency: str | None = None
    institution_name: str | None = Field(default=None, max_length=200)
    credit_card: CreditCardFields | None = None

    @model_validator(mode="after")
    def _validate_currency(self) -> "AccountUpdate":
        if self.currency is not None and self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(SUPPORTED_CURRENCIES)}")
        return self


class CreditCardDetailsRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    credit_limit_minor: int
    statement_day: int
    payment_due_day: int
    minimum_payment_minor: int | None
    # Computed, never stored, so they can never drift from balance_minor/credit_limit_minor.
    available_credit_minor: int
    utilization_percent: float


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    type: AccountType
    balance_minor: int
    currency: str
    institution_name: str | None
    is_active: bool
    credit_card: CreditCardDetailsRead | None
    created_at: datetime
    updated_at: datetime
