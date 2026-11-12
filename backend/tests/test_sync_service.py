"""Tests for the Phase B automatic-sync orchestration
(app.services.sync_service): link lifecycle, the ingestion pipeline
(dedup/normalize/categorize/confidence), SyncRun bookkeeping, and the
security invariants the pipeline must never violate."""

import ast
import inspect
import logging
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
from httpx import AsyncClient
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.classifier.base import (
    MerchantClassificationRequest,
    MerchantClassificationResult,
    validate_classification,
)
from app.core.errors import NotFoundError, ValidationAppError
from app.models.linked_account import LinkedAccount, SyncConsentStatus
from app.models.sync_run import SyncRun, SyncRunStatus
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.sync import LinkedAccountRead
from app.schemas.transaction import TransactionCreate
from app.services import merchant_rule_service, sync_service, transaction_service
from app.services.merchant_normalization import normalize_merchant
from app.sync.provider.base import (
    ExternalTransaction,
    LinkCompletion,
    LinkedInstitutionAccount,
    LinkInitiation,
)

_FAKE_EXTERNAL_ACCOUNT_ID = "fake-acc-001"


@dataclass
class _FakeMerchantClassifier:
    """A fake MerchantClassifier for sync-pipeline tests - never the real
    mock or Anthropic implementation, and never a real network call.
    Routes every response through the SAME validate_classification choke
    point a real implementation uses, so a test can't accidentally exercise
    behavior a real implementation wouldn't actually produce (e.g. an
    out-of-allow-list category "succeeding"). `error`, when set, is raised
    instead of returning a result, to exercise sync_service's fail-safe
    handling. `calls` records every request this classifier actually
    received, for tests to inspect - both "was it called at all" and
    "what exactly was in the request"."""

    name: str = "fake"
    category_name: str | None = None
    confidence: float = 0.9
    error: Exception | None = None
    calls: list[MerchantClassificationRequest] = field(default_factory=list)

    async def classify(
        self, request: MerchantClassificationRequest
    ) -> MerchantClassificationResult:
        self.calls.append(request)
        if self.error is not None:
            raise self.error
        return validate_classification(
            category_name=self.category_name,
            confidence=self.confidence,
            category_names=request.category_names,
        )


@dataclass
class _FakeSyncProvider:
    name: str = "fake"
    institution_name: str = "Fake Bank"
    external_account_id: str = _FAKE_EXTERNAL_ACCOUNT_ID
    masked_account_ref: str = "XX9999"
    consent_status: str = "active"
    consent_expires_at: datetime | None = datetime(2027, 1, 1, tzinfo=UTC)
    transactions: list[ExternalTransaction] = field(default_factory=list)
    list_transactions_error: Exception | None = None
    revoke_calls: list[str] = field(default_factory=list)

    async def initiate_link(
        self, *, user_id: uuid.UUID, institution_hint: str | None = None
    ) -> LinkInitiation:
        return LinkInitiation(
            provider=self.name,
            consent_handle=f"fake-handle-{user_id}",
            redirect_url="https://fake-aa.invalid/consent",
            expires_at=datetime(2027, 1, 1, tzinfo=UTC),
        )

    async def complete_link(self, *, consent_handle: str) -> LinkCompletion:
        return LinkCompletion(
            consent_id=f"fake-consent-{consent_handle}",
            consent_status=self.consent_status,
            consent_expires_at=self.consent_expires_at,
            accounts=(
                LinkedInstitutionAccount(
                    external_account_id=self.external_account_id,
                    institution_name=self.institution_name,
                    fip_reference="FAKE-FIP-001",
                    masked_account_ref=self.masked_account_ref,
                ),
            ),
        )

    async def list_linked_institution_accounts(
        self, *, consent_id: str
    ) -> tuple[LinkedInstitutionAccount, ...]:
        return (
            LinkedInstitutionAccount(
                external_account_id=self.external_account_id,
                institution_name=self.institution_name,
                fip_reference="FAKE-FIP-001",
                masked_account_ref=self.masked_account_ref,
            ),
        )

    async def list_transactions(
        self, *, consent_id: str, external_account_id: str, since: date, until: date
    ) -> tuple[ExternalTransaction, ...]:
        if self.list_transactions_error is not None:
            raise self.list_transactions_error
        return tuple(self.transactions)

    async def revoke_consent(self, *, consent_id: str) -> None:
        self.revoke_calls.append(consent_id)


def _ext_txn(**overrides: object) -> ExternalTransaction:
    defaults: dict = {
        "external_transaction_id": "ext-1",
        "external_account_id": _FAKE_EXTERNAL_ACCOUNT_ID,
        "occurred_on": date(2026, 9, 1),
        "amount_minor": 39_900,
        "direction": "debit",
        "narration": "UPI/DR/399/SWIGGY/paytm@ybl/Swiggy Order",
    }
    defaults.update(overrides)
    return ExternalTransaction(**defaults)  # type: ignore[arg-type]


async def _get_user_id(client: AsyncClient, headers: dict) -> uuid.UUID:
    response = await client.get("/api/v1/auth/me", headers=headers)
    return uuid.UUID(response.json()["data"]["id"])


async def _get_category_id(client: AsyncClient, headers: dict, name: str) -> uuid.UUID:
    response = await client.get("/api/v1/categories", headers=headers)
    for category in response.json()["data"]:
        if category["name"] == name:
            return uuid.UUID(category["id"])
    raise AssertionError(f"category {name!r} not found in list")


async def _link(db_session: AsyncSession, *, user_id: uuid.UUID) -> LinkedAccountRead:
    linked = await sync_service.complete_link(
        db_session, user_id=user_id, consent_handle=f"handle-{user_id}-{uuid.uuid4()}"
    )
    await db_session.commit()
    return linked[0]


# --- link lifecycle ----------------------------------------------------------


async def test_complete_link_creates_linked_account_and_internal_account(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider()
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)

    linked = await _link(db_session, user_id=user_id)

    assert linked.account_id is not None
    assert linked.consent_status == SyncConsentStatus.ACTIVE
    assert linked.masked_account_ref == "XX9999"

    accounts = await client.get("/api/v1/accounts", headers=auth_headers)
    account_ids = [a["id"] for a in accounts.json()["data"]]
    assert str(linked.account_id) in account_ids


async def test_complete_link_is_idempotent_for_same_consent(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider()
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)

    first = await sync_service.complete_link(
        db_session, user_id=user_id, consent_handle="same-handle"
    )
    await db_session.commit()
    second = await sync_service.complete_link(
        db_session, user_id=user_id, consent_handle="same-handle"
    )
    await db_session.commit()

    assert first[0].id == second[0].id

    linked_accounts = await sync_service.list_linked_accounts(db_session, user_id=user_id)
    assert len(linked_accounts) == 1  # no duplicate row from the second completion


async def test_revoke_link_marks_consent_revoked_and_blocks_further_sync(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider()
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    revoked = await sync_service.revoke_link(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()

    assert revoked.consent_status == SyncConsentStatus.REVOKED
    assert fake.revoke_calls  # the provider's revoke_consent was actually called

    with pytest.raises(ValidationAppError):
        await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)


async def test_trigger_sync_rejects_an_expired_consent(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase F6: consent_expires_at is checked independently of
    consent_status - a link whose provider-reported status is still
    "active" but whose expiry timestamp has already passed must be
    rejected the same way a revoked consent is, never silently synced
    against stale/expired authorization."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(consent_expires_at=datetime(2020, 1, 1, tzinfo=UTC))
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    with pytest.raises(ValidationAppError):
        await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)


async def test_trigger_sync_allows_a_consent_with_no_expiry_information(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A provider that reports no expiry at all (consent_expires_at=None)
    must never be treated as expired - only an actual past timestamp is."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(consent_expires_at=None)
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)

    assert run.status.value == "success"


async def test_user_cannot_access_another_users_linked_account(
    client: AsyncClient,
    auth_headers: dict,
    other_auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner_id = await _get_user_id(client, auth_headers)
    intruder_id = await _get_user_id(client, other_auth_headers)
    fake = _FakeSyncProvider()
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=owner_id)

    with pytest.raises(NotFoundError):
        await sync_service.get_linked_account(
            db_session, user_id=intruder_id, linked_account_id=linked.id
        )
    with pytest.raises(NotFoundError):
        await sync_service.trigger_sync(
            db_session, user_id=intruder_id, linked_account_id=linked.id
        )
    with pytest.raises(NotFoundError):
        await sync_service.revoke_link(db_session, user_id=intruder_id, linked_account_id=linked.id)


# --- sync pipeline -------------------------------------------------------------


async def test_trigger_sync_empty_provider_response(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(transactions=[])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status == SyncRunStatus.SUCCESS
    assert run.transactions_fetched == 0
    assert run.transactions_created == 0
    assert run.transactions_skipped_duplicate == 0
    assert run.error_message is None


async def test_trigger_sync_creates_transaction_through_existing_create_transaction_path(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(transactions=[_ext_txn()])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    before = await client.get(f"/api/v1/accounts/{linked.account_id}", headers=auth_headers)
    assert before.json()["data"]["balance_minor"] == 0

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status == SyncRunStatus.SUCCESS
    assert run.transactions_fetched == 1
    assert run.transactions_created == 1
    assert run.transactions_skipped_duplicate == 0

    after = await client.get(f"/api/v1/accounts/{linked.account_id}", headers=auth_headers)
    # An expense debits the account - the exact same balance effect a
    # manually-created transaction gets, applied by the existing
    # transaction_service._apply_balance_effect, never a second formula.
    assert after.json()["data"]["balance_minor"] == -39_900

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)]
    assert len(synced) == 1
    assert synced[0]["merchant"] == "Swiggy"
    assert synced[0]["category_id"] is not None  # high confidence - auto-categorized
    assert synced[0]["needs_review"] is False


async def test_trigger_sync_high_confidence_known_merchant_auto_posts_categorized(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(transactions=[_ext_txn(narration="UPI/DR/399/SWIGGY/paytm@ybl/Order")])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    categories = await client.get("/api/v1/categories", headers=auth_headers)
    food_id = next(c["id"] for c in categories.json()["data"] if c["name"] == "Food")

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == food_id
    assert synced["needs_review"] is False


async def test_trigger_sync_unknown_merchant_is_uncategorized_and_needs_review(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-unknown",
                narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None  # Uncategorized convention - never guessed
    assert synced["needs_review"] is True


async def test_trigger_sync_weak_keyword_match_is_low_confidence_needs_review(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A narration that matches the generic Food keyword list ("restaurant")
    but has no confidently recognized merchant identity must still be
    treated as LOW confidence - the keyword tier alone is never enough to
    auto-post a category (see sync_service._decide_confidence)."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-weak",
                narration="NEFT/DR/N999999999999/CORNER RESTAURANT PAYMENT",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_ai_categorization_gate_defaults_to_false(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    """UserSettings.ai_categorization_enabled defaults to False - a brand
    new user is opted out of background AI categorization until they
    explicitly turn it on (see app.models.user_settings)."""
    user_id = await _get_user_id(client, auth_headers)
    allowed = await sync_service._ai_categorization_enabled_for_user(db_session, user_id=user_id)
    assert allowed is False


async def test_ai_categorization_gate_true_after_user_opts_in(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )

    allowed = await sync_service._ai_categorization_enabled_for_user(db_session, user_id=user_id)
    assert allowed is True


async def test_ai_categorization_gate_is_isolated_per_user(
    client: AsyncClient,
    auth_headers: dict,
    other_auth_headers: dict,
    db_session: AsyncSession,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    other_user_id = await _get_user_id(client, other_auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )

    assert (
        await sync_service._ai_categorization_enabled_for_user(db_session, user_id=user_id)
    ) is True
    # The second user never opted in - their own gate must stay closed
    # regardless of the first user's setting.
    assert (
        await sync_service._ai_categorization_enabled_for_user(db_session, user_id=other_user_id)
    ) is False


async def test_categorize_reaches_ai_gate_only_after_tiers_1_to_3_miss(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The opt-in gate (_ai_categorization_enabled_for_user) is the seam a
    future AI classifier tier will be called behind - it must only be
    reached once USER_RULE, MERCHANT_MAP, and KEYWORD have all missed."""
    user_id = await _get_user_id(client, auth_headers)
    gate_calls: list[uuid.UUID] = []
    original_gate = sync_service._ai_categorization_enabled_for_user

    async def _spy_gate(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
        gate_calls.append(user_id)
        return await original_gate(db, user_id=user_id)

    monkeypatch.setattr(sync_service, "_ai_categorization_enabled_for_user", _spy_gate)

    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-gate-reached",
                narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert gate_calls == [user_id]  # reached exactly once, after every deterministic tier missed


async def test_categorize_skips_ai_gate_when_user_rule_matches(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    education_id = await _get_category_id(client, auth_headers, "Education")
    await merchant_rule_service.upsert_rule(
        db_session, user_id=user_id, raw_merchant="ABC EDUCATION", category_id=education_id
    )
    await db_session.commit()

    gate_calls: list[uuid.UUID] = []

    async def _spy_gate(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
        gate_calls.append(user_id)
        return False

    monkeypatch.setattr(sync_service, "_ai_categorization_enabled_for_user", _spy_gate)

    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-user-rule-hit",
                narration="UPI/DR/500/ABC EDUCATION PVT LTD/edu@icici/Fee Payment",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert gate_calls == []  # Tier 1 (USER_RULE) hit - the AI gate is never even checked


async def test_categorize_skips_ai_gate_when_merchant_map_matches(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    gate_calls: list[uuid.UUID] = []

    async def _spy_gate(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
        gate_calls.append(user_id)
        return False

    monkeypatch.setattr(sync_service, "_ai_categorization_enabled_for_user", _spy_gate)

    fake = _FakeSyncProvider(transactions=[_ext_txn(narration="UPI/DR/399/SWIGGY/paytm@ybl/Order")])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert gate_calls == []  # Tier 2 (MERCHANT_MAP) hit - the AI gate is never even checked


async def test_categorize_skips_ai_gate_when_keyword_matches(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    gate_calls: list[uuid.UUID] = []

    async def _spy_gate(db: AsyncSession, *, user_id: uuid.UUID) -> bool:
        gate_calls.append(user_id)
        return False

    monkeypatch.setattr(sync_service, "_ai_categorization_enabled_for_user", _spy_gate)

    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-keyword-hit",
                narration="NEFT/DR/N999999999999/CORNER RESTAURANT PAYMENT",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert gate_calls == []  # Tier 3 (KEYWORD) hit - the AI gate is never even checked


async def test_disabled_user_unknown_merchant_behavior_is_unchanged(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No AI classifier exists yet (Phase F). With ai_categorization_enabled
    left at its default False, an unknown merchant must behave exactly as
    it does today: Uncategorized + needs_review=True, never guessed at and
    never routed to any AI call."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-disabled-gate",
                narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_enabled_user_ai_with_no_category_stays_uncategorized_and_needs_review(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Phase F3: with ai_categorization_enabled=True and every deterministic
    tier missing, the AI tier is now genuinely reached - but a classifier
    that itself declines to classify (category_name=None) must produce
    exactly the same outcome as no tier matching at all: Uncategorized +
    needs_review=True, tier falls to NONE."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name=None)
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-enabled-gate",
                narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert len(fake_classifier.calls) == 1

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_enabled_user_known_merchant_still_auto_posts_via_merchant_map(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: enabling ai_categorization_enabled must not disturb the
    existing deterministic tiers - a recognized merchant still auto-posts
    via MERCHANT_MAP exactly as before, and the AI classifier (now genuinely
    wired in) is never even attempted, proven with a classifier that raises
    if it's ever called."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Transport")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(transactions=[_ext_txn(narration="UPI/DR/399/SWIGGY/paytm@ybl/Order")])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status.value == "success"
    assert fake_classifier.calls == []  # MERCHANT_MAP won - AI is never even attempted
    categories = await client.get("/api/v1/categories", headers=auth_headers)
    food_id = next(c["id"] for c in categories.json()["data"] if c["name"] == "Food")

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == food_id
    assert synced["needs_review"] is False


# --- Phase F3: AI_CLASSIFIER tier ------------------------------------------------------


async def test_ai_not_called_when_disabled_by_default(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 1 & 13: ai_categorization_enabled defaults to False - a fresh
    user's sync never invokes the classifier at all, even for a merchant no
    deterministic tier can resolve."""
    user_id = await _get_user_id(client, auth_headers)
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert fake_classifier.calls == []
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_ai_called_when_enabled_and_deterministic_tiers_all_miss(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 2 & 6: with the setting on and no deterministic tier matching,
    a valid AI classification IS applied - category set, needs_review
    still True (never fully trusted)."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Food", confidence=0.87)
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert len(fake_classifier.calls) == 1
    categories = await client.get("/api/v1/categories", headers=auth_headers)
    food_id = next(c["id"] for c in categories.json()["data"] if c["name"] == "Food")

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == food_id
    assert synced["needs_review"] is True  # AI is never treated as fully trusted


async def test_categorize_returns_ai_classifier_tier_for_a_valid_ai_category(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    """Direct unit-level check (bypassing the HTTP layer) that the returned
    tier enum is exactly CategorizationTier.AI_CLASSIFIER - the tier value
    itself isn't observable through the transactions API, so this is
    asserted directly against _categorize's return value."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    food_id = await _get_category_id(client, auth_headers, "Food")
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    normalized = normalize_merchant("UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")

    category_id, tier = await sync_service._categorize(
        db_session,
        user_id=user_id,
        classifier=fake_classifier,
        normalized=normalized,
        transaction_type="expense",
        amount_minor=50000,
        currency="INR",
        category_names=["Food", "Shopping"],
        category_id_by_name={"Food": food_id, "Shopping": food_id},
    )

    assert tier is sync_service.CategorizationTier.AI_CLASSIFIER
    assert category_id == food_id


async def test_user_rule_beats_ai_classifier_never_called(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 3: a USER_RULE hit means the classifier is never attempted,
    regardless of the AI opt-in setting."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    health_id = await _get_category_id(client, auth_headers, "Health")
    await merchant_rule_service.upsert_rule(
        db_session,
        user_id=user_id,
        raw_merchant="NEFT/DR/N999999999999/CORNER RESTAURANT PAYMENT",
        category_id=health_id,
    )
    await db_session.commit()
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-user-rule-beats-ai",
                narration="NEFT/DR/N999999999999/CORNER RESTAURANT PAYMENT",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert fake_classifier.calls == []
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == str(health_id)
    assert synced["needs_review"] is False


async def test_keyword_beats_ai_classifier_never_called(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 5: a KEYWORD hit means the classifier is never attempted - and,
    exactly like today, the KEYWORD suggestion itself is still discarded
    (category stays None, needs_review True), unaffected by AI being
    enabled."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Shopping")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-keyword-beats-ai",
                narration="NEFT/DR/N999999999999/CORNER RESTAURANT PAYMENT",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert fake_classifier.calls == []
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_ai_invalid_category_is_rejected_end_to_end(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 8: a classifier "claiming" a category outside the user's own
    list must never result in a fabricated category being stored - the
    transaction still proceeds, just without a category."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Not A Real Category")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.transactions_created == 1  # still ingested
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_categorize_rejects_a_category_even_if_the_classifier_itself_did_not(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    """Defense-in-depth: _categorize must not blindly trust
    result.category_name even from a (hypothetically buggy) classifier
    implementation that skipped its own allow-list validation - the
    membership re-check in _classify_with_ai is not the only thing
    standing between AI output and the ledger, but it must still work on
    its own."""

    class _BypassingClassifier:
        name = "bypassing"

        async def classify(
            self, request: MerchantClassificationRequest
        ) -> MerchantClassificationResult:
            # Deliberately skips validate_classification - simulates a
            # non-conformant implementation "claiming" a category outside
            # request.category_names.
            return MerchantClassificationResult(category_name="Totally Made Up", confidence=0.99)

    user_id = await _get_user_id(client, auth_headers)
    food_id = await _get_category_id(client, auth_headers, "Food")
    normalized = normalize_merchant("UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")

    category_id, tier = await sync_service._categorize(
        db_session,
        user_id=user_id,
        classifier=_BypassingClassifier(),
        normalized=normalized,
        transaction_type="expense",
        amount_minor=50000,
        currency="INR",
        category_names=["Food"],
        category_id_by_name={"Food": food_id},
    )

    assert category_id is None
    assert tier is sync_service.CategorizationTier.NONE


async def test_ai_raises_exception_ingestion_still_succeeds(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 9: a classifier that raises must never fail the SyncRun or block
    ingestion - the transaction is still created, just uncategorized."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(error=RuntimeError("simulated classifier crash"))
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status.value == "success"
    assert run.transactions_created == 1
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_ai_categorization_failure_log_contains_no_sensitive_data(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Phase F5 production-readiness check, at the sync-service boundary
    (complements the classifier-level equivalent in test_ai_classifier.py):
    the ai_categorization_failed warning logged by _classify_with_ai must
    carry only safe, structured metadata (user_id - expected, matching
    every other log line in this module - and the classifier's own safe
    `name` label) and must never include the merchant name, category
    names, or transaction amount anywhere in its text."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(error=RuntimeError("simulated classifier crash"))
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)
    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase",
                amount_minor=987654,
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    with caplog.at_level(logging.WARNING, logger="app.sync"):
        await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    failure_records = [r for r in caplog.records if r.message == "ai_categorization_failed"]
    assert len(failure_records) == 1
    record = failure_records[0]
    assert record.user_id == str(user_id)
    assert record.classifier == "fake"

    full_text = caplog.text
    assert "SOME RANDOM LOCAL SHOP" not in full_text
    assert "987654" not in full_text


async def test_ai_timeout_ingestion_still_succeeds(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 10: same fail-safe behavior for a timeout specifically."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(error=TimeoutError("simulated timeout"))
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status.value == "success"
    assert run.transactions_created == 1
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_ai_high_confidence_is_still_needs_review(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 11: even a 0.99-confidence AI classification is never treated as
    fully trusted - needs_review is always True for AI_CLASSIFIER."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Food", confidence=0.99)
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    categories = await client.get("/api/v1/categories", headers=auth_headers)
    food_id = next(c["id"] for c in categories.json()["data"] if c["name"] == "Food")
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == food_id
    assert synced["needs_review"] is True


async def test_ai_low_confidence_category_still_populated_and_needs_review(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 12: a low self-reported AI confidence doesn't block the category
    from being applied - the category/confidence-value distinction doesn't
    change whether category_id is populated, only that needs_review is
    always True for this tier either way."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Food", confidence=0.12)
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    categories = await client.get("/api/v1/categories", headers=auth_headers)
    food_id = next(c["id"] for c in categories.json()["data"] if c["name"] == "Food")
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == food_id
    assert synced["needs_review"] is True


async def test_ai_classifier_request_contains_only_allowed_fields(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 15, 16 & 17: the exact request sent to the classifier carries
    only merchant/transaction_type/amount_minor/currency/category_names -
    the normalized merchant, never the raw narration - and structurally
    has no field for a user/account/provider identifier at all."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    raw_narration = "UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase"
    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(narration=raw_narration, amount_minor=123456, direction="debit")
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert len(fake_classifier.calls) == 1
    request = fake_classifier.calls[0]

    # Exactly the allowed fields - nothing else on the model at all.
    assert set(type(request).model_fields) == {
        "merchant",
        "transaction_type",
        "amount_minor",
        "currency",
        "category_names",
    }
    assert request.transaction_type == "expense"
    assert request.amount_minor == 123456
    assert request.currency == "INR"
    assert isinstance(request.category_names, tuple)
    assert "Food" in request.category_names

    # The normalized merchant, never the raw provider narration.
    assert request.merchant != raw_narration
    assert "UPI" not in request.merchant
    assert "xyz@upi" not in request.merchant

    # No user/account/provider identifier of any kind is even possible -
    # the model has no such field to check a value against.
    for forbidden_attr in (
        "user_id",
        "account_id",
        "linked_account_id",
        "external_transaction_id",
        "consent_id",
        "narration",
    ):
        assert not hasattr(request, forbidden_attr)


async def test_ai_classification_never_duplicates_or_bypasses_transaction_creation(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """req 18: the classifier cannot write to the database - it has no
    session and no way to. This proves the ONLY effect an AI classification
    has is on the single transaction create_transaction already writes -
    exactly one transaction row results, never zero, never two."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    before = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    before_count = len(before.json()["data"])

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    after = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    after_count = len(after.json()["data"])

    assert run.transactions_created == 1
    assert after_count - before_count == 1


def test_sync_service_module_has_no_forbidden_names_anywhere() -> None:
    """req 19: extends test_sync_service_has_no_forbidden_public_functions'
    check to EVERY name defined in the module (including the new private
    _classify_with_ai/_categorize helpers), via ast parsing of the source
    itself rather than runtime introspection - confirms Phase F3 introduced
    no payment/transfer/withdrawal-shaped identifier anywhere."""
    tree = ast.parse(Path(inspect.getfile(sync_service)).read_text(encoding="utf-8"))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.add(node.name)
    _assert_no_forbidden_names(names)


# --- Phase F4: hardening / regression coverage ------------------------------------------
#
# Note on concurrency (Test Area 12): AI classification introduces no NEW concurrency
# surface beyond what already existed pre-Phase-F - _classify_with_ai never writes
# anything itself, and the existing idempotency backstop
# (test_idempotency_race_hits_db_backstop_without_error, unmodified by Phase F3/F4) is
# what actually protects a real concurrent-sync race, exactly as it did before AI
# existed. A true multi-request concurrency test would require simulating two
# overlapping trigger_sync calls against the same database session/connection, which
# this test suite's fixtures don't support without a larger harness change - out of
# scope for this hardening phase per its own instructions. The tests below instead
# cover the AI-specific idempotency questions that ARE practical here: does a normal
# sequential re-sync ever duplicate a transaction or re-invoke the classifier, and does
# a classifier failure on the first sync still get idempotently skipped on the second.


async def test_sync_still_succeeds_when_ai_disabled(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Area 1.2: with ai_categorization_enabled left at its default
    False, the sync run itself completes successfully (not just "the
    transaction happens to look right") - the classifier is a no-op, never
    a source of run-level failure."""
    user_id = await _get_user_id(client, auth_headers)
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)
    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status.value == "success"
    assert run.transactions_created == 1
    assert fake_classifier.calls == []


async def test_ai_enabled_for_one_user_never_affects_another_users_sync(
    client: AsyncClient,
    auth_headers: dict,
    other_auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Area 1.5, at the full sync level (not just the settings-only or
    gate-only checks F0 already has): user A opts in, user B never does -
    syncing user B's own linked account must never reach the classifier,
    regardless of what user A did."""
    user_a = await _get_user_id(client, auth_headers)
    user_b = await _get_user_id(client, other_auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)

    unmatched = "UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase"
    fake_a = _FakeSyncProvider(transactions=[_ext_txn(narration=unmatched)])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake_a)
    linked_a = await _link(db_session, user_id=user_a)
    await sync_service.trigger_sync(db_session, user_id=user_a, linked_account_id=linked_a.id)
    await db_session.commit()
    assert len(fake_classifier.calls) == 1  # user A: opted in, reached AI

    fake_b = _FakeSyncProvider(
        transactions=[_ext_txn(external_transaction_id="ext-user-b", narration=unmatched)]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake_b)
    linked_b = await _link(db_session, user_id=user_b)
    await sync_service.trigger_sync(db_session, user_id=user_b, linked_account_id=linked_b.id)
    await db_session.commit()

    assert len(fake_classifier.calls) == 1  # unchanged - user B never opted in
    transactions = await client.get("/api/v1/transactions?limit=50", headers=other_auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked_b.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_ai_gate_reflects_a_setting_change_between_two_syncs(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Area 1.6: the setting is read fresh on every sync run, never
    cached from a previous one - enabling, syncing, then disabling and
    syncing again must visibly change whether the classifier is reached,
    within the SAME process/test, with no restart in between."""
    user_id = await _get_user_id(client, auth_headers)
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)
    unmatched = "UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase"

    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake = _FakeSyncProvider(
        transactions=[_ext_txn(external_transaction_id="ext-1", narration=unmatched)]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)
    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()
    assert len(fake_classifier.calls) == 1

    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": False}
    )
    fake.transactions = [_ext_txn(external_transaction_id="ext-2", narration=unmatched)]
    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()
    assert len(fake_classifier.calls) == 1  # unchanged - disabled before this second sync


async def test_categorize_fails_closed_when_the_category_list_is_empty(
    client: AsyncClient, auth_headers: dict, db_session: AsyncSession
) -> None:
    """Test Area 4/7: "if category names cannot be loaded safely, AI
    classification must fail closed" - an empty category_names list can
    never reach the classifier at all (MerchantClassificationRequest
    itself requires at least one - see app.ai.classifier.base), and that
    failure is caught the same way any other classifier-boundary failure
    is, falling to NONE rather than propagating."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    normalized = normalize_merchant("UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")

    category_id, tier = await sync_service._categorize(
        db_session,
        user_id=user_id,
        classifier=fake_classifier,
        normalized=normalized,
        transaction_type="expense",
        amount_minor=50000,
        currency="INR",
        category_names=[],
        category_id_by_name={},
    )

    assert category_id is None
    assert tier is sync_service.CategorizationTier.NONE
    assert fake_classifier.calls == []  # never even reached the classifier


@pytest.mark.parametrize("ai_confidence", [0.99, 0.50, 0.01])
async def test_ai_needs_review_is_always_true_regardless_of_confidence_value(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
    ai_confidence: float,
) -> None:
    """Test Area 3: the AI's own numeric confidence - high, middling, or
    barely above zero - must never automatically approve/post the
    transaction. needs_review is always True for AI_CLASSIFIER; only the
    presence of a valid category_name, never the confidence value, decides
    whether category_id is populated."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Food", confidence=ai_confidence)
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)
    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    categories = await client.get("/api/v1/categories", headers=auth_headers)
    food_id = next(c["id"] for c in categories.json()["data"] if c["name"] == "Food")
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == food_id
    assert synced["needs_review"] is True


async def test_ai_category_case_mismatch_is_rejected_end_to_end(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Area 7: a classifier "claiming" a category that differs from
    the user's own only by case ("food" vs "Food") must be rejected exactly
    like any other unrecognized category - never treated as a fuzzy match."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="food")  # lowercase - not "Food"
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)
    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_ai_duplicate_sync_creates_exactly_one_transaction_and_calls_ai_once(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Area 5: re-syncing the same external transaction must not
    duplicate it, and - since the idempotency check happens BEFORE
    categorization in _ingest_one - the classifier must only ever be
    invoked once, on the first sync, never again on the duplicate-skipped
    second run."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    fake_classifier = _FakeMerchantClassifier(category_name="Food")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier)
    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    first_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()
    second_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()

    assert first_run.transactions_created == 1
    assert second_run.transactions_created == 0
    assert second_run.transactions_skipped_duplicate == 1
    assert len(fake_classifier.calls) == 1  # never re-invoked for the duplicate-skipped retry

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)]
    assert len(synced) == 1


async def test_ai_failure_then_successful_resync_does_not_duplicate(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Area 5: a classifier failure on the first sync (transaction
    still created, just uncategorized) must not prevent the SAME external
    transaction from being correctly recognized as a duplicate on a later
    re-sync - the idempotency key is derived from the provider's own
    transaction identity, never from whatever AI did or didn't do."""
    user_id = await _get_user_id(client, auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    failing_classifier = _FakeMerchantClassifier(error=RuntimeError("simulated crash"))
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: failing_classifier)
    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    first_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()
    assert first_run.transactions_created == 1

    # A later sync, even with a now-working classifier, must still treat
    # the same external transaction as a duplicate - never re-created.
    working_classifier = _FakeMerchantClassifier(category_name="Food")
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: working_classifier)
    second_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()

    assert second_run.transactions_created == 0
    assert second_run.transactions_skipped_duplicate == 1
    assert working_classifier.calls == []  # the dedup check ran first - AI never reached

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)]
    assert len(synced) == 1
    assert synced[0]["category_id"] is None  # still whatever the FIRST (failed) sync produced


async def test_ai_classifier_receives_only_the_syncing_users_own_category_names(
    client: AsyncClient,
    auth_headers: dict,
    other_auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Area 8: each user has their own distinct custom category - the
    classifier request built for user A's sync must contain only user A's
    own category names, never user B's, and vice versa."""
    user_a = await _get_user_id(client, auth_headers)
    user_b = await _get_user_id(client, other_auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    await client.patch(
        "/api/v1/settings", headers=other_auth_headers, json={"ai_categorization_enabled": True}
    )
    await client.post(
        "/api/v1/categories",
        headers=auth_headers,
        json={"name": "Users A Only Category", "icon": "star", "color": "#F59E0B"},
    )
    await client.post(
        "/api/v1/categories",
        headers=other_auth_headers,
        json={"name": "Users B Only Category", "icon": "star", "color": "#F59E0B"},
    )

    unmatched = "UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase"
    fake_classifier_a = _FakeMerchantClassifier(category_name=None)
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier_a)
    fake_a = _FakeSyncProvider(transactions=[_ext_txn(narration=unmatched)])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake_a)
    linked_a = await _link(db_session, user_id=user_a)
    await sync_service.trigger_sync(db_session, user_id=user_a, linked_account_id=linked_a.id)
    await db_session.commit()

    assert len(fake_classifier_a.calls) == 1
    category_names_seen_by_a = fake_classifier_a.calls[0].category_names
    assert "Users A Only Category" in category_names_seen_by_a
    assert "Users B Only Category" not in category_names_seen_by_a

    fake_classifier_b = _FakeMerchantClassifier(category_name=None)
    monkeypatch.setattr(sync_service, "get_merchant_classifier", lambda: fake_classifier_b)
    fake_b = _FakeSyncProvider(
        transactions=[_ext_txn(external_transaction_id="ext-user-b", narration=unmatched)]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake_b)
    linked_b = await _link(db_session, user_id=user_b)
    await sync_service.trigger_sync(db_session, user_id=user_b, linked_account_id=linked_b.id)
    await db_session.commit()

    assert len(fake_classifier_b.calls) == 1
    category_names_seen_by_b = fake_classifier_b.calls[0].category_names
    assert "Users B Only Category" in category_names_seen_by_b
    assert "Users A Only Category" not in category_names_seen_by_b


async def test_ai_classification_cannot_assign_another_users_category_id(
    client: AsyncClient,
    auth_headers: dict,
    other_auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Test Area 8: both users independently create their OWN custom
    category with the identical name ("Duplicate Name Category" - the
    per-user uniqueness index on (user_id, name) only prevents a
    collision within the same user, so two different users can each have
    their own row with this same name). An AI classification of that name
    for each user must resolve to THAT user's own category id, never
    accidentally the other user's, even though the name collides -
    category_id_by_name is built fresh per sync from only that user's own
    visible categories (see trigger_sync)."""
    user_a = await _get_user_id(client, auth_headers)
    user_b = await _get_user_id(client, other_auth_headers)
    await client.patch(
        "/api/v1/settings", headers=auth_headers, json={"ai_categorization_enabled": True}
    )
    await client.patch(
        "/api/v1/settings", headers=other_auth_headers, json={"ai_categorization_enabled": True}
    )
    category_body = {"name": "Duplicate Name Category", "icon": "star", "color": "#F59E0B"}
    create_a = await client.post("/api/v1/categories", headers=auth_headers, json=category_body)
    create_b = await client.post(
        "/api/v1/categories", headers=other_auth_headers, json=category_body
    )
    food_id_a = create_a.json()["data"]["id"]
    food_id_b = create_b.json()["data"]["id"]
    assert food_id_a != food_id_b  # each user has their OWN row, despite the identical name

    unmatched = "UPI/DR/700/SOME RANDOM LOCAL SHOP/xyz@upi/Purchase"
    monkeypatch.setattr(
        sync_service,
        "get_merchant_classifier",
        lambda: _FakeMerchantClassifier(category_name="Duplicate Name Category"),
    )
    fake_a = _FakeSyncProvider(transactions=[_ext_txn(narration=unmatched)])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake_a)
    linked_a = await _link(db_session, user_id=user_a)
    await sync_service.trigger_sync(db_session, user_id=user_a, linked_account_id=linked_a.id)
    await db_session.commit()

    fake_b = _FakeSyncProvider(
        transactions=[_ext_txn(external_transaction_id="ext-user-b", narration=unmatched)]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake_b)
    linked_b = await _link(db_session, user_id=user_b)
    await sync_service.trigger_sync(db_session, user_id=user_b, linked_account_id=linked_b.id)
    await db_session.commit()

    transactions_a = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced_a = next(
        t for t in transactions_a.json()["data"] if t["linked_account_id"] == str(linked_a.id)
    )
    transactions_b = await client.get("/api/v1/transactions?limit=50", headers=other_auth_headers)
    synced_b = next(
        t for t in transactions_b.json()["data"] if t["linked_account_id"] == str(linked_b.id)
    )
    assert synced_a["category_id"] == food_id_a
    assert synced_b["category_id"] == food_id_b


async def test_trigger_sync_preserves_raw_narration_as_description(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    narration = "UPI/DR/399/SWIGGY/paytm@ybl/Swiggy Order"
    fake = _FakeSyncProvider(transactions=[_ext_txn(narration=narration)])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["description"] == narration


async def test_duplicate_sync_creates_zero_duplicate_transactions(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(transactions=[_ext_txn(), _ext_txn(external_transaction_id="ext-2")])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    first_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()
    assert first_run.transactions_created == 2
    assert first_run.transactions_skipped_duplicate == 0

    second_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()
    assert second_run.transactions_created == 0
    assert second_run.transactions_skipped_duplicate == 2

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)]
    assert len(synced) == 2  # never 4


async def test_idempotency_race_hits_db_backstop_without_error(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Mirrors test_recurring_transactions.py's
    test_concurrent_generate_hits_db_backstop_without_500: calling
    transaction_service.create_transaction directly twice with the exact
    same sync idempotency_key reproduces a concurrent-sync race
    deterministically against the real unique constraint, without needing
    actual thread timing."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider()
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    idempotency_key = f"sync:{linked.id}:race-ext-1"
    data = TransactionCreate(
        account_id=linked.account_id,
        type="expense",
        amount_minor=10_000,
        occurred_at=datetime(2026, 9, 1, tzinfo=UTC),
    )

    first = await transaction_service.create_transaction(
        db_session,
        user_id=user_id,
        data=data,
        idempotency_key=idempotency_key,
        linked_account_id=linked.id,
        external_transaction_id="race-ext-1",
    )
    await db_session.commit()

    second = await transaction_service.create_transaction(
        db_session,
        user_id=user_id,
        data=data,
        idempotency_key=idempotency_key,
        linked_account_id=linked.id,
        external_transaction_id="race-ext-1",
    )
    await db_session.commit()

    assert second.id == first.id

    matching = await TransactionRepository(db_session).get_by_idempotency_key(
        user_id, idempotency_key
    )
    assert matching is not None
    assert matching.id == first.id


async def test_trigger_sync_provider_failure_records_failed_run_and_creates_nothing(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(list_transactions_error=RuntimeError("provider unreachable"))
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status == SyncRunStatus.FAILED
    assert run.transactions_created == 0
    assert run.error_message is not None

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)]
    assert synced == []


async def test_trigger_sync_provider_failure_never_touches_existing_transactions(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(transactions=[_ext_txn()])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    good_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()
    assert good_run.transactions_created == 1

    fake.list_transactions_error = RuntimeError("provider down now")
    failed_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()
    assert failed_run.status == SyncRunStatus.FAILED

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)]
    assert len(synced) == 1  # the earlier successful import is untouched


async def test_trigger_sync_partial_failure_keeps_successful_imports(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    valid = _ext_txn(external_transaction_id="ext-valid")
    invalid = _ext_txn(external_transaction_id="ext-invalid", amount_minor=0)  # fails validation
    fake = _FakeSyncProvider(transactions=[valid, invalid])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status == SyncRunStatus.PARTIAL
    assert run.transactions_fetched == 2
    assert run.transactions_created == 1
    assert run.error_message is not None

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)]
    assert len(synced) == 1


async def test_trigger_sync_all_invalid_is_fully_failed(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(external_transaction_id="ext-bad-amount", amount_minor=0),
            _ext_txn(external_transaction_id="ext-bad-direction", direction="hold"),
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status == SyncRunStatus.FAILED
    assert run.transactions_created == 0


async def test_trigger_sync_rejects_transaction_from_a_different_external_account(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Defensive provider-data validation: a transaction claiming a
    different external_account_id than the linked account itself must
    never be imported, even if a misbehaving provider returns one."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(transactions=[_ext_txn(external_account_id="not-the-linked-account")])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.transactions_created == 0
    assert run.status == SyncRunStatus.FAILED


# --- SyncRun bookkeeping ---------------------------------------------------------


async def test_sync_run_counters_and_timestamps(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(transactions=[_ext_txn(), _ext_txn(external_transaction_id="ext-2")])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.linked_account_id == linked.id
    assert run.started_at is not None
    assert run.completed_at is not None
    assert run.completed_at >= run.started_at
    assert run.transactions_fetched == 2
    assert run.transactions_created == 2
    assert run.transactions_skipped_duplicate == 0


# --- security ----------------------------------------------------------------

_FORBIDDEN_SUBSTRINGS = (
    "pin",
    "cvv",
    "otp",
    "password",
    "transfer",
    "withdraw",
    "debit_auth",
    "payment_auth",
    "send_money",
)


_FORBIDDEN_PATTERN = re.compile(
    "|".join(
        # Short, common-substring-risk terms ("pin") need letter-boundary
        # matching so an innocent identifier like
        # `update_linked_account_mapping` ("map-PIN-g") never false-positives;
        # the longer, distinctive phrases keep plain substring matching so a
        # real field like `payment_authorization_token` still matches
        # "payment_auth" as a prefix.
        rf"(?<![a-z]){re.escape(term)}(?![a-z])" if len(term) <= 3 else re.escape(term)
        for term in _FORBIDDEN_SUBSTRINGS
    )
)


def _assert_no_forbidden_names(names: set[str]) -> None:
    for name in names:
        match = _FORBIDDEN_PATTERN.search(name.lower())
        assert match is None, f"forbidden name found: {name!r}"


def test_sync_service_has_no_forbidden_public_functions() -> None:
    public_functions = {
        name
        for name, member in inspect.getmembers(sync_service, inspect.isfunction)
        if not name.startswith("_")
    }
    assert "initiate_link" in public_functions
    assert "trigger_sync" in public_functions
    _assert_no_forbidden_names(public_functions)


def test_linked_account_model_has_no_forbidden_columns() -> None:
    columns = {c.key for c in sa_inspect(LinkedAccount).columns}
    _assert_no_forbidden_names(columns)


def test_sync_run_model_has_no_forbidden_columns() -> None:
    columns = {c.key for c in sa_inspect(SyncRun).columns}
    _assert_no_forbidden_names(columns)


def test_linked_account_read_schema_has_no_forbidden_fields() -> None:
    _assert_no_forbidden_names(set(LinkedAccountRead.model_fields))


def test_transaction_create_schema_rejects_sync_provenance_fields() -> None:
    """A client must never be able to forge needs_review=False or a
    linked_account_id/external_transaction_id through the public API - only
    app.services.sync_service ever sets them, via
    transaction_service.create_transaction's own keyword-only arguments."""
    with pytest.raises(PydanticValidationError):
        TransactionCreate(
            account_id=uuid.uuid4(),
            type="expense",
            amount_minor=100,
            needs_review=False,  # type: ignore[call-arg]
        )
    with pytest.raises(PydanticValidationError):
        TransactionCreate(
            account_id=uuid.uuid4(),
            type="expense",
            amount_minor=100,
            linked_account_id=uuid.uuid4(),  # type: ignore[call-arg]
        )


async def test_sync_never_classifies_two_transactions_as_a_transfer(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A debit on one synced account and a credit on another must each be
    imported as an ordinary expense/income - sync_service has no transfer-
    matching logic at all, and TransactionCreate's own account_id (never
    transfer_account_id) is all _ingest_one ever sets."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(external_transaction_id="ext-debit", direction="debit"),
            _ext_txn(
                external_transaction_id="ext-credit",
                direction="credit",
                narration="IMPS/CR/987654321098/SALARY ACME CORP",
            ),
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = [t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)]
    assert len(synced) == 2
    assert all(t["type"] != "transfer" for t in synced)
    assert all(t["transfer_account_id"] is None for t in synced)


# --- Phase E: user merchant rule categorization ------------------------------


async def test_user_rule_overrides_known_merchant_mapping(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Swiggy normally resolves to Food via the curated merchant map (see
    app.services.keyword_categorization) - a user rule for the exact same
    merchant must win instead."""
    user_id = await _get_user_id(client, auth_headers)
    shopping_id = await _get_category_id(client, auth_headers, "Shopping")
    await merchant_rule_service.upsert_rule(
        db_session, user_id=user_id, raw_merchant="Swiggy", category_id=shopping_id
    )
    await db_session.commit()

    fake = _FakeSyncProvider(transactions=[_ext_txn(narration="UPI/DR/399/SWIGGY/paytm@ybl/Order")])
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == str(shopping_id)  # not Food - the user rule wins
    assert synced["needs_review"] is False


async def test_user_rule_overrides_keyword_categorization(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ "CORNER RESTAURANT" matches the generic "Food" keyword (a weak,
    low-confidence signal on its own - see
    test_trigger_sync_weak_keyword_match_is_low_confidence_needs_review). A
    user rule for the same normalized merchant must override it."""
    user_id = await _get_user_id(client, auth_headers)
    health_id = await _get_category_id(client, auth_headers, "Health")
    # The narration's fallback-normalized merchant is "Corner Restaurant
    # Payment" - the rule must target that exact canonical key to match.
    await merchant_rule_service.upsert_rule(
        db_session,
        user_id=user_id,
        raw_merchant="NEFT/DR/N999999999999/CORNER RESTAURANT PAYMENT",
        category_id=health_id,
    )
    await db_session.commit()

    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-weak",
                narration="NEFT/DR/N999999999999/CORNER RESTAURANT PAYMENT",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == str(health_id)  # not Food (keyword) - the user rule wins
    assert synced["needs_review"] is False


async def test_user_rule_is_high_confidence_even_for_an_unrecognized_merchant(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The exact scenario from the phase spec: "ABC EDUCATION" is not in
    the curated alias list (normalize_merchant's own `recognized` flag is
    False for it), so a plain merchant-map/keyword match would never be
    high confidence - but a user rule must still auto-post, never sit in
    needs_review waiting for a signal the built-in list will never give it."""
    user_id = await _get_user_id(client, auth_headers)
    education_id = await _get_category_id(client, auth_headers, "Education")
    await merchant_rule_service.upsert_rule(
        db_session,
        user_id=user_id,
        raw_merchant="ABC EDUCATION",
        category_id=education_id,
    )
    await db_session.commit()

    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-abc-edu",
                narration="UPI/DR/500/ABC EDUCATION PVT LTD/edu@icici/Fee Payment",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status.value == "success"
    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] == str(education_id)
    assert synced["needs_review"] is False
    assert synced["merchant"] == "Abc Education"


async def test_unknown_merchant_without_a_rule_still_needs_review(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression: existing needs_review behavior for a merchant with no
    user rule, no merchant-map hit, and no keyword hit must be unchanged."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(
        transactions=[
            _ext_txn(
                external_transaction_id="ext-unknown-2",
                narration="UPI/DR/700/TOTALLY UNKNOWN VENDOR/xyz@upi/Purchase",
            )
        ]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = next(
        t for t in transactions.json()["data"] if t["linked_account_id"] == str(linked.id)
    )
    assert synced["category_id"] is None
    assert synced["needs_review"] is True


async def test_different_users_have_independent_rules_for_the_same_merchant_in_sync(
    client: AsyncClient,
    auth_headers: dict,
    other_auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    user_id = await _get_user_id(client, auth_headers)
    other_user_id = await _get_user_id(client, other_auth_headers)
    education_id = await _get_category_id(client, auth_headers, "Education")
    other_health_id = await _get_category_id(client, other_auth_headers, "Health")

    await merchant_rule_service.upsert_rule(
        db_session, user_id=user_id, raw_merchant="ABC EDUCATION", category_id=education_id
    )
    await merchant_rule_service.upsert_rule(
        db_session, user_id=other_user_id, raw_merchant="ABC EDUCATION", category_id=other_health_id
    )
    await db_session.commit()

    fake = _FakeSyncProvider(
        transactions=[_ext_txn(narration="UPI/DR/500/ABC EDUCATION/edu@icici/Fee")]
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)

    my_linked = await _link(db_session, user_id=user_id)
    await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=my_linked.id)
    await db_session.commit()

    # Sharing the same fake external_account_id across both users' links is
    # fine - each LinkedAccount row is still distinguished by its own
    # consent_id (derived from the per-user consent_handle), and every
    # query here is scoped by user_id regardless.
    their_linked = await _link(db_session, user_id=other_user_id)
    await sync_service.trigger_sync(
        db_session, user_id=other_user_id, linked_account_id=their_linked.id
    )
    await db_session.commit()

    my_transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    my_synced = next(
        t for t in my_transactions.json()["data"] if t["linked_account_id"] == str(my_linked.id)
    )
    assert my_synced["category_id"] == str(education_id)

    their_transactions = await client.get(
        "/api/v1/transactions?limit=50", headers=other_auth_headers
    )
    their_synced = next(
        t
        for t in their_transactions.json()["data"]
        if t["linked_account_id"] == str(their_linked.id)
    )
    assert their_synced["category_id"] == str(other_health_id)


# --- Phase F9: end-to-end sandbox sync validation ----------------------------------------
#
# IMPORTANT: every transaction below is a LOCAL, DETERMINISTIC TEST FIXTURE, shaped to look
# like a plausible Setu Account Aggregator sandbox response (Indian UPI/NEFT bank-statement
# narrations, matching MockSyncProvider's own existing convention) - it is never real
# customer data, and it is never the product of an actual network call to Setu or any other
# provider. This section proves the EXISTING sync_service pipeline correctly ingests
# Setu-shaped data end to end; it does NOT test real Setu sandbox connectivity, which
# app.sync.provider.setu_sandbox.SetuSandboxSyncProvider does not implement (see that
# module's own docstring and SYNC_PROVIDER.md §9). `_FakeSyncProvider` (defined earlier in
# this file) is the same reusable, Protocol-conformant test double already used throughout
# this suite - just configured here with Setu-sandbox-shaped fixture data instead of the
# generic defaults.

_SETU_SANDBOX_FIXTURE_ACCOUNT_ID = "setu-sandbox-fixture-acc-001"


def _setu_sandbox_fixture_transactions() -> list[ExternalTransaction]:
    """Deterministic local test fixture only - see the section docstring
    above. Covers: a known merchant on each direction (SWIGGY/expense,
    UBER/expense - both in the curated merchant-alias list, so both prove
    the existing MERCHANT_MAP tier still auto-posts unchanged), an unknown-
    merchant income credit (proves the existing "never guess" NONE-tier
    behavior on a direction other than expense), a same-batch duplicate
    external_transaction_id, and a malformed entry (amount_minor=0, fails
    TransactionCreate's own positive-amount validation)."""
    return [
        ExternalTransaction(
            external_transaction_id="setu-fixture-txn-001",
            external_account_id=_SETU_SANDBOX_FIXTURE_ACCOUNT_ID,
            occurred_on=date(2026, 9, 2),
            amount_minor=45_000,
            direction="debit",
            narration="UPI/DR/450/SWIGGY/swiggy@icici/Food Order",
        ),
        ExternalTransaction(
            external_transaction_id="setu-fixture-txn-002",
            external_account_id=_SETU_SANDBOX_FIXTURE_ACCOUNT_ID,
            occurred_on=date(2026, 9, 3),
            amount_minor=18_000,
            direction="debit",
            narration="UPI/DR/180/UBER/uber@hdfcbank/Cab Ride",
        ),
        # Same external_transaction_id as the UBER entry above, repeated
        # WITHIN this same fetched batch - proves the idempotency dedup
        # check also protects a single sync run's own response, not only
        # two separate trigger_sync calls (see test below).
        ExternalTransaction(
            external_transaction_id="setu-fixture-txn-002",
            external_account_id=_SETU_SANDBOX_FIXTURE_ACCOUNT_ID,
            occurred_on=date(2026, 9, 3),
            amount_minor=18_000,
            direction="debit",
            narration="UPI/DR/180/UBER/uber@hdfcbank/Cab Ride",
        ),
        ExternalTransaction(
            external_transaction_id="setu-fixture-txn-003",
            external_account_id=_SETU_SANDBOX_FIXTURE_ACCOUNT_ID,
            occurred_on=date(2026, 9, 5),
            amount_minor=7_200_000,
            direction="credit",
            narration="NEFT/CR/N556677889900/SALARY EXAMPLE TECH PVT LTD",
        ),
        # Malformed: amount_minor=0 fails TransactionCreate's `gt=0`
        # constraint - proves one bad fixture entry never blocks the rest
        # of the batch (_IngestOutcome.FAILED for this one row only).
        ExternalTransaction(
            external_transaction_id="setu-fixture-txn-004-malformed",
            external_account_id=_SETU_SANDBOX_FIXTURE_ACCOUNT_ID,
            occurred_on=date(2026, 9, 6),
            amount_minor=0,
            direction="debit",
            narration="UPI/DR/0/MALFORMED TEST ENTRY",
        ),
    ]


async def test_setu_sandbox_shaped_fixture_end_to_end_flow(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Walks the full link -> complete -> linked account -> sync ->
    ingestion -> sync history flow using local Setu-sandbox-SHAPED
    deterministic fixture data (see the section docstring - never real
    Setu connectivity), proving every existing pipeline stage - dedup,
    deterministic categorization, ledger write path, SyncRun bookkeeping,
    linked-account metadata, revoke-blocks-future-sync, and
    revoke-preserves-history - already handles this data shape correctly
    with zero changes to production code."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(
        name="fake-setu-sandbox-fixture",
        institution_name="Setu Sandbox Fixture Bank",
        external_account_id=_SETU_SANDBOX_FIXTURE_ACCOUNT_ID,
        masked_account_ref="XX7788",
        transactions=_setu_sandbox_fixture_transactions(),
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)

    # 1. Initiate link.
    initiation = await sync_service.initiate_link(db_session, user_id=user_id)
    await db_session.commit()
    assert initiation.provider == "fake-setu-sandbox-fixture"
    assert initiation.consent_handle

    # 2. Complete link.
    linked_accounts = await sync_service.complete_link(
        db_session, user_id=user_id, consent_handle=initiation.consent_handle
    )
    await db_session.commit()
    assert len(linked_accounts) == 1
    linked = linked_accounts[0]
    assert linked.consent_status == SyncConsentStatus.ACTIVE
    assert linked.account_id is not None  # auto-mapped, never left pending

    # 3. Obtain linked account.
    fetched = await sync_service.get_linked_account(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    assert fetched.id == linked.id
    assert fetched.masked_account_ref == "XX7788"

    # 4-5. Trigger sync; provider transactions are retrieved.
    first_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()
    assert first_run.transactions_fetched == 5  # the raw fixture batch, duplicate included

    # 6. Transactions pass through existing normalization/categorization -
    # known merchants (SWIGGY, UBER) auto-post via the unchanged MERCHANT_MAP
    # tier; the unknown-merchant salary credit is left Uncategorized/
    # needs_review, exactly as it would be for any other provider.
    categories = await client.get("/api/v1/categories", headers=auth_headers)
    food_id = next(c["id"] for c in categories.json()["data"] if c["name"] == "Food")
    transport_id = next(c["id"] for c in categories.json()["data"] if c["name"] == "Transport")

    transactions = await client.get("/api/v1/transactions?limit=50", headers=auth_headers)
    synced = {
        t["merchant"]: t
        for t in transactions.json()["data"]
        if t["linked_account_id"] == str(linked.id)
    }
    assert synced["Swiggy"]["category_id"] == food_id
    assert synced["Swiggy"]["needs_review"] is False
    assert synced["Uber"]["category_id"] == transport_id
    assert synced["Uber"]["needs_review"] is False
    salary_txn = next(t for t in synced.values() if t["type"] == "income")
    assert salary_txn["category_id"] is None
    assert salary_txn["needs_review"] is True

    # 7-8. Created through the existing ledger path; SyncRun counters correct -
    # 3 unique valid transactions created (Swiggy, Uber, salary), the
    # in-batch UBER duplicate skipped, the malformed entry neither created
    # nor counted as created/skipped.
    assert first_run.transactions_created == 3
    assert first_run.transactions_skipped_duplicate == 1
    assert first_run.status.value == "partial"  # 1 malformed entry, but others succeeded
    assert len(synced) == 3

    # 9. Linked account sync metadata updated.
    refreshed = await sync_service.get_linked_account(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    assert refreshed.last_synced_at is not None
    assert refreshed.last_sync_status == "partial"

    # 10. Re-running the same sync does not duplicate transactions.
    second_run = await sync_service.trigger_sync(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()
    assert second_run.transactions_created == 0
    assert second_run.transactions_skipped_duplicate == 4  # every previously-created row
    transactions_after_resync = await client.get(
        "/api/v1/transactions?limit=50", headers=auth_headers
    )
    assert (
        len([
            t
            for t in transactions_after_resync.json()["data"]
            if t["linked_account_id"] == str(linked.id)
        ])
        == 3  # still exactly 3 - never duplicated
    )

    # 11. Revoke consent prevents subsequent sync.
    revoked = await sync_service.revoke_link(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    await db_session.commit()
    assert revoked.consent_status == SyncConsentStatus.REVOKED
    with pytest.raises(ValidationAppError):
        await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)

    # 12. Transactions already imported remain preserved after revoke.
    transactions_after_revoke = await client.get(
        "/api/v1/transactions?limit=50", headers=auth_headers
    )
    assert (
        len([
            t
            for t in transactions_after_revoke.json()["data"]
            if t["linked_account_id"] == str(linked.id)
        ])
        == 3
    )

    # Sync history itself is preserved and lists both runs.
    runs = await sync_service.list_sync_runs(
        db_session, user_id=user_id, linked_account_id=linked.id
    )
    assert len(runs) == 2


async def test_setu_sandbox_shaped_fixture_empty_response_is_handled_safely(
    client: AsyncClient,
    auth_headers: dict,
    db_session: AsyncSession,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An empty provider response (a linked account with no new activity)
    must produce a clean, successful, zero-transaction SyncRun - never an
    error, never a FAILED status."""
    user_id = await _get_user_id(client, auth_headers)
    fake = _FakeSyncProvider(
        name="fake-setu-sandbox-fixture",
        external_account_id=_SETU_SANDBOX_FIXTURE_ACCOUNT_ID,
        transactions=[],
    )
    monkeypatch.setattr(sync_service, "get_sync_provider", lambda: fake)
    linked = await _link(db_session, user_id=user_id)

    run = await sync_service.trigger_sync(db_session, user_id=user_id, linked_account_id=linked.id)
    await db_session.commit()

    assert run.status.value == "success"
    assert run.transactions_fetched == 0
    assert run.transactions_created == 0
    assert run.transactions_skipped_duplicate == 0
