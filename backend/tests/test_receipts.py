import io

from httpx import AsyncClient
from reportlab.pdfgen import canvas

_PNG_1PX = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)
_JPEG_MINIMAL = b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00\xff\xd9"


def _make_pdf(lines: list[str]) -> bytes:
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(400, 400))
    y = 380
    for line in lines:
        c.drawString(20, y, line)
        y -= 20
    c.save()
    return buf.getvalue()


def _receipt_pdf_bytes() -> bytes:
    return _make_pdf(
        [
            "Corner Cafe",
            "Date: 2026-03-05",
            "Coffee            250.00",
            "Sandwich  2 x 150.00 each = 300.00",
            "Tax               50.00",
            "Grand Total       600.00",
        ]
    )


async def _upload(
    client: AsyncClient, headers: dict, *, content: bytes, filename: str, content_type: str
):
    return await client.post(
        "/api/v1/receipts/upload",
        headers=headers,
        files={"file": (filename, content, content_type)},
    )


async def _upload_pdf(client: AsyncClient, headers: dict) -> dict:
    response = await _upload(
        client,
        headers,
        content=_receipt_pdf_bytes(),
        filename="receipt.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Test Account")
    payload.setdefault("type", "cash")
    payload.setdefault("balance_minor", 10000000)
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> str:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return category["id"]
    raise AssertionError(f"category {name!r} not found in list")


# --- upload / OCR ----------------------------------------------------------------------


async def test_upload_pdf_extracts_real_embedded_text(
    client: AsyncClient, auth_headers: dict
) -> None:
    receipt = await _upload_pdf(client, auth_headers)

    assert receipt["status"] == "processed"
    assert receipt["content_type"] == "application/pdf"
    extraction = receipt["extraction"]
    assert extraction["provider"] == "mock"
    assert extraction["merchant"] == "Corner Cafe"
    assert extraction["date"] == "2026-03-05"
    assert extraction["total_minor"] == 60000
    assert extraction["tax_minor"] == 5000
    descriptions = {item["description"] for item in extraction["items"]}
    assert "Coffee" in descriptions
    assert "Sandwich" in descriptions


async def test_upload_image_is_honest_about_no_ocr(client: AsyncClient, auth_headers: dict) -> None:
    response = await _upload(
        client, auth_headers, content=_PNG_1PX, filename="receipt.png", content_type="image/png"
    )
    assert response.status_code == 201, response.text
    receipt = response.json()["data"]

    assert receipt["status"] == "processed"
    extraction = receipt["extraction"]
    assert extraction["provider"] == "mock"
    assert extraction["confidence"] == 0.0
    assert extraction["merchant"] is None
    assert extraction["total_minor"] is None
    assert extraction["items"] == []


async def test_upload_jpeg(client: AsyncClient, auth_headers: dict) -> None:
    response = await _upload(
        client,
        auth_headers,
        content=_JPEG_MINIMAL,
        filename="receipt.jpg",
        content_type="image/jpeg",
    )
    assert response.status_code == 201, response.text


async def test_upload_rejects_empty_file(client: AsyncClient, auth_headers: dict) -> None:
    response = await _upload(
        client, auth_headers, content=b"", filename="empty.pdf", content_type="application/pdf"
    )
    assert response.status_code == 422
    assert response.json()["error"]["field_errors"]["file"] == "empty"


async def test_upload_rejects_oversized_file(client: AsyncClient, auth_headers: dict) -> None:
    oversized = _PNG_1PX + b"\x00" * (10 * 1024 * 1024)
    response = await _upload(
        client, auth_headers, content=oversized, filename="big.png", content_type="image/png"
    )
    assert response.status_code == 422
    assert response.json()["error"]["field_errors"]["file"] == "too_large"


async def test_upload_rejects_unsupported_extension(
    client: AsyncClient, auth_headers: dict
) -> None:
    response = await _upload(
        client,
        auth_headers,
        content=b"hello world",
        filename="notes.txt",
        content_type="text/plain",
    )
    assert response.status_code == 422
    assert response.json()["error"]["field_errors"]["file"] == "unsupported_type"


async def test_upload_rejects_content_that_does_not_match_extension(
    client: AsyncClient, auth_headers: dict
) -> None:
    # Real PNG bytes, but dressed up as a PDF - the sniffer must catch this,
    # never trust the filename or declared content type alone.
    response = await _upload(
        client, auth_headers, content=_PNG_1PX, filename="fake.pdf", content_type="application/pdf"
    )
    assert response.status_code == 422
    assert response.json()["error"]["field_errors"]["file"] == "content_mismatch"


async def test_upload_rejects_corrupt_pdf(client: AsyncClient, auth_headers: dict) -> None:
    corrupt = b"%PDF-1.4\nnot a real pdf body"
    response = await _upload(
        client,
        auth_headers,
        content=corrupt,
        filename="corrupt.pdf",
        content_type="application/pdf",
    )
    assert response.status_code == 422
    assert response.json()["error"]["field_errors"]["file"] == "invalid_content"


# --- list / get / download --------------------------------------------------------------


async def test_list_starts_empty(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get("/api/v1/receipts", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"] == []


async def test_get_by_id(client: AsyncClient, auth_headers: dict) -> None:
    created = await _upload_pdf(client, auth_headers)
    response = await client.get(f"/api/v1/receipts/{created['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == created["id"]


async def test_get_unknown_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get(
        "/api/v1/receipts/00000000-0000-0000-0000-00000000ffff", headers=auth_headers
    )
    assert response.status_code == 404


async def test_download_file_returns_original_bytes(
    client: AsyncClient, auth_headers: dict
) -> None:
    original = _receipt_pdf_bytes()
    response = await _upload(
        client,
        auth_headers,
        content=original,
        filename="receipt.pdf",
        content_type="application/pdf",
    )
    receipt = response.json()["data"]

    file_response = await client.get(f"/api/v1/receipts/{receipt['id']}/file", headers=auth_headers)
    assert file_response.status_code == 200
    assert file_response.content == original
    assert file_response.headers["content-type"] == "application/pdf"


# --- confirm -----------------------------------------------------------------------------


async def test_confirm_sets_confirmed_fields_and_never_touches_extracted(
    client: AsyncClient, auth_headers: dict
) -> None:
    created = await _upload_pdf(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")

    response = await client.put(
        f"/api/v1/receipts/{created['id']}/confirm",
        headers=auth_headers,
        json={
            "merchant": "Corner Cafe Corrected",
            "date": "2026-03-06",
            "total_minor": 61000,
            "tax_minor": 5000,
            "items": [{"description": "Coffee", "quantity": "1", "line_total_minor": 25000}],
            "category_id": food_id,
        },
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "confirmed"
    assert data["confirmed_merchant"] == "Corner Cafe Corrected"
    assert data["confirmed_total_minor"] == 61000
    assert data["category_id"] == food_id
    # OCR candidates are untouched by the human correction.
    assert data["extraction"]["merchant"] == "Corner Cafe"
    assert data["extraction"]["total_minor"] == 60000


async def test_confirm_rejects_unknown_category(client: AsyncClient, auth_headers: dict) -> None:
    created = await _upload_pdf(client, auth_headers)
    response = await client.put(
        f"/api/v1/receipts/{created['id']}/confirm",
        headers=auth_headers,
        json={"total_minor": 1000, "category_id": "00000000-0000-0000-0000-00000000ffff"},
    )
    assert response.status_code == 422


# --- create transaction from receipt ------------------------------------------------------


async def test_create_transaction_requires_confirmation_first(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    created = await _upload_pdf(client, auth_headers)

    response = await client.post(
        f"/api/v1/receipts/{created['id']}/transaction",
        headers=auth_headers,
        json={"account_id": account["id"]},
    )
    assert response.status_code == 422


async def test_create_transaction_from_confirmed_receipt(
    client: AsyncClient, auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    created = await _upload_pdf(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")

    await client.put(
        f"/api/v1/receipts/{created['id']}/confirm",
        headers=auth_headers,
        json={
            "merchant": "Corner Cafe",
            "date": "2026-03-05",
            "total_minor": 60000,
            "category_id": food_id,
        },
    )

    response = await client.post(
        f"/api/v1/receipts/{created['id']}/transaction",
        headers=auth_headers,
        json={"account_id": account["id"]},
    )
    assert response.status_code == 201, response.text
    transaction = response.json()["data"]
    assert transaction["amount_minor"] == 60000
    assert transaction["type"] == "expense"
    assert transaction["merchant"] == "Corner Cafe"

    receipt_after = await client.get(f"/api/v1/receipts/{created['id']}", headers=auth_headers)
    assert receipt_after.json()["data"]["transaction_id"] == transaction["id"]


async def test_create_transaction_twice_conflicts(client: AsyncClient, auth_headers: dict) -> None:
    account = await _create_account(client, auth_headers)
    created = await _upload_pdf(client, auth_headers)
    await client.put(
        f"/api/v1/receipts/{created['id']}/confirm",
        headers=auth_headers,
        json={"total_minor": 60000},
    )
    first = await client.post(
        f"/api/v1/receipts/{created['id']}/transaction",
        headers=auth_headers,
        json={"account_id": account["id"]},
    )
    assert first.status_code == 201

    second = await client.post(
        f"/api/v1/receipts/{created['id']}/transaction",
        headers=auth_headers,
        json={"account_id": account["id"]},
    )
    assert second.status_code == 409


# --- delete --------------------------------------------------------------------------------


async def test_delete_receipt(client: AsyncClient, auth_headers: dict) -> None:
    created = await _upload_pdf(client, auth_headers)
    response = await client.delete(f"/api/v1/receipts/{created['id']}", headers=auth_headers)
    assert response.status_code == 200

    follow_up = await client.get(f"/api/v1/receipts/{created['id']}", headers=auth_headers)
    assert follow_up.status_code == 404


async def test_delete_unknown_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.delete(
        "/api/v1/receipts/00000000-0000-0000-0000-00000000ffff", headers=auth_headers
    )
    assert response.status_code == 404


# --- authorization isolation -----------------------------------------------------------------


async def test_cannot_read_another_users_receipt(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    theirs = await _upload_pdf(client, other_auth_headers)
    response = await client.get(f"/api/v1/receipts/{theirs['id']}", headers=auth_headers)
    assert response.status_code == 404


async def test_cannot_download_another_users_receipt_file(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    theirs = await _upload_pdf(client, other_auth_headers)
    response = await client.get(f"/api/v1/receipts/{theirs['id']}/file", headers=auth_headers)
    assert response.status_code == 404


async def test_cannot_confirm_another_users_receipt(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    theirs = await _upload_pdf(client, other_auth_headers)
    response = await client.put(
        f"/api/v1/receipts/{theirs['id']}/confirm",
        headers=auth_headers,
        json={"total_minor": 1000},
    )
    assert response.status_code == 404


async def test_cannot_create_transaction_from_another_users_receipt(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    account = await _create_account(client, auth_headers)
    theirs = await _upload_pdf(client, other_auth_headers)
    await client.put(
        f"/api/v1/receipts/{theirs['id']}/confirm",
        headers=other_auth_headers,
        json={"total_minor": 1000},
    )
    response = await client.post(
        f"/api/v1/receipts/{theirs['id']}/transaction",
        headers=auth_headers,
        json={"account_id": account["id"]},
    )
    assert response.status_code == 404


async def test_cannot_delete_another_users_receipt(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    theirs = await _upload_pdf(client, other_auth_headers)
    response = await client.delete(f"/api/v1/receipts/{theirs['id']}", headers=auth_headers)
    assert response.status_code == 404

    still_theirs = await client.get(f"/api/v1/receipts/{theirs['id']}", headers=other_auth_headers)
    assert still_theirs.status_code == 200


async def test_list_never_leaks_another_users_receipts(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    await _upload_pdf(client, other_auth_headers)
    mine = await _upload_pdf(client, auth_headers)

    response = await client.get("/api/v1/receipts", headers=auth_headers)
    ids = [r["id"] for r in response.json()["data"]]
    assert ids == [mine["id"]]
