"""Budget math: status thresholds, warning messages, and the monthly
spending projection. Pure and DB-free (same pattern as
app.services.health_score and app.services.quick_add_parser) so every
branch is unit-testable with plain numbers - nothing here is randomly
generated; the projection is a documented linear estimate from real
spending-so-far, and the status is a deterministic function of a real
percentage.
"""

import enum

_WARNING_THRESHOLD = 70.0
_NEAR_LIMIT_THRESHOLD = 90.0
_EXCEEDED_THRESHOLD = 100.0


class BudgetStatus(enum.StrEnum):
    HEALTHY = "healthy"
    WARNING = "warning"
    NEAR_LIMIT = "near_limit"
    EXCEEDED = "exceeded"


def determine_budget_status(percent_used: float) -> BudgetStatus:
    """Thresholds (of amount_minor actually spent this month, vs the budget):
    < 70% Healthy, 70-89% Warning, 90-99% Near limit, >= 100% Exceeded."""
    if percent_used >= _EXCEEDED_THRESHOLD:
        return BudgetStatus.EXCEEDED
    if percent_used >= _NEAR_LIMIT_THRESHOLD:
        return BudgetStatus.NEAR_LIMIT
    if percent_used >= _WARNING_THRESHOLD:
        return BudgetStatus.WARNING
    return BudgetStatus.HEALTHY


def build_warning_message(
    category_name: str, percent_used: float, status: BudgetStatus
) -> str | None:
    """No message for a healthy budget - a warning should only ever appear
    when there's actually something to warn about."""
    if status == BudgetStatus.HEALTHY:
        return None
    if status == BudgetStatus.EXCEEDED:
        return f"You've exceeded your {category_name} budget ({percent_used:.0f}% used)."
    return f"You've used {percent_used:.0f}% of your {category_name} budget."


def project_monthly_amount(
    amount_so_far_minor: int, *, days_elapsed: int, days_in_month: int
) -> int:
    """Linear projection from real spending-so-far: (amount so far / days
    elapsed) * days in month. An estimate, never a guarantee - callers must
    label it as such, per CLAUDE.md's financial-calculation rules."""
    if days_elapsed <= 0:
        return 0
    daily_average = amount_so_far_minor / days_elapsed
    return round(daily_average * days_in_month)
