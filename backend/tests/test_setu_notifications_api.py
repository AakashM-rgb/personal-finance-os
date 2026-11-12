"""Endpoint-level tests for POST /api/v1/setu/notifications - the
unauthenticated Setu Account Aggregator webhook. Covers payload validation,
the standard envelope, safe structured logging, and that a notification
never changes linked-account state (see
app.services.setu_notification_service for why)."""

import logging

import pytest
from httpx import AsyncClient

ENDPOINT = "/api/v1/setu/notifications"
LOGGER = "app.sync.setu_notifications"


def _consent_payload(status: str = "ACTIVE", **overrides: object) -> dict:
    payload: dict = {
        "type": "CONSENT_STATUS_UPDATE",
        "consentId": "6e0c1f2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b",
        "notificationId": "a1b2c3d4-0000-4000-8000-000000000001",
        "timestamp": "2026-10-07T06:47:47.925Z",
        "success": True,
        "data": {"status": status},
        "error": None,
    }
    payload.update(overrides)
    return payload


def _session_payload(status: str = "COMPLETED", **overrides: object) -> dict:
    payload: dict = {
        "type": "SESSION_STATUS_UPDATE",
        "consentId": "6e0c1f2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b",
        "dataSessionId": "9f8e7d6c-5b4a-4c3d-8e2f-1a0b9c8d7e6f",
        "notificationId": "a1b2c3d4-0000-4000-8000-000000000002",
        "timestamp": "2026-10-07T06:50:00.000Z",
        "success": True,
        "data": {
            "status": status,
            "fips": [
                {
                    "fipID": "setu-fip",
                    "accounts": [{"linkRefNumber": "link-ref-1", "maskedAccNumber": "XXXXXX9876"}],
                }
            ],
        },
        "error": None,
    }
    payload.update(overrides)
    return payload


def _received_records(caplog: pytest.LogCaptureFixture) -> list[logging.LogRecord]:
    return [r for r in caplog.records if r.message == "setu_notification_received"]


# --- valid notifications -----------------------------------------------------------


@pytest.mark.parametrize(
    "status", ["ACTIVE", "REJECTED", "REVOKED", "PAUSED", "EXPIRED", "PENDING"]
)
async def test_valid_consent_status_update_is_acknowledged_and_logged(
    client: AsyncClient, caplog: pytest.LogCaptureFixture, status: str
) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER):
        response = await client.post(ENDPOINT, json=_consent_payload(status))

    assert response.status_code == 200, response.text
    assert response.json() == {"data": {"received": True}, "error": None, "meta": None}

    [record] = _received_records(caplog)
    assert record.levelno == logging.INFO
    assert record.notification_type == "CONSENT_STATUS_UPDATE"
    assert record.consent_id == "6e0c1f2a-1b3d-4e5f-8a9b-0c1d2e3f4a5b"
    assert record.notification_id == "a1b2c3d4-0000-4000-8000-000000000001"
    assert record.data_session_id is None
    assert record.status == status
    assert record.success is True
    assert record.error_code is None


@pytest.mark.parametrize("status", ["PENDING", "PARTIAL", "COMPLETED", "EXPIRED", "FAILED"])
async def test_valid_session_status_update_is_acknowledged_and_logged(
    client: AsyncClient, caplog: pytest.LogCaptureFixture, status: str
) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER):
        response = await client.post(ENDPOINT, json=_session_payload(status))

    assert response.status_code == 200, response.text
    assert response.json() == {"data": {"received": True}, "error": None, "meta": None}

    [record] = _received_records(caplog)
    assert record.notification_type == "SESSION_STATUS_UPDATE"
    assert record.data_session_id == "9f8e7d6c-5b4a-4c3d-8e2f-1a0b9c8d7e6f"
    assert record.status == status


async def test_optional_identifiers_may_be_absent(client: AsyncClient) -> None:
    payload = _consent_payload()
    del payload["notificationId"]
    response = await client.post(ENDPOINT, json=payload)
    assert response.status_code == 200, response.text


async def test_unknown_upstream_fields_are_ignored(client: AsyncClient) -> None:
    payload = _consent_payload(someFutureSetuField={"anything": 1})
    payload["data"]["detail"] = {"accounts": []}
    response = await client.post(ENDPOINT, json=payload)
    assert response.status_code == 200, response.text


# --- failed notifications ----------------------------------------------------------


async def test_failed_session_notification_is_acknowledged_and_logged_as_warning(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    payload = _session_payload(
        "FAILED",
        success=False,
        error={"code": "FIPFailure", "message": "FIP did not respond"},
    )
    with caplog.at_level(logging.INFO, logger=LOGGER):
        response = await client.post(ENDPOINT, json=payload)

    assert response.status_code == 200, response.text
    assert response.json()["data"] == {"received": True}

    [record] = _received_records(caplog)
    assert record.levelno == logging.WARNING
    assert record.success is False
    assert record.error_code == "FIPFailure"
    assert record.status == "FAILED"


async def test_failed_notification_without_data_is_accepted(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    payload = _consent_payload(
        success=False, data=None, error={"code": "ConsentNotFound", "message": "not found"}
    )
    with caplog.at_level(logging.INFO, logger=LOGGER):
        response = await client.post(ENDPOINT, json=payload)

    assert response.status_code == 200, response.text
    [record] = _received_records(caplog)
    assert record.status is None
    assert record.error_code == "ConsentNotFound"


# --- logging safety ----------------------------------------------------------------


async def test_free_text_and_nested_account_data_are_never_logged(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    payload = _session_payload(
        "FAILED",
        success=False,
        error={"code": "InvalidRequest", "message": "otp=482913 pin=1234 secret=abc"},
        access_token="should-never-appear",
    )
    with caplog.at_level(logging.DEBUG, logger="app"):
        response = await client.post(ENDPOINT, json=payload)
    assert response.status_code == 200, response.text

    logged = caplog.text + " ".join(str(vars(r)) for r in caplog.records)
    for forbidden in (
        "482913",
        "1234",
        "secret=abc",
        "should-never-appear",
        "XXXXXX9876",
        "link-ref-1",
    ):
        assert forbidden not in logged


async def test_identifier_with_control_characters_is_rejected(client: AsyncClient) -> None:
    payload = _consent_payload(consentId="abc\nINFO forged log line")
    response = await client.post(ENDPOINT, json=payload)
    assert response.status_code == 422
    assert "consentId" in response.json()["error"]["field_errors"]


# --- malformed payloads ------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {k: v for k, v in _consent_payload().items() if k != "consentId"},
        {k: v for k, v in _consent_payload().items() if k != "timestamp"},
        {k: v for k, v in _consent_payload().items() if k != "success"},
        _consent_payload(timestamp="not-a-date"),
        _consent_payload(data=None),
        _consent_payload(data={}),
        _consent_payload("COMPLETED"),
        _consent_payload("SOMETHING_NEW"),
        _session_payload("ACTIVE"),
        {k: v for k, v in _session_payload().items() if k != "dataSessionId"},
        [],
    ],
    ids=[
        "missing-consent-id",
        "missing-timestamp",
        "missing-success",
        "bad-timestamp",
        "success-without-data",
        "data-without-status",
        "session-status-on-consent-update",
        "unknown-consent-status",
        "consent-status-on-session-update",
        "session-update-without-data-session-id",
        "not-an-object",
    ],
)
async def test_malformed_payload_returns_validation_envelope(
    client: AsyncClient, payload: object
) -> None:
    response = await client.post(ENDPOINT, json=payload)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["data"] is None
    assert body["meta"] is None
    assert body["error"]["code"] == "validation_error"
    assert body["error"]["field_errors"]


async def test_invalid_json_body_returns_validation_envelope(client: AsyncClient) -> None:
    response = await client.post(
        ENDPOINT, content=b"{not json", headers={"Content-Type": "application/json"}
    )
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "validation_error"


async def test_unsupported_notification_type_returns_validation_error(
    client: AsyncClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger=LOGGER):
        response = await client.post(ENDPOINT, json=_consent_payload(type="FI_DATA_READY"))

    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "validation_error"
    assert "type" in error["field_errors"]
    assert _received_records(caplog) == []


# --- authentication ----------------------------------------------------------------


async def test_no_authentication_required(client: AsyncClient) -> None:
    assert "authorization" not in client.headers
    assert not client.cookies
    response = await client.post(ENDPOINT, json=_consent_payload())
    assert response.status_code == 200, response.text


async def test_user_credentials_are_neither_required_nor_consulted(client: AsyncClient) -> None:
    response = await client.post(
        ENDPOINT,
        json=_consent_payload(),
        headers={"Authorization": "Bearer not-a-real-token"},
    )
    assert response.status_code == 200, response.text


# --- no state changes --------------------------------------------------------------


async def test_notification_never_changes_linked_account_state(
    client: AsyncClient, auth_headers: dict
) -> None:
    initiation = (await client.post("/api/v1/sync/links", headers=auth_headers, json={})).json()[
        "data"
    ]
    callback = await client.post(
        f"/api/v1/sync/links/{initiation['consent_handle']}/callback", headers=auth_headers
    )
    assert callback.status_code == 201, callback.text
    linked = callback.json()["data"][0]
    assert linked["consent_status"] == "active"

    # The mock provider's consent id for this handle - see app.sync.provider.mock.
    consent_id = f"mock-consent-{initiation['consent_handle']}"
    response = await client.post(ENDPOINT, json=_consent_payload("REVOKED", consentId=consent_id))
    assert response.status_code == 200, response.text

    after = await client.get(f"/api/v1/sync/links/{linked['id']}", headers=auth_headers)
    assert after.json()["data"]["consent_status"] == "active"
    assert after.json()["data"]["updated_at"] == linked["updated_at"]
