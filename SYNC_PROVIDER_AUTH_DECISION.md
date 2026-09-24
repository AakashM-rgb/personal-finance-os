# Setu AA Gateway Authentication Resolution (Phase F13)

## 1. Current Status

**NOT_READY_DOCUMENTATION_GAP**

Per the explicit decision rule this phase was given: the full authentication flow (how to *obtain*
a valid credential, not merely how to *use* one) is not confirmed end-to-end by AA-Gateway-specific
documentation. One half of the question — the request-header format AA Gateway actually expects —
is now genuinely confirmed with a literal, on-page quote (§3). The other half — where the token
used in that header actually comes from, for this specific product — is not. Per the rule, this
alone keeps the state at `NOT_READY_DOCUMENTATION_GAP`; it is not upgraded merely because an
authentication mechanism exists and is documented for adjacent Setu products/surfaces.

## 2. Authentication Evidence Reviewed

All evidence below comes from Setu's own `docs.setu.co` pages, re-examined in this phase with a
deliberately literal, skeptical extraction method (asking explicitly "does this exact substring
appear on this page, quote the surrounding sentence, or say not found" rather than asking for a
general summary) to avoid treating an AI-summarization tool's inference as a documented fact.

| # | Source (exact page) | Product surface | What it literally shows |
|---|---|---|---|
| 1 | [Consent flow — Setu Docs](https://docs.setu.co/data/account-aggregator/api-integration/consent-flow) | **AA Gateway** (`/data/account-aggregator/...`) | Literal quote, re-verified this phase: `"Authorization": Bearer `access_token`` and `"x-product-instance-id": `product-instance-id`` shown as example request headers on this exact page |
| 2 | [Account Availability APIs — Setu Docs](https://docs.setu.co/data/account-aggregator/api-integration/account-availability-apis) | **AA Gateway** | `Authorization: Bearer <access token>` and `x-product-instance-id` shown as required headers (Phase F11 finding, consistent with source 1) |
| 3 | [Account Aggregator quickstart — Setu Docs](https://docs.setu.co/data/account-aggregator/quickstart) | **AA Gateway** (sandbox onboarding) | Names `x-product-instance-id`, `x-client_id`, `x-client-secret` as values you obtain after sandbox setup ("Step 2") - but, re-verified this phase with a direct, skeptical prompt, **shows no curl example, code sample, or explicit statement connecting these three values to an actual request** - it neither confirms nor denies that they are sent as literal headers |
| 4 | [Setu Bridge OAuth — Setu Docs](https://docs.setu.co/dev-tools/bridge/v1/org-settings/api-keys/oauth) | **Setu Bridge / dev-tools** (not under `/data/account-aggregator/`) | Documents `POST /api/v2/auth/token` (fields `clientID`/`secret` → response `token`/`expiresIn`) on `uat.setu.co`/`prod.setu.co` - **explicitly states this mechanism is product-specific and does not name or confirm AA Gateway** as one of the covered products (re-confirmed in Phase F11) |
| 5 | (Search-result context only, not independently fetched this phase) UPI Deeplinks OAuth and BBPS OAuth doc pages exist as **separate, product-specific** OAuth pages | UPI Deeplinks, BBPS (different products entirely) | Reinforces that Setu documents authentication **per product**, not as one universal mechanism - strengthens the case that source 4's mechanism should not be assumed to cover AA Gateway without its own explicit page |

## 3. AA Gateway Authentication Finding

**What is now confirmed, with a literal on-page quote, specific to the AA Gateway product
itself:** every documented AA Gateway request (consent creation, consent status, account
availability - sources 1 and 2) requires exactly two headers:

```
Authorization: Bearer <access_token>
x-product-instance-id: <product-instance-id>
```

This is a genuine, meaningful narrowing from Phase F11/F12: F11 could not confirm AA Gateway even
*uses* bearer-token authentication as opposed to some other scheme (e.g. static header credentials
sent directly). It now does, confirmed by a literal quote re-verified on the primary AA Gateway
consent-flow page in this phase.

**What remains unconfirmed:** *how to obtain* the `<access_token>` value, for this product
specifically. No AA-Gateway-specific page (sources 1, 2, or 3) shows a token-generation endpoint,
a curl example producing a token, or an explicit statement of the form "exchange your
`x-client_id`/`x-client-secret` for a token by calling X." Source 4's token-exchange mechanism
(`clientID`/`secret` → `token`) is structurally very plausible as the answer - it uses a similarly
named credential pair, and the AA Gateway pages never describe any alternative acquisition path -
but source 4 itself disclaims universal product coverage, and no AA-Gateway-specific page
cross-references it. Treating source 4 as the answer would mean inferring across a product
boundary the phase's own instructions explicitly forbid ("Do NOT treat authentication
documentation for another Setu product as proof of AA Gateway authentication").

**Explicit statement, as instructed**: the exact AA Gateway token-acquisition mechanism is **not
publicly verifiable** from anything reviewed in Phase F11 or this phase.

## 4. Product/Authentication Boundary

Explicitly distinguished, as requested:

- **Setu AA Gateway itself**: confirmed to require `Authorization: Bearer <token>` +
  `x-product-instance-id` (§3). Token acquisition unconfirmed.
- **Setu Bridge/OAuth**: a separate, dev-tools-level page documenting a `clientID`/`secret` →
  `token` exchange, explicitly product-specific, not confirmed to cover AA Gateway.
- **Authentication mechanisms documented for other Setu products** (UPI Deeplinks OAuth, BBPS
  OAuth): exist as their own, separate, product-specific pages - further evidence that Setu's own
  documentation convention is per-product, reinforcing why source 4 cannot be assumed to
  transitively cover AA Gateway.
- **FIU/FIP-side credentials**: not an authentication concept at all in this context - `fipID`,
  AA handles, and similar are resource/routing identifiers within the AA ecosystem itself (see
  `SYNC_PROVIDER_RESEARCH.md` §C), unrelated to how *this application* authenticates its own calls
  to Setu's API.
- **Sandbox credentials**: the quickstart page (source 3) frames `x-product-instance-id`/
  `x-client_id`/`x-client-secret` specifically as sandbox-onboarding outputs ("Step 2" of setting
  up a sandbox FIU app) - confirmed sandbox-scoped, not confirmed as request-header values.
- **Application/client credentials**: the `x-client_id`/`x-client-secret` (or `clientID`/`secret`
  on source 4 - not confirmed to be the identical field-naming convention) represent the
  application-level credential pair Setu Bridge issues per FIU app; not confirmed whether this
  pair is sent directly as request headers or exchanged for a token first.
- **Consent/session identifiers**: `consentId`, data-session `id`, `fipID` etc. are resource
  identifiers returned by and passed to specific API calls (already well-documented, see
  `SYNC_PROVIDER_READINESS.md` §5/§7) - not credentials, and not part of this authentication
  question at all.

## 5. Remaining Transaction Contract Gap

Re-examined with the same literal, skeptical method. A genuine (partial) resolution was found this
phase:

**Newly confirmed** (literal JSON structure quoted from the AA Gateway data-APIs page): the outer
nesting skeleton of a completed data-session response is

```
{ "fips": [ { "fipID": "...", "accounts": [ { "linkRefNumber": "...", "maskedAccNumber": "...",
  "status": "DELIVERED", "data": { "account": { "transactions": { "startDate": "...",
  "endDate": "..." } } } } ] } ] }
```

**Still missing**: the page's own example does not populate the `transactions` object with actual
transaction array items - it shows only the date-range container (`startDate`/`endDate`), not the
array key name individual transactions live under, nor a populated example entry. Phase F7/F11
separately identified the individual transaction *field names* likely involved (`amount`,
`currentBalance`, `mode`, `narration`, `reference`, `transactionTimestamp`, `txnId`, `type`,
`valueDate`) from a different part of the same data-APIs page, but their exact position within
this now-confirmed outer nesting skeleton (e.g. `data.account.transactions.txn[]` vs
`data.account.transactions.transaction[]` vs some other array key) remains unconfirmed by anything
retrieved.

**Net effect**: this gap narrowed (outer shape now known) but is not resolved (inner array shape
still unknown) - `list_transactions`'s real mapping code still cannot be written correctly without
guessing the innermost array key name.

## 6. Architecture Impact

**`BankSyncProvider` remains sufficient. No Protocol change is required or was made.** This
phase's findings are entirely about *how an adapter authenticates its own outbound HTTP calls* and
*what shape the response JSON has* - both are internal implementation details of a future
`SetuSandboxSyncProvider` rewrite, never something that needs to appear in the Protocol's method
signatures (`initiate_link`, `complete_link`, `list_linked_institution_accounts`,
`list_transactions`, `revoke_consent` all remain unchanged, re-verified by a fresh read of
`backend/app/sync/provider/base.py` this phase). Bearer-token acquisition/refresh, and the
per-request `x-product-instance-id` header, belong entirely inside the adapter's own private HTTP
client construction (mirroring how `AnthropicMerchantClassifier` owns its own API-key/client
handling internally, never exposing it through `MerchantClassifier`'s Protocol) - not a `sync_service.py`
or Protocol-level concern.

## 7. Evidence Required to Unblock Implementation

In priority order, narrower than Phase F12's checklist now that §3 has resolved the header format:

1. **The AA Gateway token-acquisition endpoint/flow, confirmed from an AA-Gateway-specific
   source** - the account-specific API reference or Postman collection Setu provides once an FIU
   app is created in Setu Bridge (per the quickstart's own "Start API integration" pointer), read
   by a developer with actual sandbox access; or a direct, written answer from Setu developer
   support confirming whether `POST /api/v2/auth/token` (source 4) is the correct mechanism for
   AA Gateway specifically, and on which host (`fiu-sandbox.setu.co` vs `uat.setu.co`).
2. **A fully populated example (or real sandbox dummy-data) `GET /sessions/:id` response**, to
   confirm the innermost transaction array's key name and per-item shape (§5).
3. Everything already listed as non-blocking in `SYNC_PROVIDER_DECISION.md` §3 (pagination, rate
   limits, webhook signature verification) remains non-blocking and unchanged by this phase.

## 8. Security Requirements

Authoritative evidence still required before any real implementation, restated precisely per this
phase's instructions:

| Requirement | Status after this phase |
|---|---|
| Exact authentication mechanism | ⚠️ Half-confirmed - request format yes (§3), acquisition no |
| Credential/token format | ⚠️ Partially known - `Bearer <token>` usage confirmed; whether the token is a JWT, its structure, and how it's minted for AA Gateway is not |
| Credential storage expectations | ✅ Already defined by this repository's own design, independent of Setu's answer - `Settings.setu_sandbox_*` fields, never logged/persisted/returned (`SYNC_PROVIDER_DECISION.md` §5, unchanged) |
| Required headers | ✅ Confirmed for AA Gateway - `Authorization: Bearer <token>`, `x-product-instance-id`, `Content-Type: application/json` |
| Token/session lifetime | ❌ Not found anywhere reviewed - source 4 mentions a default `expiresIn` of 1800 seconds, but that is the *other* product-agnostic OAuth page again, not AA-Gateway-confirmed |
| Sandbox host | ✅ Confirmed - `fiu-sandbox.setu.co` (resource API); the auth/token host, if source 4 does apply, would be `uat.setu.co` - unconfirmed pairing |
| Production host separation | ✅ Confirmed for resource APIs (`fiu.setu.co`); same unconfirmed-pairing caveat for the auth host |
| Consent/session identifiers | ✅ Fully documented already (`SYNC_PROVIDER_READINESS.md` §5/§7) - not a security gap |
| Error behavior relevant to authentication | ❌ Not found - the general error schema (`errorMsg`/`errorCode`/`txnid`/`timestamp`) is documented, but no example of an authentication-specific failure (expired token, invalid credential) was found |

**No secret was placed in source code, tests, fixtures, documentation, git history, frontend code,
or logs in this phase, or in any prior phase** - re-confirmed by this phase touching no code file
at all (see §10/final report).

## 9. Implementation Boundary

Unchanged from `SYNC_PROVIDER_DECISION.md` §6 - restated here as still governing, since this phase
did not reach `READY_FOR_SANDBOX_IMPLEMENTATION` and therefore did not need to revise it. The
first real implementation may only touch sandbox hosts with sandbox-only credentials, may only
perform the five documented read-only operations, and must never add, request, or store anything
resembling a payment credential or payment/transfer/withdrawal capability - see that document for
the complete list.

## 10. Final Decision

**`NOT_READY_DOCUMENTATION_GAP`** - unchanged in category from Phase F11/F12, but meaningfully
more precisely scoped: the gap is no longer "is AA Gateway's authentication mechanism even
Bearer-token-based?" (now answered: yes, confirmed) but narrows to exactly one open question - "how
is that Bearer token obtained for the AA Gateway product specifically?" - plus the secondary,
non-blocking-for-architecture transaction-nesting detail in §5. Per this phase's explicit rule,
having *an* authentication mechanism documented for Setu Bridge generally is not treated as proof
of AA Gateway authentication, so this finding does not upgrade the state to
`READY_FOR_SANDBOX_IMPLEMENTATION`. No implementation was attempted, no live API call was made, and
`BankSyncProvider` and `SetuSandboxSyncProvider` remain exactly as they were before this phase.
