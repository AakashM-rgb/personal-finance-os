"""Savings goal request/response schemas.

Money fields are always integer minor units. `current_amount_minor` must
never exceed `target_amount_minor` - the product does not support
overfunded goals - checked here for a same-request create, and again in
app.services.savings_goal_service against the stored value for a partial
update (a DB check constraint backs both, as defense in depth).
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.account import SUPPORTED_CURRENCIES


class SavingsGoalCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    target_amount_minor: int = Field(gt=0)
    current_amount_minor: int = Field(default=0, ge=0)
    currency: str = "INR"
    target_date: date

    @model_validator(mode="after")
    def _validate(self) -> "SavingsGoalCreate":
        if self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(SUPPORTED_CURRENCIES)}")
        if self.current_amount_minor > self.target_amount_minor:
            raise ValueError("current_amount_minor must not exceed target_amount_minor")
        return self


class SavingsGoalUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    target_amount_minor: int | None = Field(default=None, gt=0)
    current_amount_minor: int | None = Field(default=None, ge=0)
    currency: str | None = None
    target_date: date | None = None

    @model_validator(mode="after")
    def _validate_currency(self) -> "SavingsGoalUpdate":
        if self.currency is not None and self.currency not in SUPPORTED_CURRENCIES:
            raise ValueError(f"currency must be one of {sorted(SUPPORTED_CURRENCIES)}")
        return self


class SavingsGoalRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    target_amount_minor: int
    current_amount_minor: int
    currency: str
    target_date: date

    progress_percent: float
    remaining_minor: int
    is_completed: bool
    # Positive: days until the target date. Zero: due today. Negative: the
    # target date has already passed.
    days_remaining: int

    # None when the target date is today or already in the past and the
    # goal isn't yet complete - see app.services.savings_goal_calculations.
    required_monthly_savings_minor: int | None
    required_weekly_savings_minor: int | None

    created_at: datetime
    updated_at: datetime
