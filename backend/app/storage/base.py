"""Storage provider abstraction. The application never talks to a specific
storage backend directly - every caller goes through this interface, so the
backing implementation (local filesystem today, an object-storage service
later) can change without touching any service that stores or reads a file.

`key` is always a server-generated internal identifier (see
app.services.receipt_service), never a client-supplied path or filename -
every implementation must treat it as an opaque string, not something to
parse or trust structurally beyond what it generated itself.
"""

import re
import uuid
from typing import Protocol

# A storage key is always exactly this shape: "<user_id>/<random>.<ext>".
# Every provider re-validates an incoming key against this before touching
# a backing store, so even a key that somehow originated somewhere other
# than generate_storage_key (a bug, a future code path) can never smuggle a
# path-traversal segment ("..", "/", "\\") through to a filesystem call.
_KEY_PATTERN = re.compile(r"^[0-9a-f-]{36}/[0-9a-f]{32}\.[a-z0-9]{1,10}$")


def is_safe_storage_key(key: str) -> bool:
    return bool(_KEY_PATTERN.fullmatch(key))


def generate_storage_key(user_id: uuid.UUID, extension: str) -> str:
    """A server-generated, unguessable internal identifier - never derived
    from a client-supplied filename. The user_id prefix keeps one user's
    files grouped together on the backing store without ever using it (or
    anything else client-controlled) as a path component beyond this exact,
    validated shape."""
    return f"{user_id}/{uuid.uuid4().hex}.{extension}"


class StorageError(Exception):
    """Raised when a storage operation fails (missing key, I/O failure, ...).
    Callers translate this into a generic user-facing error - never leak
    filesystem paths or provider internals to the client."""


class StorageProvider(Protocol):
    """Every method is async so a future network-backed implementation
    (S3, GCS, ...) fits the same call sites as the local filesystem one
    without any caller needing to change."""

    async def save(self, key: str, content: bytes, *, content_type: str) -> None:
        """Stores `content` under `key`, creating or overwriting it."""
        ...

    async def read(self, key: str) -> bytes:
        """Returns the stored content for `key`. Raises StorageError if it
        does not exist."""
        ...

    async def delete(self, key: str) -> None:
        """Removes the stored content for `key`. A no-op if it does not
        exist (deleting something already gone is not an error)."""
        ...

    async def exists(self, key: str) -> bool:
        """Whether `key` currently has stored content."""
        ...
