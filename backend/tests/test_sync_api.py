"""Endpoint-level tests for /api/v1/sync/* - authentication, ownership,
request validation, and that the router stays a thin pass-through to
app.services.sync_service (business logic, counters, and security
invariants are already covered by tests/test_sync_service.py)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient

from app.services import sync_service
from app.sync.provider.base import (
    ExternalTransaction,
    LinkCompletion,
    LinkedInstitutionAccount,
    LinkInitiation,
)


async def _get_user_id(client: AsyncClient, headers: dict) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=headers)
    return uuid.UUID(response.json()["data"]["id"])


async def _create_account(client: AsyncClient, headers: dict, **payload) -> dict:
    payload.setdefault("name", "Wallet")
    payload.setdefault("type", "cash")
    payload.setdefault("balance_minor", 500_000)
    response = await client.post("/api/v1/accounts", headers=headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _initiate(client: AsyncClient, headers: dict) -> dict:
    response = await client.post("/api/v1/sync/links", headers=headers, json={})
    assert response.status_code == 201, response.text
    return response.json()["data"]


async def _link(client: AsyncClient, headers: dict) -> dict:
    """Initiates + completes a link using the real deterministic mock
    provider, returning the first (and, for the mock, only) LinkedAccount."""
    initiation = await _initiate(client, headers)
    response = await client.post(
        f"/api/v1/sync/links/{initiation['consent_handle']}/callback", headers=headers
    )
    assert response.status_code == 201, response.text
    return response.json()["data"][0]


# --- A: link lifecycle -----------------------------------------------------------


async def test_initiate_link_returns_redirect_and_handle(
    client: AsyncClient, auth_headers: dict
) -> None:
    data = await _initiate(client, auth_headers)
    assert data["provider"] == "mock"
    assert data["consent_handle"]
    assert data["redirect_url"]
    assert data["expires_at"]


async def test_callback_completes_link_and_creates_internal_account(
    client: AsyncClient, auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    assert linked["account_id"] is not None
    assert linked["consent_status"] == "active"
    assert linked["masked_account_ref"] == "XX4321"
    assert linked["provider"] == "mock"

    accounts = await client.get("/api/v1/accounts", headers=auth_headers)
    account_ids = [a["id"] for a in accounts.json()["data"]]
    assert linked["account_id"] in account_ids


async def test_list_links_returns_only_my_links(client: AsyncClient, auth_headers: dict) -> None:
    linked = await _link(client, auth_headers)
    response = await client.get("/api/v1/sync/links", headers=auth_headers)
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["data"]]
    assert linked["id"] in ids
    assert response.json()["meta"]["count"] == len(ids)


async def test_get_link_returns_the_linked_account(client: AsyncClient, auth_headers: dict) -> None:
    linked = await _link(client, auth_headers)
    response = await client.get(f"/api/v1/sync/links/{linked['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["id"] == linked["id"]


async def test_update_link_remaps_to_an_existing_account(
    client: AsyncClient, auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    other_account = await _create_account(client, auth_headers, name="Savings")

    response = await client.patch(
        f"/api/v1/sync/links/{linked['id']}",
        headers=auth_headers,
        json={"account_id": other_account["id"]},
    )
    assert response.status_code == 200
    assert response.json()["data"]["account_id"] == other_account["id"]


async def test_revoke_link_marks_it_revoked(client: AsyncClient, auth_headers: dict) -> None:
    linked = await _link(client, auth_headers)
    response = await client.delete(f"/api/v1/sync/links/{linked['id']}", headers=auth_headers)
    assert response.status_code == 200
    assert response.json()["data"]["consent_status"] == "revoked"


# --- B: ownership ------------------------------------------------------------------


async def test_user_b_cannot_view_user_a_link(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    response = await client.get(f"/api/v1/sync/links/{linked['id']}", headers=other_auth_headers)
    assert response.status_code == 404


async def test_user_b_cannot_sync_user_a_link(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    response = await client.post(
        f"/api/v1/sync/links/{linked['id']}/sync", headers=other_auth_headers
    )
    assert response.status_code == 404


async def test_user_b_cannot_update_user_a_link(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    their_account = await _create_account(client, other_auth_headers)
    response = await client.patch(
        f"/api/v1/sync/links/{linked['id']}",
        headers=other_auth_headers,
        json={"account_id": their_account["id"]},
    )
    assert response.status_code == 404


async def test_user_b_cannot_revoke_user_a_link(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    response = await client.delete(f"/api/v1/sync/links/{linked['id']}", headers=other_auth_headers)
    assert response.status_code == 404


async def test_user_b_cannot_view_user_a_sync_runs(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    await client.post(f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers)
    response = await client.get(
        f"/api/v1/sync/links/{linked['id']}/runs", headers=other_auth_headers
    )
    assert response.status_code == 404


async def test_unauthenticated_requests_are_rejected(client: AsyncClient) -> None:
    assert (await client.get("/api/v1/sync/links")).status_code == 401
    assert (await client.post("/api/v1/sync/links", json={})).status_code == 401


# --- C: sync endpoint ----------------------------------------------------------------


async def test_manual_sync_creates_transactions_through_phase_b(
    client: AsyncClient, auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)

    response = await client.post(f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers)
    assert response.status_code == 200
    run = response.json()["data"]
    assert run["status"] == "success"
    assert run["transactions_fetched"] == run["transactions_created"]
    assert run["transactions_created"] > 0
    assert run["transactions_skipped_duplicate"] == 0

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [
        t for t in transactions.json()["data"] if t["linked_account_id"] == linked["id"]
    ]
    assert len(synced) == run["transactions_created"]


async def test_manual_sync_is_idempotent_on_repeat(client: AsyncClient, auth_headers: dict) -> None:
    """Repeating a sync must never create a duplicate transaction. Note the
    second call's own `since` window naturally starts from the first
    call's completion time (see sync_service.trigger_sync), so on the same
    day it legitimately re-fetches nothing new (transactions_fetched=0) -
    the meaningful invariant proven here is the transaction COUNT never
    grows, whichever way a run gets to zero new imports."""
    linked = await _link(client, auth_headers)

    first = await client.post(f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers)
    first_created = first.json()["data"]["transactions_created"]
    assert first_created > 0

    second = await client.post(f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers)
    second_data = second.json()["data"]
    assert second_data["status"] == "success"
    assert second_data["transactions_created"] == 0

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == linked["id"]]
    assert len(synced) == first_created  # never duplicated


async def test_sync_run_history_lists_prior_runs(client: AsyncClient, auth_headers: dict) -> None:
    linked = await _link(client, auth_headers)
    await client.post(f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers)
    await client.post(f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers)

    response = await client.get(f"/api/v1/sync/links/{linked['id']}/runs", headers=auth_headers)
    assert response.status_code == 200
    runs = response.json()["data"]
    assert len(runs) == 2
    assert response.json()["meta"]["count"] == 2
    for run in runs:
        assert set(run) == {
            "id",
            "linked_account_id",
            "started_at",
            "completed_at",
            "status",
            "transactions_fetched",
            "transactions_created",
            "transactions_skipped_duplicate",
            "error_message",
        }


@dataclass
class _FailingSyncProvider:
    name: str = "mock"

    async def initiate_link(
        self, *, user_id: uuid.UUID, institution_hint: str | None = None
    ) -> LinkInitiation:
        return LinkInitiation(
            provider=self.name,
            consent_handle=f"fail-handle-{user_id}",
            redirect_url="https://fail-provider.invalid/consent",
            expires_at=datetime(2027, 1, 1, tzinfo=UTC),
        )

    async def complete_link(self, *, consent_handle: str) -> LinkCompletion:
        return LinkCompletion(
            consent_id=f"mock-consent-{consent_handle}",
            consent_status="active",
            consent_expires_at=datetime(2027, 1, 1, tzinfo=UTC),
            accounts=(
                LinkedInstitutionAccount(
                    external_account_id="fail-acc",
                    institution_name="Fail Bank",
                    fip_reference=None,
                    masked_account_ref="XX0000",
                ),
            ),
        )

    async def list_linked_institution_accounts(
        self, *, consent_id: str
    ) -> tuple[LinkedInstitutionAccount, ...]:
        return ()

    async def list_transactions(
        self, *, consent_id: str, external_account_id: str, since: date, until: date
    ) -> tuple[ExternalTransaction, ...]:
        raise RuntimeError("provider unreachable")

    async def revoke_consent(self, *, consent_id: str) -> None:
        return None


async def test_manual_sync_provider_failure_returns_failed_run_not_500(
    client: AsyncClient, auth_headers: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    fake = _FailingSyncProvider()
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)

    initiation = await _initiate(client, auth_headers)
    completed = await client.post(
        f"/api/v1/sync/links/{initiation['consent_handle']}/callback", headers=auth_headers
    )
    linked = completed.json()["data"][0]

    response = await client.post(f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers)
    assert response.status_code == 200  # never a raw 500
    run = response.json()["data"]
    assert run["status"] == "failed"
    assert run["error_message"] is not None
    assert "provider unreachable" in run["error_message"]
    assert "Traceback" not in run["error_message"]


# --- D: unlink behavior --------------------------------------------------------------


async def test_unlink_does_not_delete_historical_transactions(
    client: AsyncClient, auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    sync_response = await client.post(
        f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers
    )
    created = sync_response.json()["data"]["transactions_created"]
    assert created > 0

    await client.delete(f"/api/v1/sync/links/{linked['id']}", headers=auth_headers)

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == linked["id"]]
    assert len(synced) == created  # nothing was cascade-deleted

    still_visible = await client.get(f"/api/v1/sync/links/{linked['id']}", headers=auth_headers)
    assert still_visible.status_code == 200
    assert still_visible.json()["data"]["consent_status"] == "revoked"


# --- E: security ---------------------------------------------------------------------


def test_no_payment_or_money_moving_route_exists() -> None:
    from app.api.v1.sync import router

    forbidden = ("pay", "transfer", "withdraw", "debit", "credit", "send-money", "send_money")
    for route in router.routes:
        path = route.path.lower()  # type: ignore[attr-defined]
        for term in forbidden:
            assert term not in path, f"unexpected route segment {term!r} in {path!r}"


async def test_linked_account_response_never_exposes_consent_id_or_external_account_id(
    client: AsyncClient, auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    assert "consent_id" not in linked
    assert "external_account_id" not in linked
    assert "provider_credentials" not in linked

    response = await client.get(f"/api/v1/sync/links/{linked['id']}", headers=auth_headers)
    assert "consent_id" not in response.json()["data"]


async def test_sync_run_response_never_exposes_raw_provider_payload(
    client: AsyncClient, auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    response = await client.post(f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers)
    run = response.json()["data"]
    assert set(run) == {
        "id",
        "linked_account_id",
        "started_at",
        "completed_at",
        "status",
        "transactions_fetched",
        "transactions_created",
        "transactions_skipped_duplicate",
        "error_message",
    }


# --- F: validation -------------------------------------------------------------------


async def test_initiate_link_rejects_extra_fields(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.post(
        "/api/v1/sync/links", headers=auth_headers, json={"institution_hint": "HDFC", "pin": "1234"}
    )
    assert response.status_code == 422


async def test_update_link_rejects_extra_fields(client: AsyncClient, auth_headers: dict) -> None:
    linked = await _link(client, auth_headers)
    response = await client.patch(
        f"/api/v1/sync/links/{linked['id']}",
        headers=auth_headers,
        json={"account_id": linked["account_id"], "consent_status": "active"},
    )
    assert response.status_code == 422


async def test_update_link_rejects_mapping_to_another_users_account(
    client: AsyncClient, auth_headers: dict, other_auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    their_account = await _create_account(client, other_auth_headers)
    response = await client.patch(
        f"/api/v1/sync/links/{linked['id']}",
        headers=auth_headers,
        json={"account_id": their_account["id"]},
    )
    assert response.status_code == 404


async def test_update_link_rejects_mapping_to_archived_account(
    client: AsyncClient, auth_headers: dict
) -> None:
    linked = await _link(client, auth_headers)
    archived = await _create_account(client, auth_headers, name="Old Wallet")
    await client.delete(f"/api/v1/accounts/{archived['id']}", headers=auth_headers)

    response = await client.patch(
        f"/api/v1/sync/links/{linked['id']}",
        headers=auth_headers,
        json={"account_id": archived["id"]},
    )
    assert response.status_code == 422


async def test_sync_rejects_a_revoked_link(client: AsyncClient, auth_headers: dict) -> None:
    linked = await _link(client, auth_headers)
    await client.delete(f"/api/v1/sync/links/{linked['id']}", headers=auth_headers)

    response = await client.post(f"/api/v1/sync/links/{linked['id']}/sync", headers=auth_headers)
    assert response.status_code == 422


async def test_get_nonexistent_link_is_404(client: AsyncClient, auth_headers: dict) -> None:
    response = await client.get(f"/api/v1/sync/links/{uuid.uuid4()}", headers=auth_headers)
    assert response.status_code == 404
