# Automatic Transaction Sync — Provider Integration Guide

This document describes the `BankSyncProvider` abstraction (`backend/app/sync/provider/`), what
a future real financial-data provider integration must and must not do, and the security boundary
that protects the rest of the application from it. It exists so any future engineer — human or
AI — implementing a real provider has one place to read before writing a line of provider code.

`CLAUDE.md` remains the permanent engineering constitution for this project; this file is a
detailed elaboration of its §14/§20 rules as they apply specifically to `app.sync.provider`. If
anything here ever appears to conflict with `CLAUDE.md`, `CLAUDE.md` wins.

---

## 1. What this application is — and is not

- This application is a **personal finance tracker** that can optionally **read** transaction
  history from a linked external account, to save the user manual entry.
- **This application is not a payment processor.** It never initiates, authorizes, confirms, or
  represents a payment, transfer, withdrawal, or any other movement of money, in any code path,
  for any provider, real or mock.
- **No banking authentication secret is ever stored or requested** by this application: no bank
  password, no net-banking password, no UPI PIN, no ATM/card PIN, no CVV, no OTP, no payment
  authorization token. A real provider integration only ever hands this application an **opaque
  consent identifier it manages entirely on its own side** — the same way `MockSyncProvider`
  already does today.
- **No screen scraping is permitted.** A real provider integration must be a legitimate,
  authorized, read-only financial-data API (e.g. an RBI-licensed Account Aggregator in India, or
  an equivalent regulated open-banking/read-only data API elsewhere) — never a scraper that logs
  into a bank's consumer website/app on the user's behalf.
- Every transaction a provider reports must enter the **existing** Transactions ledger through the
  **existing** `app.services.transaction_service.create_transaction` path — there is not, and must
  never be, a second transaction-writing code path for synced data (see §6).

## 2. Current state (as of Phase F8)

`SYNC_PROVIDER=mock` remains the default and the only provider that does anything real (against
deterministic fixture data). `SYNC_PROVIDER=setu_sandbox` (added in Phase F8) selects
`SetuSandboxSyncProvider` — a **structural seam only**: every one of its five `BankSyncProvider`
operations currently raises `SetuSandboxNotImplementedError` rather than making any network call.
See §9 for exactly why, and what's required before that changes. Setting `SYNC_PROVIDER` to
anything other than `mock`/`setu_sandbox` still raises a clear `RuntimeError` at provider-selection
time (`app/sync/provider/factory.py`) rather than silently falling back to the mock or pretending a
real integration ran. **No real, working provider integration, SDK, or production credential is
implemented in this or any prior phase.**

## 3. The `BankSyncProvider` boundary

`app/sync/provider/base.py` defines the entire surface a provider — mock or real — may ever
expose. It is deliberately, permanently **read-only**, and consists of exactly five operations:

| Method | Purpose |
|---|---|
| `initiate_link(user_id, institution_hint=None)` | Starts a consent flow; returns a redirect URL and an opaque, short-lived `consent_handle`. |
| `complete_link(consent_handle)` | Finishes the consent flow; returns the resulting `consent_id`, its status/expiry, and the institution accounts it covers. |
| `list_linked_institution_accounts(consent_id)` | Re-lists the accounts an existing consent covers (e.g. if a provider lets a user add accounts to a consent later, or for a future "manage linked accounts" refresh flow — not currently called by `sync_service`, but part of the required boundary). |
| `list_transactions(consent_id, external_account_id, since, until)` | Pulls transaction history for one account, bounded by date range. |
| `revoke_consent(consent_id)` | Revokes the consent on the provider's own side. |

**No other method may ever be added to this Protocol.** In particular, never add anything that
could:
- initiate, authorize, or confirm a payment, transfer, or withdrawal;
- change an account's balance directly;
- accept or transmit a PIN, CVV, OTP, password, or other payment-authorization credential;
- perform any action beyond reading consent/account/transaction data and revoking a consent.

A `BankSyncProvider` implementation must be `runtime_checkable` against the `Protocol` in
`base.py` — a real class implements this Protocol structurally (duck typing), it does not need to
literally subclass anything.

### Provider selection stays isolated from orchestration

`app.services.sync_service` never imports `MockSyncProvider` (or any future
`SomeRealSyncProvider`) directly — it only ever calls `app.sync.provider.factory.get_sync_provider()`
and programs against the `BankSyncProvider` Protocol. **A real provider implementation is added
entirely inside `app/sync/provider/`** (a new module, e.g. `app/sync/provider/account_aggregator.py`)
and wired into exactly one place — `build_sync_provider()` in `factory.py` — mirroring how
`app.ai.classifier.factory` selects `AnthropicMerchantClassifier` vs. `MockMerchantClassifier`, and
how `app.storage.factory` / `app.ocr.factory` make their own provider selections. `sync_service.py`
itself should require **zero changes** to adopt a real provider, beyond whatever `Settings` fields
`factory.py` needs to read to construct it (see §8).

## 4. The normalized transaction contract

Every provider — mock or real — must resolve to `app.sync.provider.base.ExternalTransaction`
before a transaction reaches the sync pipeline:

| Field | Type | Notes |
|---|---|---|
| `external_transaction_id` | `str` | Opaque, provider-defined. Used verbatim as the primary basis of the transaction's idempotency key (see §7). |
| `external_account_id` | `str` | Opaque, provider-defined; must match the `LinkedAccount.external_account_id` the sync was requested for — validated, never trusted (`_ingest_one` step 1). |
| `occurred_on` | `date` | **Date-only, deliberately.** Most bank/UPI statement feeds report a date, not a precise timestamp; `_ingest_one` stores it as midnight UTC on that date (`datetime.combine(occurred_on, time.min, tzinfo=UTC)`). If a future provider supplies genuine time-of-day precision, preserving it would be an explicit, separate architecture change — not implied by this contract, and out of scope for F6. |
| `amount_minor` | `int` | Non-negative integer minor units (paise) — never a float, never negative; the ledger's own sign is implied by `direction`/transaction type, never stored as a signed amount (CLAUDE.md §13). |
| `direction` | `Literal["debit", "credit"]` | Maps to `TransactionType.EXPENSE` / `TransactionType.INCOME` respectively. |
| `narration` | `str` | The raw, unstructured statement text (e.g. `"UPI/DR/399/SWIGGY/paytm@ybl/..."`). Untrusted, unparsed here — `app.services.merchant_normalization` consumes it later. Stored verbatim (truncated to 500 chars) as the transaction's `description`. |

**Deliberately absent: `currency`.** This application enforces one base currency per user
(CLAUDE.md §4/§13) — the internal ledger `Account` a `LinkedAccount` posts into is created with
the user's own base currency at link-completion time (`_resolve_user_currency`), and every
provider transaction is assumed to already be denominated in that same currency. A provider that
can report multi-currency transactions on a single linked account is out of scope for the current
single-base-currency architecture and would require an explicit, separate redesign — never a
field silently bolted onto `ExternalTransaction`.

**Do not add** any other field — no merchant category (categorization is this application's own,
existing deterministic + optional-AI pipeline, never the provider's), no balance, no account
number, no counterparty PII (name/email/phone/address), no geolocation, no device/session
metadata. If a real provider's raw API response contains any of this, the provider adapter itself
is responsible for discarding it before ever constructing an `ExternalTransaction` — none of it
may cross into `app.sync.provider.base`'s dataclasses.

## 5. The normalized linked-account contract

`app.models.linked_account.LinkedAccount` is the complete, final set of fields a link may ever
carry. A real provider adapter must be able to populate all of the non-nullable ones and nothing
more:

| Field | Notes |
|---|---|
| `user_id`, `account_id` | This application's own identifiers — never provider-supplied. |
| `provider` | Which `BankSyncProvider` implementation created this link (e.g. `"mock"`, or a real provider's own `name`) — never a specific bank name (see `external_institution_name` below). |
| `external_institution_name` | Human-readable institution name (e.g. "HDFC Bank"). |
| `external_account_id` | Opaque, provider-defined identifier for this specific account. |
| `fip_reference` | Opaque Financial Information Provider reference (Account-Aggregator-specific concept) — nullable, since not every provider model has one. |
| `consent_id` | Opaque consent handle the provider manages on its own side — **never a credential**. |
| `consent_status` | One of `pending / active / paused / revoked / expired` (`SyncConsentStatus`). |
| `consent_expires_at` | Nullable; when present, enforced independently of `consent_status` (§6). |
| `masked_account_ref` | **Masked only** (e.g. `"XX1234"`) — never a full account number. |
| `last_synced_at`, `last_sync_status` | This application's own sync bookkeeping. |

**There is no field, and there must never be one added, for**: a bank password, net-banking
password, UPI PIN, card/ATM PIN, CVV, OTP, security question/answer, biometric token, or any other
authentication/authorization credential of any kind. If a real provider's own consent/link
response includes anything resembling one, the provider adapter must never pass it through to
`LinkedAccount` — discard it before it leaves the adapter.

## 6. Consent lifecycle

```
Not connected
    │  initiate_link()
    ▼
Link initiated  ─── (no LinkedAccount row persisted yet - see app.services.sync_service.initiate_link;
    │                the provider hands back everything the client needs: redirect_url + consent_handle)
    │  user completes consent in their own bank/AA app, client calls complete_link(consent_handle)
    ▼
Consent completed → Linked  ─── LinkedAccount row created, consent_status from the provider's own
    │                             response (mock always reports "active" - see complete_link),
    │                             account_id auto-mapped to a new internal ledger Account immediately
    │                             (never left pending user action)
    │  trigger_sync()
    ▼
Syncing  ─── transient; a SyncRun row tracks this specific attempt's own status independently of
    │         the LinkedAccount's overall state
    ▼
Synced  ─── last_synced_at / last_sync_status updated on LinkedAccount; consent_status unchanged
    │
    │  revoke_link()                              OR  consent_expires_at passes (Phase F6)
    ▼                                                  ▼
Revoked (consent_status=REVOKED,               Effectively expired: trigger_sync now checks
provider.revoke_consent() called)              consent_expires_at independently of
                                                consent_status (see below) - future sync is
                                                rejected even if the provider hasn't (yet)
                                                reported consent_status="expired" itself
```

**Revocation preserves already-imported transactions.** `revoke_link` only ever sets
`consent_status = REVOKED` and calls `provider.revoke_consent()` — it never touches, deletes, or
hides any `Transaction` row already created through this link. `trigger_sync` rejects any further
attempt once `consent_status != ACTIVE` (`ValidationAppError`, tested in
`test_revoke_link_marks_consent_revoked_and_blocks_further_sync`).

**Expiry is checked independently of `consent_status` (Phase F6).** A provider's own reported
`consent_status` can lag reality — nothing in this architecture depends on a background job to
proactively flip a stale consent to `EXPIRED` before `trigger_sync` would otherwise use it.
`trigger_sync` now also rejects a sync attempt whenever `consent_expires_at` is set and has
already passed, regardless of what `consent_status` currently says
(`test_trigger_sync_rejects_an_expired_consent`). A `None` expiry (a provider that reports none)
is never treated as expired.

`SyncConsentStatus` also defines `PENDING` and `PAUSED`, ready for a real provider that reports
either — `_parse_consent_status` already accepts any valid value generically; only `MockSyncProvider`
never produces anything but `"active"` today.

## 7. Failure handling this architecture already represents

| Failure | How it's handled today |
|---|---|
| Provider timeout / provider unavailable | `trigger_sync`'s call to `provider.list_transactions(...)` is wrapped in a generic `except Exception` — the `SyncRun` is marked `FAILED` with a capped, safe error message; no transaction is created; nothing is raised to the caller. |
| Consent revoked | Rejected before any provider call is even made (`consent_status != ACTIVE` check). |
| Consent expired | Rejected before any provider call is even made (`consent_expires_at` check, Phase F6) — independent of the revoked check above. |
| Malformed provider transaction (wrong account, invalid direction, fails `TransactionCreate` validation) | That single transaction is skipped (`_IngestOutcome.FAILED`) — every other transaction in the same batch still ingests; the `SyncRun` becomes `PARTIAL` if some succeeded, `FAILED` only if none did (`_decide_run_status`). |
| Duplicate external transaction | The idempotency-key pre-check (backstopped by a real database unique constraint) marks it `SKIPPED_DUPLICATE` — never a duplicate ledger row, never a duplicate AI-classification attempt (the dedup check runs before categorization in `_ingest_one`). |
| Partial sync failure | `_decide_run_status` distinguishes `SUCCESS` / `PARTIAL` / `FAILED` from the fetched/created/skipped/failed counts — a batch is never all-or-nothing. |

A real provider adapter should raise ordinary Python exceptions for its own transport/API-level
failures (timeouts, HTTP errors, auth failures) from `list_transactions`/`complete_link`/etc. —
`sync_service` already treats any exception from those calls as a provider failure generically. Do
not invent provider-specific exception handling inside `sync_service.py`; if a real provider needs
special retry/backoff behavior, that belongs entirely inside the provider adapter module, never in
the orchestration layer.

## 8. Implementing a real provider — checklist

None of this is implemented in F6. When a legitimate, authorized, read-only provider integration
is actually undertaken:

1. Add a new module under `app/sync/provider/` (e.g. `account_aggregator.py`) implementing the
   exact `BankSyncProvider` Protocol from `base.py` — no more, no fewer methods.
2. Add only the configuration `Settings` fields genuinely required (API base URL, an API key/client
   credential, timeout) — following the existing lazy/optional pattern used by
   `app.ai.provider.anthropic_provider.AnthropicProvider` and
   `app.ai.classifier.anthropic.AnthropicMerchantClassifier` (lazy SDK import, never required for
   the app to start, `SYNC_PROVIDER=mock` remains the safe default).
3. Wire the new class into `build_sync_provider()` in `factory.py` only — `sync_service.py` should
   need zero changes.
4. Never store a raw account number, balance, or any authentication credential on `LinkedAccount`
   or in any log line — see §5.
5. Add provider-specific tests mirroring the existing `test_sync_provider.py`/`test_sync_service.py`
   coverage (link lifecycle, transaction mapping, error mapping) — using a fake/recorded-response
   double for the real provider's HTTP client, never a real network call in the test suite.
6. Never bypass `transaction_service.create_transaction` — every ledger write still goes through
   the exact same path a manually-entered or AI-assisted transaction takes.

## 9. The Setu sandbox seam (Phase F8)

**Which route was selected, and why (based only on `SYNC_PROVIDER_RESEARCH.md`):** Setu, because
that research document's §E found it "the most immediately self-serviceable" of the sandboxes
surveyed (publicly documented, pre-seeded sandbox keys, a published Postman collection, and
explicit personal-finance-management support in its mock data) and its own §L named Setu's sandbox
as the concrete next step. Selecting Setu here is an *engineering* choice about which sandbox to
build the seam against first — it is not, and must not be read as, a decision about which provider
(or whether any provider) this application will use in production; that remains the unresolved
business/legal decision described in `SYNC_PROVIDER_RESEARCH.md` §D/§F.

**Exact sandbox-only boundary:** `app/sync/provider/setu_sandbox.py`'s `SetuSandboxSyncProvider`
implements the `BankSyncProvider` Protocol structurally (all five methods exist, with the correct
signatures and return types), but **every method currently raises
`SetuSandboxNotImplementedError`** instead of making any network call. Selecting
`SYNC_PROVIDER=setu_sandbox` therefore cannot connect to any account, real or sandboxed, today —
it is a compile-time-checkable contract seam, not a working integration.

**Why it stops here rather than guessing:** `SYNC_PROVIDER_RESEARCH.md` was built from Setu's
public documentation *landing pages*, and captured the conceptual flow shape (consent-create →
redirect → status fetch → FI-data fetch → decrypt) but never captured concrete, implementable
specifics — exact endpoint paths, exact request/response JSON schemas, or the exact authentication/
signing mechanism. Phase F8's instructions were explicit that inventing any of those would be
unsafe. See `app/sync/provider/setu_sandbox.py`'s own module docstring for the full reasoning and
the exact numbered checklist of what a future implementer must confirm from Setu's *live* API
reference before writing a single real HTTP call.

**Required credentials/configuration, if any:** none are required today — `SetuSandboxSyncProvider`
never reads them for any real purpose yet. Three optional, sandbox-only `Settings` fields exist as
placeholders for when real implementation begins: `SETU_SANDBOX_BASE_URL`, `SETU_SANDBOX_CLIENT_ID`,
`SETU_SANDBOX_CLIENT_SECRET` (see `.env.example`). Their field names (`client_id`/`client_secret`)
are a *placeholder shape*, not a confirmed fact about Setu's actual auth mechanism — that must be
verified against Setu's live API reference too.

**What is intentionally NOT implemented:** all five operations' actual HTTP calls; response
parsing; the AA encrypted-data-envelope decryption step; any mapping from a real Setu response
into `ExternalTransaction`/`LinkedInstitutionAccount`/`LinkCompletion`; any retry/backoff behavior;
any webhook receiver for asynchronous consent-status notifications (see `SYNC_PROVIDER_RESEARCH.md`
§G's note that this would be a new HTTP route, not a `BankSyncProvider` change).

**What must be completed before production financial-data access:** everything in §8 above, plus
every item in `app/sync/provider/setu_sandbox.py`'s own docstring checklist, plus — as established
in `SYNC_PROVIDER_RESEARCH.md` §D/§K — the underlying business/legal FIU-eligibility question,
which is entirely outside this seam's or this document's scope.

**This application has no payment or money-movement capability, in the mock provider, in this
sandbox seam, or anywhere else in the codebase** — restated here for emphasis, not because
anything about this phase changed it. See §1.
