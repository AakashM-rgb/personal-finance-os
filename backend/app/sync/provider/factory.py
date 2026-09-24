"""Selects which BankSyncProvider implementation to use, based on
configuration alone (same pattern as app.ai.classifier.factory /
app.storage.factory / app.ocr.factory).

`SYNC_PROVIDER=mock` remains the default and the only provider that runs
without any configuration at all. `SYNC_PROVIDER=setu_sandbox` (Phase F8)
selects `SetuSandboxSyncProvider` - a SANDBOX/UAT-only structural seam whose
every operation currently raises `SetuSandboxNotImplementedError` (see that
module's own docstring for exactly why, and what's required before it can
do anything else). Selecting either provider never makes a network call by
itself: `MockSyncProvider()` and `SetuSandboxSyncProvider(...)` both
construct instantly, with no I/O.

Any other `SYNC_PROVIDER` value fails closed with a clear `RuntimeError` -
never a silent fallback to the mock, and never a pretend real provider run.
"""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.sync.provider.base import BankSyncProvider
from app.sync.provider.mock import MockSyncProvider
from app.sync.provider.setu_sandbox import SetuSandboxSyncProvider


def build_sync_provider(settings: Settings) -> BankSyncProvider:
    if settings.sync_provider == "mock":
        return MockSyncProvider()

    if settings.sync_provider == "setu_sandbox":
        return SetuSandboxSyncProvider(
            base_url=settings.setu_sandbox_base_url,
            client_id=settings.setu_sandbox_client_id,
            client_secret=settings.setu_sandbox_client_secret,
        )

    raise RuntimeError(
        f"SYNC_PROVIDER={settings.sync_provider!r} is not a supported provider. "
        "Only 'mock' and 'setu_sandbox' (sandbox-only, not yet implemented - see "
        "app.sync.provider.setu_sandbox) are recognized today; add a real "
        "provider class and wire it in here before configuring anything else."
    )


@lru_cache
def get_sync_provider() -> BankSyncProvider:
    return build_sync_provider(get_settings())
