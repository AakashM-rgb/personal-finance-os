"""Verifies the baseline security response headers (app.main.
SecurityHeadersMiddleware) are actually present on real responses - both
a successful JSON response and an error response, and both an
authenticated and unauthenticated request, since a middleware bug could
easily only affect one of those paths."""

from httpx import AsyncClient


async def test_security_headers_present_on_a_public_endpoint(client: AsyncClient) -> None:
    response = await client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "strict-origin-when-cross-origin"


async def test_security_headers_present_on_an_authenticated_response(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.get("/api/v1/accounts", headers=auth_headers)
    assert response.status_code == 200
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_security_headers_present_on_an_error_response(client: AsyncClient) -> None:
    response = await client.get("/api/v1/accounts")
    assert response.status_code == 401
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"


async def test_hsts_is_not_sent_outside_production(client: AsyncClient) -> None:
    """The test environment runs with ENVIRONMENT=test, so HSTS (only
    meaningful once the app is actually served over TLS) must be absent -
    sending it over plain HTTP would be pointless and confusing."""
    response = await client.get("/api/v1/health")
    assert "strict-transport-security" not in response.headers
