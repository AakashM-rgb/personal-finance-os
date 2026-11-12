# Setu Provider Evidence Acquisition Gate (Phase F14)

## 1. Current Status

**`NOT_READY_DOCUMENTATION_GAP`**

Phase F14 (2026-09-25) is an evidence gate only. No production code, test, config, or migration was
changed. A follow-up in the same phase found and read Setu's official, public **AA Gateway OpenAPI
specification** (§2, P9). It is the source that the `getToken` link (P6) renders from. The spec
resolved three of the five blockers from the first F14 pass. Two remain, and each is now reduced to
one question:

1. **Sandbox token host (U1).** The spec fully defines the token request. It declares exactly one
   token server, `https://orgservice-prod.setu.co/v1`, with no sandbox/production label. The spec's
   resource servers, by contrast, are explicitly labelled `Sandbox` and `Production`. No official
   source says sandbox credentials are exchanged at this production-named host.
2. **Transaction direction values (U5b).** The spec fully defines the path to each deposit
   transaction and its field names. But every item field is an unconstrained `string`, with no enum
   and none required. The literal values of `type` (debit vs credit) are not documented for
   `GET /v2/sessions/{session_id}`.

Under the decision rule, neither item may be upgraded because a plausible answer exists. The state
stays `NOT_READY_DOCUMENTATION_GAP`.

## 2. Public Evidence Reviewed

**Network activity this phase:** we made only anonymous HTTP GET requests to publicly readable
documentation. Those were `docs.setu.co` pages, the public OpenAPI file those pages load
(`docs.setu.co/api-specs/data/account-aggregator.json`), and Setu's public Postman documenter. We also
ran two web searches. We made **no** request to any Setu API host (`fiu-sandbox.setu.co`,
`fiu.setu.co`, `uat.setu.co`, `prod.setu.co`, `orgservice-prod.setu.co`). We used no credential,
created no account, and submitted no consent.

**Extraction method:**

- **P1–P8** were read with a model-based page-fetch tool, which was asked for literal quotes or an
  explicit `NOT FOUND`.
- **P9** is machine-readable JSON. It was parsed directly with Python's `json` module, with no model
  in the loop, so its findings below are exact.

| # | Source | Product surface | What it literally establishes |
|---|---|---|---|
| P1 | [Consent flow](https://docs.setu.co/data/account-aggregator/api-integration/consent-flow) | AA Gateway | Headers `Authorization: Bearer access_token`, `x-product-instance-id`, `Content-Type: application/json`. Sandbox `https://fiu-sandbox.setu.co`, production `https://fiu.setu.co`. No token endpoint, expiry, or auth error example. |
| P2 | [Data APIs](https://docs.setu.co/data/account-aggregator/api-integration/data-apis) | AA Gateway | The prose example for `GET /sessions/:id` shows `transactions: {startDate, endDate}` only. A populated `transaction[]` appears only in the *Auto-Fetch notification* example, which is **not** used as evidence for the GET response. |
| P3 | [AA quickstart](https://docs.setu.co/data/account-aggregator/quickstart) | AA Gateway | Sandbox setup yields `x-product-instance-id`, `x-client_id`, `x-client-secret`. |
| P4 | [Account Availability APIs](https://docs.setu.co/data/account-aggregator/api-integration/account-availability-apis) | AA Gateway | Same headers as P1. Contains the P6 sentence. |
| P5 | [AA API reference](https://docs.setu.co/data/account-aggregator/api-reference) | AA Gateway | A client-rendered page. Its HTML references `/api-specs/data/account-aggregator.json` (= P9). |
| P6 | Sentence on P4 | AA Gateway | *"FIUs must use [Auth Mechanism](/data/account-aggregator/api-reference#/operation~getToken) to obtain an access token for authentication."* |
| P7 | [AA Postman collection "FIU V2 service - public"](https://documenter.getpostman.com/view/22511424/2s9Y5VU4MC) | AA Gateway | "Token API" `POST https://orgservice-prod.setu.co/v1/users/login`. Consistent with P9. |
| P8 | [Setu Bridge OAuth](https://docs.setu.co/dev-tools/bridge/v1/org-settings/api-keys/oauth) | Setu Bridge | `POST uat.setu.co / prod.setu.co /api/v2/auth/token` → `data.token`, `data.expiresIn`. Does not name AA Gateway. **Not used as AA evidence.** It is now also contradicted by P9 on path, body and response field. |
| **P9** | [AA Gateway OpenAPI spec](https://docs.setu.co/api-specs/data/account-aggregator.json) (`info.title: "AA Gateway"`, `info.description: "API spec for Setu AA gateway"`, `openapi 3.0.2`, version `v2`) | **AA Gateway (authoritative)** | See the P9 findings below. |

**P9 findings (exact):**

- **Root `servers`:**
  - `https://fiu-sandbox.setu.co/`, with `description: "Sandbox"`. Note the trailing slash.
  - `https://fiu.setu.co`, with `description: "Production"`.
- **`getToken`:**
  - Path item `/users/login`, which has its **own** `servers: [{"url": "https://orgservice-prod.setu.co/v1"}]`. That is one entry, with **no** `description`.
  - `POST`, summary "Get Token".
  - Header parameter `client`, required, `enum ["bridge"]`.
  - Request body `TokenAPIRequest`, all fields required:
    - `clientID` (string, "client_id obtained from bridge")
    - `grant_type` (`enum ["client_credentials"]`)
    - `secret` (string, "client secret obtained from bridge")
  - Response `200` is `TokenAPIResponse`:
    - `access_token` (string, **required**, "Bearer token")
    - `refresh_token` (string, optional, "Bearer token")
  - There is **no** token-type field and **no** expiry field.
  - Response `400` is `ErrorResponse`.
- **Resource paths**, all under `/v2`:
  - `POST /v2/consents`
  - `GET /v2/consents/{request_id}`, with an `expanded` query parameter
  - `POST /v2/consents/{request_id}/revoke`, which returns `{status}` with enum `PENDING|ACTIVE|PAUSED|REVOKED|EXPIRED|REJECTED`
  - `POST /v2/sessions`
  - `GET /v2/sessions/{session_id}`
  - `GET /v2/fips/{fip_id}`
  - others not needed here

  Each resource operation declares required header parameters `Authorization` ("Authorization Bearer
  token") and `x-product-instance-id` ("Product instance ID of FIU").
- **`ConsentResponseV2`:**
  - Required: `id`, `url`, `status`, `accountsLinked`.
  - `status` enum: `PENDING, INITIATED, FAILED, ACTIVE, PAUSED, REVOKED, EXPIRED, REJECTED`.
  - `detail.consentExpiry` is a date-time and required.
  - It also carries a **`PAN`** property.
- **`accountsLinked[]` item:** `fipId`, `accType`, `fiType`, `maskedAccNumber`, and `linkRefNumber`
  ("FIP's linkRefNumber as shared by the FIP after linking").
- **`GET /v2/sessions/{session_id}` → `FIDataFetchResponseV2`:**
  - Top level (all required): `id`, `consentId`, `status`, `format`, `dataRange`, `fips[]`.
    - `status` enum: `ACTIVE, PENDING, COMPLETED, EXPIRED, FAILED, PARTIAL`.
    - `format` enum: `xml, json`.
  - `fips[]` items: `fipID`, `accounts[]`.
  - `accounts[]` items: required `linkRefNumber`, `maskedAccNumber`, `FIstatus`, `data`.
  - `data` is a `oneOf` of 11 FI-type schemas with **no discriminator**.
  - For **`DepositJSON`**, the path is `data.account.transactions.transaction[]`. The array is
    `nullable`, and each item is `DepositJSONAccountTransactionsTransaction`.
  - Transaction item properties: `amount`, `currentBalance`, `mode`, `narration`, `reference`,
    `transactionTimestamp`, `txnId`, `type`, `valueDate`. **All are plain `string`, none required,
    and none has an enum or format.**
  - `DepositJSON.account` also carries `linkedAccRef`, `maskedAccNumber`, `type`, `version`,
    `profile.holders` (PII) and `summary` (balances, IFSC and similar).
- **`GET /v2/fips/{fip_id}`:** returns `data[]` of `FIPResponseObject`, with required `name`,
  `fipId`, `fiTypes`, `institutionType`, `status`.
- **`ErrorResponse`:** required `errorCode`, `errorMsg`, `timestamp`, `txnid`, `ver`. No `401`
  or `403` response is declared anywhere in the spec.

**Product boundaries** are unchanged from the first F14 pass:

- AA Gateway evidence comes from P1–P7 and P9 only.
- Setu Bridge's OAuth page (P8) is not merged into it.
- `clientID` / `secret` are this application's FIU credentials, issued by Bridge.
- No FIP credential exists or is held.
- `x-product-instance-id` is a non-secret routing header.

## 3. Unresolved Provider Evidence

**U1. Sandbox token host (blocking).**
The request is fully resolved by P9 (method, path, header, body, grant type). The host is not
resolved for sandbox:

- P9's only token server is `https://orgservice-prod.setu.co/v1`, unlabelled and production-named.
- The resource servers are explicitly split into Sandbox and Production.
- Nothing in P9 says the same token server serves sandbox credentials.
- Nothing documents a sandbox token server.

**U5b. Transaction value semantics in `GET /v2/sessions/{session_id}` (blocking).**
The structure is resolved (U5a), but the item field values are not:

- **Blocking:** `type` has no documented literal values, so `debit` / `credit` cannot be mapped
  without guessing.
- **Handled by strict fail-closed parsing, so non-blocking:**
  - the `amount` string format
  - the `transactionTimestamp` / `valueDate` string format

**Resolved in this phase:**

- **U2 token response.** `access_token`, required (P9).
- **U5a transaction structure.** Fully defined for `GET /v2/sessions/{session_id}` (P9).
- **U6 path prefix.** Everything is `/v2/...`, including revoke (P9).
- **U7 `accountsLinked` item shape.** Resolved (P9).

**Non-blocking by design:**

- **U3 token lifetime.** P9 has no expiry field.
- **U4 auth error behavior.** P9 declares only `400` → `ErrorResponse`.
- **U8 pagination.** P9 shows no cursor or page field in `FIDataFetchResponseV2`.
- **U9 rate limits and webhook signatures.**

## 4. Evidence Classification Table

| Item | Current Evidence | Classification | Minimum Evidence Needed | Implementation Blocker |
|---|---|---|---|---|
| Request auth headers | P1, P4, P7, and P9's per-operation required headers | `RESOLVED_BY_PUBLIC_DOCS` | None | No |
| Sandbox resource base URL | P9 root server `https://fiu-sandbox.setu.co/`, labelled Sandbox | `RESOLVED_BY_PUBLIC_DOCS` | None. The adapter joins paths without a double slash | No |
| U1 Token request (method, path, headers, body, grant type) | P9 `getToken` | `RESOLVED_BY_PUBLIC_DOCS` | None | No |
| U1 **Sandbox token host** | P9's only token server is unlabelled `orgservice-prod.setu.co/v1` | `REQUIRES_PROVIDER_SUPPORT` | A written Setu statement naming the token host sandbox FIU credentials must use. This is either confirmation that `orgservice-prod.setu.co/v1` is correct for sandbox, or the sandbox host itself | **Yes** |
| U2 Token response format | P9 `TokenAPIResponse.access_token` (required, "Bearer token"). `refresh_token` optional | `RESOLVED_BY_PUBLIC_DOCS` | None | No |
| U3 Token lifetime / refresh | No expiry field in P9. No refresh operation in P9 | `NOT_REQUIRED_FOR_INITIAL_READ_ONLY_SANDBOX` | None, under a fresh-token-per-operation design (§8). `refresh_token` is ignored and never stored | No |
| U4 Auth error behavior | P9 declares only `400` → `ErrorResponse`. No 401/403 | `NOT_REQUIRED_FOR_INITIAL_READ_ONLY_SANDBOX` | None, under fail-closed handling (G9) | No |
| U5a Transaction structure in `GET /v2/sessions/{session_id}` | P9 `FIDataFetchResponseV2` down to `DepositJSONAccountTransactionsTransaction` | `RESOLVED_BY_PUBLIC_DOCS` | None | No |
| U5b Transaction `type` literal values | P9: unconstrained `string`. Only the Auto-Fetch example shows `"CREDIT"`, and it is not accepted as evidence | `REQUIRES_AUTHENTICATED_PROVIDER_ACCESS` | One sandbox dummy-data `GET /v2/sessions/{session_id}` (`COMPLETED`, ≥1 debit + ≥1 credit, PII redacted), **or** a written Setu statement of the allowed `type` values | **Yes** |
| U5b `amount` / timestamp formats | P9: unconstrained `string` | `NOT_REQUIRED_FOR_INITIAL_READ_ONLY_SANDBOX` | None, under strict parsing: any value not matching a plain decimal with ≤2 fraction digits, or not parseable as ISO-8601, fails that row visibly and is never coerced. The same U5b sample confirms the formats | No |
| U6 Resource paths | P9: every path under `/v2`, including revoke and `GET /v2/consents/{request_id}` | `RESOLVED_BY_PUBLIC_DOCS` | None | No |
| U7 `accountsLinked` item shape | P9 `ConsentResponseConsentDetailAccountsItem` | `RESOLVED_BY_PUBLIC_DOCS` | None | No |
| Account join identifier | P9: `linkRefNumber` is in `accountsLinked[]` and is **required** in sessions `accounts[]` | `RESOLVED_BY_PUBLIC_DOCS` | None. `external_account_id = linkRefNumber`. The inner `data.account.linkedAccRef` is not used | No |
| Institution name | P9: `GET /v2/fips/{fip_id}` → required `name` | `RESOLVED_BY_PUBLIC_DOCS` | None | No |
| Consent status vocabulary | P9 `ConsentResponseV2.status` enum (8 values) | `RESOLVED_BY_PUBLIC_DOCS` | None. The internal mapping decision is in §8 | No |
| U8 Pagination | P9 shows no cursor or page field | `NOT_REQUIRED_FOR_INITIAL_READ_ONLY_SANDBOX` | None. P9's response schema is complete and has no continuation field | No |
| U9 Rate limits, webhook signatures | Not documented | `NOT_REQUIRED_FOR_INITIAL_READ_ONLY_SANDBOX` | None: no retries, polling only | No |

**Blocking items: U1 (sandbox token host) and U5b (transaction `type` values).**

## 5. Minimum Provider Evidence Package

The package holds **field names, types, structure and hosts only**. No real credential, token,
consent handle, PAN, or account identifier may ever be written into this repository, a ticket, or
this document.

| Needed? | Evidence | Why |
|---|---|---|
| **Yes** | A written Setu answer: *"Which token host must sandbox FIU credentials use for AA Gateway `getToken`?"* | U1. Only Setu can state this. P9 is silent on environment |
| **Yes** (either route) | The allowed values of the transaction `type` field. Either (a) a written Setu answer, or (b) one PII-redacted sandbox `GET /v2/sessions/{session_id}` response with a debit and a credit | U5b. Route (b) needs developer/sandbox access to Setu Bridge |
| Only for route (b) | Developer/sandbox Setu Bridge account with an AA Gateway FIU app | A human does this, outside this repository |
| Config names only | Product instance ID (string, non-secret routing header). Client ID (string). Client secret (secret string) | Already `SETU_SANDBOX_CLIENT_ID` and `SETU_SANDBOX_CLIENT_SECRET`. `SETU_SANDBOX_PRODUCT_INSTANCE_ID` is added at implementation |
| No longer needed | Token endpoint shape, token response sample, sandbox resource base URL, consent create/status examples, linked-account example, revoke example | Resolved by P9 |
| Optional | Authentication error example, token expiry/refresh information | Non-blocking by design (U3, U4) |

## 6. Transaction Contract Requirements

Derived from `ExternalTransaction` / `LinkedInstitutionAccount` / `LinkCompletion`
(`backend/app/sync/provider/base.py`), `sync_service._ingest_one`, `_build_idempotency_key`,
`TransactionCreate` and the `transactions` / `linked_accounts` models. Setu field paths are from P9.

**6.1 Required fields (per `ExternalTransaction`)**

| Internal field | Pipeline constraint | Setu source (P9) |
|---|---|---|
| `external_account_id: str` | Must equal `LinkedAccount.external_account_id`, or the row `FAILED`s. ≤200 chars | `fips[].accounts[].linkRefNumber`. The same value as `accountsLinked[].linkRefNumber` |
| `occurred_on: date` | Stored as midnight UTC of this date | `transaction[].transactionTimestamp` or `valueDate` (string). Which field to use, and how its offset maps to a calendar date, is decided and documented at implementation. An unparseable value fails the row |
| `amount_minor: int` | **> 0**, integer paise | `transaction[].amount` (string). `Decimal` only, never `float`. Reject >2 fraction digits, non-numeric, ≤0, or non-finite |
| `direction` | `"debit"` / `"credit"`, else `FAILED` | `transaction[].type`. **Allowed literals undocumented (U5b, blocking)** |
| `narration: str` | Merchant input, `description[:500]`, part of the fallback hash | `transaction[].narration`. Untrusted text |

**6.2 Optional fields**

| Internal field | Constraint | Setu source (P9) |
|---|---|---|
| `external_transaction_id` | Empty → fallback hash. Stored verbatim in `String(200)`. **>200 chars → reject the row** (never truncate) | `transaction[].txnId` |
| `LinkedInstitutionAccount.institution_name` | Required, ≤200 | `GET /v2/fips/{fip_id}` → `data[].name` |
| `LinkedInstitutionAccount.fip_reference` | ≤200 | `accountsLinked[].fipId` |
| `LinkedInstitutionAccount.masked_account_ref` | ≤50, **masked only** (verify, else drop) | `accountsLinked[].maskedAccNumber` |
| `LinkCompletion.consent_expires_at` | `None` allowed | `detail.consentExpiry` (date-time, required) |

**Adapter scoping:**

- Request `fiTypes: ["DEPOSIT"]` only.
- Request `format: "json"`.
- Treat any `data` object that lacks `account.transactions` as a failed account. Because `data` is a
  `oneOf` with no discriminator, never guess its FI type.
- Only transactions under a `linkRefNumber` equal to the requested `external_account_id` are
  returned. A `null` `transaction` array means zero transactions.

**6.3 Provider fields that must NOT be persisted** (read transiently at most; never stored, logged,
or returned):

- **Credentials and tokens:** `access_token`, `refresh_token`, the client secret, and the full token
  response.
- **Consent PII:** `ConsentResponseV2.PAN`, and all of `profile` (`holders`: names, PAN, mobile,
  email, address, DOB, etc.).
- **Account metadata:** `summary` (`currentBalance`, IFSC, MICR, branch, limits and similar),
  `accType`, `fiType`, `FIstatus`, `linkedAccRef`, and account `type` / `version`.
- **Transaction fields not mapped:** `transaction[].currentBalance`, `mode`, `reference`, and the
  date field not chosen for `occurred_on`.
- **Identifiers and errors:** session `id`, `traceId`, `txnid`, and raw error bodies.
- **Raw data:** any unmasked account number, and the raw JSON response in any form. That includes
  unredacted test fixtures.

## 7. Security Gate

Every condition must be ✅ before real Setu adapter code is written.

| # | Gate | Evidence required | Status |
|---|---|---|---|
| G1 | AA Gateway authentication mechanism | Token request (✅ P9) **and** sandbox token host (U1) | ❌ Sandbox token host |
| G2 | Credential/token handling | `access_token` field known (✅ P9). The token is held in memory for one provider operation only. It is never persisted, logged, cached across users, or returned. `refresh_token` is ignored and never stored. Client ID/secret come from `Settings` only | ✅ |
| G3 | Sandbox host | Resource host ✅ (P9 "Sandbox"). Token host ❌ (U1) | ❌ |
| G4 | Production host separation | The adapter hard-refuses `fiu.setu.co` and any production resource host. **The only documented token host is production-named. This gate cannot pass until Setu confirms the sandbox token host (U1)** | ❌ |
| G5 | Product-instance handling | `x-product-instance-id` is a required header on every resource operation (P9). It comes from `Settings`, is never sent to the token call, and is never returned to the frontend | ✅ |
| G6 | Consent/session identifiers | Consent `id` → `consent_id`. The session `id` stays transient. Neither is logged | ✅ |
| G7 | Transaction response schema | Structure ✅ (P9). `type` literal values ❌ (U5b) | ❌ |
| G8 | Token lifetime / refresh | Not required, because each operation gets its own fresh token | ✅ (by design) |
| G9 | Authentication error behavior | Fail-closed: any non-2xx or unparseable response raises a fixed-message error. It never includes the response body, token, or headers. No automatic retry | ✅ (by design) |
| G10 | Timeout policy | An explicit timeout on every call, including `getToken` (`_DEFAULT_TIMEOUT_SECONDS = 15.0`). Session polling is bounded by attempt count and total deadline, and ends on `COMPLETED` / `PARTIAL` / `FAILED` / `EXPIRED` | ✅ (policy defined) |
| G11 | No payment capability | 5 read-only Protocol methods. The P9 operations used are consent and data reads only | ✅ |
| G12 | No PIN/CVV/OTP/password collection | No P9 schema carries one | ✅ |
| G13 | No raw sensitive payload persistence | The §6.3 list is enforced, now including `PAN` and `refresh_token` | ✅ (discipline + tests) |
| G14 | No secret logging | `setu_sandbox.py` has no logging. The no-leak tests are extended to cover tokens at implementation | ✅ |
| G15 | No frontend exposure of provider credentials | `SETU_SANDBOX_*` exists only in backend `Settings` | ✅ |
| G16 | Mock stays the default; sandbox needs explicit `SYNC_PROVIDER=setu_sandbox` | Existing tests | ✅ |

**Gates G1, G3, G4 and G7 fail. Implementation is not permitted.**

## 8. Architecture Decision

**`BankSyncProvider` stays unchanged.** Its methods are `initiate_link`, `complete_link`,
`list_linked_institution_accounts`, `list_transactions` and `revoke_consent`. Nothing in P9 needs a
new method or signature, and no change was made. Everything below fits inside the adapter:

- **Token acquisition.** Each public provider method calls `getToken` once, uses `access_token`
  for that operation only, and then discards it. No cache, no persistence, no refresh.
- **FI data fetch.** `list_transactions` does `POST /v2/sessions` (with `fiTypes`/`format` as in
  §6), then polls `GET /v2/sessions/{session_id}` within the G10 bounds. A terminal non-success
  status raises, and `trigger_sync` records it as a provider failure (existing behavior).
- **Linked accounts.** `complete_link` and `list_linked_institution_accounts` use
  `GET /v2/consents/{request_id}?expanded=true` → `accountsLinked`. They resolve `institution_name`
  through `GET /v2/fips/{fip_id}`.
- **Consent status mapping** is adapter-internal. `SyncConsentStatus` has `pending/active/paused/
  revoked/expired`, while P9 adds `INITIATED`, `FAILED` and `REJECTED`. An explicit, documented
  mapping is required at implementation, for example:
  - `INITIATED` → `pending`
  - `REJECTED` and `FAILED` → `complete_link` raises, so no `LinkedAccount` rows are created

  This is not a Protocol change. `_parse_consent_status` already rejects unmapped values.

No change is required. None is proposed.

## 9. Implementation Readiness Criteria

The state may move to `READY_FOR_SANDBOX_IMPLEMENTATION` only when **all** of the following hold:

1. **G1–G16 are all ✅.**
2. **U1 is resolved by a written, AA-Gateway-specific Setu statement of the sandbox token host.** If
   Setu confirms sandbox credentials are exchanged at `orgservice-prod.setu.co`, record that as an
   explicit production-separation decision for the user before proceeding. G4 must then be restated
   (e.g. as an allow-list of exactly the two confirmed hosts). It must not be silently relaxed.
3. **U5b is resolved** by a written Setu statement or a redacted sandbox sample giving the allowed
   `type` values.
4. **Evidence is recorded as structure only** in an update to this document. Test fixtures use
   obviously synthetic values.
5. **The implementation plan limits itself to the five Protocol methods.** No schema migration.
   Adding `SETU_SANDBOX_PRODUCT_INSTANCE_ID` is config only.

## 10. Final Decision

**`NOT_READY_DOCUMENTATION_GAP`**

- **Resolved publicly by the official AA Gateway OpenAPI spec (P9):**
  - the token request
  - the token response field (`access_token`)
  - all resource paths
  - the `accountsLinked` shape
  - the `GET /v2/sessions/{session_id}` transaction structure
  - the account join key (`linkRefNumber`)
  - the institution name source
  - the consent status vocabulary
- **Still blocking:**
  - U1, the sandbox token host (`REQUIRES_PROVIDER_SUPPORT`)
  - U5b, the transaction `type` values (`REQUIRES_AUTHENTICATED_PROVIDER_ACCESS`)
- **Not modified:** `BankSyncProvider`, `SetuSandboxSyncProvider`, the database schema, and all
  production code. No Setu API was called.
