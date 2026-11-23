"""Every request body is capped (app.core.body_limit), and the refusal is the
normal JSON error envelope -- with a request id -- not plain text."""

from collections.abc import AsyncIterator

from httpx import AsyncClient, Response

from app.core.body_limit import MAX_REQUEST_BODY_BYTES
from app.core.request_id import HEADER_NAME
from app.schemas.receipt import RECEIPT_MAX_FILE_SIZE_BYTES


def _assert_413_envelope(response: Response) -> None:
    assert response.status_code == 413
    error = response.json()["error"]
    assert error["code"] == "payload_too_large"
    assert "too large" in error["message"]
    assert response.headers.get(HEADER_NAME)


async def test_a_declared_oversized_body_is_refused_before_it_is_read(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await client.post(
        "/api/v1/accounts",
        headers={**auth_headers, "Content-Type": "application/json"},
        content=b"x" * (MAX_REQUEST_BODY_BYTES + 1),
    )
    _assert_413_envelope(response)


async def test_a_streamed_body_without_content_length_is_cut_off(
    client: AsyncClient, auth_headers: dict
) -> None:
    """A chunked upload declares no length, so the limit has to be enforced
    while the body arrives."""

    async def chunks() -> AsyncIterator[bytes]:
        chunk = b"x" * (1024 * 1024)
        for _ in range(MAX_REQUEST_BODY_BYTES // len(chunk) + 2):
            yield chunk

    response = await client.post(
        "/api/v1/accounts",
        headers={**auth_headers, "Content-Type": "application/json"},
        content=chunks(),
    )
    _assert_413_envelope(response)


async def test_an_ordinary_request_is_unaffected(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/accounts",
        headers=auth_headers,
        json={"name": "Main Bank", "type": "bank_account", "balance_minor": 1_000_00},
    )
    assert response.status_code == 201, response.text


def test_the_limit_still_admits_a_maximum_size_receipt() -> None:
    assert MAX_REQUEST_BODY_BYTES > RECEIPT_MAX_FILE_SIZE_BYTES
