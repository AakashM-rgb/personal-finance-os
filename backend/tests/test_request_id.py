"""Request-id correlation (CLAUDE.md §17: errors logged with enough context
to debug them).

Covers the header contract, the ContextVar reaching app.* log records, and
the fact that an inbound id is attacker-controlled text that must never be
able to forge a log line.
"""

import logging
import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.config import get_settings
from app.core.logging import configure_app_logging
from app.core.request_id import HEADER_NAME, get_request_id, sanitize
from app.main import app

HEX_32 = 32


async def test_every_response_carries_a_request_id(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")

    request_id = response.headers.get(HEADER_NAME)
    assert request_id is not None
    assert len(request_id) == HEX_32
    int(request_id, 16)  # a uuid4 hex, not arbitrary text


async def test_each_request_gets_its_own_id(client: AsyncClient) -> None:
    first = await client.get("/api/v1/health")
    second = await client.get("/api/v1/health")

    assert first.headers[HEADER_NAME] != second.headers[HEADER_NAME]


async def test_a_proxy_supplied_id_is_reused_so_traces_join_up(client: AsyncClient) -> None:
    supplied = "edge-7f3a9c2b-01"

    response = await client.get("/api/v1/health", headers={HEADER_NAME: supplied})

    assert response.headers[HEADER_NAME] == supplied


async def test_an_error_response_still_carries_an_id(client: AsyncClient) -> None:
    """A 401 is produced by an exception handler inside the middleware
    stack; the id must survive it."""
    response = await client.get("/api/v1/accounts")

    assert response.status_code == 401
    assert response.headers.get(HEADER_NAME) is not None


_BOOM_PATH = "/api/v1/__test_unhandled_error"


@pytest.fixture
async def crashing_client() -> AsyncGenerator[AsyncClient, None]:
    """A route that raises an unhandled exception, removed again afterwards.
    `raise_app_exceptions=False` because Starlette re-raises after sending the
    500 (so servers can log it); the test wants the response a browser would
    see."""

    async def boom() -> None:
        raise RuntimeError("deliberate test failure")

    app.add_api_route(_BOOM_PATH, boom, methods=["GET"])
    route = app.router.routes[-1]
    transport = ASGITransport(app=app, raise_app_exceptions=False)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac
    finally:
        app.router.routes.remove(route)


async def test_an_unhandled_500_carries_an_id_and_security_headers(
    crashing_client: AsyncClient,
) -> None:
    """Starlette sends this response from ServerErrorMiddleware, outside every
    add_middleware() entry - the case a plain add_middleware() misses."""
    response = await crashing_client.get(_BOOM_PATH)

    assert response.status_code == 500
    assert response.json()["error"]["code"] == "internal_error"
    assert len(response.headers[HEADER_NAME]) == HEX_32
    assert response.headers["X-Content-Type-Options"] == "nosniff"
    assert response.headers["X-Frame-Options"] == "DENY"


async def test_the_500_header_matches_the_id_on_its_logged_traceback(
    crashing_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    """The point of the id: a user quotes the header, the operator finds the
    traceback. Both must name the same request."""
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        response = await crashing_client.get(_BOOM_PATH)

    records = [r for r in caplog.records if r.name == "app.errors" and r.exc_info]
    assert len(records) == 1
    assert getattr(records[0], "request_id", None) == response.headers[HEADER_NAME]


async def test_a_proxy_supplied_id_reaches_the_500_and_its_log(
    crashing_client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.ERROR, logger="app.errors"):
        response = await crashing_client.get(_BOOM_PATH, headers={HEADER_NAME: "edge-500-trace"})

    assert response.headers[HEADER_NAME] == "edge-500-trace"
    records = [r for r in caplog.records if r.name == "app.errors" and r.exc_info]
    assert getattr(records[0], "request_id", None) == "edge-500-trace"


async def test_a_cors_preflight_carries_an_id(client: AsyncClient) -> None:
    """CORSMiddleware answers a preflight itself, without calling the app."""
    origin = get_settings().cors_origin_list[0]

    response = await client.options(
        "/api/v1/auth/login",
        headers={"Origin": origin, "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == origin
    assert len(response.headers[HEADER_NAME]) == HEX_32


async def test_a_refused_cors_preflight_carries_an_id_but_no_cors_grant(
    client: AsyncClient,
) -> None:
    response = await client.options(
        "/api/v1/auth/login",
        headers={"Origin": "https://evil.example", "Access-Control-Request-Method": "POST"},
    )

    assert response.status_code == 400
    assert "access-control-allow-origin" not in response.headers
    assert len(response.headers[HEADER_NAME]) == HEX_32


async def test_a_validation_error_carries_an_id(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/accounts", headers=auth_headers, json={"type": "bank_account"}
    )

    assert response.status_code == 422
    assert response.headers.get(HEADER_NAME) is not None


@pytest.mark.parametrize(
    "hostile",
    [
        "abc\ndef",  # a newline could forge a whole log line
        "abc\r\nWARNING fake",
        "id with spaces",
        "id;rm -rf /",
        "../../etc/passwd",
        "\x00null",
        "x" * 201,  # unbounded padding
        "   ",
        "",
        None,
    ],
)
def test_a_hostile_inbound_id_is_dropped(hostile: str | None) -> None:
    assert sanitize(hostile) is None


@pytest.mark.parametrize(
    "acceptable",
    ["edge-7f3a9c2b-01", uuid.uuid4().hex, "a.b_c-1", "x" * 200],
)
def test_a_reasonable_inbound_id_is_kept(acceptable: str) -> None:
    assert sanitize(acceptable) == acceptable


async def test_a_hostile_inbound_id_never_reaches_the_response(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health", headers={HEADER_NAME: "abc-def"})
    assert response.headers[HEADER_NAME] == "abc-def"

    # httpx itself rejects a header value containing a newline, so the
    # sanitizer is what protects against a proxy or client that does not.
    spoofed = await client.get("/api/v1/health", headers={HEADER_NAME: "id with spaces"})
    assert spoofed.headers[HEADER_NAME] != "id with spaces"
    assert len(spoofed.headers[HEADER_NAME]) == HEX_32


def test_outside_a_request_there_is_no_id() -> None:
    """A background job or startup log must not inherit a stale id."""
    assert get_request_id() is None


def test_app_log_records_are_stamped_with_the_current_id(
    caplog: pytest.LogCaptureFixture,
) -> None:
    from app.core.request_id import set_request_id

    configure_app_logging()
    set_request_id("test-correlation-1")
    logger = logging.getLogger("app.test")

    handler = next(h for h in logging.getLogger("app").handlers)
    record = logging.LogRecord("app.test", logging.INFO, __file__, 1, "boom", (), None)
    for log_filter in handler.filters:
        log_filter.filter(record)

    assert getattr(record, "request_id", None) == "test-correlation-1"
    assert logger.name.startswith("app.")
