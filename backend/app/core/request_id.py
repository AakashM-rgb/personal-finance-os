"""A correlation id for one request, readable from anywhere without being
threaded through every function signature.

CLAUDE.md §17 requires backend errors to be logged with enough context to
debug them -- request id, user id, operation -- without logging secrets or
sensitive payloads. A stack trace alone cannot be tied back to the request a
user is complaining about, and on a single-instance deployment serving
concurrent requests the interleaved log lines cannot be separated at all.

The id is held in a ContextVar, so it follows the request through every
`await` without being passed around, and it is attached to every `app.*` log
record automatically by the filter in app.core.logging. It is also returned
as the `X-Request-Id` response header so a user can quote it.

It is deliberately not a secret and carries no user data: either a trusted
proxy's own id or a random uuid4.
"""

import uuid
from contextvars import ContextVar

HEADER_NAME = "X-Request-Id"

# 200 is far more than any sane id needs and short enough that a hostile
# header cannot pad a log line out to something unreadable.
_MAX_LENGTH = 200

_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def new_request_id() -> str:
    return uuid.uuid4().hex


def sanitize(candidate: str | None) -> str | None:
    """An inbound id is attacker-controlled: it reaches the logs, so it must
    not be able to inject newlines (forging log lines) or control characters,
    and must not be unbounded. Anything suspect is dropped rather than
    cleaned, and a fresh id is generated instead."""
    if not candidate:
        return None
    stripped = candidate.strip()
    if not stripped or len(stripped) > _MAX_LENGTH:
        return None
    if not all(character.isalnum() or character in "-_." for character in stripped):
        return None
    return stripped


def set_request_id(value: str) -> None:
    _request_id.set(value)


def get_request_id() -> str | None:
    return _request_id.get()
