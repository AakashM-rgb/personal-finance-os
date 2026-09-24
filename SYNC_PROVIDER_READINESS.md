# Real Sandbox Connectivity Readiness Audit (Phase F10)

## 1. Audit date

2026-09-24

## 2. Provider audited

Setu (Setu Bridge Account Aggregator gateway) — the sandbox route selected in Phase F8, based on
`SYNC_PROVIDER_RESEARCH.md` §E/§L. No other provider was re-evaluated in this phase; see
`SYNC_PROVIDER_RESEARCH.md` for why Setu specifically was chosen over Finvu/OneMoney/others.

## 3. Readiness state

# `NOT_READY_DOCUMENTATION_GAP`

The existing architecture (`BankSyncProvider`, the factory, `sync_service.py`, the credential
configuration) is confirmed **sufficient** — see §6/§9. The blocker is exclusively that this
repository does not yet have concrete, authoritative, implementable API detail for Setu's sandbox
(exact base URL, exact request/response schemas, exact authentication mechanism, pagination,
error format). Per this phase's own instructions, **no external API call was made**, because not
all five required preconditions were met (see §5).

## 4. Verified documentation sources

Every source below was already captured in `SYNC_PROVIDER_RESEARCH.md` (Phase F7, 2026-09-24 web
research); no new external source was fetched in this phase — the task instructed reusing F7's
research "unless an additional current public source is genuinely required," and none was found
to be required for an audit (as opposed to an implementation).

- [Account Aggregator quickstart — Setu Docs](https://docs.setu.co/data/account-aggregator/quickstart)
- [API integration — AA Gateway API Integration — Setu Docs](https://docs.setu.co/data/account-aggregator/api-integration)
- [Account Aggregator API reference — Setu Docs](https://docs.setu.co/data/account-aggregator/api-reference)
- [FIU go-live process — Setu Docs](https://docs.setu.co/data/account-aggregator/licenses-and-go-live/go-live)
- [Licenses required to participate in AA — Setu Docs](https://docs.setu.co/data/account-aggregator/licenses-and-go-live/licenses)
- [NBFC-Account Aggregator (AA) API Specification v2.0.0 — ReBIT](https://specifications.rebit.org.in/artefacts/NBFC-AA_API_Specification_v2.0.0.pdf)
- [ReBIT specifications portal](https://specifications.rebit.org.in/) (schema documentation index, e.g. `deposit.xsd`)
- [Finvu sandbox overview](https://finvu.github.io/sandbox/) (cross-reference only — general AA-ecosystem sandbox/UAT conventions, not Setu-specific)

## 5. Known sandbox requirements vs. current repository support

Each row states what the source **establishes**, and whether this repository currently has enough
information to implement against it.

| Requirement | Documented? | Source establishes | Repository has enough to implement? |
|---|---|---|---|
| Sandbox base URL | **No** | Only that a sandbox exists and is reachable via Setu Bridge's developer console; the actual base URL/hostname was never captured in F7's research | **No** |
| Authentication method | **No** | Setu's docs mention "pre-seeded sandbox keys"; the *exact* mechanism (bearer API key header? OAuth2 client-credentials? signed-request scheme like Finvu's documented JWS requirement?) was never confirmed for Setu specifically | **No** |
| Application/client credential requirements | **No** | Only that an "FIU app" is created in Setu Bridge, yielding some credential — exact field names/shape unconfirmed | **No** — `SETU_SANDBOX_CLIENT_ID`/`SETU_SANDBOX_CLIENT_SECRET` (Phase F8) are explicitly documented as a *placeholder shape*, not a confirmed fact |
| Consent/link initiation flow | **Partially** | Conceptual shape only: create a consent → redirect user to AA app/web flow → opaque handle returned | No concrete request/response schema |
| Consent completion/callback flow | **Partially** | Conceptual shape (status fetch after redirect); Finvu's docs (cross-ecosystem, not Setu-specific) additionally mention an async webhook for approve/reject/revoke notifications | No concrete schema; whether Setu specifically requires/offers a webhook, and its exact contract, is unconfirmed |
| Linked-account/institution-account retrieval | **Partially** | Conceptual ("discover accounts" style call) | No concrete schema |
| Transaction retrieval | **Partially** | Conceptual (an FI-data-fetch request, an encrypted response per the ReBIT cryptographic envelope, decrypted by the FIU); ReBIT's `deposit.xsd` schema exists publicly but was not parsed field-by-field in F7 | No concrete request schema, no decrypted-response field mapping |
| Consent revocation | **Partially** | Conceptual (a direct revoke call exists in the ecosystem) | No concrete endpoint/schema |
| Pagination | **No** | Not addressed anywhere in F7's research | **No** — genuinely unknown whether/how Setu paginates transaction or account-list responses |
| Date-range parameters | **No** | `BankSyncProvider.list_transactions`'s own `since`/`until` are this application's own abstraction, not confirmed to map onto any specific Setu request parameter name/format | **No** |
| Error format | **No** | Not captured | **No** |
| Rate limits | **No** | Not captured for Setu specifically | **No** |
| Webhook/event behavior | **Partially** | Generic AA-ecosystem pattern documented for a different provider (Finvu); not confirmed for Setu | **No** Setu-specific confirmation |
| Test/sandbox data availability | **Yes** | Setu's own docs explicitly state the sandbox supports "customisable mock data sources... for... personal finance management" | Confirmed available — this is the one item fully ready |
| Production-vs-sandbox separation | **Partially** | Standard, expected practice across the ecosystem (UAT dummy-data-only policy documented for a different provider, Finvu); Setu's own exact separation mechanism (distinct base URL? distinct key prefix?) unconfirmed | Conceptually expected, not concretely confirmed for Setu |

**Summary: 1 of 15 items is fully documented and implementable; the remaining 14 are either
partially known (conceptual shape only) or entirely undocumented in this repository's research.**
This is the concrete basis for the `NOT_READY_DOCUMENTATION_GAP` determination in §3.

## 6. Current repository support (architecture side)

Confirmed sufficient, unchanged from Phase F8/F9's own conclusions, re-verified in this audit by
re-reading `base.py`, `factory.py`, `sync_service.py`, `api/v1/sync.py`, and the relevant
repositories/models fresh:

- `BankSyncProvider`'s five methods (`initiate_link`, `complete_link`,
  `list_linked_institution_accounts`, `list_transactions`, `revoke_consent`) map cleanly onto the
  conceptual AA flow shape documented in §5 — see `SYNC_PROVIDER.md` §9 for the method-by-method
  mapping, re-audited here and found still accurate.
- **No protocol expansion is required or justified.** No `BankSyncProvider` method needs a new
  parameter, and no new method is needed — including for the webhook question in §5: a webhook
  receiver, if Setu's real flow needs one, is a **new HTTP route** (e.g. a future
  `POST /api/v1/sync/webhook`) that would call the *same* `complete_link`-shaped logic already in
  `sync_service.py`, not a `BankSyncProvider` Protocol change. `app/api/v1/sync.py` currently has no
  such route — confirmed by direct read; adding one is future work, not a gap in the current
  Protocol.
- `app/sync/provider/setu_sandbox.py` remains exactly as built in Phase F8: a **structural stub**.
  All five methods exist with correct signatures and return types (satisfying `isinstance(...,
  BankSyncProvider)`), and every one raises `SetuSandboxNotImplementedError` rather than
  attempting a network call. It is not partially implemented, not fully implementable from
  currently-verified documentation (§5 proves why), and it does not incorrectly assume any
  provider behavior — it assumes nothing, because it does nothing yet. **No change was made to it
  in this phase**, per the task's instruction not to change it merely for style, and because no
  genuine correction was found necessary.

## 7. Exact gaps

Restating §5's table as a plain list, since this is what actually blocks implementation:

1. No confirmed Setu sandbox base URL.
2. No confirmed Setu authentication/signing mechanism.
3. No confirmed exact credential field shape (the current `client_id`/`client_secret` fields are
   an explicitly-labeled placeholder, not a verified fact).
4. No concrete request/response JSON schema for any of the five operations.
5. No confirmed pagination behavior.
6. No confirmed date-range parameter format.
7. No confirmed error-response format.
8. No confirmed rate limits.
9. No Setu-specific confirmation of webhook/event behavior (only a different provider's
   documented pattern, which may or may not match Setu's own).
10. No Setu-specific confirmation of the exact sandbox-vs-production separation mechanism (base
    URL difference, credential-prefix difference, or something else).

None of these are credential-configuration gaps (§5's "credential requirements optional" is
already correctly built — see §9) and none are architecture gaps (§6). They are all documentation
gaps: information that must come from Setu's own live, authenticated API reference
(`docs.setu.co/data/account-aggregator/api-reference`) or direct commercial/developer contact with
Setu, not from this repository's own further reasoning or this audit repeating itself.

## 8. Security boundary

Unchanged and re-confirmed in this audit — see §9's credential/configuration audit and the
existing, unmodified guarantees in `SYNC_PROVIDER.md` §1/§4/§5:

- Sandbox/UAT only; no production financial account was, or could be, connected to in this phase.
- No UPI PIN, ATM/card PIN, CVV, OTP, banking password, or payment-authorization credential is
  requested, stored, or has any field anywhere in `LinkedAccount`, `ExternalTransaction`,
  `LinkedInstitutionAccount`, `LinkCompletion`, `Settings`, or `SetuSandboxSyncProvider` — verified
  by direct read and by the existing forbidden-field test suite (`test_sync_provider.py`).
- No screen scraping, no browser automation against any financial website, anywhere in this
  codebase.
- No payment/transfer/withdrawal/debit/credit/beneficiary-management/balance-modification
  operation exists on `BankSyncProvider` or any implementation — confirmed by direct read of the
  Protocol (exactly five methods) and by the existing forbidden-method test suite.
- No parallel transaction ledger — `transaction_service.create_transaction` remains the sole
  ledger-writing path; nothing in this audit touched `sync_service.py`'s ingestion logic.
- AI categorization and its per-user opt-in (`ai_categorization_enabled`, default `false`) are
  entirely untouched by this phase — no file under `app/ai/` was read or modified.

## 9. Credential/configuration audit (Section D)

Re-verified directly against the current `app/core/config.py` and `.env.example`:

| Check | Result |
|---|---|
| Sandbox credentials are optional | **Confirmed** — `setu_sandbox_base_url`/`_client_id`/`_client_secret` are all `str \| None = Field(default=None, ...)` |
| Mock remains the default | **Confirmed** — `sync_provider: str = Field(default="mock", ...)` |
| `SYNC_PROVIDER=setu_sandbox` is required to select the sandbox provider | **Confirmed** — `build_sync_provider()` only returns `SetuSandboxSyncProvider` when `settings.sync_provider == "setu_sandbox"` exactly; no other condition selects it |
| Production credentials cannot silently activate the sandbox provider | **Confirmed** — already directly tested in Phase F9 (`test_setu_sandbox_credentials_alone_do_not_activate_the_provider`): setting the `SETU_SANDBOX_*` fields alone, without also setting `SYNC_PROVIDER`, leaves the active provider as mock |
| Secrets are never logged | **Confirmed** — `setu_sandbox.py` contains zero logging statements; directly tested in Phase F9 (`test_setu_sandbox_provider_failure_never_exposes_the_configured_secret`, `test_setu_sandbox_provider_failures_never_expose_consent_or_account_identifiers`) |
| Secrets are never returned by API responses | **Confirmed** — `LinkedAccountRead`/`SyncRunRead` (schemas/sync.py) have no field for any of the new `Settings` fields, and never will, since they're process configuration, not per-link data |
| Secrets are not persisted in database models | **Confirmed** — `LinkedAccount` (models/linked_account.py) has no credential column; the sandbox `Settings` fields are pure environment configuration, never written to any table |
| No secret is placed in frontend code | **Confirmed** — a direct search of `frontend/` for `setu_sandbox`/`SETU_SANDBOX`/`SetuSandbox` (any casing) returns zero matches |

**No configuration change was made in this phase** — the audit found the existing configuration
already correct on every point above.

## 10. Implementation plan (not applicable — state is NOT_READY)

Per the task's own instruction, an implementation plan is produced only when the state is
`READY_FOR_SANDBOX_IMPLEMENTATION`. Since this audit concluded `NOT_READY_DOCUMENTATION_GAP`, no
implementation plan is included here — inventing one would require inventing the exact endpoints,
schemas, and auth mechanism §7 lists as missing, which this phase's instructions explicitly forbid.

**What would need to happen before a plan could responsibly be written:** a developer (not this
audit) must obtain Setu sandbox developer-portal access and read the *live, authenticated* API
reference at `docs.setu.co/data/account-aggregator/api-reference`, recording the exact answers to
every row in §5's table. Once that is done, a follow-up phase can re-run this same audit structure
(Sections A–D) and, if every §5 row is then resolved, produce the implementation plan Section E
describes.

## 11. Explicit statement

**No production financial connectivity is enabled anywhere in this repository.** No real Setu
sandbox connection was established, attempted, or tested in this phase, in Phase F9, or in any
prior phase. `SetuSandboxSyncProvider` remains exactly the structural stub built in Phase F8: every
one of its five operations raises `SetuSandboxNotImplementedError` before any network code would
run. The only thing this repository can currently do, end to end, is exercise the deterministic
mock provider (`MockSyncProvider`) and locally-fixtured Setu-*shaped* test data (Phase F9) — never
a real external request to Setu, any other Account Aggregator, or any bank.
