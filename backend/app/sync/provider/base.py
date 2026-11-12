"""Bank/Account-Aggregator sync-provider data model, plus the
`BankSyncProvider` Protocol every provider (mock or a real Account
Aggregator client) implements.

This Protocol is deliberately, permanently READ-ONLY. It can start and
complete a consent flow, list the institution accounts a consent covers,
pull transaction history for one of those accounts, and revoke a consent -
nothing else. Per CLAUDE.md §14/§20 (no unrestricted external access, never
fake functionality that could move money): no payment, transfer,
withdrawal, debit-authorization, send-money, or bank-settings method may
ever be added here. `masked_account_ref` on `LinkedInstitutionAccount` is
always a masked reference (e.g. "XX1234"), never a full account number, and
nothing in this module can ever represent a PIN, password, OTP, CVV, or any
other payment-authorization credential - a provider only ever hands back an
opaque `consent_id`/`consent_handle` it manages on its own side.

`ExternalTransaction.narration` is the raw, unstructured statement text a
real bank/UPI feed actually returns (e.g. "UPI/DR/399/SWIGGY/..."). It is
untrusted, unparsed data here - merchant normalization, categorization, and
transaction creation from it are a later phase's service-layer concern, not
this provider's.

No ingestion/orchestration logic lives in this module - only the seam.
"""

import uuid
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Literal, Protocol, runtime_checkable

TransactionDirection = Literal["debit", "credit"]


@dataclass(frozen=True)
class LinkInitiation:
    """The result of starting a consent flow - `redirect_url` is where the
    user completes consent in their own bank/Account Aggregator app;
    `consent_handle` is the opaque, provider-managed reference `complete_link`
    is later called with once that flow finishes."""

    provider: str
    consent_handle: str
    redirect_url: str
    expires_at: datetime


@dataclass(frozen=True)
class LinkedInstitutionAccount:
    """One institution account a consent covers. `external_account_id` is
    an opaque, provider-defined identifier - never assumed to have a
    particular shape. `masked_account_ref` is masked-only (e.g. "XX1234"),
    never a full account number."""

    external_account_id: str
    institution_name: str
    fip_reference: str | None
    masked_account_ref: str | None


@dataclass(frozen=True)
class LinkCompletion:
    """The result of finishing a consent flow. `consent_status` mirrors the
    plain string values of app.models.linked_account.SyncConsentStatus,
    kept as a plain str here since a provider has no business depending on
    this application's own enum type."""

    consent_id: str
    consent_status: str
    consent_expires_at: datetime | None
    accounts: tuple[LinkedInstitutionAccount, ...] = field(default_factory=tuple)


@dataclass(frozen=True)
class ExternalTransaction:
    """One raw transaction as the provider reports it - never normalized,
    categorized, or matched to an internal Transaction here (see the module
    docstring). `amount_minor` is always a non-negative integer minor-unit
    value; `direction` says which way the money moved."""

    external_transaction_id: str
    external_account_id: str
    occurred_on: date
    amount_minor: int
    direction: TransactionDirection
    narration: str


@runtime_checkable
class BankSyncProvider(Protocol):
    """`name` is a safe, non-secret label (e.g. "mock") so callers can
    honestly indicate demo mode - see CLAUDE.md: "never fabricate results
    silently"."""

    name: str

    async def initiate_link(
        self, *, user_id: uuid.UUID, institution_hint: str | None = None
    ) -> LinkInitiation: ...

    async def complete_link(self, *, consent_handle: str) -> LinkCompletion: ...

    async def list_linked_institution_accounts(
        self, *, consent_id: str
    ) -> tuple[LinkedInstitutionAccount, ...]: ...

    async def list_transactions(
        self,
        *,
        consent_id: str,
        external_account_id: str,
        since: date,
        until: date,
    ) -> tuple[ExternalTransaction, ...]: ...

    async def revoke_consent(self, *, consent_id: str) -> None: ...
