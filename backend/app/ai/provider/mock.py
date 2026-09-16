"""The deterministic development/demo AI provider - used automatically
whenever no external AI provider is configured (see app.ai.provider.factory).

This is NOT a simulation of a real language model. It runs a fixed,
two-round protocol against app.ai.provider.mock_intents' deterministic
classifier:

Round 1 (no tool outcomes yet in the conversation): classify the user's
latest question and request exactly the allowlisted tool call(s) that
question needs - or, if the question doesn't match any recognized shape (or
an "afford" question has no parseable amount), answer immediately with an
explicit insufficient-data/insufficient-tools message and no tool call at
all.

Round 2 (tool outcomes are present): compose the final answer using ONLY
the real values the tools returned. Every number in the response text
traces directly to a tool outcome; nothing here is invented, and an empty
or error outcome always produces an explicit "not enough data" answer
rather than a fabricated one.

`name` is always "mock" - never a real vendor name - so nothing downstream
can mistake this for a real external AI call.
"""

from app.ai.provider.base import (
    AIProvider,
    ConversationMessage,
    ProviderTurn,
    ToolCall,
    ToolDefinition,
    ToolOutcome,
)
from app.ai.provider.mock_intents import ClassifiedIntent, Intent, classify_intent
from app.services.export_formatting import format_money

_SUPPORTED_EXAMPLES = (
    "Where am I spending the most?",
    "How much did I spend on food this month?",
    "Compare this month with last month.",
    "What are my biggest recurring expenses?",
    "How much should I save each month?",
    "Can I afford a ₹70,000 phone?",
)

_INSUFFICIENT_DATA = "There is not enough data to answer that reliably."


def _last_user_text(conversation: list[ConversationMessage]) -> str:
    for message in reversed(conversation):
        if message.role == "user" and message.text is not None:
            return message.text
    return ""


def _last_tool_outcomes(conversation: list[ConversationMessage]) -> tuple[ToolOutcome, ...]:
    if conversation and conversation[-1].role == "user":
        return conversation[-1].tool_outcomes
    return ()


def _outcome_by_name(outcomes: tuple[ToolOutcome, ...], name: str) -> ToolOutcome | None:
    for outcome in outcomes:
        if outcome.name == name:
            return outcome
    return None


def _tool_calls_for_intent(classified: ClassifiedIntent) -> tuple[ToolCall, ...]:
    intent = classified.intent
    if intent in (Intent.TOP_SPENDING, Intent.CATEGORY_SPENDING):
        return (ToolCall(id="1", name="get_category_spending", arguments={}),)
    if intent == Intent.COMPARE_MONTHS:
        return (ToolCall(id="1", name="compare_periods", arguments={}),)
    if intent == Intent.BIGGEST_RECURRING:
        return (ToolCall(id="1", name="get_recurring_expenses", arguments={}),)
    if intent == Intent.SAVINGS_RECOMMENDATION:
        return (
            ToolCall(id="1", name="get_savings_goals", arguments={}),
            ToolCall(id="2", name="get_monthly_spending", arguments={}),
        )
    if intent == Intent.AFFORDABILITY:
        if classified.amount_minor is None:
            return ()
        return (
            ToolCall(id="1", name="get_account_balances", arguments={}),
            ToolCall(id="2", name="get_monthly_spending", arguments={}),
        )
    if intent == Intent.BUDGET_STATUS:
        return (ToolCall(id="1", name="get_budget_status", arguments={}),)
    if intent == Intent.ACCOUNT_BALANCES:
        return (ToolCall(id="1", name="get_account_balances", arguments={}),)
    if intent == Intent.TRANSACTIONS_LOOKUP:
        return (ToolCall(id="1", name="get_transactions", arguments={}),)
    return ()


def _compose_no_tool_answer(classified: ClassifiedIntent) -> str:
    if classified.intent == Intent.AFFORDABILITY:
        return (
            f"{_INSUFFICIENT_DATA} I couldn't find a specific amount in your question - "
            'try asking, for example, "Can I afford a ₹70,000 phone?"'
        )
    examples = "\n".join(f"- {q}" for q in _SUPPORTED_EXAMPLES)
    return (
        "The available financial tools can't answer that question. I can only answer "
        "questions grounded in your real recorded data, such as:\n"
        f"{examples}"
    )


def _compose_category_answer(
    classified: ClassifiedIntent, outcomes: tuple[ToolOutcome, ...]
) -> str:
    outcome = _outcome_by_name(outcomes, "get_category_spending")
    if outcome is None or outcome.is_error:
        return _INSUFFICIENT_DATA
    data = outcome.output
    currency = data.get("currency", "INR")
    period_label = data.get("period_label", "this period")
    categories = data.get("categories", [])

    if not categories or data.get("total_expense_minor", 0) <= 0:
        return f"{_INSUFFICIENT_DATA} I couldn't find any expense transactions for {period_label}."

    if classified.intent == Intent.CATEGORY_SPENDING and classified.keyword:
        keyword = classified.keyword.lower()
        match = next(
            (c for c in categories if keyword in c["name"].lower() or c["name"].lower() in keyword),
            None,
        )
        if match is None:
            names = ", ".join(c["name"] for c in categories)
            return (
                f'{_INSUFFICIENT_DATA} I couldn\'t find a category matching "{classified.keyword}" '
                f"in {period_label}. Categories with spending this period: {names}."
            )
        amount = format_money(match["amount_minor"], currency)
        return (
            f"In {period_label}, you spent {amount} on {match['name']} "
            f"({match['percent']}% of your total expenses)."
        )

    top = categories[0]
    lines = [f"In {period_label}, here's where your money went, highest first:"]
    for category in categories[:5]:
        lines.append(
            f"- {category['name']}: {format_money(category['amount_minor'], currency)} "
            f"({category['percent']}%)"
        )
    lines.append(
        f"\nYou're spending the most on {top['name']} "
        f"({format_money(top['amount_minor'], currency)}, {top['percent']}% of total expenses)."
    )
    return "\n".join(lines)


def _compose_compare_answer(outcomes: tuple[ToolOutcome, ...]) -> str:
    outcome = _outcome_by_name(outcomes, "compare_periods")
    if outcome is None or outcome.is_error:
        return _INSUFFICIENT_DATA
    data = outcome.output
    currency = data.get("currency", "INR")
    period_a, period_b = data["period_a"], data["period_b"]

    if (
        period_a["total_expense_minor"] == 0
        and period_b["total_expense_minor"] == 0
        and period_a["total_income_minor"] == 0
        and period_b["total_income_minor"] == 0
    ):
        return (
            f"{_INSUFFICIENT_DATA} No transactions were recorded in "
            f"{period_a['label']} or {period_b['label']}."
        )

    lines = [
        f"{period_a['label']}: {format_money(period_a['total_expense_minor'], currency)} spent, "
        f"{format_money(period_a['total_income_minor'], currency)} earned.",
        f"{period_b['label']}: {format_money(period_b['total_expense_minor'], currency)} spent, "
        f"{format_money(period_b['total_income_minor'], currency)} earned.",
    ]
    expense_change = data.get("expense_percent_change")
    expense_diff = data["expense_diff_minor"]
    if expense_change is not None:
        direction = "more" if expense_diff > 0 else "less"
        lines.append(
            f"\nYou spent {format_money(abs(expense_diff), currency)} {direction} in "
            f"{period_a['label']} than {period_b['label']} ({expense_change:+.1f}%)."
        )
    else:
        lines.append(
            f"\nSpending changed by {format_money(expense_diff, currency)}, but a percent change "
            f"isn't meaningful since {period_b['label']} had no recorded expenses."
        )
    return "\n".join(lines)


def _compose_recurring_answer(outcomes: tuple[ToolOutcome, ...]) -> str:
    outcome = _outcome_by_name(outcomes, "get_recurring_expenses")
    if outcome is None or outcome.is_error:
        return _INSUFFICIENT_DATA
    data = outcome.output
    currency = data.get("currency", "INR")
    active_items = [item for item in data.get("items", []) if item["is_active"]]
    if not active_items:
        return f"{_INSUFFICIENT_DATA} You don't have any active recurring expenses set up."

    lines = ["Your biggest recurring expenses, highest actual paid first:"]
    for item in active_items[:5]:
        label = "subscription" if item["is_subscription"] else "recurring expense"
        lines.append(
            f"- {item['name']} ({label}, {item['frequency']}): scheduled "
            f"{format_money(item['scheduled_monthly_cost_minor'], currency)}/month, actually paid "
            f"{format_money(item['actual_paid_minor'], currency)} this period"
        )
    lines.append(
        "\nTotal scheduled monthly commitment: "
        f"{format_money(data.get('total_scheduled_monthly_minor', 0), currency)}."
    )
    return "\n".join(lines)


def _compose_savings_answer(outcomes: tuple[ToolOutcome, ...]) -> str:
    goals_outcome = _outcome_by_name(outcomes, "get_savings_goals")
    monthly_outcome = _outcome_by_name(outcomes, "get_monthly_spending")
    if goals_outcome is None or goals_outcome.is_error:
        return _INSUFFICIENT_DATA
    if monthly_outcome is None or monthly_outcome.is_error:
        return _INSUFFICIENT_DATA

    goals = goals_outcome.output.get("goals", [])
    monthly = monthly_outcome.output
    currency = monthly.get("currency", "INR")
    total_income = monthly.get("total_income_minor", 0)

    active_goals = [
        g
        for g in goals
        if not g["is_completed"] and g["required_monthly_savings_minor"] is not None
    ]

    if not active_goals and total_income <= 0:
        return (
            f"{_INSUFFICIENT_DATA} You have no active savings goals and no income was recorded "
            "this month."
        )

    lines: list[str] = []
    if active_goals:
        total_required = sum(g["required_monthly_savings_minor"] for g in active_goals)
        lines.append(
            f"Fact: based on your {len(active_goals)} active savings goal(s), you need to save "
            f"{format_money(total_required, currency)} per month in total to hit their target "
            "dates:"
        )
        for goal in active_goals:
            required = format_money(goal["required_monthly_savings_minor"], currency)
            lines.append(
                f"- {goal['name']}: {required}/month "
                f"({goal['progress_percent']}% there, target {goal['target_date']})"
            )
    else:
        lines.append("You don't currently have any active savings goals with a target date.")

    if total_income > 0:
        net = monthly.get("net_minor", 0)
        lines.append(
            f"\nFact: in {monthly.get('period_label')}, you earned "
            f"{format_money(total_income, currency)} and are currently saving "
            f"{format_money(net, currency)} ({monthly.get('savings_rate_percent')}% of income)."
        )
        estimate_20_percent = round(total_income * 0.20)
        lines.append(
            "Estimate (a common general guideline, not personalized advice): saving at least "
            f"20% of income would be {format_money(estimate_20_percent, currency)}/month. This is "
            "a rule of thumb, not a calculation of what you specifically need beyond any goals "
            "above."
        )
    return "\n".join(lines)


def _compose_affordability_answer(
    classified: ClassifiedIntent, outcomes: tuple[ToolOutcome, ...]
) -> str:
    amount_minor = classified.amount_minor
    assert amount_minor is not None  # guaranteed by _tool_calls_for_intent

    balances_outcome = _outcome_by_name(outcomes, "get_account_balances")
    if balances_outcome is None or balances_outcome.is_error:
        return _INSUFFICIENT_DATA

    balances = balances_outcome.output
    currency = balances.get("currency", "INR")
    total_assets = balances.get("total_assets_minor", 0)
    accounts = balances.get("accounts", [])
    if not accounts:
        return (
            f"{_INSUFFICIENT_DATA} No accounts are set up yet, so I have no balance to check "
            "this against."
        )

    remaining = total_assets - amount_minor
    lines = [
        f"Assumptions: this compares {format_money(amount_minor, currency)} against your "
        f"combined balance across all active accounts ({format_money(total_assets, currency)}), "
        "not a single account, and ignores anything already earmarked for savings goals or "
        "upcoming bills.",
        "",
        f"Calculation: {format_money(total_assets, currency)} - "
        f"{format_money(amount_minor, currency)} = {format_money(remaining, currency)} remaining.",
    ]

    monthly_outcome = _outcome_by_name(outcomes, "get_monthly_spending")
    if monthly_outcome is not None and not monthly_outcome.is_error:
        monthly = monthly_outcome.output
        expense = monthly.get("total_expense_minor", 0)
        if expense > 0:
            months_of_expenses = round(remaining / expense, 1)
            lines.append(
                f"\nContext: your recorded expenses in {monthly.get('period_label')} were "
                f"{format_money(expense, currency)}. After this purchase you'd have roughly "
                f"{months_of_expenses} month(s) of spending at that rate left in these accounts."
            )

    if remaining < 0:
        lines.append(
            f"\nThis purchase would exceed your combined account balance by "
            f"{format_money(-remaining, currency)}."
        )
    else:
        lines.append(
            f"\nYou would have {format_money(remaining, currency)} left after this purchase."
        )

    lines.append(
        "\nLimitations: this is based only on your recorded account balances and this month's "
        "spending - it doesn't know about upcoming bills, income you haven't logged yet, or your "
        "broader financial goals, and this is not personalized financial advice."
    )
    return "\n".join(lines)


def _compose_budget_answer(outcomes: tuple[ToolOutcome, ...]) -> str:
    outcome = _outcome_by_name(outcomes, "get_budget_status")
    if outcome is None or outcome.is_error:
        return _INSUFFICIENT_DATA
    data = outcome.output
    currency = data.get("currency", "INR")
    items = data.get("items", [])
    if not items:
        return f"{_INSUFFICIENT_DATA} You don't have any budgets set up yet."

    lines = ["Here's your budget status for this month:"]
    for item in items:
        lines.append(
            f"- {item['category_name']}: {format_money(item['spent_minor'], currency)} of "
            f"{format_money(item['amount_minor'], currency)} spent "
            f"({item['percent_used']}%, {item['status']})"
        )
    return "\n".join(lines)


def _compose_balances_answer(outcomes: tuple[ToolOutcome, ...]) -> str:
    outcome = _outcome_by_name(outcomes, "get_account_balances")
    if outcome is None or outcome.is_error:
        return _INSUFFICIENT_DATA
    data = outcome.output
    currency = data.get("currency", "INR")
    accounts = data.get("accounts", [])
    if not accounts:
        return f"{_INSUFFICIENT_DATA} No accounts are set up yet."

    lines = ["Here are your account balances:"]
    for account in accounts:
        lines.append(
            f"- {account['name']} ({account['type']}): "
            f"{format_money(account['balance_minor'], currency)}"
        )
    lines.append(
        f"\nNet worth: {format_money(data.get('net_worth_minor', 0), currency)} "
        f"(assets {format_money(data.get('total_assets_minor', 0), currency)}, "
        f"liabilities {format_money(data.get('total_liabilities_minor', 0), currency)})."
    )
    return "\n".join(lines)


def _compose_transactions_answer(outcomes: tuple[ToolOutcome, ...]) -> str:
    outcome = _outcome_by_name(outcomes, "get_transactions")
    if outcome is None or outcome.is_error:
        return _INSUFFICIENT_DATA
    data = outcome.output
    transactions = data.get("transactions", [])
    if not transactions:
        return f"{_INSUFFICIENT_DATA} No transactions were found."

    lines = [f"Here are your {len(transactions)} most recent matching transactions:"]
    for txn in transactions[:10]:
        label = txn.get("merchant") or txn.get("description") or txn.get("category_name") or "—"
        lines.append(
            f"- {txn['occurred_at'][:10]}: {label} - "
            f"{format_money(txn['amount_minor'], txn['currency'])} ({txn['type']})"
        )
    total_matching = data.get("total_matching", 0)
    if total_matching > len(transactions):
        lines.append(f"\n({total_matching} total match your filters; showing {len(transactions)}.)")
    return "\n".join(lines)


def _compose_answer(classified: ClassifiedIntent, outcomes: tuple[ToolOutcome, ...]) -> str:
    intent = classified.intent
    if intent in (Intent.TOP_SPENDING, Intent.CATEGORY_SPENDING):
        return _compose_category_answer(classified, outcomes)
    if intent == Intent.COMPARE_MONTHS:
        return _compose_compare_answer(outcomes)
    if intent == Intent.BIGGEST_RECURRING:
        return _compose_recurring_answer(outcomes)
    if intent == Intent.SAVINGS_RECOMMENDATION:
        return _compose_savings_answer(outcomes)
    if intent == Intent.AFFORDABILITY:
        return _compose_affordability_answer(classified, outcomes)
    if intent == Intent.BUDGET_STATUS:
        return _compose_budget_answer(outcomes)
    if intent == Intent.ACCOUNT_BALANCES:
        return _compose_balances_answer(outcomes)
    if intent == Intent.TRANSACTIONS_LOOKUP:
        return _compose_transactions_answer(outcomes)
    return _INSUFFICIENT_DATA


class MockProvider:
    """A pure function of the conversation history - holds no per-request
    instance state, so a single instance (see app.ai.provider.factory) is
    safe to reuse concurrently across requests."""

    name = "mock"

    async def next_turn(
        self,
        *,
        system_prompt: str,
        conversation: list[ConversationMessage],
        tools: list[ToolDefinition],
    ) -> ProviderTurn:
        del system_prompt, tools  # unused - the mock's behavior is fixed, not prompted

        outcomes = _last_tool_outcomes(conversation)
        original_text = _last_user_text(conversation)
        classified = classify_intent(original_text)

        if not outcomes:
            calls = _tool_calls_for_intent(classified)
            if not calls:
                return ProviderTurn(text=_compose_no_tool_answer(classified))
            return ProviderTurn(tool_calls=calls)

        return ProviderTurn(text=_compose_answer(classified, outcomes))


assert isinstance(MockProvider(), AIProvider)
