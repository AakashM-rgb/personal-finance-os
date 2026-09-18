"""Selects which BankSyncProvider implementation to use, based on
configuration alone (same pattern as app.storage.factory / app.ocr.factory).
There is deliberately no real Account Aggregator vendor wired up yet - only
the seam. Setting SYNC_PROVIDER to anything other than "mock" today raises
a clear configuration error rather than silently falling back to the mock
and pretending a real provider ran.
"""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.sync.provider.base import BankSyncProvider
from app.sync.provider.mock import MockSyncProvider


def build_sync_provider(settings: Settings) -> BankSyncProvider:
    if settings.sync_provider == "mock":
        return MockSyncProvider()

    raise RuntimeError(
        f"SYNC_PROVIDER={settings.sync_provider!r} is not a supported provider. "
        "Only 'mock' is implemented today; add a real provider class and wire "
        "it in here before configuring anything else."
    )


@lru_cache
def get_sync_provider() -> BankSyncProvider:
    return build_sync_provider(get_settings())
