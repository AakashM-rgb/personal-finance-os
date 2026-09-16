import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import pytest

from app.ai.provider.base import ConversationMessage, ProviderTurn, ToolCall, ToolDefinition
from app.models.transaction import TransactionType
from app.schemas.category import CategoryRead
from app.search import interpreter as interpreter_module
from app.search.interpreter import (
    AnthropicSearchInterpreter,
    DeterministicSearchInterpreter,
    SearchInterpretationError,
    get_search_interpreter,
    interpret,
)

_NOW = datetime(2026, 3, 15, tzinfo=UTC)


def _category(name: str) -> CategoryRead:
    now = datetime.now(UTC)
    return CategoryRead(
        id=uuid.uuid4(),
        name=name,
        icon="X",
        color="#000000",
        budget_minor=None,
        parent_id=None,
        is_system=True,
        is_active=True,
        created_at=now,
        updated_at=now,
    )


@pytest.fixture
def categories() -> list[CategoryRead]:
    return [_category("Food"), _category("Transport"), _category("Shopping")]


@pytest.fixture
def interpreter() -> DeterministicSearchInterpreter:
    return DeterministicSearchInterpreter()


# --- A/6.F/6.G/6.H: the six core supported examples -----------------------------------------


async def test_food_last_month(interpreter, categories) -> None:
    outcome = await interpreter.interpret("food last month", categories=categories, now=_NOW)
    food = next(c for c in categories if c.name == "Food")
    assert outcome.query.category_id == food.id
    assert outcome.query.start_date.isoformat() == "2026-02-01"
    assert outcome.query.end_date.isoformat() == "2026-02-28"
    assert outcome.query.transaction_type == TransactionType.EXPENSE
    assert outcome.requires_confirmation is False


async def test_amazon_purchases_above_1000(interpreter, categories) -> None:
    outcome = await interpreter.interpret(
        "Amazon purchases above ₹1000", categories=categories, now=_NOW
    )
    assert outcome.query.search_text == "Amazon"
    assert outcome.query.min_amount_minor == 100000
    assert outcome.query.transaction_type == TransactionType.EXPENSE
    assert outcome.requires_confirmation is False


async def test_transport_expenses_in_august(interpreter, categories) -> None:
    outcome = await interpreter.interpret(
        "transport expenses in August", categories=categories, now=_NOW
    )
    transport = next(c for c in categories if c.name == "Transport")
    assert outcome.query.category_id == transport.id
    assert outcome.query.start_date.isoformat() == "2025-08-01"
    assert outcome.query.end_date.isoformat() == "2025-08-31"
    assert outcome.requires_confirmation is False


async def test_biggest_expenses_this_year(interpreter, categories) -> None:
    outcome = await interpreter.interpret(
        "biggest expenses this year", categories=categories, now=_NOW
    )
    assert outcome.query.transaction_type == TransactionType.EXPENSE
    assert outcome.query.start_date.isoformat() == "2026-01-01"
    assert outcome.query.end_date.isoformat() == "2026-03-15"
    assert outcome.query.sort == "amount_desc"
    assert outcome.requires_confirmation is False


async def test_weekend_spending(interpreter, categories) -> None:
    outcome = await interpreter.interpret("weekend spending", categories=categories, now=_NOW)
    assert outcome.query.days_of_week == [0, 6]
    assert outcome.query.transaction_type == TransactionType.EXPENSE
    assert outcome.requires_confirmation is False


async def test_weekend_spending_this_month(interpreter, categories) -> None:
    outcome = await interpreter.interpret(
        "weekend spending this month", categories=categories, now=_NOW
    )
    assert outcome.query.days_of_week == [0, 6]
    assert outcome.query.start_date.isoformat() == "2026-03-01"
    assert outcome.requires_confirmation is False


async def test_subscriptions_this_month(interpreter, categories) -> None:
    outcome = await interpreter.interpret(
        "subscriptions this month", categories=categories, now=_NOW
    )
    assert outcome.query.subscriptions_only is True
    assert outcome.query.start_date.isoformat() == "2026-03-01"
    assert outcome.requires_confirmation is False


# --- amount phrase variations -----------------------------------------------------------


@pytest.mark.parametrize(
    "phrase",
    [
        "Amazon above ₹1000",
        "Amazon over ₹1000",
        "Amazon more than ₹1000",
        "Amazon at least ₹1000",
    ],
)
async def test_min_amount_phrase_equivalents(interpreter, categories, phrase) -> None:
    outcome = await interpreter.interpret(phrase, categories=categories, now=_NOW)
    assert outcome.query.min_amount_minor == 100000


@pytest.mark.parametrize(
    "phrase",
    ["Amazon under ₹500", "Amazon below ₹500", "Amazon less than ₹500"],
)
async def test_max_amount_phrase_equivalents(interpreter, categories, phrase) -> None:
    outcome = await interpreter.interpret(phrase, categories=categories, now=_NOW)
    assert outcome.query.max_amount_minor == 50000


async def test_comma_separated_amount() -> None:
    interp = DeterministicSearchInterpreter()
    outcome = await interp.interpret("Amazon above ₹1,000", categories=[], now=_NOW)
    assert outcome.query.min_amount_minor == 100000


async def test_decimal_amount() -> None:
    interp = DeterministicSearchInterpreter()
    outcome = await interp.interpret("above ₹999.50", categories=[], now=_NOW)
    assert outcome.query.min_amount_minor == 99950


async def test_amount_never_misrounds_due_to_floats() -> None:
    interp = DeterministicSearchInterpreter()
    outcome = await interp.interpret("above ₹2336.50", categories=[], now=_NOW)
    assert outcome.query.min_amount_minor == 233650


async def test_k_shorthand_amount() -> None:
    interp = DeterministicSearchInterpreter()
    outcome = await interp.interpret("Amazon above 70k", categories=[], now=_NOW)
    assert outcome.query.min_amount_minor == 7000000


# --- capitalization / whitespace robustness ----------------------------------------------


async def test_capitalization_does_not_affect_interpretation(interpreter, categories) -> None:
    outcome = await interpreter.interpret("FOOD LAST MONTH", categories=categories, now=_NOW)
    food = next(c for c in categories if c.name == "Food")
    assert outcome.query.category_id == food.id


async def test_extra_whitespace_does_not_affect_interpretation(interpreter, categories) -> None:
    outcome = await interpreter.interpret(
        "  food    last   month  ", categories=categories, now=_NOW
    )
    food = next(c for c in categories if c.name == "Food")
    assert outcome.query.category_id == food.id


# --- income vs expense -----------------------------------------------------------------


async def test_income_keyword_sets_income_type() -> None:
    interp = DeterministicSearchInterpreter()
    outcome = await interp.interpret("income this month", categories=[], now=_NOW)
    assert outcome.query.transaction_type == TransactionType.INCOME


async def test_default_type_is_expense_when_unspecified() -> None:
    interp = DeterministicSearchInterpreter()
    outcome = await interp.interpret("Amazon", categories=[], now=_NOW)
    assert outcome.query.transaction_type == TransactionType.EXPENSE


# --- ambiguity handling (§17) -----------------------------------------------------------


async def test_amazon_alone_is_not_ambiguous(interpreter, categories) -> None:
    # A merchant/text search is well-defined on its own data model - see
    # app.search.interpreter._has_qualifying_signal's docstring.
    outcome = await interpreter.interpret("Amazon", categories=categories, now=_NOW)
    assert outcome.requires_confirmation is False
    assert outcome.query.search_text == "Amazon"


async def test_bare_month_alone_is_ambiguous(interpreter, categories) -> None:
    outcome = await interpreter.interpret("August", categories=categories, now=_NOW)
    assert outcome.requires_confirmation is True
    assert outcome.ambiguity_reason is not None
    # The interpreted period is still shown, never hidden while waiting for confirmation.
    assert outcome.query.start_date.isoformat() == "2025-08-01"


async def test_generic_word_alone_is_ambiguous(interpreter, categories) -> None:
    outcome = await interpreter.interpret("expenses", categories=categories, now=_NOW)
    assert outcome.requires_confirmation is True
    assert outcome.ambiguous_categories == []


async def test_ambiguous_category_phrase_requires_confirmation() -> None:
    categories = [_category("Car Insurance"), _category("Car Rental"), _category("Food")]
    interp = DeterministicSearchInterpreter()
    outcome = await interp.interpret("car", categories=categories, now=_NOW)
    assert outcome.requires_confirmation is True
    assert len(outcome.ambiguous_categories) == 2
    assert outcome.query.category_id is None


async def test_empty_query_is_ambiguous(interpreter) -> None:
    outcome = await interpreter.interpret("", categories=[], now=_NOW)
    assert outcome.requires_confirmation is True


# --- AI-assisted interpreter (AnthropicSearchInterpreter) ----------------------------------
#
# Exercised with a fake AIProvider (never a real network call) - this is the
# path that only ever runs once ANTHROPIC_API_KEY is configured, so it must
# be just as thoroughly covered as the deterministic path: the model is an
# untrusted proposer of arguments, never a source of truth, and everything
# it returns still goes through FinancialSearchQuery.model_validate() before
# use (see app.search.interpreter.interpret's docstring).


@dataclass
class _FakeProvider:
    name: str = "anthropic"
    turn: ProviderTurn | None = None
    exc: Exception | None = None
    calls: list[dict[str, Any]] = field(default_factory=list)

    async def next_turn(
        self,
        *,
        system_prompt: str,
        conversation: list[ConversationMessage],
        tools: list[ToolDefinition],
    ) -> ProviderTurn:
        self.calls.append({"system_prompt": system_prompt, "conversation": conversation})
        if self.exc is not None:
            raise self.exc
        assert self.turn is not None
        return self.turn


def _tool_call(arguments: dict[str, Any]) -> ProviderTurn:
    call = ToolCall(id="call_1", name="interpret_financial_search", arguments=arguments)
    return ProviderTurn(tool_calls=(call,))


def _patch_provider(monkeypatch: pytest.MonkeyPatch, fake: _FakeProvider) -> None:
    monkeypatch.setattr(interpreter_module, "get_ai_provider", lambda: fake)


def test_get_search_interpreter_selects_anthropic_when_configured_and_ai_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_provider(monkeypatch, _FakeProvider())
    result = get_search_interpreter(ai_enabled=True)
    assert isinstance(result, AnthropicSearchInterpreter)


def test_get_search_interpreter_falls_back_to_deterministic_when_ai_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """CLAUDE.md §14: disabling the per-user AI setting must actually stop
    an AI provider call, not just hide UI - the interpreter selection
    itself refuses the AI-assisted path, mirroring
    app.ai.tools.registry.validate_and_execute's ai_enabled check."""
    _patch_provider(monkeypatch, _FakeProvider())
    result = get_search_interpreter(ai_enabled=False)
    assert isinstance(result, DeterministicSearchInterpreter)


def test_get_search_interpreter_uses_deterministic_when_no_provider_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _patch_provider(monkeypatch, _FakeProvider(name="mock"))
    result = get_search_interpreter(ai_enabled=True)
    assert isinstance(result, DeterministicSearchInterpreter)


async def test_ai_disabled_never_invokes_the_provider_even_via_interpret(
    monkeypatch: pytest.MonkeyPatch, categories
) -> None:
    fake = _FakeProvider(turn=_tool_call({"search_text": "Amazon"}))
    _patch_provider(monkeypatch, fake)
    await interpret("Amazon", categories=categories, now=_NOW, ai_enabled=False)
    assert fake.calls == []


async def test_anthropic_interpreter_builds_valid_query_from_tool_call(categories) -> None:
    fake = _FakeProvider(
        turn=_tool_call(
            {"search_text": "Amazon", "min_amount_minor": 100000, "transaction_type": "expense"}
        )
    )
    interp = AnthropicSearchInterpreter.__new__(AnthropicSearchInterpreter)
    interp._provider = fake
    outcome = await interp.interpret("Amazon above 1000", categories=categories, now=_NOW)
    assert outcome.query.search_text == "Amazon"
    assert outcome.query.min_amount_minor == 100000
    assert outcome.query.transaction_type == TransactionType.EXPENSE


async def test_anthropic_interpreter_defaults_type_to_expense_when_unspecified(categories) -> None:
    """An unset transaction_type must never reach the query builder as
    `None` - that would map to "no type filter" and let transfers leak
    into a search result (see app.search.interpreter's fix comment)."""
    fake = _FakeProvider(turn=_tool_call({"search_text": "Amazon"}))
    interp = AnthropicSearchInterpreter.__new__(AnthropicSearchInterpreter)
    interp._provider = fake
    outcome = await interp.interpret("Amazon", categories=categories, now=_NOW)
    assert outcome.query.transaction_type == TransactionType.EXPENSE


async def test_anthropic_interpreter_respects_explicit_income_type(categories) -> None:
    fake = _FakeProvider(turn=_tool_call({"transaction_type": "income"}))
    interp = AnthropicSearchInterpreter.__new__(AnthropicSearchInterpreter)
    interp._provider = fake
    outcome = await interp.interpret("salary this month", categories=categories, now=_NOW)
    assert outcome.query.transaction_type == TransactionType.INCOME


async def test_anthropic_interpreter_drops_hallucinated_category_id(categories) -> None:
    """A category id the model invented (never offered in the categories
    list passed to it) must never be trusted - see the "never look it up
    blindly" comment in AnthropicSearchInterpreter.interpret."""
    fake = _FakeProvider(turn=_tool_call({"category_id": str(uuid.uuid4()), "search_text": "test"}))
    interp = AnthropicSearchInterpreter.__new__(AnthropicSearchInterpreter)
    interp._provider = fake
    outcome = await interp.interpret("something", categories=categories, now=_NOW)
    assert outcome.query.category_id is None


async def test_anthropic_interpreter_accepts_offered_category_id(categories) -> None:
    food = next(c for c in categories if c.name == "Food")
    fake = _FakeProvider(turn=_tool_call({"category_id": str(food.id)}))
    interp = AnthropicSearchInterpreter.__new__(AnthropicSearchInterpreter)
    interp._provider = fake
    outcome = await interp.interpret("food", categories=categories, now=_NOW)
    assert outcome.query.category_id == food.id


async def test_anthropic_interpreter_rejects_unknown_field_from_model(categories) -> None:
    """Even a "helpful" extra field the model invents (e.g. trying to smuggle
    through something FinancialSearchQuery doesn't define) is rejected by
    Pydantic's extra="forbid", not silently dropped-and-accepted elsewhere."""
    fake = _FakeProvider(
        turn=_tool_call({"search_text": "Amazon", "sql": "DROP TABLE transactions"})
    )
    interp = AnthropicSearchInterpreter.__new__(AnthropicSearchInterpreter)
    interp._provider = fake
    with pytest.raises(SearchInterpretationError):
        await interp.interpret("Amazon", categories=categories, now=_NOW)


async def test_anthropic_interpreter_rejects_malformed_amount(categories) -> None:
    fake = _FakeProvider(turn=_tool_call({"min_amount_minor": -500}))
    interp = AnthropicSearchInterpreter.__new__(AnthropicSearchInterpreter)
    interp._provider = fake
    with pytest.raises(SearchInterpretationError):
        await interp.interpret("something", categories=categories, now=_NOW)


async def test_anthropic_interpreter_raises_when_model_skips_tool_call(categories) -> None:
    fake = _FakeProvider(turn=ProviderTurn(text="I'm not sure what you mean."))
    interp = AnthropicSearchInterpreter.__new__(AnthropicSearchInterpreter)
    interp._provider = fake
    with pytest.raises(SearchInterpretationError):
        await interp.interpret("???", categories=categories, now=_NOW)


async def test_anthropic_interpreter_raises_when_provider_call_fails(categories) -> None:
    fake = _FakeProvider(exc=RuntimeError("network exploded"))
    interp = AnthropicSearchInterpreter.__new__(AnthropicSearchInterpreter)
    interp._provider = fake
    with pytest.raises(SearchInterpretationError):
        await interp.interpret("Amazon", categories=categories, now=_NOW)


# --- top-level interpret(): AI-assisted failures always fall back cleanly -------------------


async def test_interpret_falls_back_to_deterministic_when_provider_errors(
    monkeypatch: pytest.MonkeyPatch, categories
) -> None:
    _patch_provider(monkeypatch, _FakeProvider(exc=RuntimeError("boom")))
    outcome = await interpret("food last month", categories=categories, now=_NOW, ai_enabled=True)
    food = next(c for c in categories if c.name == "Food")
    assert outcome.query.category_id == food.id
    assert outcome.requires_confirmation is False


async def test_interpret_falls_back_to_deterministic_when_model_omits_tool_call(
    monkeypatch: pytest.MonkeyPatch, categories
) -> None:
    _patch_provider(monkeypatch, _FakeProvider(turn=ProviderTurn(text="not a tool call")))
    outcome = await interpret("weekend spending", categories=categories, now=_NOW, ai_enabled=True)
    assert outcome.query.days_of_week == [0, 6]


async def test_interpret_falls_back_to_deterministic_when_tool_output_is_malformed(
    monkeypatch: pytest.MonkeyPatch, categories
) -> None:
    _patch_provider(
        monkeypatch, _FakeProvider(turn=_tool_call({"limit": 99999, "sql": "SELECT * FROM users"}))
    )
    outcome = await interpret("Amazon", categories=categories, now=_NOW, ai_enabled=True)
    # The deterministic fallback still produces a normal, valid result.
    assert outcome.query.search_text == "Amazon"
