"""A ceiling on the size of every request body.

Without one, the server accepts a body of any size: FastAPI reads a JSON body
fully into memory, and Starlette spools a multipart upload to disk before the
receipt endpoint's own 10 MB check ever runs. Either is a cheap way to exhaust
the single small instance this app is deployed on.

Starlette ships a body-limit middleware, but it answers in plain text
("Content Too Large"), and when the client declares an oversized
Content-Length it replaces even an application's JSON error with that text.
The frontend parses every error as the `{data, error, meta}` envelope, and
CLAUDE.md §17 forbids surfacing bare status text, so this one keeps the
envelope:

* a declared Content-Length over the limit is refused before the app runs;
* a body that streams past the limit (no or false Content-Length) raises
  `RequestBodyTooLarge` from `receive`. It is an HTTPException on purpose:
  FastAPI turns any other exception raised while reading a body into a
  generic 400, but re-raises HTTPExceptions, so this reaches the app's normal
  HTTP error handler and is sent as a 413 envelope.
"""

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.core.errors import error_envelope
from app.schemas.receipt import RECEIPT_MAX_FILE_SIZE_BYTES

# The largest legitimate body is a receipt upload; multipart framing (the
# boundary, part headers, the filename) adds a little on top of the file.
MAX_REQUEST_BODY_BYTES = RECEIPT_MAX_FILE_SIZE_BYTES + 1024 * 1024
_MESSAGE = "This request is too large. Receipts must be 10MB or smaller."


class RequestBodyTooLarge(HTTPException):
    def __init__(self) -> None:
        super().__init__(status_code=413, detail=_MESSAGE)


def _declared_length(scope: Scope) -> int | None:
    raw = Headers(scope=scope).get("content-length")
    try:
        return int(raw) if raw is not None else None
    except ValueError:
        return None


class RequestBodyLimitMiddleware:
    def __init__(self, app: ASGIApp, max_bytes: int = MAX_REQUEST_BODY_BYTES) -> None:
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > self.max_bytes:
            response = JSONResponse(
                status_code=413, content=error_envelope("payload_too_large", _MESSAGE)
            )
            await response(scope, receive, send)
            return

        received = 0

        async def receive_within_limit() -> Message:
            nonlocal received
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > self.max_bytes:
                    raise RequestBodyTooLarge()
            return message

        await self.app(scope, receive_within_limit, send)
