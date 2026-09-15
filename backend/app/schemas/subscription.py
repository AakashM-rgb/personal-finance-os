"""Subscription request/response schemas.

A subscription is always an expense - there is no `type` field here at
all (unlike RecurringTransactionCreate/Update), so a caller can never
create an "income subscription." Every other field mirrors
RecurringTransactionCreate/Update exactly, since a subscription's
schedule, amount, account, and category ARE a RecurringTransaction's
(see app.services.subscription_service).
"""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.recurring_transaction import RecurrenceFrequency


class SubscriptionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=200)
    account_id: UUID
    category_id: UUID | None = None
    amount_minor: int = Field(gt=0)
    frequency: RecurrenceFrequency
    start_date: date


class SubscriptionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str | None = Field(default=None, min_length=1, max_length=200)
    account_id: UUID | None = None
    category_id: UUID | None = None
    clear_category: bool = False
    amount_minor: int | None = Field(default=None, gt=0)
    frequency: RecurrenceFrequency | None = None


class SubscriptionRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    recurring_transaction_id: UUID
    name: str
    account_id: UUID
    account_name: str
    category_id: UUID | None
    category_name: str | None
    category_icon: str | None
    category_color: str | None
    amount_minor: int
    currency: str
    frequency: RecurrenceFrequency

    # Deterministic monthly/yearly-equivalent figures - see
    # app.services.subscription_calculations. Never estimated.
    monthly_cost_minor: int
    yearly_cost_minor: int
    next_renewal_date: date

    is_active: bool

    # None = insufficient evidence, no claim made. True/False = an
    # evidence-based claim either way. `unused_reason` always explains
    # which. See app.services.subscription_calculations.evaluate_unused_evidence.
    is_possibly_unused: bool | None
    unused_reason: str

    created_at: datetime
    updated_at: datetime
