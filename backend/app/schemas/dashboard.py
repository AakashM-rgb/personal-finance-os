"""Dashboard response schema. Every field is computed from real account/
transaction data - nothing here is a placeholder or random value."""

from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel

from app.schemas.transaction import TransactionRead


class HealthScoreFactor(BaseModel):
    key: str
    label: str
    weight: float
    score: float | None
    detail: str
    is_positive: bool | None


class HealthScore(BaseModel):
    score: int | None
    label: str | None
    factors: list[HealthScoreFactor]


class CategoryBreakdownItem(BaseModel):
    category_id: UUID | None
    name: str
    icon: str
    color: str
    amount_minor: int
    percent: float


class MonthlySpending(BaseModel):
    current_month_expense_minor: int
    previous_month_expense_minor: int
    percent_change: float | None
    daily_average_minor: int
    projected_month_expense_minor: int
    days_elapsed: int
    days_in_month: int


class UpcomingPayment(BaseModel):
    account_id: UUID
    account_name: str
    kind: str
    due_date: date
    amount_minor: int
    description: str


class DashboardRead(BaseModel):
    currency: str
    generated_at: datetime

    total_balance_minor: int
    net_worth_minor: int
    total_income_minor: int
    total_expense_minor: int
    savings_minor: int
    savings_rate: float | None

    monthly_spending: MonthlySpending
    category_breakdown: list[CategoryBreakdownItem]
    recent_transactions: list[TransactionRead]
    upcoming_payments: list[UpcomingPayment]
    health_score: HealthScore

    # Informational - accounts in a currency other than the user's base
    # currency are excluded from every total above rather than silently
    # summed in with mismatched units.
    excluded_other_currency_accounts: int
