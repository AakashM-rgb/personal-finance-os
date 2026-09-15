"""Analytics request/response schemas.

Every figure here is computed from the authenticated caller's own real
transaction, budget, and recurring-transaction data - nothing is
estimated or randomly generated. Money fields are always integer minor
units. `budget_performance` is the literal `BudgetItemRead` shape the
Budgets module already returns (see app.schemas.budget) - reused
directly rather than re-derived, so budget numbers can never drift
between the Budgets page and the Analytics page.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.models.recurring_transaction import RecurrenceFrequency
from app.schemas.budget import BudgetItemRead
from app.services.analytics_calculations import AnalyticsRangePreset, Granularity, TrendDirection


class AnalyticsRequest(BaseModel):
    """Query parameters for GET /analytics. `custom_from`/`custom_to` are
    required (and only used) when `range` is "custom"."""

    model_config = ConfigDict(extra="forbid")

    range: AnalyticsRangePreset = AnalyticsRangePreset.CURRENT_MONTH
    custom_from: date | None = None
    custom_to: date | None = None


class TrendInfo(BaseModel):
    # None when there are fewer than 2 periods to compare - insufficient
    # data, never a guessed direction.
    direction: TrendDirection | None
    percent_change: float | None


class SpendingOverTimePoint(BaseModel):
    period: date
    amount_minor: int


class SpendingOverTime(BaseModel):
    """Answers: is my spending increasing or decreasing?"""

    granularity: Granularity
    points: list[SpendingOverTimePoint]
    trend: TrendInfo


class CategoryBreakdownItem(BaseModel):
    category_id: UUID | None
    name: str
    icon: str
    color: str
    amount_minor: int
    percent: float


class CategoryBreakdown(BaseModel):
    """Answers: where is my money going?"""

    items: list[CategoryBreakdownItem]
    total_expense_minor: int


class IncomeVsExpense(BaseModel):
    """Answers: am I spending more than I earn?"""

    total_income_minor: int
    total_expense_minor: int
    net_minor: int
    is_spending_more_than_earning: bool


class SavingsTrendPoint(BaseModel):
    period: date
    income_minor: int
    expense_minor: int
    savings_minor: int
    savings_rate: float | None = Field(
        description="savings_minor / income_minor * 100, or null when income is 0."
    )


class SavingsTrend(BaseModel):
    """Answers: is my savings position improving?"""

    points: list[SavingsTrendPoint]
    trend: TrendInfo


class DailySpendingPoint(BaseModel):
    day: date
    amount_minor: int


class DailySpending(BaseModel):
    """Answers: which days am I spending the most?"""

    points: list[DailySpendingPoint]
    highest_day: date | None
    highest_amount_minor: int


class RecurringExpenseBreakdownItem(BaseModel):
    recurring_transaction_id: UUID
    name: str
    frequency: RecurrenceFrequency
    amount_minor: int
    currency: str
    is_active: bool
    is_subscription: bool
    # A deterministic monthly-equivalent of amount_minor/frequency (see
    # app.services.subscription_calculations) - a scheduled commitment,
    # computed regardless of whether it has actually been billed yet.
    scheduled_monthly_cost_minor: int
    # Real money actually paid within the selected range, from the
    # ledger - never assumed just because a schedule exists. Can be 0
    # for a schedule that hasn't come due yet in this range.
    actual_paid_minor: int


class RecurringExpenseBreakdown(BaseModel):
    """Answers: how much of my spending is committed to recurring expenses?"""

    items: list[RecurringExpenseBreakdownItem]
    # Sum of scheduled_monthly_cost_minor over ACTIVE items only - current
    # ongoing commitment, not a historical figure.
    total_scheduled_monthly_minor: int
    # Sum of actual_paid_minor over every item - real money paid in range.
    total_actual_paid_minor: int
    # total_actual_paid_minor as a percent of the range's total real
    # expense, or null if there was no expense at all in the range.
    recurring_share_of_expense_percent: float | None


class AnalyticsRead(BaseModel):
    currency: str
    range: AnalyticsRangePreset
    date_from: date
    date_to: date  # inclusive, for display

    spending_over_time: SpendingOverTime
    category_breakdown: CategoryBreakdown
    income_vs_expense: IncomeVsExpense
    savings_trend: SavingsTrend
    budget_performance: list[BudgetItemRead]
    daily_spending: DailySpending
    recurring_expense_breakdown: RecurringExpenseBreakdown
