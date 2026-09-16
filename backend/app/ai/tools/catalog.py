"""THE fixed allowlist of financial tools the AI may call - exactly eight,
by design (CLAUDE.md - "Only these eight financial tools may be exposed to
the model"). This module is the single source of truth for which tool
names exist; app.ai.tools.registry refuses anything not listed here, and
nothing else in the codebase may add a ninth entry at runtime.
"""

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from app.ai.tools import executors
from app.ai.tools.schemas import (
    AccountBalancesArgs,
    BudgetStatusArgs,
    CategorySpendingArgs,
    ComparePeriodsArgs,
    MonthlySpendingArgs,
    RecurringExpensesArgs,
    SavingsGoalsArgs,
    TransactionsArgs,
)


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    args_model: type[BaseModel]
    executor: Callable[..., Awaitable[BaseModel]]

    @property
    def input_schema(self) -> dict[str, Any]:
        """JSON Schema for this tool's arguments - handed to a real
        provider (e.g. Anthropic) verbatim as its tool definition."""
        return self.args_model.model_json_schema()


TOOL_CATALOG: tuple[ToolSpec, ...] = (
    ToolSpec(
        name="get_monthly_spending",
        description=(
            "Get the authenticated user's total income, expense, and net savings for one "
            "calendar month. Transfers between the user's own accounts are excluded. "
            "`period` is optional: 'current_month' (default), 'previous_month', or 'YYYY-MM'."
        ),
        args_model=MonthlySpendingArgs,
        executor=executors.execute_get_monthly_spending,
    ),
    ToolSpec(
        name="get_category_spending",
        description=(
            "Get the authenticated user's expense spending grouped by category for one "
            "calendar month, ranked highest first, including uncategorized spending as its "
            "own explicit entry. Transfers are excluded. `period` is optional, same format "
            "as get_monthly_spending."
        ),
        args_model=CategorySpendingArgs,
        executor=executors.execute_get_category_spending,
    ),
    ToolSpec(
        name="get_transactions",
        description=(
            "List the authenticated user's own individual transactions, most recent first, "
            "optionally filtered by date range, category, or type (income/expense/transfer). "
            "Returns at most 50 transactions per call."
        ),
        args_model=TransactionsArgs,
        executor=executors.execute_get_transactions,
    ),
    ToolSpec(
        name="get_budget_status",
        description=(
            "Get the authenticated user's current budgets with real spent/remaining amounts "
            "and progress for the current calendar month, one entry per budgeted category."
        ),
        args_model=BudgetStatusArgs,
        executor=executors.execute_get_budget_status,
    ),
    ToolSpec(
        name="get_savings_goals",
        description=(
            "Get the authenticated user's savings goals with real progress, remaining amount, "
            "and the required monthly/weekly savings pace needed to hit each goal's target date."
        ),
        args_model=SavingsGoalsArgs,
        executor=executors.execute_get_savings_goals,
    ),
    ToolSpec(
        name="get_recurring_expenses",
        description=(
            "Get the authenticated user's recurring expenses (including subscriptions), each "
            "with its scheduled monthly-equivalent cost AND the amount actually paid from real "
            "transaction history during the selected month. `period` is optional, same format "
            "as get_monthly_spending."
        ),
        args_model=RecurringExpensesArgs,
        executor=executors.execute_get_recurring_expenses,
    ),
    ToolSpec(
        name="get_account_balances",
        description=(
            "Get the authenticated user's active account balances (bank, cash, credit card, "
            "etc.) in their base currency, plus total assets, total liabilities, and net worth."
        ),
        args_model=AccountBalancesArgs,
        executor=executors.execute_get_account_balances,
    ),
    ToolSpec(
        name="compare_periods",
        description=(
            "Compare real income/expense totals between two periods - defaults to current "
            "month vs previous month. Accepts two 'YYYY-MM' months (period_a/period_b), or two "
            "explicit date ranges (date_from_a/date_to_a and date_from_b/date_to_b). Returns "
            "each period's totals plus the difference and percent change (percent change is "
            "omitted, not fabricated, when the earlier period's value is zero)."
        ),
        args_model=ComparePeriodsArgs,
        executor=executors.execute_compare_periods,
    ),
)

TOOL_NAMES: frozenset[str] = frozenset(spec.name for spec in TOOL_CATALOG)
_TOOLS_BY_NAME: dict[str, ToolSpec] = {spec.name: spec for spec in TOOL_CATALOG}

assert len(TOOL_CATALOG) == 8, "The AI tool catalog must expose exactly eight tools."


def get_tool_spec(name: str) -> ToolSpec | None:
    return _TOOLS_BY_NAME.get(name)
