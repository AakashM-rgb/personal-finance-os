"""The deterministic mock BankSyncProvider - used whenever no real Account
Aggregator integration is configured (see app.sync.provider.factory). Every
consent handle and transaction it returns is a fixed, hardcoded fixture,
never randomly generated and never dependent on wall-clock time, so the
same call always produces the same result and tests can assert against
exact values.

Narrations are intentionally messy/realistic (e.g. "UPI/DR/399/SWIGGY/...")
because real bank/UPI statement narrations are exactly this unstructured -
a later phase's merchant-normalization work consumes this raw text. This
provider does no normalization, categorization, or transaction creation
itself; it only returns the raw fixture data, mirroring exactly what a real
provider would hand back before any of that processing happens.

`name` is always "mock" - never a real vendor name - so nothing downstream
can mistake this for a real external call (CLAUDE.md: "never fabricate
results silently").
"""

import uuid
from datetime import UTC, date, datetime

from app.sync.provider.base import (
    ExternalTransaction,
    LinkCompletion,
    LinkedInstitutionAccount,
    LinkInitiation,
)

_PROVIDER_NAME = "mock"

_MOCK_INSTITUTION_NAME = "Mock Bank"
_MOCK_FIP_REFERENCE = "MOCKBANK-FIP-001"
_MOCK_EXTERNAL_ACCOUNT_ID = "mock-acc-0001"
_MOCK_MASKED_ACCOUNT_REF = "XX4321"
_MOCK_CONSENT_EXPIRES_AT = datetime(2027, 1, 1, tzinfo=UTC)

_MOCK_ACCOUNT = LinkedInstitutionAccount(
    external_account_id=_MOCK_EXTERNAL_ACCOUNT_ID,
    institution_name=_MOCK_INSTITUTION_NAME,
    fip_reference=_MOCK_FIP_REFERENCE,
    masked_account_ref=_MOCK_MASKED_ACCOUNT_REF,
)

# Deliberately messy, realistic UPI/NEFT/IMPS statement narrations - see the
# module docstring. Amounts are minor-unit integers (paise), matching the
# narration's rupee figure exactly (e.g. "UPI/DR/399/..." -> 39_900 paise).
_MOCK_TRANSACTIONS: tuple[ExternalTransaction, ...] = (
    ExternalTransaction(
        external_transaction_id="mocktxn-0001",
        external_account_id=_MOCK_EXTERNAL_ACCOUNT_ID,
        occurred_on=date(2026, 8, 2),
        amount_minor=39_900,
        direction="debit",
        narration="UPI/DR/399/SWIGGY/paytm@ybl/Swiggy Order",
    ),
    ExternalTransaction(
        external_transaction_id="mocktxn-0002",
        external_account_id=_MOCK_EXTERNAL_ACCOUNT_ID,
        occurred_on=date(2026, 8, 5),
        amount_minor=85_000,
        direction="debit",
        narration="UPI/DR/850/AMZN MKTPLACE/amazon@icici/Online Purchase",
    ),
    ExternalTransaction(
        external_transaction_id="mocktxn-0003",
        external_account_id=_MOCK_EXTERNAL_ACCOUNT_ID,
        occurred_on=date(2026, 8, 7),
        amount_minor=1_500_000,
        direction="debit",
        narration="NEFT/DR/N123456789012/RENT PAYMENT LANDLORD",
    ),
    ExternalTransaction(
        external_transaction_id="mocktxn-0004",
        external_account_id=_MOCK_EXTERNAL_ACCOUNT_ID,
        occurred_on=date(2026, 8, 31),
        amount_minor=6_500_000,
        direction="credit",
        narration="IMPS/CR/987654321098/SALARY ACME CORP PVT LTD",
    ),
    ExternalTransaction(
        external_transaction_id="mocktxn-0005",
        external_account_id=_MOCK_EXTERNAL_ACCOUNT_ID,
        occurred_on=date(2026, 9, 1),
        amount_minor=12_000,
        direction="debit",
        narration="UPI/DR/120/BESCOM BBMP/bescom@sbi/Electricity Bill",
    ),
)


class MockSyncProvider:
    name = _PROVIDER_NAME

    async def initiate_link(
        self, *, user_id: uuid.UUID, institution_hint: str | None = None
    ) -> LinkInitiation:
        consent_handle = f"mock-consent-handle-{user_id}"
        return LinkInitiation(
            provider=_PROVIDER_NAME,
            consent_handle=consent_handle,
            redirect_url=f"https://mock-aa.invalid/consent/{consent_handle}",
            expires_at=_MOCK_CONSENT_EXPIRES_AT,
        )

    async def complete_link(self, *, consent_handle: str) -> LinkCompletion:
        return LinkCompletion(
            consent_id=f"mock-consent-{consent_handle}",
            consent_status="active",
            consent_expires_at=_MOCK_CONSENT_EXPIRES_AT,
            accounts=(_MOCK_ACCOUNT,),
        )

    async def list_linked_institution_accounts(
        self, *, consent_id: str
    ) -> tuple[LinkedInstitutionAccount, ...]:
        return (_MOCK_ACCOUNT,)

    async def list_transactions(
        self,
        *,
        consent_id: str,
        external_account_id: str,
        since: date,
        until: date,
    ) -> tuple[ExternalTransaction, ...]:
        return tuple(
            txn
            for txn in _MOCK_TRANSACTIONS
            if txn.external_account_id == external_account_id and since <= txn.occurred_on <= until
        )

    async def revoke_consent(self, *, consent_id: str) -> None:
        return None
