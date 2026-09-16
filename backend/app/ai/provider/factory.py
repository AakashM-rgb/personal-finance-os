"""Selects which AIProvider implementation to use, based on configuration
alone - the only place that decision is made (same pattern as
app.storage.factory / app.ocr.factory). AnthropicProvider runs automatically
once ANTHROPIC_API_KEY is set; otherwise the deterministic MockProvider
runs, clearly labeled as such via its own `name` attribute - never a silent
pretend call to a real model.
"""

from functools import lru_cache

from app.ai.provider.anthropic_provider import AnthropicProvider
from app.ai.provider.base import AIProvider
from app.ai.provider.mock import MockProvider
from app.core.config import Settings, get_settings


def build_ai_provider(settings: Settings) -> AIProvider:
    if settings.anthropic_api_key:
        return AnthropicProvider(api_key=settings.anthropic_api_key, model=settings.ai_model)
    return MockProvider()


@lru_cache
def get_ai_provider() -> AIProvider:
    return build_ai_provider(get_settings())
