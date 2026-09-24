"""Selects which MerchantClassifier implementation to use - mirrors the
selection pattern in app.ai.provider.factory (and app.storage.factory /
app.ocr.factory), but for this narrow one-shot classifier instead of the
conversational provider.

Phase F1 builds only the abstraction and the mock: no real classifier
implementation exists yet, so this always returns MockMerchantClassifier,
regardless of whether ANTHROPIC_API_KEY is configured for the
conversational assistant (app.ai.provider.factory) - the two are selected
independently, never coupled. A future real implementation (e.g. an
Anthropic-backed classifier) will be added as its own module here and
selected by this function the same way build_ai_provider selects
AnthropicProvider once ANTHROPIC_API_KEY is set - this function is the one
place that choice will be made, so nothing else will need to change to
adopt it.

This module is not wired into app.services.sync_service yet - see that
module's `_ai_categorization_enabled_for_user` gate, which a future caller
will use together with this factory.
"""

from functools import lru_cache

from app.ai.classifier.base import MerchantClassifier
from app.ai.classifier.mock import MockMerchantClassifier
from app.core.config import Settings, get_settings


def build_merchant_classifier(settings: Settings) -> MerchantClassifier:
    del settings  # unused for now - no real implementation exists to select yet
    return MockMerchantClassifier()


@lru_cache
def get_merchant_classifier() -> MerchantClassifier:
    return build_merchant_classifier(get_settings())
