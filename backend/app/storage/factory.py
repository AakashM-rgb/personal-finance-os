"""Selects which StorageProvider implementation to use, based on
configuration alone - the only place that decision is made. Every caller
depends on the StorageProvider interface, never on LocalStorageProvider or
S3StorageProvider directly, so this is the single seam a real deployment
configures through (setting S3_BUCKET) without any other code changing.
"""

from functools import lru_cache

from app.core.config import Settings, get_settings
from app.storage.base import StorageProvider
from app.storage.local import LocalStorageProvider


def build_storage_provider(settings: Settings) -> StorageProvider:
    if settings.s3_bucket:
        from app.storage.s3 import S3StorageProvider

        return S3StorageProvider(bucket=settings.s3_bucket, region=settings.s3_region)

    # No external storage configured - use the local filesystem. This is
    # not a fallback-after-failure; it is the intended, fully-supported
    # development/self-hosted mode, and never pretends to be S3.
    return LocalStorageProvider(settings.receipt_storage_dir)


@lru_cache
def get_storage_provider() -> StorageProvider:
    return build_storage_provider(get_settings())
