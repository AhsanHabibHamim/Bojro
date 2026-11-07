# Provider Integration Register

This document records the authoritative source and activation gate for every Bojro payment and courier adapter. Mock mode is deterministic local/CI behavior; it is never evidence that a live provider contract is valid.

## Activation Rules

- Real providers remain disabled until official current documentation, an approved merchant test account, sanitized contract fixtures, callback DNS/TLS, credential rotation, reconciliation and dead-letter runbooks all exist.
- Production rejects `mock` and `sandbox` modes, placeholder credentials, non-HTTPS callback origins, missing Redis, and enabled providers without verified configuration.
- Secrets and certificates are environment-only. Admin settings hold non-secret accept-new/kill switches, not credentials.
- Provider calls use fixed allowlisted origins, TLS verification, no redirects, strict timeouts and bounded response sizes.
- Browser returns are hints. Only verified webhooks, official validation/query calls, or authoritative reconciliation may mark money paid or shipments delivered.

## Payment Providers

### COD

- Contract source: Bojro internal business rules.
- Phase 6 status: supported in mock/manual mode.
- Capture authority: delivered order transition.
- Refund authority: audited manual reference.

### SSLCOMMERZ

- Official source: [SSLCOMMERZ v4 integration documentation](https://developer.sslcommerz.com/doc/v4/).
- Document version: 4.00, page states update date May 12, 2019.
- Retrieved: 2026-11-07.
- Official sandbox origin: `https://sandbox.sslcommerz.com`.
- Confirmed operations: hosted session creation (`POST /gwprocess/v4/api.php`), IPN POST, transaction validation (`GET /validator/api/validationserverAPI.php`), refund API.
- Required validation: merchant transaction ID, amount, currency, validation ID and validation status. TLS 1.2 or newer.
- Phase 6 status: official sandbox client plus deterministic mock; live mode remains credential/DNS gated.

### bKash Tokenized Checkout

- Official merchant documentation was not publicly retrievable from the current environment on 2026-11-07.
- Required evidence before sandbox/live activation: current tokenized-checkout API version and origins, grant/refresh fields, create/execute/query/refund contracts, callback/webhook verification, idempotency and rate limits.
- Phase 6 status: provider-specific deterministic mock and fail-closed real adapter boundary. No guessed URLs or credential fields.

### Nagad

- Official merchant/developer documentation was not publicly retrievable from the current environment on 2026-11-07.
- Required evidence: official merchant API/version, sandbox, certificate/key requirements, exact RSA algorithms/canonicalization, initialize/complete/verify/query/refund and callback verification.
- Phase 6 status: provider-specific deterministic mock and fail-closed real adapter boundary. No unofficial cryptographic implementation.

## Courier Providers

### Pathao

- The official merchant portal is JavaScript/authentication gated; a complete API contract was not publicly retrievable on 2026-11-07.
- Required evidence: official test environment, auth/token lifecycle, store/location catalogs, booking/query/cancel schemas, webhook signature/retries/status mapping and rate limits.
- Phase 6 status: provider-specific deterministic mock and fail-closed real adapter boundary.

### Steadfast

- Official API documentation was not reachable from the current environment on 2026-11-07.
- Required evidence: official base URL/version, sandbox availability, authentication headers, booking/tracking/cancel/webhook contracts, COD/weight units and terminal statuses.
- Phase 6 status: provider-specific deterministic mock and fail-closed real adapter boundary. If no official sandbox exists, activation requires an approved merchant test account.

### RedX

- Official developer/onboarding documentation was not publicly retrievable on 2026-11-07.
- Required evidence: official test environment, token lifecycle, location mappings, create/query/cancel, webhook authentication/event IDs/retries, status map, idempotency and rate limits.
- Phase 6 status: provider-specific deterministic mock and fail-closed real adapter boundary.

## Operational Runbook

- Do not retry unknown create/execute/booking/refund outcomes. Query or reconcile by the stable internal merchant reference first.
- Monitor unknown attempts, webhook verification failures, processing lag, reconciliation failures, dead letters, refund failures and shipment-status lag.
- Invalid unauthenticated webhooks are rejected before database insertion. Verified events deduplicate by kind, provider and official event ID.
- Workers claim durable rows with leases and `FOR UPDATE SKIP LOCKED`; handlers remain idempotent under at-least-once execution.
- Rotate one provider credential/certificate at a time, validate sandbox health, then retire the previous version according to provider instructions.
- Never include raw credentials, signatures, tokens, full provider payloads or customer PII in logs, audit responses or support exports.
