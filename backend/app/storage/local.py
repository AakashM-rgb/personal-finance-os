"""Local filesystem storage - the default, always-available implementation
used whenever no external object-storage provider is configured. Files
live under a directory outside any static/public web root (see
app.core.config.Settings.receipt_storage_dir), so nothing here is ever
reachable by a plain HTTP GET - the only way to read a file back out is
through this class, called from an authenticated, ownership-checked
service function.
"""

import asyncio
from pathlib import Path

from app.storage.base import StorageError, is_safe_storage_key


class LocalStorageProvider:
    def __init__(self, base_dir: str) -> None:
        self._base_dir = Path(base_dir).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_path(self, key: str) -> Path:
        """Rejects anything that isn't exactly the shape
        generate_storage_key produces, then re-confirms with the
        filesystem itself (`is_relative_to`) that the resolved path still
        lands inside the base directory - defense in depth against path
        traversal even though a validated key can never contain "..".
        """
        if not is_safe_storage_key(key):
            raise StorageError("Invalid storage key.")

        path = (self._base_dir / key).resolve()
        if not path.is_relative_to(self._base_dir):
            raise StorageError("Invalid storage key.")
        return path

    async def save(self, key: str, content: bytes, *, content_type: str) -> None:
        path = self._resolve_path(key)

        def _write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(content)

        await asyncio.to_thread(_write)

    async def read(self, key: str) -> bytes:
        path = self._resolve_path(key)
        if not path.is_file():
            raise StorageError("File not found.")
        return await asyncio.to_thread(path.read_bytes)

    async def delete(self, key: str) -> None:
        path = self._resolve_path(key)

        def _delete() -> None:
            path.unlink(missing_ok=True)

        await asyncio.to_thread(_delete)

    async def exists(self, key: str) -> bool:
        path = self._resolve_path(key)
        return await asyncio.to_thread(path.is_file)
