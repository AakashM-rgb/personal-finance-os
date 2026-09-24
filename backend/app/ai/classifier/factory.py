"""Selects which MerchantClassifier implementation to use - mirrors the
selection pattern in app.ai.provider.factory (and app.storage.factory /
app.ocr.factory), but for this narrow one-shot classifier instead of the
conversational provider.

AnthropicMerchantClassifier is selected once `settings.anthropic_api_key`
is configured - the SAME key already used by app.ai.provider.factory for
the conversational assistant (no new environment variable is introduced
for this classifier; see app.ai.classifier.anthropic's module docstring
for why reusing it is safe: the two are selected independently here, never
coupled, and nothing about the assistant's behavior changes). Otherwise -
including when the key is absent, which is the default - the deterministic
MockMerchantClassifier runs, exactly like Phase F1.

Selecting AnthropicMerchantClassifier here (including via
get_merchant_classifier() at whatever point in the future something calls
it) never makes a network call and never raises: construction only stores
plain values, and the real `anthropic.AsyncAnthropic` client - along with
the optional 'anthropic' package import itself - is deferred until
`classify()` actually runs (see that class's own docstring). So configuring
(or misconfiguring) Anthropic can never block application startup, and
Anthropic is never made mandatory for the app to run.

This module is still not wired into app.services.sync_service (Phase F2 is
this class and its factory selection only) - see that module's
`_ai_categorization_enabled_for_user` gate, which a future caller will use
together with this factory.
"""

from functools import lru_cache

from app.ai.classifier.anthropic import AnthropicMerchantClassifier
from app.ai.classifier.base import MerchantClassifier
from app.ai.classifier.mock import MockMerchantClassifier
from app.core.config import Settings, get_settings


def build_merchant_classifier(settings: Settings) -> MerchantClassifier:
    if settings.anthropic_api_key:
        return AnthropicMerchantClassifier(
            api_key=settings.anthropic_api_key, model=settings.ai_model
        )
    return MockMerchantClassifier()


@lru_cache
def get_merchant_classifier() -> MerchantClassifier:
    return build_merchant_classifier(get_settings())
