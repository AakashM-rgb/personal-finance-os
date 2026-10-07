# Setu Support Request — AA Gateway Sandbox Contract (DRAFT, NOT SENT)

**Status:** draft only. Not yet sent to Setu. This draft contains no credentials, tokens, product
instance IDs, consent IDs, or account identifiers, and none should be added to it. Background is in
`SYNC_PROVIDER_EVIDENCE_GATE.md`, blockers U1 and U5b.

---

**Subject:** AA Gateway sandbox — token endpoint host and transaction `type` values

Hello Setu team,

We are integrating with the Setu AA Gateway (v2) as an FIU and have two questions that the public
documentation does not answer for the sandbox environment.

## Context

- We are building a **read-only** personal finance application that imports a user's own bank
  transactions, with the user's consent, through the Account Aggregator framework.
- We will **not** start payments, transfers, withdrawals, or any other money movement.
- We will **not** collect or store PINs, CVVs, OTPs, passwords, or any payment-authorization
  credentials. Consent approval happens only in the AA consent-manager flow.
- We will build our adapter only once the sandbox contract is unambiguous, so that nothing is
  inferred from production documentation or from other Setu products.

## Questions

**Question 1 — Sandbox authentication**

For the Setu AA Gateway sandbox, when using the documented AA Gateway `POST /users/login` request
with `client: bridge`, `clientID`, `secret`, and `grant_type=client_credentials`, which exact
hostname/base URL should sandbox FIU credentials use to obtain the `access_token`? Is
`https://orgservice-prod.setu.co/v1/users/login` also the correct endpoint for sandbox
credentials, or is there a separate sandbox token endpoint?

**Question 2 — Transaction type**

For `GET /v2/sessions/{session_id}`, what exact values can the
`fips[].accounts[].data.account.transactions.transaction[].type` field contain? Please provide the
documented enum/allowed values or a redacted sandbox response showing both a debit and credit
transaction.

## Please also confirm

1. Is the `access_token` returned for sandbox credentials valid for requests to
   `https://fiu-sandbox.setu.co`?
2. Are the documented `/v2` paths, including `POST /v2/sessions`, `GET /v2/sessions/{session_id}`
   and `POST /v2/consents/{request_id}/revoke`, the same in sandbox?
3. Does sandbox authentication need any headers beyond `client: bridge`? We already send the
   documented `Authorization: Bearer <access_token>` and `x-product-instance-id` on resource
   requests.

## References (official Setu documentation)

- AA Gateway OpenAPI specification (`getToken`, `/v2` paths, session response schema):
  https://docs.setu.co/api-specs/data/account-aggregator.json
- AA Gateway API reference, "Auth Mechanism" / `getToken`:
  https://docs.setu.co/data/account-aggregator/api-reference#/operation~getToken
- Account Availability APIs (the "FIUs must use Auth Mechanism to obtain an access token" statement):
  https://docs.setu.co/data/account-aggregator/api-integration/account-availability-apis
- Consent flow (sandbox/production base URLs, request headers):
  https://docs.setu.co/data/account-aggregator/api-integration/consent-flow
- Data APIs (FI data sessions):
  https://docs.setu.co/data/account-aggregator/api-integration/data-apis
- AA quickstart (sandbox credentials, link to the Postman collection):
  https://docs.setu.co/data/account-aggregator/quickstart
- AA Postman collection "FIU V2 service - public" (Token API request):
  https://documenter.getpostman.com/view/22511424/2s9Y5VU4MC
- Bridge settings, API credentials (test vs live credentials):
  https://docs.setu.co/dev-tools/bridge/settings

Thank you,
Aakash M
Personal Project / Personal Finance Application
