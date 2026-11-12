"""Real Anthropic-backed implementation of MerchantClassifier (Phase F2).

Still the same one-shot contract as app.ai.classifier.base: a single
`classify()` call in, a single MerchantClassificationResult out. No
conversation history, no tool-calling LOOP (a single forced tool call is
used only as a structured-output mechanism - see `_request_classification`
- never a multi-round assistant-style exchange), no database session, no
`user_id`, no account/balance/credential data of any kind. The only data
ever sent to Anthropic is what's already on MerchantClassificationRequest:
`merchant`, `transaction_type`, `amount_minor`, `currency`, and
`category_names` - see `_build_user_message`, the one place the outbound
request text is assembled, for the exhaustive list.

DELIBERATE DIFFERENCE from app.ai.provider.anthropic_provider.AnthropicProvider:
that class raises a configuration error at CONSTRUCTION time when the
optional 'anthropic' package isn't installed, because a conversational-
assistant failure is directly visible to the user in chat and CLAUDE.md
requires never silently pretending an unconfigured integration works. This
classifier is different: it is a background categorization aid, and per
the Phase F design (see app.services.sync_service's
`_ai_categorization_enabled_for_user` docstring - "AI failure must never
prevent transaction ingestion"), it must NEVER be able to raise out of
`classify()` for any reason - missing key, missing SDK, network error,
timeout, a malformed or unexpected API response, an invalid category, or
an out-of-range confidence. Every one of those becomes the exact same safe
result a genuinely unclassifiable merchant would produce:
`MerchantClassificationResult(category_name=None, confidence=0.0)`. A
caller can never distinguish "the AI declined to classify this" from "the
AI was unreachable" - that is intentional, not an oversight.

Nothing here is wired into app.services.sync_service yet (Phase F2 scope
is this class and its factory selection only - see
app.ai.classifier.factory).
"""

import asyncio
import logging
from typing import Any

from pydantic import ValidationError

from app.ai.classifier.base import (
    MerchantClassificationRequest,
    MerchantClassificationResult,
    validate_classification,
)

logger = logging.getLogger("app.ai.classifier")

# Short and fixed - a classification is a small, cheap request with no
# reason to run long. Not configurable in this phase (CLAUDE.md - add only
# the minimum configuration actually required); a single call, no retries.
_DEFAULT_TIMEOUT_SECONDS = 8.0

_TOOL_NAME = "classify_merchant"

_SYSTEM_PROMPT = (
    "You are a deterministic merchant-category classifier for a personal finance app.\n\n"
    "You are given a merchant name and a closed list of allowed category names. "
    "Classify the merchant into EXACTLY ONE of the supplied category names by calling the "
    f"{_TOOL_NAME} tool. If none of the supplied categories is a good fit, omit category_name "
    "entirely (leave it null) - never invent a category that is not in the supplied list, and "
    "never return a category name spelled differently from the supplied list.\n\n"
    "confidence must be a number from 0.0 to 1.0. It represents your confidence in the CATEGORY "
    "CLASSIFICATION ONLY - it has nothing to do with financial risk, fraud, or whether the "
    "transaction is legitimate.\n\n"
    "Respond only by calling the tool with structured output. Do not provide any explanation, "
    "commentary, or any field beyond category_name and confidence."
)


def _build_tool_definition(category_names: tuple[str, ...]) -> dict[str, Any]:
    """The tool's own JSON Schema restricts `category_name` to exactly the
    caller's allow-list (`enum`) - a first layer of defense, but never the
    only one: the application NEVER trusts this by itself and always
    re-validates locally afterward (see `validate_classification` and
    MerchantClassificationResult's own `extra="forbid"`)."""
    return {
        "name": _TOOL_NAME,
        "description": (
            "Record the merchant's category classification. category_name must be exactly one "
            "of the allowed category names, or omitted if none of them applies."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "category_name": {
                    "type": "string",
                    "enum": list(category_names),
                    "description": "One of the supplied category names - omit if none applies.",
                },
                "confidence": {
                    "type": "number",
                    "minimum": 0.0,
                    "maximum": 1.0,
                    "description": "Confidence in the category classification, 0.0 to 1.0.",
                },
            },
            "required": ["confidence"],
            "additionalProperties": False,
        },
    }


def _build_user_message(request: MerchantClassificationRequest) -> str:
    """The ONLY place the outbound request text is assembled - every line
    here reads directly off `request`'s own fields (merchant,
    transaction_type, amount_minor, currency, category_names) and nothing
    else, so there is no code path by which a user_id, account number,
    balance, or any other sensitive field could ever be included: none of
    those exist on MerchantClassificationRequest in the first place (see
    app.ai.classifier.base)."""
    lines = [f"Merchant: {request.merchant}"]
    if request.transaction_type is not None:
        lines.append(f"Transaction type: {request.transaction_type}")
    if request.amount_minor is not None and request.currency is not None:
        lines.append(f"Amount: {request.amount_minor} minor units {request.currency}")
    lines.append("Allowed category names: " + ", ".join(request.category_names))
    return "\n".join(lines)


class AnthropicMerchantClassifier:
    name = "anthropic"

    def __init__(
        self,
        *,
        api_key: str | None,
        model: str,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
        client: Any | None = None,
    ) -> None:
        """`client` is a test-only injection seam - an object exposing an
        async `messages.create(...)` matching the Anthropic SDK's shape.
        Production code always leaves it None; the real
        `anthropic.AsyncAnthropic` client (and the 'anthropic' package
        import itself) is constructed lazily on first use inside
        `classify()`, never here - so this constructor can never raise,
        never imports the optional SDK, and never makes a network call,
        even when the 'anthropic' package isn't installed or `api_key` is
        None (see the class docstring for why that's deliberate here)."""
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._injected_client = client

    async def classify(
        self, request: MerchantClassificationRequest
    ) -> MerchantClassificationResult:
        empty = MerchantClassificationResult(category_name=None, confidence=0.0)

        if not self._api_key:
            # No real API call is ever attempted without a key - this is
            # checked BEFORE anything else, not discovered via a failed
            # request.
            return empty

        try:
            parsed = await asyncio.wait_for(
                self._request_classification(request), timeout=self._timeout_seconds
            )
        except Exception:  # noqa: BLE001 - every classify() failure mode fails safe, never raises
            logger.warning(
                "ai_classifier_request_failed",
                extra={"classifier": self.name},
                exc_info=True,
            )
            return empty

        if parsed is None:
            return empty

        # Local validation, step 2 of 2: MerchantClassificationResult.model_validate
        # (inside _request_classification) already rejected a malformed
        # shape, an out-of-range confidence, or an unexpected extra field.
        # This re-check is the allow-list step that model alone can't
        # enforce - MerchantClassificationResult has no notion of which
        # categories THIS caller actually offered.
        return validate_classification(
            category_name=parsed.category_name,
            confidence=parsed.confidence,
            category_names=request.category_names,
        )

    def _get_client(self) -> Any:
        if self._injected_client is not None:
            return self._injected_client
        import anthropic  # lazy import - see __init__'s docstring for why

        return anthropic.AsyncAnthropic(api_key=self._api_key)

    async def _request_classification(
        self, request: MerchantClassificationRequest
    ) -> MerchantClassificationResult | None:
        """Makes exactly one request to Anthropic, forcing the model to
        respond via the `classify_merchant` tool (structured output, not a
        conversational tool-calling round-trip - there is no second turn
        here, unlike app.ai.provider.AnthropicProvider's multi-round
        protocol). Returns None for any response shape that doesn't
        contain the expected tool call at all (never guessed at); raises
        (to the caller's single catch-all) for anything else, including a
        response that fails MerchantClassificationResult's own strict
        validation - a malformed confidence, an unrecognized extra field,
        or a category_name of the wrong type."""
        client = self._get_client()
        response = await client.messages.create(
            model=self._model,
            max_tokens=200,
            system=_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _build_user_message(request)}],
            tools=[_build_tool_definition(request.category_names)],
            tool_choice={"type": "tool", "name": _TOOL_NAME},
        )

        for block in response.content:
            if getattr(block, "type", None) == "tool_use" and getattr(block, "name", None) == (
                _TOOL_NAME
            ):
                try:
                    return MerchantClassificationResult.model_validate(dict(block.input))
                except ValidationError:
                    return None

        return None
