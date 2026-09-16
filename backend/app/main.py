"""FastAPI application entrypoint."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.v1.router import api_router
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_app_logging
from app.core.rate_limit import limiter

configure_app_logging()

settings = get_settings()

app = FastAPI(title="Finance App API", version="0.1.0")

# Note: SlowAPIMiddleware (Starlette BaseHTTPMiddleware) is deliberately not
# added. It is not required for the per-route @limiter.limit(...) decorators
# below to work - RateLimitExceeded is already handled in register_exception_handlers -
# and BaseHTTPMiddleware's task-per-request model is incompatible with the
# asyncpg driver's event-loop binding.
app.state.limiter = limiter

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

register_exception_handlers(app)

app.include_router(api_router)
