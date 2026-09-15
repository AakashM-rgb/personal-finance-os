"""Report request/response schemas.

Every report is computed via the same repositories/services the rest of
the app already uses (analytics_service, budget_service,
savings_goal_service, account_service, and the recurring/subscription
cost calculations) - a report is a different PRESENTATION of the same
real numbers, never a second, divergent calculation of them. Where a
report embeds an existing module's own read schema (BudgetItemRead,
SavingsGoalRead, CategoryBreakdown, TransactionRead), that is deliberate:
it guarantees the report can never drift from what that module's own
page already shows.
"""

from datetime import date
from uuid import UUID

from pydantic import BaseModel

from app.schemas.analytics import CategoryBreakdown, RecurringExpenseBreakdown, TrendInfo
from app.schemas.budget import BudgetItemRead
from app.schemas.savings_goal import SavingsGoalRead
from app.schemas.transaction import TransactionRead


class MonthlyReport(BaseModel):
    year: int
    month: int
    currency: str
    date_from: date
    date_to: date
    total_income_minor: int
    total_expense_minor: int
    net_cash_flow_minor: int
    savings_minor: int
    savings_rate: float | None
    category_breakdown: CategoryBreakdown
    budget_performance: list[BudgetItemRead]
    recurring_expense_breakdown: RecurringExpenseBreakdown


class MonthlyAmount(BaseModel):
    month: date
    amount_minor: int


class YearlyReport(BaseModel):
    year: int
    currency: str
    total_income_minor: int
    total_expense_minor: int
    net_cash_flow_minor: int
    savings_minor: int
    savings_rate: float | None
    monthly_income_trend: list[MonthlyAmount]
    monthly_expense_trend: list[MonthlyAmount]
    monthly_savings_trend: list[MonthlyAmount]
    category_totals: CategoryBreakdown


class CategoryReportItem(BaseModel):
    category_id: UUID | None
    name: str
    icon: str
    color: str
    amount_minor: int
    percent: float
    transaction_count: int


class CategoryReport(BaseModel):
    currency: str
    date_from: date
    date_to: date
    total_expense_minor: int
    items: list[CategoryReportItem]


class TimeSeriesPoint(BaseModel):
    period: date
    amount_minor: int


class IncomeReport(BaseModel):
    currency: str
    date_from: date
    date_to: date
    total_income_minor: int
    transaction_count: int
    by_source: list[CategoryReportItem]
    over_time: list[TimeSeriesPoint]
    largest_transactions: list[TransactionRead]


class ExpenseReport(BaseModel):
    currency: str
    date_from: date
    date_to: date
    total_expense_minor: int
    transaction_count: int
    by_category: list[CategoryReportItem]
    over_time: list[TimeSeriesPoint]
    largest_transactions: list[TransactionRead]
    recurring_expense_minor: int
    non_recurring_expense_minor: int


class BudgetReport(BaseModel):
    currency: str
    items: list[BudgetItemRead]
    total_budgeted_minor: int
    total_spent_minor: int
    at_risk_count: int
    exceeded_count: int


class SavingsTrendPoint(BaseModel):
    period: date
    income_minor: int
    expense_minor: int
    savings_minor: int
    savings_rate: float | None


class SavingsReport(BaseModel):
    currency: str
    date_from: date
    date_to: date
    total_income_minor: int
    total_expense_minor: int
    savings_minor: int
    savings_rate: float | None
    trend: list[SavingsTrendPoint]
    trend_direction: TrendInfo
    goals: list[SavingsGoalRead]


class NetWorthAccountItem(BaseModel):
    account_id: UUID
    name: str
    type: str
    balance_minor: int
    currency: str
    is_liability: bool


class NetWorthTrendPoint(BaseModel):
    month: date
    net_worth_minor: int


class NetWorthReport(BaseModel):
    currency: str
    total_assets_minor: int
    total_liabilities_minor: int
    net_worth_minor: int
    accounts: list[NetWorthAccountItem]
    # Reconstructed from the current balances and the real transaction
    # ledger since each month-end (see
    # app.services.report_service._build_net_worth_trend) - not a stored
    # historical snapshot. See that function's docstring for the one
    # documented assumption this relies on.
    trend: list[NetWorthTrendPoint]
