"""Selects which OcrProvider implementation to use, based on configuration
alone. Every caller depends on the OcrProvider interface, never on
MockOcrProvider directly, so a real vendor integration is a config change
(setting OCR_PROVIDER), not a rewrite of app.services.receipt_service.

There is deliberately no real external OCR vendor wired up yet - only the
seam. Setting OCR_PROVIDER to anything other than "mock" today raises a
clear configuration error rather than silently falling back to the mock
and pretending a real provider ran.
"""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.ocr.base import OcrProvider
from app.ocr.mock import MockOcrProvider


def build_ocr_provider(settings: Settings) -> OcrProvider:
    if settings.ocr_provider == "mock":
        return MockOcrProvider()

    raise RuntimeError(
        f"OCR_PROVIDER={settings.ocr_provider!r} is not a supported provider. "
        "Only 'mock' is implemented today; add a real provider class and wire "
        "it in here before configuring anything else."
    )


@lru_cache
def get_ocr_provider() -> OcrProvider:
    return build_ocr_provider(get_settings())
