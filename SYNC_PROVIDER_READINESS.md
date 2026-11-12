# Real Sandbox Connectivity Readiness Audit

**This document was created in Phase F10 (2026-09-24) and substantially updated in Phase F11
(2026-09-24, same day) after a deeper research pass against Setu's live API reference. It
supersedes the original F10 findings; the F10 conclusion (`NOT_READY_DOCUMENTATION_GAP`, based on
landing-page-only research) is preserved for context in §4/§7 rather than deleted.**

## 1. Audit date

2026-09-24 (F10 audit), updated 2026-09-24 (F11 deep-dive addendum)

## 2. Provider audited

Setu (Setu Bridge Account Aggregator gateway) — the sandbox route selected in Phase F8, based on
`SYNC_PROVIDER_RESEARCH.md` §E/§L. No other provider was re-evaluated in this phase; see
`SYNC_PROVIDER_RESEARCH.md` for why Setu specifically was chosen over Finvu/OneMoney/others.

## 3. Readiness state

# `NOT_READY_DOCUMENTATION_GAP`

**Unchanged from F10's category, but the gap itself has narrowed dramatically.** Phase F11 found
concrete, implementable, cross-referenced documentation for nearly every required item in §5 —
base URLs, consent lifecycle endpoints, transaction-fetch endpoints, revocation, error format,
webhook event shape, and date-range parameters. **The single remaining blocker is authentication**:
Setu's Account Aggregator product's own specific authentication mechanism was not confirmed, and a
dedicated OAuth-token-exchange mechanism found in Setu's docs explicitly states it is
"product-specific," without confirming it covers the AA Gateway product. Since every one of the
five `BankSyncProvider` operations requires a successful authenticated request, an unresolved
authentication mechanism means "implement all required read-only operations without guessing" is
not yet achievable — so the state remains `NOT_READY`, not `READY`. See §5/§7 for the full,
item-by-item reasoning, and §10 for exactly what would resolve this.

## 4. Verified documentation sources

**Phase F10** sources (landing/marketing pages, found via web search): Setu's quickstart,
FIU-go-live, and licenses pages; ReBIT's API Specification v2.0.0; Finvu's sandbox overview
(cross-ecosystem context only). Full list in `SYNC_PROVIDER_RESEARCH.md`.

**Phase F11** sources (Setu's live API *reference* pages, fetched directly — the primary new
evidence this update is based on):

| # | URL | What it establishes |
|---|---|---|
| 1 | [`/data/account-aggregator/api-integration/consent-flow`](https://docs.setu.co/data/account-aggregator/api-integration/consent-flow) | AA Gateway base URLs, consent create/get/revoke endpoints and schemas, consent redirect URL pattern |
| 2 | [`/data/account-aggregator/api-integration/data-apis`](https://docs.setu.co/data/account-aggregator/api-integration/data-apis) | Data-session (transaction fetch) create/poll endpoints, transaction field names, error schema |
| 3 | [`/data/account-aggregator/consent-object`](https://docs.setu.co/data/account-aggregator/consent-object) | Full consent request/response object field list |
| 4 | [`/data/account-aggregator/api-integration/account-availability-apis`](https://docs.setu.co/data/account-aggregator/api-integration/account-availability-apis) | The account-availability (phone-number-based discovery) endpoint — determined NOT to be the right mapping for our `list_linked_institution_accounts` (see §6) |
| 5 | [`/data/account-aggregator/api-integration/fip-apis`](https://docs.setu.co/data/account-aggregator/api-integration/fip-apis) | FIP-listing endpoints and error schema (cross-confirms the error format seen in source 2) |
| 6 | [`/data/account-aggregator/api-integration/notifications`](https://docs.setu.co/data/account-aggregator/api-integration/notifications) | Webhook event types and payload shape for consent and FI-data events |
| 7 | [`/data/account-aggregator/overview`](https://docs.setu.co/data/account-aggregator/overview) | Confirms an "HTTP APIs" building block; did not resolve authentication or rate limits |
| 8 | [`/data/account-aggregator/quickstart`](https://docs.setu.co/data/account-aggregator/quickstart) | Names `x-product-instance-id`/`x-client_id`/`x-client-secret` as sandbox setup outputs — a DIFFERENT credential shape than source 9's token exchange |
| 9 | [`/dev-tools/bridge/v1/org-settings/api-keys/oauth`](https://docs.setu.co/dev-tools/bridge/v1/org-settings/api-keys/oauth) | A Setu Bridge OAuth token-exchange mechanism (`POST /api/v2/auth/token` on `uat.setu.co`/`prod.setu.co`) — explicitly states it is product-specific, does not confirm AA Gateway coverage |

**Methodological caveat**: sources 1–9 were retrieved via automated web-fetch tooling that itself
uses an AI model to summarize page content — not a human directly reading rendered HTML. Findings
repeated consistently across 2+ independent fetches (the base URLs, the Bearer-token requirement,
the error schema) carry higher confidence; single-source findings (the exact OAuth token endpoint,
the webhook payload field names) carry lower confidence and should be independently re-verified by
a human developer, ideally with authenticated Setu Bridge dashboard access, before any
implementation is written.

## 5. Known sandbox requirements vs. current repository support (updated)

| Requirement | F10 status | F11 status | Confidence |
|---|---|---|---|
| Sandbox base URL | Not documented | **`https://fiu-sandbox.setu.co`** (production: `https://fiu.setu.co`) | High — consistent across sources 1 and 5 |
| Authentication mechanism | Not documented | **Unresolved** — `Authorization: Bearer <token>` is consistently required (sources 1, 4), but where that token comes from for the AA Gateway product specifically is not confirmed. Source 9 documents a token-exchange flow but says it's product-specific; source 8 instead names static `x-client_id`/`x-client-secret`/`x-product-instance-id` values | Low — the single blocking gap |
| Credential/client config | Not documented | Setu Bridge issues `x-product-instance-id`, and either (a) a `clientID`/`secret` pair exchanged for a bearer token (source 9), or (b) `x-client_id`/`x-client-secret` used directly (source 8) — which of these two shapes applies is the same unresolved question as above | Low |
| Consent/link initiation | Conceptual only | **`POST /consents`** — request: `consentDuration`, `vua`, `dataRange{from,to}`, `context`, `additionalParams`; response: `id`, `url` (redirect target), `status`, `detail`, `traceId` | High — sources 1 and 3 agree |
| Consent completion/callback | Conceptual only | **`GET /consents/:id`** (optionally `?expanded=true`) for polling; response includes `status` (`PENDING\|ACTIVE\|REJECTED\|...`) and, when expanded, `accountsLinked` — **plus** an async webhook (`CONSENT_STATUS_UPDATE` event, source 6) as an alternative/complement to polling | High for the polling shape; medium for the webhook (single-source) |
| Linked institution/account retrieval | Conceptual only | **Engineering correction**: NOT `POST /v2/account-availability` (source 4 — that takes a `mobileNumber`, not a `consent_id`, and appears to be a *pre-consent* discovery check, not "which accounts does this granted consent cover"). The actual source is almost certainly the `accountsLinked` field already returned by `GET /consents/:id?expanded=true` (source 1) | Medium — this is cross-referenced reasoning against our own method signature, not a single direct quote naming this exact mapping |
| Transaction retrieval | Conceptual only | **`POST /sessions`** (request: `consentId`, `dataRange{from,to}`, `format`) to start a fetch, then **`GET /sessions/:id`** to poll/retrieve; per-account statuses (`PENDING/READY/DELIVERED/TIMEOUT/DENIED`), combined session status (`PENDING/PARTIAL/COMPLETED/EXPIRED/FAILED`); transaction fields named: `amount`, `currentBalance`, `mode`, `narration`, `reference`, `transactionTimestamp`, `txnId`, `type`, `valueDate` | High for endpoints/field names; the full nested response shape (how transactions nest under accounts under FIPs under one session) was not fully captured |
| Consent revocation | Conceptual only | **`POST /v2/consents/:request_id/revoke`** (empty body); response `{status: "REVOKED", traceId}` | High — source 1 |
| Pagination | Not documented | **Still not documented** — the FIP-list endpoint (source 5) returns a flat array with no page/cursor parameters shown; unclear whether transaction/account lists ever paginate | Unresolved |
| Date-range parameters | Not documented | **`dataRange: {from, to}`**, ISO-8601 timestamps — used identically in both consent creation and data-session creation | High — sources 1, 2, 3 agree |
| Request/response schemas | Not documented | Substantially documented for consent + data-session + FIP-list (see rows above); the full transaction-nesting shape within a completed data session remains incomplete | Medium-high |
| Error format | Not documented | **`{errorMsg, errorCode, txnid, timestamp, ver?}`** | High — sources 2 and 5 independently agree |
| Rate limits | Not documented | **Still not documented anywhere retrieved** | Unresolved |
| Webhook/event contract | Not documented (only a different provider's pattern) | Setu-specific now: consent events (`ACTIVE/REJECTED/REVOKED/PAUSED/EXPIRED`) and FI events (session/account status), payload shape with `type`, `data.status`, `timestamp`, `success`/`error` fields (source 6) — **signature/authenticity verification for incoming webhooks was explicitly confirmed absent from the documentation retrieved** | Medium for shape; confirmed gap for verification |
| Sandbox test data | Confirmed available | Unchanged — still confirmed available (F7/F10) | High |
| Production-vs-sandbox separation | Conceptual only | **Confirmed for the AA Gateway resource APIs** (`fiu-sandbox.setu.co` vs `fiu.setu.co`) — but a *different* pair of hosts (`uat.setu.co`/`prod.setu.co`) appeared on the OAuth page, and whether these are two genuinely separate services (auth host + resource host, a common and legitimate pattern) or a documentation inconsistency was not resolved | Medium |

**Summary: roughly 10 of 16 F10 items now have concrete, largely cross-referenced documentation.
The decisive remaining blocker is authentication** — every operation above depends on it, so its
ambiguity alone is sufficient to keep the overall state at `NOT_READY_DOCUMENTATION_GAP` even
though most other items have moved from "unknown" to "documented."

## 6. Terminology verification (Section B)

Unchanged from `SYNC_PROVIDER_RESEARCH.md` §C's findings, restated briefly per this phase's
request:

- **Account Aggregator (AA)**: an RBI-licensed NBFC that moves encrypted consent-based financial
  data between an FIP and an FIU, and nothing else ("blind pipe").
- **Financial Information Provider (FIP)**: the regulated institution holding the user's data
  (e.g. a bank).
- **Financial Information User (FIU)**: the entity *receiving* the data — legally restricted to
  entities already regulated by RBI, SEBI, IRDAI, or PFRDA (`SYNC_PROVIDER_RESEARCH.md` §C/§D).
- **Technology Service Provider (TSP)**: a technology vendor that builds the FIP/FIU *technical
  module* on behalf of a regulated client; a TSP does not itself need an NBFC-AA license, and does
  not change who the legal FIU of record is.
- **Setu's role**: Setu's own documentation describes creating an "FIU app" via Setu Bridge and
  calling Setu's gateway APIs to integrate with the AA ecosystem — consistent with Setu operating
  as a **TSP-style gateway/integration layer**, through which a client's own FIU-registered entity
  would access AA data. This document makes **no legal conclusion** about Setu's own licensing
  status or about whether using Setu's gateway changes the underlying FIU-eligibility requirement
  established in `SYNC_PROVIDER_RESEARCH.md` §D (it does not, per that document's own findings) —
  that remains a business/legal question outside this audit's scope.

## 7. Comparison to existing architecture (Section C)

For each `BankSyncProvider` method — corresponding Setu operation, required request data, expected
response, auth requirement, and whether our internal contract can represent it:

| `BankSyncProvider` method | Setu operation | Request needed | Response | Auth | Can our contract represent it? |
|---|---|---|---|---|---|
| `initiate_link(user_id, institution_hint)` | `POST /consents` | `vua`, `dataRange`, `consentDuration`, etc. (not `user_id`/`institution_hint` directly — these would inform *our own* request construction, never sent to Setu as-is) | `id`, `url`, `status` | Bearer token (mechanism unresolved) | **Yes** — `LinkInitiation(provider, consent_handle=id, redirect_url=url, expires_at)` maps cleanly |
| `complete_link(consent_handle)` | `GET /consents/:id?expanded=true` (and/or the `CONSENT_STATUS_UPDATE` webhook) | the consent `id` | `status`, `accountsLinked` | Bearer token (mechanism unresolved) | **Yes** — `LinkCompletion(consent_id, consent_status, consent_expires_at, accounts)`; `accounts` would be built from `accountsLinked` |
| `list_linked_institution_accounts(consent_id)` | Most likely `GET /consents/:id?expanded=true`'s `accountsLinked` field (see §5's correction) — **not** `POST /v2/account-availability` | the consent `id` | `accountsLinked` array | Bearer token (mechanism unresolved) | **Yes**, once the exact `accountsLinked` item shape is confirmed (currently only the field's existence is known, not its per-account fields) |
| `list_transactions(consent_id, external_account_id, since, until)` | `POST /sessions` then `GET /sessions/:id` | `consentId`, `dataRange{from,to}`, `format` | per-account/per-FIP transaction data (fields listed in §5) | Bearer token (mechanism unresolved) | **Yes** for the fields already named (`amount`, `narration`, `transactionTimestamp`/`valueDate`, `type`, `txnId`) — `ExternalTransaction`'s existing fields all have a plausible source field; the full nesting/pagination shape needs confirming before writing the mapping code |
| `revoke_consent(consent_id)` | `POST /v2/consents/:request_id/revoke` | the consent id | `{status: "REVOKED"}` | Bearer token (mechanism unresolved) | **Yes** — direct 1:1 mapping |

**The existing five-method `BankSyncProvider` Protocol remains sufficient. No expansion is
justified or was made.** Every Setu operation found maps onto one of the five existing methods;
nothing required a sixth method or a money-movement-shaped one.

**On the webhook**: Setu's notification mechanism (source 6) would, if used, need a **new HTTP
route** (e.g. `POST /api/v1/sync/webhook`) that authenticates/validates the incoming payload and
then calls the *same* underlying `sync_service` logic `complete_link`/a future consent-status-
refresh function already represents — **not** a `BankSyncProvider` Protocol change, consistent
with `SYNC_PROVIDER.md` §9's existing conclusion. This was not implemented in this phase (research
and documentation only).

## 8. Security review (Section D)

Every boundary re-confirmed as maintainable with what's now known, with one explicit caveat:

- No payment capability: confirmed — every Setu operation found is a data read/consent-lifecycle
  operation; nothing resembling a payment/transfer/withdrawal endpoint was found anywhere in the
  pages fetched.
- No PIN/CVV/OTP/password storage: confirmed — none of the documented request/response schemas
  (consent, data-session, revoke, webhook) contain such a field. The consent redirect flow itself
  is where a user would authenticate directly with their AA/bank app, per the ecosystem's own
  design (`SYNC_PROVIDER_RESEARCH.md` §I) — never a credential Setu or this application would ever see or transmit.
- No authorization-credential persistence: confirmed by the same schemas — nothing to persist that
  resembles one.
- No raw provider payload persistence: this remains an implementation *discipline* this codebase
  would need to maintain (map into `ExternalTransaction` immediately, never store the raw Setu
  response) — the documentation doesn't force this either way, so it stays a requirement on
  whoever eventually writes the adapter, exactly as `SYNC_PROVIDER.md` §8/§9 already states.
- No provider secret logging / no secret to frontend / no secret in database: unaffected by this
  phase's findings — these are properties of *our own* code (`setu_sandbox.py`, `Settings`,
  `LinkedAccount`), already verified in Phases F8–F10 and re-confirmed unchanged here (git status
  shows no production file touched this phase).
- Mock remains the default; explicit `SYNC_PROVIDER=setu_sandbox` selection required: unchanged,
  unaffected by this phase (no config file was touched).

**Explicit conflict check (as instructed): does Setu's documented credential requirement conflict
with this application's security boundary?** No conflict was found — whichever of the two
candidate auth mechanisms (§5) turns out to be correct, both are ordinary API credentials (a
client id/secret pair, or an OAuth client-credentials-style token), never a PIN/CVV/OTP/banking
password. Nothing retrieved in this phase requires storing anything this project's boundary
forbids. The unresolved item is *which* credential shape to configure, not whether a forbidden
credential type is required — so there is nothing to "stop and document as a conflict" beyond the
documentation-gap already recorded in §5.

## 9. Whether `BankSyncProvider` needs changes

**No.** Re-confirmed in §7: all five existing methods map cleanly onto documented (or
high-confidence-inferred) Setu operations. No method needs a new parameter, and no new method is
needed — including for the webhook, which belongs as a separate API route per §7's reasoning, not
a Protocol change.

## 10. Exact remaining gaps (what's still needed to reach READY)

1. **Setu's AA-Gateway-specific authentication mechanism**, confirmed from an AA-specific page (not
   inferred from a generic Bridge-wide OAuth page, and not inferred from a quickstart page that
   only names credential outputs without describing how they're used in a request). This requires
   either: a developer with actual Setu Bridge sandbox access reading the *authenticated* API
   reference/Postman collection Setu provides once an FIU app is created, or a direct
   confirmation from Setu's own support/developer relations channel.
2. Webhook signature/authenticity verification mechanism (needed only if/when a webhook receiver
   is actually built — not a blocker for the five core read-only methods themselves).
3. Pagination behavior for transaction/account result sets.
4. Rate limits.
5. The full nested response shape for a completed data-session's transaction data (how
   transactions nest under accounts under FIPs), so `ExternalTransaction` mapping code can be
   written without guessing field paths.
6. Resolution of the `fiu-sandbox.setu.co`/`fiu.setu.co` vs `uat.setu.co`/`prod.setu.co` host
   question — almost certainly two legitimately different services (a shared Bridge auth host plus
   a per-product resource host), but not explicitly confirmed as such by any source retrieved.

None of these require guessing to resolve — all six are answerable by a developer with actual
Setu Bridge sandbox/developer-portal access (which this phase deliberately does not have and did
not attempt to obtain), reading the authenticated, account-specific API reference Setu provides
once an FIU app exists, or by direct contact with Setu's developer relations.

## 11. Explicit statement

**No production financial connectivity is enabled anywhere in this repository, and no network
request — sandbox or production — was made in this phase or any prior phase.** Every finding in
§4/§5 came from fetching Setu's own **public** documentation pages, which require no account,
credential, or authentication to read. `SetuSandboxSyncProvider` (`backend/app/sync/provider/setu_sandbox.py`)
was not modified in this phase and remains exactly the structural stub built in Phase F8: every one
of its five operations still raises `SetuSandboxNotImplementedError` before any network code would
run. This document narrows the *documentation* gap; it does not itself provide connectivity, and
none should be inferred from it.
