# Phase F7 — Real Provider & Sandbox Research (India Account Aggregator)

**Status: research and architecture-validation only. No real provider is implemented, connected
to, or contacted by this document or this phase. See `SYNC_PROVIDER.md` for the engineering
boundary this research validates against.**

Every factual claim below is attributed to a public source found via web search on 2026-09-24.
Anything not attributed to a source is this document's own **engineering interpretation** —
clearly labeled as such — never a documented regulatory fact and never a recommendation on the
project owner's behalf about whether or how to pursue a real integration. That decision is a
business and legal one outside this document's scope.

---

## A. Executive summary

India's read-only bank-data-sharing standard is the RBI-regulated **Account Aggregator (AA)**
framework. It is consent-based, encrypted end-to-end, and structurally incapable of moving money —
an AA only ever brokers *data*, never a transaction. A personal-finance app like this one is a
natural **data consumer** in that framework (a **Financial Information User**, FIU), but — this is
the single most important finding of this research — **FIU status itself is legally restricted to
entities already regulated by RBI, SEBI, IRDAI, or PFRDA** [Sahamati, HyperVerge]. An unregulated
consumer app cannot become an FIU by itself; it can only reach AA data by (a) obtaining a relevant
financial-sector license itself, or (b) reaching a commercial arrangement with an already-regulated
entity/partner that holds FIU status, with this application's engineering integrating against
that partner's system. Several AA gateways (Setu, Finvu, OneMoney/Moneyone) already publish **free,
publicly documented developer sandboxes with dummy data**, which are useful for engineering
familiarization today, independent of that business decision.

The existing `BankSyncProvider` abstraction (Phases A–F6) was audited against this research and
found to be **architecturally sufficient** for a future sandbox adapter — see §G and §6 of the
task. No production-code change was made in this phase.

## B. Current architecture (as of commit `3d12dcb`)

- `app/sync/provider/base.py` — the permanently read-only `BankSyncProvider` Protocol: `initiate_link`,
  `complete_link`, `list_linked_institution_accounts`, `list_transactions`, `revoke_consent`. No
  other method may ever be added (see `SYNC_PROVIDER.md` §3).
- `app/sync/provider/mock.py` — `MockSyncProvider`, the only implementation today, and the
  permanent default/dev-test provider.
- `app/sync/provider/factory.py` — the sole selection point; `sync_service.py` is provider-agnostic
  and never imports a specific implementation.
- `app/services/sync_service.py` — orchestration: link lifecycle, idempotent ingestion, deterministic
  + optional-AI categorization (unmodified by this phase — see §K), `SyncRun` bookkeeping, consent
  expiry/revocation enforcement (Phase F6).
- `app/models/linked_account.py` — `LinkedAccount` / `SyncConsentStatus`; no credential field exists
  or may ever exist on it.
- Full contract details already documented in `SYNC_PROVIDER.md` (§3–§7) — not repeated verbatim here.

## C. India AA ecosystem roles

Four distinct roles, all defined and enforced by the RBI Master Direction and the ReBIT technical
specification [ReBIT, Sahamati, financialservices.gov.in]:

| Role | What it does | Who it can be |
|---|---|---|
| **Account Aggregator (AA)** | An RBI-licensed NBFC whose *sole* business is moving encrypted financial data, with the user's explicit consent, from an FIP to an FIU. It never reads, stores, or decrypts the data itself ("blind pipe") and cannot lend or advise. | Only a company licensed by RBI as an **NBFC-AA** (Master Direction – NBFC-Account Aggregator Directions, 2016, as amended) [HyperVerge, RBI]. |
| **Financial Information Provider (FIP)** | The institution that actually holds the user's data (a bank, NBFC, mutual fund RTA, insurer, pension fund, etc.) and releases it through the AA once consent is granted. | A regulated financial institution. |
| **Financial Information User (FIU)** | The entity that *receives and uses* the data, with consent, for a purpose matching its own regulatory charter. | **Only an entity already regulated by RBI, SEBI, IRDAI, or PFRDA** [Sahamati — "an entity registered with and regulated by any financial sector regulator"]. By the ecosystem's "reciprocity principle," an RBI-regulated FIU must also register as an FIP if it holds equivalent data itself [Sahamati]. |
| **Technology Service Provider (TSP)** | A technology vendor that builds and operates the FIP/FIU *technical module* (ReBIT-spec API client, encryption, consent-handling UI/SDK) on behalf of a regulated client, so that client doesn't have to build ReBIT compliance from scratch. **A TSP itself does not need an NBFC-AA license** [Sahamati], but a TSP **does not change who the legal FIU is** — the data still only ever flows to the regulated entity of record. |

**Engineering interpretation:** a "TSP route" is a way to get the *technical integration* done
faster and more correctly (ReBIT signature/encryption compliance, consent SDK, certification
support) — it is **not** a way for an unregulated app to bypass FIU regulation. One search result
states this plainly: *"the framework is designed to prevent raw financial data from flowing to
unregulated parties"* [search synthesis citing Setu/HyperVerge]. This is the most important
distinction for this project to keep straight going forward.

## D. Regulatory/eligibility considerations

- **This application, as it exists today, is not eligible to register as an FIU.** It is not a
  bank, NBFC, SEBI-registered intermediary, IRDAI-regulated insurer, or PFRDA-regulated pension
  entity. This is stated as a documented fact, not an assumption the task asked me not to make —
  the eligibility criterion itself (regulator-registered entity only) is what's documented; that
  *this specific codebase's owner/company* doesn't currently hold such a license is an inference
  from the fact that no such registration has been mentioned or implied anywhere in this
  repository or conversation, not a claim I can verify externally.
- To legitimately reach AA data, the two documented paths are:
  1. **Obtain a relevant financial-sector registration/license directly** (e.g. an NBFC or an
     investment-advisor registration whose charter is "commensurate with" using the data for
     personal-finance purposes [Sahamati]) — a substantial legal/business/compliance undertaking,
     entirely outside engineering scope.
  2. **Partner commercially with an already-regulated FIU** (or a TSP that operates on behalf of
     one), so that the regulated partner is the legal FIU of record and this application consumes
     data through an API/SDK that partner exposes — a business/legal/contractual decision, not an
     engineering one, and one this document deliberately does not recommend for or against.
- **Certification is mandatory regardless of the path chosen.** Any FIU-side module — whether
  built in-house by a regulated entity or supplied by a TSP — must pass Sahamati certification for
  ReBIT technical-spec adherence and enroll in the ecosystem's **Central Registry** before
  production go-live; sandbox/UAT testing against an RBI-approved AA sandbox is itself part of that
  certification pathway [Sahamati go-live sources, Setu].
- **UAT/sandbox environments are required to use dummy data only** — one AA's published UAT
  policy states that all data shared in UAT must be "strictly dummy data" and that "under no
  circumstances should any user account(s) or replica(s) of production accounts be discoverable or
  linkable in the UAT environment" [search synthesis citing Finvu sandbox documentation]. This is a
  documented ecosystem-wide expectation, not specific to one vendor.
- **ReBIT technical specification**: the current published version is **v2.0.0** (dated
  2023-08-09; supersedes v1.1 from 2019-11-08) — several sandboxes (e.g. some OneMoney/Moneyone
  flows) still document against v1.1 for existing integrations, so version alignment must be
  checked per-provider before building against it [ReBIT specifications.rebit.org.in, OneMoney docs].

## E. Sandbox/UAT options researched

No credentials were created, no sign-up was performed, and no sandbox was called. This is a
desk-research summary of what each provider **publicly documents** about its sandbox as of
2026-09-24.

| Provider/org | Role supported | Public sandbox/UAT? | Docs | Dummy data? | Onboarding friction (as documented) |
|---|---|---|---|---|---|
| **Setu** | AA gateway product for FIUs (an RBI-licensed AA integration layer) | Yes — publicly documented, pre-seeded sandbox keys, Postman collection | `docs.setu.co/data/account-aggregator` | Yes — "customisable mock data sources" for various use cases including personal finance management | Create a Setu Bridge account, create an FIU app; full production go-live still requires the Sahamati certification/Central Registry process described in §D |
| **Finvu (Cookiejar Technologies)** | AA-side sandbox (an implementation of the AA's own REST APIs) | Yes — `finvu.github.io/sandbox/`, documented UAT dummy-data policy | Finvu sandbox docs; Sahamati participant list for UAT access request | Yes, explicitly required/enforced in UAT | Requires registering on the Sahamati participant list to request UAT access; API calls must be JWS-signed |
| **OneMoney / Moneyone** (FinSec AA Solutions) | AA-side sandbox, developer portal | Yes — `developer.onemoney.in`, org/app/API-key self-service onboarding | `onemoney.in/docs`, `docs.moneyone.in` | Implied via sandbox environment separation (`aa.sandbox.onemoney.in`) | Self-service developer-portal signup; existing docs reference ReBIT API spec v1.1 for some flows |
| **Anumati (Perfios)** | RBI-licensed AA; Perfios also has a broader financial-data-analytics business | Not directly confirmed in this research pass — Perfios/Anumati is documented as a major AA by FIP coverage, but a public self-service sandbox URL was not found in the sources retrieved | General Perfios/Anumati marketing and comparison pages only | Not confirmed | Likely requires direct commercial contact (unconfirmed) |
| **CAMS FinServ** | RBI-licensed AA (CAMS Financial Information Services) | Not directly confirmed; a partner product ("Finduit," via a Sterling Software partnership) is described as simplifying FIP/FIU onboarding, but no public sandbox URL was retrieved | General comparison/marketing pages only | Not confirmed | Likely requires direct commercial contact (unconfirmed) |
| **NADL** | RBI-licensed AA, listed among top providers by FIP coverage | Not directly confirmed in this research pass | General comparison pages only | Not confirmed | Likely requires direct commercial contact (unconfirmed) |

**Note on completeness:** Anumati/CAMS FinServ/NADL are real, RBI-licensed AAs with meaningful
market share [comparison-article search synthesis], but this pass did not retrieve a public,
self-service sandbox landing page for them the way it did for Setu/Finvu/OneMoney. That is a gap
in *this research pass*, not necessarily a gap in what those providers offer — a follow-up research
or direct-contact step would be needed to confirm.

## F. Candidate integration routes

Given §D's regulatory finding, there are really only two structurally different routes, not
several:

1. **Direct FIU route** — this application (or its operating company) itself becomes a regulated
   entity and a certified FIU, using a TSP (e.g. Setu, or another ReBIT-compliant module vendor) or
   an in-house build to satisfy the technical/certification requirements. Highest control,
   highest regulatory/business burden.
2. **Partner-FIU route** — a commercial arrangement with an already-regulated, already-certified
   FIU (which may itself be built on a TSP's module), where this application's backend calls that
   partner's own API to receive AA data on the end user's behalf, under whatever data-sharing
   agreement that partnership establishes. Lower regulatory burden for this application directly,
   but introduces a third-party dependency and a commercial/contractual relationship outside
   engineering's control.

Both routes converge on the same integration shape from this codebase's point of view once a
partner/license is in place: an adapter behind `BankSyncProvider` that speaks to that partner's
(or this app's own certified module's) REST API. See §G.

This document takes no position on which route is preferable — that is a business decision
involving legal, compliance, and cost tradeoffs this document is not positioned to make.

## G. Technical mapping to `BankSyncProvider`

Each `BankSyncProvider` method maps cleanly onto the AA ecosystem's documented flow shape. This is
engineering interpretation, cross-checked against the sandbox flow descriptions found in §E's
sources (in particular Setu's and Finvu's documented consent/webhook flows):

| `BankSyncProvider` method | AA ecosystem equivalent (engineering interpretation) |
|---|---|
| `initiate_link(user_id, institution_hint)` | Create a **consent request** against the FIU module/gateway; the AA (via the gateway) returns a redirect URL to the user's chosen AA app/web flow and an opaque consent handle — directly matches `LinkInitiation`'s existing shape (`redirect_url` + `consent_handle` + `expires_at`). |
| `complete_link(consent_handle)` | Fetch the **consent status** once the user returns from the AA flow (approved/rejected) and, on approval, the linked institution account(s) the consent now covers — matches `LinkCompletion`'s existing shape (`consent_id`, `consent_status`, `consent_expires_at`, `accounts`). **Nuance:** real integrations (e.g. Finvu) additionally expose an **asynchronous webhook** for consent-status changes (approved/rejected/revoked) rather than relying solely on the user's browser redirect returning [Finvu docs synthesis]. This does **not** require a `BankSyncProvider` Protocol change — a webhook is a new HTTP entry point (e.g. a future `POST /api/v1/sync/webhook`) that would call the *same* underlying `sync_service` logic `complete_link`/consent-status-refresh already represents; the Protocol method itself is orthogonal to which HTTP path triggers it. |
| `list_linked_institution_accounts(consent_id)` | Re-list accounts covered by an existing consent (an AA "discover accounts"/consent-detail style call) — already represented, not currently called by `sync_service` (documented in `SYNC_PROVIDER.md` §3 as forward-looking API surface). |
| `list_transactions(consent_id, external_account_id, since, until)` | An AA **FI (Financial Information) data-fetch request/decrypt** cycle — a real adapter requests data for a date range, then decrypts the AA's encrypted response using the FIU's own key material (per the ReBIT spec's cryptographic envelope) and maps each resulting bank-statement-schema transaction into `ExternalTransaction`. |
| `revoke_consent(consent_id)` | A direct AA consent-revocation call. |

## H. Data/security boundaries

Unchanged from, and fully consistent with, `SYNC_PROVIDER.md` (§1, §4, §5) — this research did not
surface anything that requires widening the boundary already documented there:

- `BankSyncProvider` remains permanently read-only; a real adapter's job is to translate the AA
  ecosystem's (much richer, XML-schema-based, encrypted) transaction/account representation *down*
  into the existing minimal `ExternalTransaction`/`LinkedInstitutionAccount` shape — never to widen
  those dataclasses to carry the AA's raw payload.
- Decryption of the AA's encrypted FI-data response happens **entirely inside the future provider
  adapter module**, using key material that adapter manages — never inside `sync_service.py`, and
  the decrypted plaintext must be reduced to `ExternalTransaction`'s existing fields before it ever
  leaves the adapter.
- `masked_account_ref` stays masked-only; a real AA `LinkedInstitutionAccount` response's fuller
  account reference must be truncated/masked by the adapter before it reaches `LinkedAccount`.

## I. What must NEVER be collected

Restated explicitly, as required, and consistent with `SYNC_PROVIDER.md` §1/§5 and every prior
phase's security tests:

- **PIN** (UPI PIN, ATM/card PIN, or any other PIN)
- **CVV**
- **OTP**
- **Password** (net-banking, bank app, or any other banking password)
- **Payment authorization credentials of any kind**

None of these have any legitimate role in the AA framework in the first place — the AA's entire
design point is that the user authenticates and authorizes **directly with the AA/their bank's own
app**, never by handing a credential to the FIU (this application) [RBI/Sahamati framework
description, §C]. A future adapter that somehow required one of these would not be a legitimate AA
integration and must not be built.

## J. What must NEVER be supported

Restated explicitly, as required:

- **Payment**
- **Transfer**
- **Withdrawal**
- **Account modification**

The AA framework itself is structurally incapable of any of these (an AA is a "blind pipe" for
data only, licensed for exactly that and nothing else [RBI Master Direction, §C]) — so a
correctly-scoped adapter built against it could not add these capabilities even if someone tried;
they would require an entirely different (payments) license and API relationship this project does
not have and this document does not discuss further.

## K. Production prerequisites before any real integration

Purely a restatement/consolidation of §D–§F's documented findings, for a future engineer's
checklist — not new information:

1. A resolved business/legal decision on the direct-FIU vs. partner-FIU route (§F) — outside
   engineering scope.
2. If direct-FIU: the underlying regulatory registration/license itself, obtained through
   whatever legal process that requires.
3. Either way: Sahamati certification of the FIU module (in-house or TSP-built) against ReBIT's
   technical specification, and enrollment in the ecosystem's Central Registry (§D).
4. Sandbox/UAT integration and testing against an RBI-approved AA sandbox, using dummy data only
   (§D, §E) — this is a legitimate engineering task that could begin **before** the business
   decision in (1) is fully resolved, using one of the publicly documented free sandboxes in §E,
   entirely for architecture/adapter validation purposes.
5. A concrete adapter module under `app/sync/provider/` implementing `BankSyncProvider` end to
   end (§G), including the AA-specific cryptographic envelope handling, kept entirely inside that
   module.
6. Wiring the new adapter into `build_sync_provider()` only (`app/sync/provider/factory.py`) —
   `sync_service.py` should require no changes (§B, and confirmed by this phase's audit, §6).
7. Provider-specific tests using recorded/fake sandbox responses — never a real network call in
   the automated test suite (mirroring every existing provider/classifier test in this codebase).
8. A real go-live decision, including which specific AA/FIU partner or module to use — again a
   business decision, not made or implied here.

## L. Recommended next engineering phase

Framed as an engineering recommendation only — not a business/regulatory one:

**If and when the business/legal decision in K(1)–(2) is resolved**, the next *engineering* phase
should be a narrowly-scoped **sandbox adapter spike**: implement `BankSyncProvider` against one
publicly documented free sandbox (Setu's is the most immediately self-serviceable per §E) using
dummy data only, entirely inside a new `app/sync/provider/` module, with zero changes to
`sync_service.py`, and with tests built against recorded fixture responses (never a live sandbox
call in CI). That spike would concretely validate §G's mapping against real API responses and
surface any genuine schema gap before any production commitment is made — while still fully
honoring every constraint in `SYNC_PROVIDER.md` and this document.

Until that business decision is made, **no further engineering work on a real provider is
recommended** — the existing `BankSyncProvider` abstraction and `MockSyncProvider` already fully
serve the application's current needs, and this research found no code-level gap requiring a
change today (§6 of the phase task, confirmed in the final report).

---

## Sources

- [Account Aggregator Framework: India's Consent-Based Data Sharing System (2026 Guide) — HyperVerge](https://hyperverge.co/blog/account-aggregator-framework-rbi/)
- [Account Aggregator Framework — Department of Financial Services, Ministry of Finance, Government of India](https://financialservices.gov.in/account-aggregator-framework)
- [Master Direction — Reserve Bank of India](https://www.rbi.org.in/Scripts/BS_ViewMasDirections.aspx?id=10598)
- [Account Aggregators — Sahamati](https://sahamati.org.in/account-aggregators/)
- [FIPs & FIUs in the AA Ecosystem — Sahamati](https://sahamati.org.in/fip-fiu-in-account-aggregators-ecosystem/)
- [Financial Information User (FIU) — Sahamati](https://sahamati.org.in/financial-information-user-fiu/)
- [How to join the Account Aggregator Network — Sahamati](https://sahamati.org.in/how-to-join-the-account-aggregator-network-to-share-and-access-financial-data/)
- [Technology Service Provider (TSP) — Sahamati](https://sahamati.org.in/tsp/)
- [License types by Financial Regulators RBI, SEBI, IRDAI, PFRDA — Sahamati](https://sahamati.org.in/license-types-by-financial-regulators-rbi-sebi-irdai-pfrda/)
- [NBFC-Account Aggregator (AA) API Specification v2.0.0 — ReBIT](https://specifications.rebit.org.in/artefacts/NBFC-AA_API_Specification_v2.0.0.pdf)
- [ReBIT specifications portal](https://specifications.rebit.org.in/)
- [ReBIT API portal](https://api.rebit.org.in/)
- [FIU go-live process — Setu Docs](https://docs.setu.co/data/account-aggregator/licenses-and-go-live/go-live)
- [Licenses required to participate in AA — Setu Docs](https://docs.setu.co/data/account-aggregator/licenses-and-go-live/licenses)
- [Licenses for Fintechs to go live on Account Aggregator — Setu Blog](https://blog.setu.co/articles/licences-for-fintechs-to-go-live-on-account-aggregator)
- [Account Aggregator quickstart — Setu Docs](https://docs.setu.co/data/account-aggregator/quickstart)
- [Finvu sandbox overview](https://finvu.github.io/sandbox/)
- [Onemoney AA API Docs — Introduction](https://www.onemoney.in/docs/api/introduction.html)
- [Onemoney developer portal](https://developer.onemoney.in/)
- [Moneyone Technical documentation](https://docs.moneyone.in/tech/)
- [State of Account Aggregator in 2026 — CASParser](https://casparser.in/blog/state-of-account-aggregator-2026/)
- [Account Aggregator integration in 2026: a builder's guide — ecorpit](https://ecorpit.com/account-aggregator-integration-fintech-builders-2026/)
- [Pick the Right Account Aggregator: An FIU Selection Guide — HyperVerge](https://hyperverge.co/blog/best-account-aggregators/)
- [Finvu vs Anumati vs OneMoney: AA Comparison — Fintegration](https://www.fintegrationfs.com/post/a-comparative-analysis-of-finvu-anumati-and-onemoney-in-india-s-aa-landscape)

All sources were accessed via public web search/fetch on 2026-09-24. No account was created, no
credential was obtained, and no sandbox or production API was called while producing this
document.
