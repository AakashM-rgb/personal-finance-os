"""Tests for the narrow one-shot merchant-classification abstraction
(app.ai.classifier) - deliberately separate from the conversational
Financial AI Assistant (app.ai.provider, covered by test_ai_*.py). No
database is involved anywhere in this file: every implementation here is a
pure function of its input, and that is itself part of what's being
verified.
"""

import ast
import asyncio
import inspect
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.ai.classifier import anthropic as classifier_anthropic
from app.ai.classifier import base as classifier_base
from app.ai.classifier import mock as classifier_mock
from app.ai.classifier.anthropic import _TOOL_NAME, AnthropicMerchantClassifier
from app.ai.classifier.base import (
    MerchantClassificationRequest,
    MerchantClassificationResult,
    MerchantClassifier,
    validate_classification,
)
from app.ai.classifier.factory import build_merchant_classifier, get_merchant_classifier
from app.ai.classifier.mock import MockMerchantClassifier
from app.core.config import get_settings

# --- mock classification behavior --------------------------------------------------------


async def test_mock_classifies_a_known_merchant_into_a_supplied_category() -> None:
    classifier = MockMerchantClassifier()
    request = MerchantClassificationRequest(
        merchant="Swiggy",
        transaction_type="expense",
        category_names=("Food", "Shopping", "Transport"),
    )

    result = await classifier.classify(request)

    assert result.category_name == "Food"
    assert 0.0 < result.confidence <= 1.0


async def test_mock_returns_no_classification_for_an_unknown_merchant() -> None:
    classifier = MockMerchantClassifier()
    request = MerchantClassificationRequest(
        merchant="Some Random Local Shop",
        category_names=("Food", "Shopping", "Transport"),
    )

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


async def test_mock_never_returns_a_category_missing_from_category_names() -> None:
    """Swiggy is a recognized merchant, but this caller's own category list
    doesn't happen to include "Food" - the mock must never hand back a
    category the caller didn't offer, even one it "knows" the answer for."""
    classifier = MockMerchantClassifier()
    request = MerchantClassificationRequest(
        merchant="Swiggy",
        category_names=("Utilities", "Rent"),
    )

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


async def test_mock_repeated_calls_are_deterministic() -> None:
    classifier = MockMerchantClassifier()
    request = MerchantClassificationRequest(
        merchant="Amazon", category_names=("Shopping", "Food")
    )

    first = await classifier.classify(request)
    second = await classifier.classify(request)

    assert first == second


async def test_mock_requires_no_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """The mock must work even when no AI provider is configured at all -
    it never reads ANTHROPIC_API_KEY or any other credential."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    classifier = MockMerchantClassifier()
    request = MerchantClassificationRequest(merchant="Netflix", category_names=("Entertainment",))

    result = await classifier.classify(request)

    assert result.category_name == "Entertainment"


def test_mock_satisfies_the_merchant_classifier_protocol() -> None:
    assert isinstance(MockMerchantClassifier(), MerchantClassifier)


# --- validate_classification (the shared allow-list choke point) ------------------------


def test_validate_classification_accepts_an_allowed_category() -> None:
    result = validate_classification(
        category_name="Food", confidence=0.8, category_names=("Food", "Shopping")
    )
    assert result.category_name == "Food"
    assert result.confidence == 0.8


def test_validate_classification_rejects_a_category_outside_the_allow_list() -> None:
    result = validate_classification(
        category_name="Made Up Category", confidence=0.95, category_names=("Food", "Shopping")
    )
    assert result.category_name is None
    assert result.confidence == 0.0


def test_validate_classification_treats_none_category_as_empty() -> None:
    result = validate_classification(
        category_name=None, confidence=0.5, category_names=("Food",)
    )
    assert result.category_name is None
    assert result.confidence == 0.0


# --- strict model validation --------------------------------------------------------------


def test_classification_result_rejects_confidence_below_zero() -> None:
    with pytest.raises(ValidationError):
        MerchantClassificationResult(category_name="Food", confidence=-0.01)


def test_classification_result_rejects_confidence_above_one() -> None:
    with pytest.raises(ValidationError):
        MerchantClassificationResult(category_name="Food", confidence=1.01)


def test_classification_result_rejects_a_malformed_confidence_type() -> None:
    with pytest.raises(ValidationError):
        MerchantClassificationResult(category_name="Food", confidence="very confident")  # type: ignore[arg-type]


def test_classification_result_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        MerchantClassificationResult(
            category_name="Food",
            confidence=0.5,
            transaction_id="11111111-1111-1111-1111-111111111111",  # type: ignore[call-arg]
        )


def test_classification_request_rejects_unexpected_fields() -> None:
    with pytest.raises(ValidationError):
        MerchantClassificationRequest(
            merchant="Swiggy",
            category_names=("Food",),
            user_id="11111111-1111-1111-1111-111111111111",  # type: ignore[call-arg]
        )


def test_classification_request_rejects_an_empty_category_list() -> None:
    with pytest.raises(ValidationError):
        MerchantClassificationRequest(merchant="Swiggy", category_names=())


def test_classification_request_rejects_an_empty_merchant_name() -> None:
    with pytest.raises(ValidationError):
        MerchantClassificationRequest(merchant="", category_names=("Food",))


@pytest.mark.parametrize(
    "forbidden_field",
    [
        "user_id",
        "account_id",
        "account_number",
        "balance",
        "pin",
        "cvv",
        "otp",
        "password",
        "consent_id",
        "consent_handle",
        "provider_secret",
        "api_key",
        "tool_call",
        "action",
    ],
)
def test_classification_request_has_no_sensitive_or_action_fields(forbidden_field: str) -> None:
    assert forbidden_field not in MerchantClassificationRequest.model_fields


@pytest.mark.parametrize(
    "forbidden_field",
    ["transaction_id", "user_id", "account_id", "tool_call", "action"],
)
def test_classification_result_has_no_identifier_or_action_fields(forbidden_field: str) -> None:
    assert forbidden_field not in MerchantClassificationResult.model_fields


# --- factory --------------------------------------------------------------------------------


def test_factory_returns_the_mock_classifier_by_default() -> None:
    classifier = build_merchant_classifier(get_settings())
    assert isinstance(classifier, MockMerchantClassifier)
    assert classifier.name == "mock"


def test_factory_returns_the_anthropic_classifier_when_an_api_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase F2: once ANTHROPIC_API_KEY is configured, the factory selects
    AnthropicMerchantClassifier - the SAME key app.ai.provider.factory
    already uses for the conversational assistant, selected independently
    here (see app.ai.classifier.factory's module docstring)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-test")

    classifier = build_merchant_classifier(settings)

    assert isinstance(classifier, AnthropicMerchantClassifier)
    assert classifier.name == "anthropic"


def test_factory_selecting_anthropic_makes_no_network_call(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Constructing AnthropicMerchantClassifier (even via the factory) must
    never touch the network or import the optional 'anthropic' package -
    both are deferred until classify() actually runs (see that class's own
    docstring) - so selecting it can never block or fail application
    startup."""
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-test")

    classifier = build_merchant_classifier(settings)

    assert classifier._injected_client is None  # type: ignore[attr-defined]


def test_get_merchant_classifier_returns_a_classifier_instance() -> None:
    classifier = get_merchant_classifier()
    assert isinstance(classifier, MerchantClassifier)


# --- structural boundaries: no database, no ORM, no forbidden financial surface ---------


def _imported_module_names(module: object) -> set[str]:
    """The actual `import`/`from ... import` targets of a module - parsed
    via `ast` rather than a raw substring search, since these modules'
    own docstrings deliberately name app.services/app.repositories in
    prose to explain what they DON'T import; a text search would
    false-positive on that documentation."""
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


@pytest.mark.parametrize("module", [classifier_base, classifier_mock, classifier_anthropic])
def test_classifier_modules_never_import_the_database_or_orm(module: object) -> None:
    imported = _imported_module_names(module)
    forbidden_prefixes = (
        "sqlalchemy",
        "app.repositories",
        "app.services",
        "app.models",
        "app.core.database",
        "app.ai.tools",
        "app.ai.provider",
    )
    for name in imported:
        assert not name.startswith(forbidden_prefixes), (
            f"{module.__name__} imports forbidden module {name!r}"
        )


@pytest.mark.parametrize("module", [classifier_base, classifier_mock, classifier_anthropic])
def test_classifier_modules_never_reference_forbidden_financial_actions_in_code(
    module: object,
) -> None:
    """Checks executable code only (function/class bodies), not
    docstrings, for any hint of a payment/transfer/withdrawal surface or
    sensitive-credential handling."""
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    forbidden_substrings = (
        "transfer",
        "withdraw",
        "payment_auth",
        "debit_auth",
        "send_money",
        "pin",
        "cvv",
        "otp",
        "password",
        "consent",
        "credential",
    )
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            continue  # skip string literals/docstrings - identifiers only
        name = (
            getattr(node, "id", None) or getattr(node, "attr", None) or getattr(node, "arg", None)
        )
        if name is None:
            continue
        lowered = name.lower()
        for substring in forbidden_substrings:
            assert substring not in lowered, f"{module.__name__} defines forbidden name {name!r}"


def test_merchant_classifier_protocol_has_no_db_session_or_user_id_parameter() -> None:
    signature = inspect.signature(MerchantClassifier.classify)
    param_names = set(signature.parameters) - {"self"}
    assert param_names == {"request"}


# --- AnthropicMerchantClassifier -----------------------------------------------------------
#
# All of these use an injected fake client (see AnthropicMerchantClassifier's `client`
# constructor parameter) - never the real `anthropic` package, and never a real network
# call. This also lets these tests run without the optional 'anthropic' dependency
# installed at all, exactly like production code never importing it unless classify()
# actually runs with a real key and no injected client.


@dataclass
class _FakeToolUseBlock:
    type: str = "tool_use"
    name: str = _TOOL_NAME
    input: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeResponse:
    content: list[Any]


class _FakeMessages:
    def __init__(
        self,
        *,
        response: _FakeResponse | None = None,
        exception: Exception | None = None,
        delay: float = 0.0,
        capture: list[dict[str, Any]] | None = None,
    ) -> None:
        self._response = response
        self._exception = exception
        self._delay = delay
        self._capture = capture

    async def create(self, **kwargs: Any) -> _FakeResponse:
        if self._capture is not None:
            self._capture.append(kwargs)
        if self._delay:
            await asyncio.sleep(self._delay)
        if self._exception is not None:
            raise self._exception
        assert self._response is not None
        return self._response


class _FakeAnthropicClient:
    def __init__(
        self,
        *,
        response: _FakeResponse | None = None,
        exception: Exception | None = None,
        delay: float = 0.0,
        capture: list[dict[str, Any]] | None = None,
    ) -> None:
        self.messages = _FakeMessages(
            response=response, exception=exception, delay=delay, capture=capture
        )


class _ExplodingClient:
    """A client that fails the test if it's ever touched - used to prove a
    real call was never even attempted."""

    @property
    def messages(self) -> Any:
        raise AssertionError("no API call should be attempted without an API key")


def _tool_response(**tool_input: Any) -> _FakeResponse:
    return _FakeResponse(content=[_FakeToolUseBlock(input=tool_input)])


# 1. construction with a configured API key


def test_anthropic_classifier_can_be_constructed_with_a_configured_api_key() -> None:
    classifier = AnthropicMerchantClassifier(api_key="fake-key-for-test", model="claude-sonnet-5")
    assert classifier.name == "anthropic"


# 2 & 3. request payload contains only allowed fields / no sensitive fields possible


async def test_anthropic_classifier_request_contains_only_allowed_fields() -> None:
    captured: list[dict[str, Any]] = []
    fake_client = _FakeAnthropicClient(
        response=_tool_response(category_name="Food", confidence=0.9), capture=captured
    )
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(
        merchant="Swiggy",
        transaction_type="expense",
        amount_minor=50000,
        currency="INR",
        category_names=("Food", "Shopping"),
    )

    await classifier.classify(request)

    assert len(captured) == 1
    call_kwargs = captured[0]
    user_message = call_kwargs["messages"][0]["content"]
    assert "Swiggy" in user_message
    assert "expense" in user_message
    assert "50000" in user_message
    assert "INR" in user_message
    assert "Food" in user_message and "Shopping" in user_message

    forbidden_terms = (
        "user_id",
        "account_number",
        "linked_account",
        "external_transaction",
        "balance",
        "pin",
        "cvv",
        "otp",
        "password",
        "consent",
        "secret",
        "token",
        "email",
        "phone",
        "address",
    )
    lowered_message = user_message.lower()
    for term in forbidden_terms:
        # Word-boundary matching - a short term like "pin" must not
        # false-positive on an innocent substring like "shoPPINg".
        assert re.search(rf"(?<![a-z]){re.escape(term)}(?![a-z])", lowered_message) is None

    tool_schema = call_kwargs["tools"][0]["input_schema"]
    assert tool_schema["properties"]["category_name"]["enum"] == ["Food", "Shopping"]


def test_classification_request_rejects_narration_and_linked_account_fields() -> None:
    """Sensitive fields the task explicitly forbids sending - raw
    narration, linked_account_id, external_transaction_id - have no way
    into the request contract at all."""
    for forbidden_kwarg in ("narration", "linked_account_id", "external_transaction_id"):
        with pytest.raises(ValidationError):
            MerchantClassificationRequest(
                merchant="Swiggy",
                category_names=("Food",),
                **{forbidden_kwarg: "some-value"},
            )


# 4. a valid response returns the validated result


async def test_anthropic_classifier_returns_validated_result_for_a_valid_response() -> None:
    fake_client = _FakeAnthropicClient(
        response=_tool_response(category_name="Food", confidence=0.91)
    )
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food", "Shopping"))

    result = await classifier.classify(request)

    assert result.category_name == "Food"
    assert result.confidence == 0.91


# 5. invalid category is converted to category_name=None, confidence=0.0


async def test_anthropic_classifier_rejects_a_category_outside_the_allow_list() -> None:
    fake_client = _FakeAnthropicClient(
        response=_tool_response(category_name="Made Up Category", confidence=0.99)
    )
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(
        merchant="Weird Store", category_names=("Food", "Shopping")
    )

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


# 6. malformed structured output fails safely


async def test_anthropic_classifier_fails_safe_on_malformed_tool_input() -> None:
    fake_client = _FakeAnthropicClient(
        response=_tool_response(category_name="Food", confidence="very confident")
    )
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food",))

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


async def test_anthropic_classifier_fails_safe_on_unexpected_response_shape() -> None:
    """No tool_use block at all (e.g. the model returned only text) - never
    guessed at, treated the same as any other failure."""
    fake_client = _FakeAnthropicClient(response=_FakeResponse(content=[]))
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food",))

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


# 7. API failure fails safely


async def test_anthropic_classifier_fails_safe_on_api_error() -> None:
    fake_client = _FakeAnthropicClient(exception=RuntimeError("simulated API error"))
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food",))

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


# 8. timeout fails safely


async def test_anthropic_classifier_fails_safe_on_timeout() -> None:
    fake_client = _FakeAnthropicClient(
        response=_tool_response(category_name="Food", confidence=0.9), delay=5.0
    )
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test",
        model="claude-sonnet-5",
        client=fake_client,
        timeout_seconds=0.05,
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food",))

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


# 9. missing API key never causes a real API call


async def test_anthropic_classifier_makes_no_call_without_an_api_key() -> None:
    classifier = AnthropicMerchantClassifier(
        api_key=None, model="claude-sonnet-5", client=_ExplodingClient()
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food",))

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


async def test_anthropic_classifier_makes_no_call_with_an_empty_api_key() -> None:
    classifier = AnthropicMerchantClassifier(
        api_key="", model="claude-sonnet-5", client=_ExplodingClient()
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food",))

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


# 10. model extra fields never leak into the final result


async def test_anthropic_classifier_rejects_extra_fields_in_tool_input() -> None:
    fake_client = _FakeAnthropicClient(
        response=_tool_response(
            category_name="Food", confidence=0.9, explanation="because it sells pizza"
        )
    )
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food",))

    result = await classifier.classify(request)

    # extra="forbid" on MerchantClassificationResult rejects the whole
    # response rather than silently dropping the extra field.
    assert result.category_name is None
    assert result.confidence == 0.0
    assert not hasattr(result, "explanation")


# 11. confidence outside 0.0-1.0 fails safely


@pytest.mark.parametrize("bad_confidence", [-0.5, 1.5, 2.0])
async def test_anthropic_classifier_fails_safe_on_out_of_range_confidence(
    bad_confidence: float,
) -> None:
    fake_client = _FakeAnthropicClient(
        response=_tool_response(category_name="Food", confidence=bad_confidence)
    )
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food",))

    result = await classifier.classify(request)

    assert result.category_name is None
    assert result.confidence == 0.0


# 12. empty/invalid category_names can never produce a fabricated category


def test_anthropic_classifier_cannot_be_invoked_with_empty_category_names() -> None:
    with pytest.raises(ValidationError):
        MerchantClassificationRequest(merchant="Swiggy", category_names=())


async def test_anthropic_classifier_tool_schema_allow_list_matches_request_categories() -> None:
    captured: list[dict[str, Any]] = []
    fake_client = _FakeAnthropicClient(
        response=_tool_response(category_name="Rent", confidence=0.8), capture=captured
    )
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(merchant="Landlord Co", category_names=("Rent",))

    await classifier.classify(request)

    tool_schema = captured[0]["tools"][0]["input_schema"]
    assert tool_schema["properties"]["category_name"]["enum"] == ["Rent"]
    assert tool_schema["additionalProperties"] is False


# 13 & 14. no transaction-service / app.ai.tools imports - covered by the parametrized
# test_classifier_modules_never_import_the_database_or_orm test above (classifier_anthropic
# is included in its parametrize list).

# 15. no payment/transfer/withdrawal or credential-handling surface - covered by the
# parametrized test_classifier_modules_never_reference_forbidden_financial_actions_in_code
# test above (classifier_anthropic is included in its parametrize list).


def test_anthropic_classifier_satisfies_the_merchant_classifier_protocol() -> None:
    classifier = AnthropicMerchantClassifier(api_key="fake-key-for-test", model="claude-sonnet-5")
    assert isinstance(classifier, MerchantClassifier)


async def test_anthropic_classifier_repeated_calls_with_same_input_are_deterministic() -> None:
    """Not a claim about the model itself (a real model is not
    deterministic) - this exercises the classifier's own deterministic
    validation/fallback logic with a fixed fake response, which must
    always produce the same MerchantClassificationResult for the same
    input."""
    fake_client = _FakeAnthropicClient(
        response=_tool_response(category_name="Food", confidence=0.8)
    )
    classifier = AnthropicMerchantClassifier(
        api_key="fake-key-for-test", model="claude-sonnet-5", client=fake_client
    )
    request = MerchantClassificationRequest(merchant="Swiggy", category_names=("Food",))

    first = await classifier.classify(request)
    second = await classifier.classify(request)

    assert first == second
