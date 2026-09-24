"""Tests for the narrow one-shot merchant-classification abstraction
(app.ai.classifier) - deliberately separate from the conversational
Financial AI Assistant (app.ai.provider, covered by test_ai_*.py). No
database is involved anywhere in this file: every implementation here is a
pure function of its input, and that is itself part of what's being
verified.
"""

import ast
import inspect
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.ai.classifier import base as classifier_base
from app.ai.classifier import mock as classifier_mock
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


def test_factory_returns_the_mock_classifier_even_when_an_api_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No real classifier implementation exists yet (Phase F1) - the
    factory must not be swayed by ANTHROPIC_API_KEY, which only affects
    app.ai.provider.factory (the separate conversational-assistant
    selection)."""
    settings = get_settings()
    monkeypatch.setattr(settings, "anthropic_api_key", "fake-key-for-test")

    classifier = build_merchant_classifier(settings)

    assert isinstance(classifier, MockMerchantClassifier)


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


@pytest.mark.parametrize("module", [classifier_base, classifier_mock])
def test_classifier_modules_never_import_the_database_or_orm(module: object) -> None:
    imported = _imported_module_names(module)
    forbidden_prefixes = (
        "sqlalchemy",
        "app.repositories",
        "app.services",
        "app.models",
        "app.core.database",
    )
    for name in imported:
        assert not name.startswith(forbidden_prefixes), (
            f"{module.__name__} imports forbidden module {name!r}"
        )


@pytest.mark.parametrize("module", [classifier_base, classifier_mock])
def test_classifier_modules_never_reference_forbidden_financial_actions_in_code(
    module: object,
) -> None:
    """Checks executable code only (function/class bodies), not
    docstrings, for any hint of a payment/transfer/withdrawal surface."""
    tree = ast.parse(Path(inspect.getfile(module)).read_text(encoding="utf-8"))
    forbidden_substrings = ("transfer", "withdraw", "payment_auth", "debit_auth", "send_money")
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
