"""External object-storage seam (S3-compatible). This class only ever runs
when S3_BUCKET is actually configured (see app.storage.factory) - `boto3`
is an optional dependency (`pip install .[s3]`), imported lazily here so
the base application, tests, and local development never need it
installed just to import this module.

Never returns a public URL: every read/write goes through this class's
own methods (get_object/put_object with the bucket kept private), the
exact same call shape app.services.receipt_service already uses for the
local provider - callers never see or construct an S3 URL directly.
"""

import asyncio
from typing import Any

from app.storage.base import StorageError, is_safe_storage_key


class S3StorageProvider:
    def __init__(self, *, bucket: str, region: str | None) -> None:
        try:
            import boto3
        except ImportError as exc:
            raise StorageError(
                "S3 storage is configured but the optional 'boto3' dependency "
                "is not installed. Install it with: pip install .[s3]"
            ) from exc

        self._bucket = bucket
        self._client: Any = boto3.client("s3", region_name=region)

    async def save(self, key: str, content: bytes, *, content_type: str) -> None:
        if not is_safe_storage_key(key):
            raise StorageError("Invalid storage key.")
        await asyncio.to_thread(
            self._client.put_object,
            Bucket=self._bucket,
            Key=key,
            Body=content,
            ContentType=content_type,
        )

    async def read(self, key: str) -> bytes:
        if not is_safe_storage_key(key):
            raise StorageError("Invalid storage key.")
        try:
            response = await asyncio.to_thread(
                self._client.get_object, Bucket=self._bucket, Key=key
            )
            return response["Body"].read()  # type: ignore[no-any-return]
        except Exception as exc:  # noqa: BLE001 - boto3 raises provider-specific errors
            raise StorageError("File not found.") from exc

    async def delete(self, key: str) -> None:
        if not is_safe_storage_key(key):
            raise StorageError("Invalid storage key.")
        await asyncio.to_thread(self._client.delete_object, Bucket=self._bucket, Key=key)

    async def exists(self, key: str) -> bool:
        if not is_safe_storage_key(key):
            return False
        try:
            await asyncio.to_thread(self._client.head_object, Bucket=self._bucket, Key=key)
            return True
        except Exception:  # noqa: BLE001 - boto3 raises provider-specific errors
            return False
