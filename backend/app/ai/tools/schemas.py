"""Pydantic input/output schemas for the eight allowlisted AI tools.

Every input ("Args") schema is `extra="forbid"` and has no `user_id` field
at all - the authenticated user's identity is never accepted as a tool
argument, it always comes from the request context (see
app.services.ai_assistant_service and app.ai.tools.registry). Every bound
here (result limits, date ranges) is enforced by pydantic itself, so an
out-of-range argument is rejected before any tool ever touches the
database.

Output schemas reuse the existing Budgets/Savings-Goals/Analytics/Accounts
Read schemas wherever they already match 1:1, rather than re-deriving the
same figures a second time.
"""

import uuid
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.transaction import TransactionType
from app.schemas.account import AccountRead
from app.schemas.analytics import CategoryBreakdownItem, RecurringExpenseBreakdownItem
from app.schemas.budget import BudgetItemRead
from app.schemas.savings_goal import SavingsGoalRead

MAX_TRANSACTIONS_LIMIT = 50
DEFAULT_TRANSACTIONS_LIMIT = 20

_PERIOD_DESCRIPTION = "'current_month' (default), 'previous_month', or an explicit 'YYYY-MM'."


# --- tool arguments (untrusted - AI-supplied) ---------------------------------------


class MonthlySpendingArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str | None = Field(default=None, max_length=20, description=_PERIOD_DESCRIPTION)


class CategorySpendingArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str | None = Field(default=None, max_length=20, description=_PERIOD_DESCRIPTION)


class TransactionsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    date_from: date | None = None
    date_to: date | None = None
    category_id: uuid.UUID | None = None
    type: TransactionType | None = None
    limit: int = Field(default=DEFAULT_TRANSACTIONS_LIMIT, ge=1, le=MAX_TRANSACTIONS_LIMIT)

    @model_validator(mode="after")
    def _check_range(self) -> "TransactionsArgs":
        date_from, date_to = self.date_from, self.date_to
        if date_from is not None and date_to is not None and date_from > date_to:
            raise ValueError("date_from must not be after date_to.")
        return self


class BudgetStatusArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class SavingsGoalsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RecurringExpensesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period: str | None = Field(
        default=None,
        max_length=20,
        description=f"Which month's actual-paid amounts to report. {_PERIOD_DESCRIPTION}",
    )


class AccountBalancesArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ComparePeriodsArgs(BaseModel):
    model_config = ConfigDict(extra="forbid")

    period_a: str | None = Field(default="current_month", max_length=20)
    period_b: str | None = Field(default="previous_month", max_length=20)
    date_from_a: date | None = None
    date_to_a: date | None = None
    date_from_b: date | None = None
    date_to_b: date | None = None

    @model_validator(mode="after")
    def _check_custom_ranges_paired(self) -> "ComparePeriodsArgs":
        if (self.date_from_a is None) != (self.date_to_a is None):
            raise ValueError("date_from_a and date_to_a must be provided together.")
        if (self.date_from_b is None) != (self.date_to_b is None):
            raise ValueError("date_from_b and date_to_b must be provided together.")
        return self


# --- tool results (trusted - built by executors from real data) -------------------


class MonthlySpendingResult(BaseModel):
    period_label: str
    date_from: date
    date_to: date  # inclusive, last calendar day of the period
    currency: str
    total_income_minor: int
    total_expense_minor: int
    net_minor: int
    savings_rate_percent: float | None


class CategorySpendingResult(BaseModel):
    period_label: str
    date_from: date
    date_to: date
    currency: str
    total_expense_minor: int
    categories: list[CategoryBreakdownItem]


class TransactionSummary(BaseModel):
    """A slimmed, AI-safe projection of a transaction - never the full
    TransactionRead (no notes, tags, or internal linkage fields)."""

    id: uuid.UUID
    occurred_at: datetime
    type: TransactionType
    amount_minor: int
    currency: str
    category_name: str | None
    merchant: str | None
    description: str | None


class TransactionsResult(BaseModel):
    total_matching: int
    returned_count: int
    limit: int
    transactions: list[TransactionSummary]


class BudgetStatusResult(BaseModel):
    currency: str
    items: list[BudgetItemRead]


class SavingsGoalsResult(BaseModel):
    goals: list[SavingsGoalRead]


class RecurringExpensesResult(BaseModel):
    period_label: str
    currency: str
    items: list[RecurringExpenseBreakdownItem]
    total_scheduled_monthly_minor: int
    total_actual_paid_minor: int
    recurring_share_of_expense_percent: float | None


class AccountBalancesResult(BaseModel):
    currency: str
    accounts: list[AccountRead]
    total_assets_minor: int
    total_liabilities_minor: int
    net_worth_minor: int
    excluded_other_currency_accounts: int


class PeriodTotals(BaseModel):
    label: str
    date_from: date
    date_to: date
    total_income_minor: int
    total_expense_minor: int
    net_minor: int


class ComparePeriodsResult(BaseModel):
    currency: str
    period_a: PeriodTotals
    period_b: PeriodTotals
    expense_diff_minor: int
    expense_percent_change: float | None
    income_diff_minor: int
    income_percent_change: float | None
    net_diff_minor: int
