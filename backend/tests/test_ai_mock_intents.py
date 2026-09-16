from app.ai.provider.mock_intents import Intent, classify_intent


def test_top_spending() -> None:
    result = classify_intent("Where am I spending the most?")
    assert result.intent == Intent.TOP_SPENDING


def test_category_spending_extracts_keyword() -> None:
    result = classify_intent("How much did I spend on food this month?")
    assert result.intent == Intent.CATEGORY_SPENDING
    assert result.keyword == "food"


def test_category_spending_extracts_multiword_keyword() -> None:
    result = classify_intent("How much did I spend on eating out last month?")
    assert result.intent == Intent.CATEGORY_SPENDING
    assert result.keyword == "eating out"


def test_compare_months() -> None:
    result = classify_intent("Compare this month with last month.")
    assert result.intent == Intent.COMPARE_MONTHS


def test_biggest_recurring() -> None:
    result = classify_intent("What are my biggest recurring expenses?")
    assert result.intent == Intent.BIGGEST_RECURRING


def test_biggest_recurring_matches_subscriptions_keyword() -> None:
    result = classify_intent("List my subscriptions")
    assert result.intent == Intent.BIGGEST_RECURRING


def test_savings_recommendation() -> None:
    result = classify_intent("How much should I save each month?")
    assert result.intent == Intent.SAVINGS_RECOMMENDATION


def test_affordability_extracts_amount_with_comma_and_symbol() -> None:
    result = classify_intent("Can I afford a ₹70,000 phone?")
    assert result.intent == Intent.AFFORDABILITY
    assert result.amount_minor == 7_000_000


def test_affordability_extracts_k_shorthand() -> None:
    result = classify_intent("Can I afford a 70k laptop?")
    assert result.intent == Intent.AFFORDABILITY
    assert result.amount_minor == 7_000_000


def test_affordability_extracts_plain_number() -> None:
    result = classify_intent("Can I afford 5000 rupees for shoes?")
    assert result.intent == Intent.AFFORDABILITY
    assert result.amount_minor == 500_000


def test_affordability_without_amount_has_none() -> None:
    result = classify_intent("Can I afford this?")
    assert result.intent == Intent.AFFORDABILITY
    assert result.amount_minor is None


def test_budget_status() -> None:
    result = classify_intent("What's my budget status?")
    assert result.intent == Intent.BUDGET_STATUS


def test_account_balances() -> None:
    result = classify_intent("What's my account balance?")
    assert result.intent == Intent.ACCOUNT_BALANCES


def test_transactions_lookup() -> None:
    result = classify_intent("Show me my recent transactions")
    assert result.intent == Intent.TRANSACTIONS_LOOKUP


def test_unsupported_falls_through() -> None:
    result = classify_intent("What's the weather like today?")
    assert result.intent == Intent.UNSUPPORTED


def test_empty_text_is_unsupported() -> None:
    result = classify_intent("   ")
    assert result.intent == Intent.UNSUPPORTED


def test_afford_takes_priority_over_other_keywords() -> None:
    # Contains "budget" too, but "afford" is the more specific, intended ask.
    result = classify_intent("Given my budget, can I afford a ₹10,000 jacket?")
    assert result.intent == Intent.AFFORDABILITY
    assert result.amount_minor == 1_000_000
