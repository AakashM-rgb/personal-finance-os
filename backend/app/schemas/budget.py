"""Budget request/response schemas.

`amount_minor` is always a positive integer minor-unit amount. `category_id`
is immutable after creation (BudgetItemUpdate has no such field) - matching
the same immutability pattern as Account.type, since changing a budget's
category is really "delete this, create a different one," not an edit.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class BudgetItemCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    category_id: UUID
    amount_minor: int = Field(gt=0)


class BudgetItemUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    amount_minor: int = Field(gt=0)


class BudgetItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    category_id: UUID
    category_name: str
    category_icon: str
    category_color: str

    currency: str
    amount_minor: int
    spent_minor: int
    remaining_minor: int
    percent_used: float
    status: str  # "healthy" | "warning" | "near_limit" | "exceeded"
    warning_message: str | None

    # An estimate from real spending-so-far, never a guarantee - see
    # app.services.budget_calculations.project_monthly_amount.
    projected_month_minor: int
    days_elapsed: int
    days_in_month: int

    created_at: datetime
    updated_at: datetime


class BudgetSuggestion(BaseModel):
    category_id: UUID
    category_name: str
    category_icon: str
    category_color: str
    suggested_amount_minor: int
    based_on: str
