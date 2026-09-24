"""Setu sandbox Account Aggregator adapter seam (Phase F8) - SANDBOX/UAT ONLY.

STATUS: structural seam only. No method in this module makes, or ever will
make without further work, a real HTTP request. See `SetuSandboxNotImplementedError`
below and `SYNC_PROVIDER.md` for the full explanation.

Why this stops here rather than implementing real calls: `SYNC_PROVIDER_RESEARCH.md`
(Phase F7) is a desk-research document built from Setu's own public marketing
and documentation *landing pages* (docs.setu.co/data/account-aggregator) - it
captured the CONCEPTUAL flow shape (consent-create -> redirect -> status
fetch -> FI-data fetch -> decrypt) but never captured concrete, implementable
details: exact endpoint paths, exact request/response JSON schemas, the
exact authentication header/signing scheme, or the exact sandbox base URL.
Phase F8's own instructions are explicit: "If the research does not provide
enough concrete API information to implement a real adapter safely, STOP at
the adapter contract/stub rather than inventing endpoints, headers,
payloads, URLs, or authentication flows." Guessing any of those would be
actively dangerous - a future engineer could mistake a plausible-looking but
fabricated endpoint for a real one and ship it.

Setu was selected as the provider to build this seam against - out of the
sandboxes surveyed in `SYNC_PROVIDER_RESEARCH.md` §E - because that research
found it the most publicly self-serviceable (pre-seeded sandbox keys, a
published Postman collection, explicit personal-finance-management use-case
support in its mock data), consistent with that document's own §L
recommendation. Selecting it does not imply Setu is the eventual production
choice - that remains an unmade business/legal decision (see
`SYNC_PROVIDER_RESEARCH.md` §D/§F).

WHAT MUST HAPPEN BEFORE ANY METHOD HERE CAN BE IMPLEMENTED FOR REAL:
    1. A developer reads Setu's LIVE API reference
       (docs.setu.co/data/account-aggregator/api-reference) or an equivalent
       primary source - never this codebase's own guess - and records the
       exact endpoint paths, request/response schemas, and auth mechanism.
    2. That developer confirms the exact shape of the FI (Financial
       Information) data response (its encryption envelope and the
       bank-statement-transaction schema inside it) and writes the mapping
       into `ExternalTransaction` explicitly, never widening
       `ExternalTransaction` itself to carry the raw provider shape (see
       `SYNC_PROVIDER.md` §4).
    3. Every HTTP call this class ends up making must set an explicit
       timeout (`_DEFAULT_TIMEOUT_SECONDS` below is reserved for this), and
       every failure path must be handled the same way `sync_service.py`
       already expects any `BankSyncProvider` failure to be handled - by
       raising, never by fabricating a plausible-looking success.
    4. Credentials remain sandbox-only, sourced from `Settings`
       (`SETU_SANDBOX_*` - see `app.core.config` and `.env.example`), never
       hardcoded, and never a production Setu credential.

Nothing in this module can ever initiate a payment, transfer, or withdrawal,
or represent a PIN/CVV/OTP/password - it implements the exact same
permanently-read-only `BankSyncProvider` Protocol as `MockSyncProvider`, no
more.
"""

import uuid
from datetime import date

from app.sync.provider.base import (
    ExternalTransaction,
    LinkCompletion,
    LinkedInstitutionAccount,
    LinkInitiation,
)

_PROVIDER_NAME = "setu_sandbox"

# Reserved for the real HTTP client this class will eventually own - not
# used yet, since no method makes a request. Recorded here now so the
# eventual implementation has an explicit, deliberate timeout from the
# start rather than an unbounded default (CLAUDE.md - bounded external
# calls, no unbounded network waits).
_DEFAULT_TIMEOUT_SECONDS = 15.0


class SetuSandboxNotImplementedError(NotImplementedError):
    """Raised by every SetuSandboxSyncProvider operation today - see the
    module docstring for why. Deliberately NOT `app.core.errors.AppError`:
    this is a developer/operations-facing "this seam is not built yet"
    signal, not an end-user input-validation error, so it does not carry
    a field_errors-shaped payload. `app.services.sync_service.trigger_sync`
    already treats any exception from a provider call as a provider
    failure (recorded on the SyncRun, never crashing the request) - this
    exception is handled exactly the same way a real network failure would
    be, with no special-casing required anywhere else in the codebase."""

    def __init__(self, operation: str) -> None:
        super().__init__(
            f"SetuSandboxSyncProvider.{operation} is not implemented yet - "
            "SYNC_PROVIDER_RESEARCH.md did not capture concrete enough Setu "
            "sandbox API details (exact endpoints/schemas/auth) to implement "
            "this safely. See this module's docstring for what's required "
            "before it can be."
        )


class SetuSandboxSyncProvider:
    """A `BankSyncProvider` implementation whose every operation currently
    raises `SetuSandboxNotImplementedError` - see the module docstring.
    Constructing an instance NEVER makes a network call and NEVER raises:
    it only stores the (optional, sandbox-only) configuration values it
    will eventually need, exactly like
    `app.ai.classifier.anthropic.AnthropicMerchantClassifier`'s own
    deliberately-lazy construction. This means selecting
    `SYNC_PROVIDER=setu_sandbox` can never block or fail application
    startup, even with no sandbox credentials configured at all."""

    name = _PROVIDER_NAME

    def __init__(
        self,
        *,
        base_url: str | None,
        client_id: str | None,
        client_secret: str | None,
        timeout_seconds: float = _DEFAULT_TIMEOUT_SECONDS,
    ) -> None:
        self._base_url = base_url
        self._client_id = client_id
        self._client_secret = client_secret
        self._timeout_seconds = timeout_seconds

    async def initiate_link(
        self, *, user_id: uuid.UUID, institution_hint: str | None = None
    ) -> LinkInitiation:
        del user_id, institution_hint
        raise SetuSandboxNotImplementedError("initiate_link")

    async def complete_link(self, *, consent_handle: str) -> LinkCompletion:
        del consent_handle
        raise SetuSandboxNotImplementedError("complete_link")

    async def list_linked_institution_accounts(
        self, *, consent_id: str
    ) -> tuple[LinkedInstitutionAccount, ...]:
        del consent_id
        raise SetuSandboxNotImplementedError("list_linked_institution_accounts")

    async def list_transactions(
        self,
        *,
        consent_id: str,
        external_account_id: str,
        since: date,
        until: date,
    ) -> tuple[ExternalTransaction, ...]:
        del consent_id, external_account_id, since, until
        raise SetuSandboxNotImplementedError("list_transactions")

    async def revoke_consent(self, *, consent_id: str) -> None:
        del consent_id
        raise SetuSandboxNotImplementedError("revoke_consent")
