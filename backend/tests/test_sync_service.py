"""Tests for the Phase B automatic-sync orchestration
(app.services.sync_service): link lifecycle, the ingestion pipeline
(dedup/normalize/categorize/confidence), SyncRun bookkeeping, and the
security invariants the pipeline must never violate."""

import inspect
import re
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime

import pytest
from httpx import AsyncClient
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import inspect as sa_inspect
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors import NotFoundError, ValidationAppError
from app.models.linked_account import LinkedAccount, SyncConsentStatus
from app.models.sync_run import SyncRun, SyncRunStatus
from app.repositories.transaction_repository import TransactionRepository
from app.schemas.sync import LinkedAccountRead
from app.schemas.transaction import TransactionCreate
from app.services import merchant_rule_service, sync_service, transaction_service
from app.sync.provider.base import (
    ExternalTransaction,
    LinkCompletion,
    LinkedInstitutionAccount,
    LinkInitiation,
)

_FAKE_EXTERNAL_ACCOUNT_ID = "fake-acc-001"


@dataclass
class _FakeSyncProvider:
    name: str = "fake"
    institution_name: str = "Fake Bank"
    external_account_id: str = _FAKE_EXTERNAL_ACCOUNT_ID
    masked_account_ref: str = "XX9999"
    consent_status: str = "active"
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
            consent_expires_at=datetime(2027, 1, 1, tzinfo=UTC),
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
