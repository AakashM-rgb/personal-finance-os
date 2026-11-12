"""Tests for the read-only bank/Account-Aggregator sync-provider seam
(app.sync.provider) - the deterministic mock provider, the Setu sandbox
adapter seam (Phase F8), the BankSyncProvider Protocol they implement, the
provider factory, and the hard security boundary that no payment/transfer/
credential capability ever sneaks in."""

import dataclasses
import inspect
import re
import uuid
from datetime import date

import pytest

from app.core.config import Settings, get_settings
from app.sync.provider.base import (
    BankSyncProvider,
    ExternalTransaction,
    LinkCompletion,
    LinkedInstitutionAccount,
    LinkInitiation,
)
from app.sync.provider.factory import build_sync_provider, get_sync_provider
from app.sync.provider.mock import MockSyncProvider
from app.sync.provider.setu_sandbox import (
    SetuSandboxNotImplementedError,
    SetuSandboxSyncProvider,
)

_USER_ID = uuid.UUID("11111111-1111-1111-1111-111111111111")


# --- MockSyncProvider deterministic fixtures -------------------------------


async def test_initiate_link_is_deterministic_for_same_user() -> None:
    provider = MockSyncProvider()
    first = await provider.initiate_link(user_id=_USER_ID)
    second = await provider.initiate_link(user_id=_USER_ID)
    assert first == second
    assert first.provider == "mock"


async def test_complete_link_is_deterministic() -> None:
    provider = MockSyncProvider()
    first = await provider.complete_link(consent_handle="some-handle")
    second = await provider.complete_link(consent_handle="some-handle")
    assert first == second
    assert first.consent_status == "active"
    assert len(first.accounts) == 1


async def test_list_transactions_includes_realistic_messy_narrations() -> None:
    provider = MockSyncProvider()
    completion = await provider.complete_link(consent_handle="h")
    account = completion.accounts[0]

    transactions = await provider.list_transactions(
        consent_id=completion.consent_id,
        external_account_id=account.external_account_id,
        since=date(2026, 1, 1),
        until=date(2026, 12, 31),
    )

    narrations = [txn.narration for txn in transactions]
    assert any(n.startswith("UPI/DR/399/SWIGGY/") for n in narrations)
    assert any(n.startswith("UPI/DR/850/AMZN MKTPLACE/") for n in narrations)
    assert any(n.startswith("NEFT/DR/") for n in narrations)
    assert any(n.startswith("IMPS/CR/") for n in narrations)
    # Every fixture transaction is a plain, un-normalized raw narration -
    # no merchant/category has been extracted from it (that is Phase B).
    for txn in transactions:
        assert txn.amount_minor > 0
        assert txn.direction in ("debit", "credit")


async def test_list_transactions_is_deterministic() -> None:
    provider = MockSyncProvider()
    completion = await provider.complete_link(consent_handle="h")
    account = completion.accounts[0]
    kwargs = dict(
        consent_id=completion.consent_id,
        external_account_id=account.external_account_id,
        since=date(2026, 1, 1),
        until=date(2026, 12, 31),
    )
    first = await provider.list_transactions(**kwargs)
    second = await provider.list_transactions(**kwargs)
    assert first == second
    assert len(first) > 0


async def test_list_transactions_filters_by_date_range() -> None:
    provider = MockSyncProvider()
    completion = await provider.complete_link(consent_handle="h")
    account = completion.accounts[0]

    none_in_range = await provider.list_transactions(
        consent_id=completion.consent_id,
        external_account_id=account.external_account_id,
        since=date(2020, 1, 1),
        until=date(2020, 1, 31),
    )
    assert none_in_range == ()

    august_only = await provider.list_transactions(
        consent_id=completion.consent_id,
        external_account_id=account.external_account_id,
        since=date(2026, 8, 1),
        until=date(2026, 8, 31),
    )
    assert all(date(2026, 8, 1) <= txn.occurred_on <= date(2026, 8, 31) for txn in august_only)
    assert len(august_only) < len(
        await provider.list_transactions(
            consent_id=completion.consent_id,
            external_account_id=account.external_account_id,
            since=date(2026, 1, 1),
            until=date(2026, 12, 31),
        )
    )


async def test_list_transactions_filters_by_unknown_account() -> None:
    provider = MockSyncProvider()
    result = await provider.list_transactions(
        consent_id="whatever",
        external_account_id="not-a-real-account",
        since=date(2026, 1, 1),
        until=date(2026, 12, 31),
    )
    assert result == ()


async def test_revoke_consent_does_not_raise() -> None:
    provider = MockSyncProvider()
    assert await provider.revoke_consent(consent_id="mock-consent-h") is None


async def test_list_linked_institution_accounts_never_exposes_full_account_number() -> None:
    provider = MockSyncProvider()
    accounts = await provider.list_linked_institution_accounts(consent_id="mock-consent-h")
    assert len(accounts) == 1
    account = accounts[0]
    assert account.masked_account_ref is not None
    assert account.masked_account_ref.startswith("XX")
    assert len(account.masked_account_ref) <= 10


# --- BankSyncProvider interface ---------------------------------------------


def test_mock_provider_satisfies_bank_sync_provider_protocol() -> None:
    assert isinstance(MockSyncProvider(), BankSyncProvider)


def test_bank_sync_provider_exposes_exactly_the_read_only_methods() -> None:
    required = {
        "initiate_link",
        "complete_link",
        "list_linked_institution_accounts",
        "list_transactions",
        "revoke_consent",
    }
    protocol_methods = {
        name
        for name, member in inspect.getmembers(BankSyncProvider)
        if not name.startswith("_") and callable(member)
    }
    assert required <= protocol_methods


# --- factory -----------------------------------------------------------------


def test_build_sync_provider_returns_mock_when_sync_provider_is_mock() -> None:
    settings = get_settings()
    assert settings.sync_provider == "mock"

    provider = build_sync_provider(settings)

    assert isinstance(provider, MockSyncProvider)
    assert provider.name == "mock"


def test_build_sync_provider_rejects_unknown_provider() -> None:
    settings = get_settings().model_copy(update={"sync_provider": "real-bank-vendor"})
    try:
        build_sync_provider(settings)
    except RuntimeError as exc:
        assert "real-bank-vendor" in str(exc)
    else:
        raise AssertionError("expected RuntimeError for an unconfigured provider")


def test_get_sync_provider_is_cached_and_returns_mock_by_default() -> None:
    provider = get_sync_provider()
    assert isinstance(provider, MockSyncProvider)
    assert get_sync_provider() is provider


# --- Setu sandbox adapter seam (Phase F8) ------------------------------------


def test_build_sync_provider_returns_setu_sandbox_when_configured() -> None:
    settings = get_settings().model_copy(update={"sync_provider": "setu_sandbox"})

    provider = build_sync_provider(settings)

    assert isinstance(provider, SetuSandboxSyncProvider)
    assert provider.name == "setu_sandbox"


def test_setu_sandbox_provider_construction_makes_no_network_request_and_never_raises() -> None:
    """Mirrors app.ai.classifier.anthropic.AnthropicMerchantClassifier's own
    lazy-construction guarantee: selecting this provider, even with every
    credential field left unset, can never block or fail application
    startup."""
    provider = SetuSandboxSyncProvider(base_url=None, client_id=None, client_secret=None)
    assert provider.name == "setu_sandbox"


def test_setu_sandbox_provider_satisfies_bank_sync_provider_protocol() -> None:
    provider = SetuSandboxSyncProvider(base_url=None, client_id=None, client_secret=None)
    assert isinstance(provider, BankSyncProvider)


@pytest.mark.parametrize(
    "call",
    [
        lambda p: p.initiate_link(user_id=_USER_ID),
        lambda p: p.complete_link(consent_handle="h"),
        lambda p: p.list_linked_institution_accounts(consent_id="c"),
        lambda p: p.list_transactions(
            consent_id="c", external_account_id="a", since=date(2026, 1, 1), until=date(2026, 1, 31)
        ),
        lambda p: p.revoke_consent(consent_id="c"),
    ],
)
async def test_setu_sandbox_provider_every_operation_fails_safe_never_fabricates_data(call) -> None:
    """req 6/7 (normalized-mapping / malformed-data safety, stub-appropriate
    form): since no real HTTP call is made, there is no real response to
    map or to receive malformed - what matters is that every single
    Protocol operation fails via the SAME explicit, documented exception
    rather than ever silently returning a plausible-looking but entirely
    fabricated LinkInitiation/LinkCompletion/account/transaction."""
    provider = SetuSandboxSyncProvider(base_url=None, client_id=None, client_secret=None)
    with pytest.raises(SetuSandboxNotImplementedError):
        await call(provider)


async def test_setu_sandbox_provider_failure_never_exposes_the_configured_secret() -> None:
    distinctive_secret = "sandbox-secret-distinctive-value-xyz123"
    provider = SetuSandboxSyncProvider(
        base_url="https://sandbox.example.invalid",
        client_id="sandbox-client-id",
        client_secret=distinctive_secret,
    )

    with pytest.raises(SetuSandboxNotImplementedError) as exc_info:
        await provider.revoke_consent(consent_id="some-consent-id")

    assert distinctive_secret not in str(exc_info.value)


def test_setu_sandbox_provider_has_no_forbidden_methods_or_attributes() -> None:
    public_members = {name for name in dir(SetuSandboxSyncProvider) if not name.startswith("_")}
    _assert_no_forbidden_names(public_members)


def test_setu_sandbox_settings_have_no_forbidden_credential_fields() -> None:
    """Redundant with test_settings_has_no_forbidden_credential_fields
    (which already scans every Settings field including the new
    setu_sandbox_* ones) - kept as an explicit, narrowly-scoped assertion
    so a future reader sees the Setu-specific guarantee directly, without
    having to infer it from the generic whole-Settings scan."""
    setu_fields = {
        name for name in Settings.model_fields if name.startswith("setu_sandbox_")
    }
    assert setu_fields == {
        "setu_sandbox_base_url",
        "setu_sandbox_client_id",
        "setu_sandbox_client_secret",
    }
    _assert_no_forbidden_names(setu_fields)


async def test_setu_sandbox_provider_failures_never_expose_consent_or_account_identifiers() -> None:
    """Phase F9: strengthens test_setu_sandbox_provider_failure_never_exposes_the_configured_secret
    (which only checked the client_secret) - every argument passed into
    every operation (consent handles, account ids, user ids) must also
    never appear in what gets raised, since SetuSandboxNotImplementedError
    only ever interpolates a hardcoded operation name, never any caller
    argument."""
    provider = SetuSandboxSyncProvider(
        base_url="https://sandbox.example.invalid",
        client_id="distinctive-client-id-value",
        client_secret="distinctive-client-secret-value",
    )
    distinctive_consent_handle = "distinctive-consent-handle-value"
    distinctive_consent_id = "distinctive-consent-id-value"
    distinctive_account_id = "distinctive-external-account-id-value"

    with pytest.raises(SetuSandboxNotImplementedError) as initiate_exc:
        await provider.initiate_link(user_id=_USER_ID, institution_hint="Distinctive Bank Name")
    with pytest.raises(SetuSandboxNotImplementedError) as complete_exc:
        await provider.complete_link(consent_handle=distinctive_consent_handle)
    with pytest.raises(SetuSandboxNotImplementedError) as list_accounts_exc:
        await provider.list_linked_institution_accounts(consent_id=distinctive_consent_id)
    with pytest.raises(SetuSandboxNotImplementedError) as list_txns_exc:
        await provider.list_transactions(
            consent_id=distinctive_consent_id,
            external_account_id=distinctive_account_id,
            since=date(2026, 1, 1),
            until=date(2026, 1, 31),
        )
    with pytest.raises(SetuSandboxNotImplementedError) as revoke_exc:
        await provider.revoke_consent(consent_id=distinctive_consent_id)

    for exc_info in (
        initiate_exc,
        complete_exc,
        list_accounts_exc,
        list_txns_exc,
        revoke_exc,
    ):
        text = str(exc_info.value)
        assert str(_USER_ID) not in text
        assert "Distinctive Bank Name" not in text
        assert distinctive_consent_handle not in text
        assert distinctive_consent_id not in text
        assert distinctive_account_id not in text
        assert "distinctive-client-id-value" not in text
        assert "distinctive-client-secret-value" not in text


def test_setu_sandbox_credentials_alone_do_not_activate_the_provider() -> None:
    """Phase F9: merely configuring SETU_SANDBOX_* values, without also
    explicitly setting SYNC_PROVIDER=setu_sandbox, must never switch the
    active provider away from the mock default - there is no implicit
    "credentials present -> use them" activation anywhere in the factory."""
    settings = get_settings().model_copy(
        update={
            "setu_sandbox_base_url": "https://sandbox.example.invalid",
            "setu_sandbox_client_id": "some-client-id",
            "setu_sandbox_client_secret": "some-client-secret",
        }
    )
    assert settings.sync_provider == "mock"  # untouched by the update above

    provider = build_sync_provider(settings)

    assert isinstance(provider, MockSyncProvider)


# --- runs without any real provider credentials configured ------------------


def test_application_settings_require_no_real_sync_credentials() -> None:
    """SYNC_PROVIDER is absent from the real .env (see .env.example) and the
    setting still resolves to "mock" via its default - the application must
    never require a real bank/Account Aggregator credential to start."""
    settings = get_settings()
    assert settings.sync_provider == "mock"
    provider = build_sync_provider(settings)
    assert isinstance(provider, MockSyncProvider)


# --- no forbidden credential fields ------------------------------------------

_FORBIDDEN_SUBSTRINGS = (
    "pin",
    "cvv",
    "otp",
    "password",
    "atm_pin",
    "upi_pin",
    "card_pin",
    "transfer",
    "withdraw",
    "debit_auth",
    "payment_auth",
    "send_money",
)


_FORBIDDEN_PATTERN = re.compile(
    "|".join(
        # Short, common-substring-risk terms ("pin") need letter-boundary
        # matching so an innocent identifier never false-positives; the
        # longer, distinctive phrases keep plain substring matching so a
        # real field like `payment_authorization_token` still matches
        # "payment_auth" as a prefix.
        rf"(?<![a-z]){re.escape(term)}(?![a-z])" if len(term) <= 3 else re.escape(term)
        for term in _FORBIDDEN_SUBSTRINGS
    )
)


def _assert_no_forbidden_names(names: set[str]) -> None:
    for name in names:
        match = _FORBIDDEN_PATTERN.search(name.lower())
        assert match is None, f"forbidden field/method name found: {name!r}"


def test_sync_dataclasses_have_no_forbidden_credential_fields() -> None:
    for cls in (LinkInitiation, LinkedInstitutionAccount, LinkCompletion, ExternalTransaction):
        field_names = {f.name for f in dataclasses.fields(cls)}
        _assert_no_forbidden_names(field_names)


def test_settings_has_no_forbidden_credential_fields() -> None:
    _assert_no_forbidden_names(set(Settings.model_fields))


def test_bank_sync_provider_protocol_has_no_forbidden_methods() -> None:
    method_names = {
        name for name, member in inspect.getmembers(BankSyncProvider) if callable(member)
    }
    _assert_no_forbidden_names(method_names)


def test_mock_provider_has_no_forbidden_methods_or_attributes() -> None:
    public_members = {name for name in dir(MockSyncProvider) if not name.startswith("_")}
    _assert_no_forbidden_names(public_members)
