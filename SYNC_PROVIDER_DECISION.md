# Setu Sandbox Integration Decision

## 1. Current Status

**NOT_READY_DOCUMENTATION_GAP**

Per the explicit decision rule this phase was given (§G of the phase task, restated in this
document's own construction): authentication for the AA Gateway product specifically remains
unverified by any authoritative source reviewed in Phase F11 or re-examined in this phase. That
alone is sufficient to keep the state at `NOT_READY_DOCUMENTATION_GAP`, regardless of how many
other items have since been resolved. This is not downgraded to a minor issue anywhere in this
document.

## 2. Evidence Reviewed

No new evidence was gathered in this phase (Phase F12 is a re-audit/decision gate over Phase F11's
existing findings, not a new research pass — no network request of any kind was made). Everything
below is Phase F11's evidence, re-examined here for classification rigor.

| Source | What it proves |
|---|---|
| [Consent flow — Setu Docs](https://docs.setu.co/data/account-aggregator/api-integration/consent-flow) | AA Gateway base URLs (`fiu-sandbox.setu.co`/`fiu.setu.co`); consent create/get/revoke endpoints and schemas; consistently requires `Authorization: Bearer <token>` without showing where the token comes from |
| [Data APIs — Setu Docs](https://docs.setu.co/data/account-aggregator/api-integration/data-apis) | Data-session create/poll endpoints; individual transaction field names (`amount`, `narration`, `txnId`, `type`, `valueDate`, etc.); error schema |
| [Consent Object — Setu Docs](https://docs.setu.co/data/account-aggregator/consent-object) | Full consent request/response field list |
| [Account Availability APIs — Setu Docs](https://docs.setu.co/data/account-aggregator/api-integration/account-availability-apis) | A phone-number-based discovery endpoint, distinct from and not a substitute for "which accounts does this granted consent cover" |
| [FIP APIs — Setu Docs](https://docs.setu.co/data/account-aggregator/api-integration/fip-apis) | Independent confirmation of the same error schema seen in the Data APIs source |
| [Notifications — Setu Docs](https://docs.setu.co/data/account-aggregator/api-integration/notifications) | Webhook event types and payload shape; explicitly does not document signature/authenticity verification |
| [Account Aggregator overview — Setu Docs](https://docs.setu.co/data/account-aggregator/overview) | Confirms an "HTTP APIs" building block exists; does not resolve authentication or rate limits |
| [Account Aggregator quickstart — Setu Docs](https://docs.setu.co/data/account-aggregator/quickstart) | Names `x-product-instance-id`/`x-client_id`/`x-client-secret` as sandbox setup outputs, without describing how they're used in an actual request |
| [Setu Bridge OAuth — Setu Docs](https://docs.setu.co/dev-tools/bridge/v1/org-settings/api-keys/oauth) | Documents a token-exchange mechanism (`POST /api/v2/auth/token` on `uat.setu.co`/`prod.setu.co`) but explicitly states this is product-specific and does not confirm AA Gateway coverage |

Full source list with URLs and dates is in `SYNC_PROVIDER_RESEARCH.md`; full per-item evidence
mapping is in `SYNC_PROVIDER_READINESS.md` §5.

## 3. Remaining Gaps

| Gap | Classification | Blocks Implementation? | Evidence Needed |
|---|---|---|---|
| 1. AA-Gateway-specific authentication mechanism | `REQUIRES_AUTHENTICATED_PROVIDER_ACCESS` | **Yes — hard blocker** | The account-specific API reference/Postman collection Setu provides once an FIU app is created in Setu Bridge, OR direct written confirmation from Setu developer support, explicitly naming which of the two candidate mechanisms (OAuth token exchange vs. static `x-client_id`/`x-client-secret` headers) applies to AA Gateway calls, and on which exact host |
| 2. Webhook signature/authenticity verification | `NOT_REQUIRED_FOR_INITIAL_READ_ONLY_SANDBOX` | No | Only needed if/when a webhook receiver is built (§4/§6); the existing `GET /consents/:id` polling path already covers consent-completion without one |
| 3. Pagination behavior | `REQUIRES_AUTHENTICATED_PROVIDER_ACCESS` | No, for a minimal first implementation (see §4) | Either the authenticated API reference, or observed behavior from an actual sandbox response once real sandbox access exists |
| 4. Rate limits | `REQUIRES_AUTHENTICATED_PROVIDER_ACCESS` | No | Same as above; affects only resilience/backoff design, not correctness, and this codebase's own established convention is no automatic retries anyway |
| 5. Complete nested transaction response shape | `REQUIRES_AUTHENTICATED_PROVIDER_ACCESS` | **Yes — hard blocker for writing the actual mapping code**, though not for the architecture decision in §4 | The authenticated API reference/Postman collection, or a real (sandbox, dummy-data) response captured during actual implementation |
| 6. Conflicting sandbox/production host information | `REQUIRES_AUTHENTICATED_PROVIDER_ACCESS` | Tied to gap 1 — moot once gap 1 is resolved, since resolving which auth mechanism applies also resolves which host it lives on | Same evidence as gap 1 |

**No gap in this table is classified `RESOLVED_BY_PUBLIC_DOCS` or `REQUIRES_PROVIDER_SUPPORT`.**
None was resolvable purely by further public-documentation reading (all six were already searched
for directly in Phase F11 using Setu's own live API reference, not just landing pages) - so none
qualifies as `RESOLVED_BY_PUBLIC_DOCS`. None was classified `REQUIRES_PROVIDER_SUPPORT` as the
*primary* path because Setu's documented pattern (create an FIU app in Setu Bridge, then read the
resulting account-specific reference) is itself a form of authenticated self-service access, not a
requirement to contact Setu directly - though direct developer-support contact remains a valid
fallback if that self-service reference still doesn't resolve gap 1 (see §7).

## 4. Architecture Decision

**`BankSyncProvider`'s existing five-method contract remains sufficient for the first sandbox
implementation. No protocol change is needed or was made.**

- **Webhook handling requires a new HTTP endpoint only, not a `BankSyncProvider` protocol
  change.** A webhook receiver (e.g. a future `POST /api/v1/sync/webhook`) would authenticate and
  parse the incoming Setu notification, then call the same underlying `sync_service` logic
  `complete_link` (or a future consent-status-refresh function) already represents. This was the
  conclusion in `SYNC_PROVIDER.md` §9 and `SYNC_PROVIDER_READINESS.md` §7, re-confirmed unchanged
  here by re-reading both `base.py` and `sync_service.py` fresh.
- **Pagination can be handled internally by `list_transactions` without any protocol change.**
  `BankSyncProvider.list_transactions` already returns a single `tuple[ExternalTransaction, ...]`
  for the full requested date range - if Setu's data-session response is ever found to paginate
  internally, a real adapter would loop over pages *inside* its own `list_transactions`
  implementation and return the fully-assembled tuple, exactly as `MockSyncProvider` already
  returns a complete tuple today. The Protocol's caller (`sync_service._ingest_one`'s loop) does
  not need to know or care whether the adapter made one HTTP call or several to produce it.
- **Date ranges already fit the existing contract exactly.** `list_transactions(*, consent_id,
  external_account_id, since: date, until: date)` maps directly onto Setu's own `dataRange: {from,
  to}` parameter (confirmed in `SYNC_PROVIDER_READINESS.md` §5/§7) - no adaptation is needed beyond
  formatting `since`/`until` as the ISO-8601 timestamps Setu's schema expects.
- **The protocol is sufficient — stated explicitly, as requested.** Every one of the five methods
  (`initiate_link`, `complete_link`, `list_linked_institution_accounts`, `list_transactions`,
  `revoke_consent`) was mapped to a specific, named Setu operation in
  `SYNC_PROVIDER_READINESS.md` §7, re-verified unchanged in this phase. Nothing found requires a
  sixth method, a changed signature, or any money-movement-shaped capability. `BankSyncProvider`
  (`backend/app/sync/provider/base.py`) was **not modified** in this phase.

## 5. Security Gate

The following conditions **must all be true** before any future real sandbox implementation is
allowed to proceed past this decision gate. Each is marked against its current status.

| # | Condition | Current status |
|---|---|---|
| 1 | Official authentication mechanism verified (for AA Gateway specifically) | ❌ **Not met — the blocker** |
| 2 | Official sandbox base URL verified | ✅ Met (`fiu-sandbox.setu.co`) |
| 3 | Official request/response contracts verified | ⚠️ Partially met (consent/revoke/data-session endpoints yes; full transaction-nesting shape no) |
| 4 | Official read-only data-access scope verified | ✅ Met — every documented Setu AA Gateway operation reviewed is a data-read or consent-lifecycle operation; nothing resembling payment/transfer/withdrawal was found anywhere in `SYNC_PROVIDER_RESEARCH.md` or `SYNC_PROVIDER_READINESS.md`'s research |
| 5 | Secret handling design verified | ✅ Met — `Settings.setu_sandbox_*` fields are optional, never logged, never persisted, never returned by any API response, never referenced anywhere in `frontend/` (verified by direct search in Phase F10/F11); this is a property of *this repository's own code*, independent of which exact credential shape Setu turns out to require |
| 6 | Timeout and failure behavior defined | ✅ Met at the architecture level — `_DEFAULT_TIMEOUT_SECONDS` is already reserved in `setu_sandbox.py`, and `sync_service.trigger_sync`'s existing generic provider-failure handling (unchanged since Phase F3) already covers any exception a real adapter would raise; no code change needed here specifically for Setu |
| 7 | No sensitive payment credentials involved | ✅ Met — nothing retrieved requires a PIN/CVV/OTP/banking password; the AA framework's own design keeps user authentication entirely between the user and their bank/AA app |
| 8 | No payment/money-movement capability | ✅ Met — confirmed by direct read of `base.py` (exactly 5 read-only methods) and by every Setu operation documented |
| 9 | Mock remains the default | ✅ Met — `sync_provider: str = Field(default="mock", ...)`, unchanged |
| 10 | Sandbox provider requires explicit configuration | ✅ Met — only `SYNC_PROVIDER=setu_sandbox` selects it; tested (`test_build_sync_provider_returns_setu_sandbox_when_configured`) |
| 11 | No production endpoint can be selected accidentally | ✅ Met — `setu_sandbox_client_id`/`_secret`/`_base_url` alone, without also setting `SYNC_PROVIDER`, never activates the sandbox provider (tested: `test_setu_sandbox_credentials_alone_do_not_activate_the_provider`); no separate "production Setu" provider exists in this codebase at all today |
| 12 | No raw provider payload is persisted | ✅ Met by design today (nothing is persisted, since nothing is fetched yet) — and remains an explicit implementation *discipline* requirement for whoever writes the real adapter (`SYNC_PROVIDER.md` §8) |
| 13 | No secrets are logged or returned to frontend | ✅ Met — `setu_sandbox.py` has zero logging statements; tested directly (`test_setu_sandbox_provider_failure_never_exposes_the_configured_secret`, `test_setu_sandbox_provider_failures_never_expose_consent_or_account_identifiers`); frontend search returns zero matches |
| 14 | `transaction_service.create_transaction` remains the sole ledger write path | ✅ Met — unchanged, re-confirmed by fresh read of `sync_service.py` this phase; no parallel ledger exists anywhere |

**11 of 14 conditions are already met by the existing architecture, independent of any Setu-side
resolution. Conditions 1 and 3 are the ones a real implementation cannot proceed without, and
condition 6 is met at the architecture level but would need a concrete timeout *value* decision
once real latency characteristics are known.**

## 6. Implementation Boundary

Restated precisely for whoever eventually resumes this work, once the gate in §5 is fully passed:

**The first real sandbox implementation MAY:**
- Make HTTP requests to `https://fiu-sandbox.setu.co` (or whatever host gap 1's resolution
  confirms) for consent creation/status/revocation and data-session creation/polling, using
  sandbox-only credentials configured via `SETU_SANDBOX_*` environment variables.
- Read financial data (account metadata, transaction history) for sandbox/dummy test users only.
- Implement exactly the five `BankSyncProvider` methods, mapping Setu's responses into the
  existing `LinkInitiation`/`LinkCompletion`/`LinkedInstitutionAccount`/`ExternalTransaction`
  dataclasses, with any Setu-specific field never persisted or exposed beyond that mapping.
- Add a new webhook HTTP route, if and when needed, that calls existing `sync_service` logic -
  never a `BankSyncProvider` change.

**The first real sandbox implementation MUST NOT:**
- Connect to any production financial account, Setu production host, or non-dummy data.
- Request, accept, or store a UPI PIN, ATM/card PIN, CVV, OTP, banking password, or any other
  payment-authorization credential - none is required by anything documented, and none may ever be
  added regardless.
- Add any payment, transfer, withdrawal, debit, credit, beneficiary-management, or
  balance-modification capability, to `BankSyncProvider` or anywhere else.
- Use screen scraping or browser automation against any financial website.
- Persist a raw, undigested Setu API response anywhere - every field must be deliberately mapped
  into the existing normalized contracts first.
- Log a secret, consent handle, account identifier, or financial data value at any log level.
- Bypass `transaction_service.create_transaction` for any ledger write.
- Change the AI categorization order or the `ai_categorization_enabled` default.
- Be selectable without an explicit `SYNC_PROVIDER=setu_sandbox` configuration - `mock` remains
  the permanent default.

## 7. Next Required Evidence

A concise checklist a developer can take to Setu's own developer resources to resolve the
remaining blockers - in priority order:

1. **Sign in to Setu Bridge, create an FIU app under the AA Gateway product** (per the documented
   quickstart flow), and read the **account-specific, authenticated API reference/Postman
   collection** Setu provides at that point - specifically to answer: *does an AA Gateway request
   use `x-client_id`/`x-client-secret` directly, or must those first be exchanged for a bearer
   token via `POST /api/v2/auth/token`, and on which exact host?*
2. If step 1 does not conclusively answer that question, contact Setu's developer support/developer
   relations channel directly and ask the same question in writing, referencing the AA Gateway
   product specifically (not Setu Bridge in general).
3. While obtaining that access, also capture: a real (sandbox, dummy-data) `GET /sessions/:id`
   response in full, to confirm the exact transaction-nesting JSON shape (gap 5); whether any list
   endpoint relevant to `list_transactions`/`list_linked_institution_accounts` returns a
   pagination cursor/next-page token under realistic data volumes (gap 3); and any documented or
   observed rate limit (gap 4).
4. Do not proceed to implementation until step 1 (or step 2) produces a written, AA-Gateway-specific
   answer - not an inference from a different Setu product's documentation, and not an assumption
   carried over from this document.

## 8. Explicit Non-Goals

- No production bank access is implemented, attempted, or enabled anywhere in this repository.
- No payment capability exists or is planned.
- No transfer capability exists or is planned.
- No withdrawal capability exists or is planned.
- No PIN, CVV, OTP, or password of any kind is requested, accepted, or stored anywhere in this
  repository.
- No screen scraping or browser automation against any financial website is used or planned.
- **No real API call - sandbox or production - was made in this phase.** Every finding in §2 is a
  re-examination of Phase F11's own already-gathered evidence; this phase performed no new network
  request of any kind.
