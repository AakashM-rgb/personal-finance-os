"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.datastructures import MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api.v1.router import api_router
from app.core.body_limit import RequestBodyLimitMiddleware
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_app_logging
from app.core.rate_limit import limiter
from app.core.request_id import HEADER_NAME, new_request_id, sanitize, set_request_id

configure_app_logging()

settings = get_settings()


class _FinanceApp(FastAPI):
    def build_middleware_stack(self) -> ASGIApp:
        # Starlette always places ServerErrorMiddleware outside every
        # add_middleware() entry, and it sends the 500 for an unhandled
        # exception straight to the server's `send`. Anything added with
        # add_middleware() therefore never sees that response, so the
        # request id and security headers would be missing from exactly the
        # response a user most needs to quote. Wrapping the built stack puts
        # both outside ServerErrorMiddleware and CORS, so every response -
        # 500s and CORS preflights included - carries them. The body limit
        # sits just inside them, so a 413 carries them too.
        return RequestIdMiddleware(
            SecurityHeadersMiddleware(RequestBodyLimitMiddleware(super().build_middleware_stack()))
        )


app = _FinanceApp(title="Finance App API", version="0.1.0")

# Note: SlowAPIMiddleware (Starlette BaseHTTPMiddleware) is deliberately not
# added. It is not required for the per-route @limiter.limit(...) decorators
# below to work - RateLimitExceeded is already handled in register_exception_handlers -
# and BaseHTTPMiddleware's task-per-request model is incompatible with the
# asyncpg driver's event-loop binding.
app.state.limiter = limiter


class RequestIdMiddleware:
    """Gives every request a correlation id, reuses a trusted proxy's own id
    when one is supplied, and echoes it back as a response header so a user
    can quote it in a bug report (see app.core.request_id).

    Plain ASGI middleware for the same reason as SecurityHeadersMiddleware
    below: BaseHTTPMiddleware's task-per-request model is incompatible with
    the asyncpg driver's event-loop binding. Running in the same task is also
    what lets the ContextVar set here stay visible to the handler.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = None
        for raw_name, raw_value in scope.get("headers", []):
            if raw_name.decode("latin-1").lower() == HEADER_NAME.lower():
                incoming = raw_value.decode("latin-1")
                break
        request_id = sanitize(incoming) or new_request_id()
        set_request_id(request_id)

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[HEADER_NAME] = request_id
            await send(message)

        await self.app(scope, receive, send_with_request_id)


class SecurityHeadersMiddleware:
    """Baseline security headers on every response - this API is never
    meant to be framed, its JSON responses are never meant to be
    MIME-sniffed into something else, and its own URLs are never meant to
    leak as a Referer to a third-party origin. HSTS is only sent once the
    app is actually deployed behind TLS (settings.is_production) - sending
    it over plain HTTP in local dev is pointless and would only be
    confusing to see in response headers there.

    Implemented as a plain ASGI middleware (not Starlette's
    BaseHTTPMiddleware, which - see the comment above - is deliberately
    avoided everywhere in this app) - it only wraps `send` to add headers
    onto the outgoing `http.response.start` message, never buffers the
    body or runs the downstream app in a separate task.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        async def send_with_headers(message: Message) -> None:
            if message["type"] == "http.response.start":
                headers = MutableHeaders(scope=message)
                headers["X-Content-Type-Options"] = "nosniff"
                headers["X-Frame-Options"] = "DENY"
                headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
                if settings.is_production:
                    headers["Strict-Transport-Security"] = "max-age=63072000; includeSubDomains"
            await send(message)

        await self.app(scope, receive, send_with_headers)


app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router)
