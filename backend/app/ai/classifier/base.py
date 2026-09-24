"""Provider-agnostic data model, plus the `MerchantClassifier` Protocol
every implementation (mock or a future real provider) implements.

This is a ONE-SHOT abstraction, not the conversational assistant:

    - Single request -> single result. No conversation history, no
      multi-round tool calling, no follow-up questions - unlike
      app.ai.provider.AIProvider (see that module's own docstring), which
      is built for exactly the opposite shape.
    - No database session, ever. This package never imports the ORM,
      app.repositories, or app.services - an implementation has no way to
      look anything up beyond what's on MerchantClassificationRequest.
    - No `user_id`, ever. `classify()` has no parameter for one; a future
      caller (not built yet - see app.services.sync_service's
      `_ai_categorization_enabled_for_user` gate) is solely responsible for
      deciding whether to call this at all and for scoping the request's
      contents to one user's own data before constructing it.
    - No transaction id, account id, category id, or any other identifier
      that could be used to look up or address a specific row - a
      classifier can only ever return a category NAME, and only one
      already offered by the caller (see `validate_classification`).
    - No field of any kind for a financial action, a tool call, a payment,
      a transfer, a withdrawal, an account number, a balance, a PIN, a
      CVV, an OTP, a password, a consent handle/token, or any provider
      secret. This module cannot leak what it was never given a field for.
"""

from typing import Literal, Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict, Field

TransactionDirection = Literal["income", "expense"]


class MerchantClassificationRequest(BaseModel):
    """Everything a classifier is allowed to see for one merchant - nothing
    else. `merchant` should be the already-normalized canonical name (see
    app.services.merchant_normalization.normalize_merchant), never raw
    narration containing UPI VPA handles or account references - that
    normalization is the caller's responsibility, not this module's.
    `category_names` is the caller's own current category list (see
    app.services.category_service) - a classifier may only ever return a
    name from this exact list (see `validate_classification`), never
    invent one that doesn't exist for that user.

    `extra="forbid"` (via ConfigDict below) means an unrecognized field -
    e.g. an attempt to smuggle in a user_id, an account number, or any
    other sensitive field - is rejected by Pydantic itself, never silently
    accepted and ignored.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    merchant: str = Field(min_length=1, max_length=200)
    transaction_type: TransactionDirection | None = None
    amount_minor: int | None = Field(default=None, gt=0)
    currency: str | None = Field(default=None, min_length=3, max_length=3)
    category_names: tuple[str, ...] = Field(min_length=1)


class MerchantClassificationResult(BaseModel):
    """The ONLY thing a classifier may hand back - a suggested category
    name (or None, meaning "no confident suggestion") and a confidence in
    [0.0, 1.0]. No transaction id, no user id, no account id, no free-form
    action, no tool call - this model has no field for any of those, by
    construction, so an implementation cannot return one even if it wanted
    to.

    Never construct this directly with a caller-supplied `category_name` -
    use `validate_classification` below, which is the single place that
    name is checked against the caller's own allow-list.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    category_name: str | None
    confidence: float = Field(ge=0.0, le=1.0)


def validate_classification(
    *, category_name: str | None, confidence: float, category_names: tuple[str, ...]
) -> MerchantClassificationResult:
    """The single choke point a raw (category_name, confidence) pair must
    pass through to become a MerchantClassificationResult - every
    MerchantClassifier implementation (the mock in app.ai.classifier.mock
    today, a real provider later) calls this rather than constructing the
    result directly, so a category outside the caller's own allow-list can
    never slip through one implementation's own hand-rolled check (the same
    "one choke point" posture as app.ai.tools.registry.validate_and_execute
    for tool calls). A category not present in `category_names` - or
    `None` - always becomes an explicit empty result (`None`, `0.0`),
    never a guess and never the nearest-looking name."""
    if category_name is None or category_name not in category_names:
        return MerchantClassificationResult(category_name=None, confidence=0.0)
    return MerchantClassificationResult(category_name=category_name, confidence=confidence)


@runtime_checkable
class MerchantClassifier(Protocol):
    """`name` is a safe, non-secret label (e.g. "mock") - not surfaced to
    end users today, but kept for the same honesty reason
    app.ai.provider.AIProvider.name is: nothing downstream should ever be
    able to mistake a demo/mock result for a real external classification.
    """

    name: str

    async def classify(
        self, request: MerchantClassificationRequest
    ) -> MerchantClassificationResult: ...
