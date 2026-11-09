# Provider Integration Register

Last reviewed: 2026-11-08. This register separates implemented adapter code from permission to activate a real provider. Mock success is never provider evidence.

## Activation Policy

- Default launch scope is COD with audited manual fulfillment. Every external payment and courier remains `disabled` until its own signed row is complete.
- Staging uses an official provider sandbox/test merchant account or leaves the provider disabled. Application `mock` mode is local/CI only.
- Production uses `live` or `disabled`; production settings reject `mock` and `sandbox`.
- Credentials, certificates, and tokens are environment-only. Database settings may hold non-secret enable/kill switches but never credentials.
- Provider calls use fixed official HTTPS origins, TLS verification, no redirects, strict timeouts, bounded responses, stable merchant references, and redacted logs.
- Browser returns are non-authoritative. Only verified webhooks, official validation/query calls, or reconciliation may change money or shipment truth.
- Unknown create/execute/refund/booking outcomes are reconciled before retry.

## Launch Readiness

`Ready` means the adapter plus external evidence is complete for the named environment. `Implemented` means code exists but activation evidence is incomplete.

| Provider                    | Code status                                               | Production launch status                                          | Required mode at initial launch    |
| --------------------------- | --------------------------------------------------------- | ----------------------------------------------------------------- | ---------------------------------- |
| COD                         | Implemented                                               | Ready after business/fraud sign-off                               | Enabled                            |
| SSLCOMMERZ                  | Official v4 sandbox client implemented                    | Not ready without live merchant evidence                          | `disabled`                         |
| bKash tokenized checkout    | Deterministic mock and fail-closed real boundary          | Not ready; official contract unavailable at implementation freeze | `disabled`                         |
| Nagad                       | Deterministic mock and fail-closed real boundary          | Not ready; official contract unavailable at implementation freeze | `disabled`                         |
| Pathao                      | Deterministic mock and fail-closed real boundary          | Not ready; merchant contract/test evidence missing                | `disabled`                         |
| Steadfast                   | Deterministic mock and fail-closed real boundary          | Not ready; merchant contract/test evidence missing                | `disabled`                         |
| RedX                        | Deterministic mock and fail-closed real boundary          | Not ready; merchant contract/test evidence missing                | `disabled`                         |
| Cloudinary                  | Signed upload, verify, and delete adapter implemented     | Environment-specific evidence required                            | `cloudinary` in staging/production |
| Resend                      | Idempotent email adapter implemented                      | DNS, account, suppression, and delivery evidence required         | Required in production             |
| SMTP                        | At-least-once adapter implemented                         | Not approved for production by current settings policy            | Disabled                           |
| External SMS                | Documentation-gated idempotent HTTPS boundary implemented | Not ready until a named provider row is signed                    | Required for production OTP        |
| Meta CAPI                   | Consent-gated delivery implemented                        | Not ready until Pixel/business/token/legal evidence exists        | `disabled` unless approved         |
| OpenAI-compatible assistant | Grounded/redacted boundary implemented                    | Not ready until DPA and zero-retention approvals exist            | `disabled` unless approved         |

The launch checklist must link a later signed approval if initial scope changes. Do not edit the status to `Ready` based only on unit tests.

## Payment Providers

### COD

- Contract source: Bojro order and fraud rules.
- Capture authority: delivered-order transition.
- Refund authority: audited manual reference.
- Launch evidence: delivery confirmation flow, cancellation/refusal handling, cash reconciliation owner, fraud limits, and daily settlement procedure.

### SSLCOMMERZ

- Official source: [SSLCOMMERZ v4 integration documentation](https://developer.sslcommerz.com/doc/v4/).
- Recorded document version: 4.00; source page stated May 12, 2019 update date.
- Retrieved for implementation: 2026-11-07.
- Official sandbox origin: `https://sandbox.sslcommerz.com`.
- Implemented operations: hosted session creation, IPN intake, transaction validation/query, and refund boundary.
- Required matching: merchant transaction ID, amount, currency, validation ID, validation status, and resource identity.
- Live gate: current merchant documentation reconfirmed, live origin/credentials, callback DNS/TLS, sandbox suite, unknown-outcome reconciliation, refund canary, live low-value canary, settlement ownership, kill-switch test, and credential rotation.

### bKash Tokenized Checkout

- Official merchant documentation was not publicly retrievable on 2026-11-07.
- Required evidence: official current API version/origins, grant/refresh fields, create/execute/query/refund contracts, callback/webhook authentication, idempotency, rate limits, sandbox account, and settlement procedure.
- No guessed URL, credential field, signature, or cryptographic behavior is permitted.

### Nagad

- Official merchant documentation was not publicly retrievable on 2026-11-07.
- Required evidence: official current merchant API/version, sandbox, certificate/key handling, exact signing/canonicalization algorithm, initialize/complete/verify/query/refund contracts, callback authentication, idempotency, and settlement procedure.
- No unofficial cryptographic implementation is permitted.

## Courier Providers

### Pathao

The official merchant portal was authentication/JavaScript gated at the 2026-11-07 review. Activation requires an official test account, auth/token lifecycle, store/location catalogs, booking/query/cancel schemas, webhook signature/retry rules, status mapping, rate limits, COD/weight units, canary delivery, and kill-switch proof.

### Steadfast

Official documentation was not reachable at the 2026-11-07 review. Activation requires the official base URL/version, merchant test path, authentication headers, booking/tracking/cancel/webhook contracts, COD/weight units, terminal statuses, reconciliation, canary delivery, and kill-switch proof.

### RedX

Official developer/onboarding documentation was not publicly retrievable at the 2026-11-07 review. Activation requires an official test environment, token lifecycle, location mappings, create/query/cancel contracts, webhook authentication/event IDs/retries, status mapping, idempotency, rate limits, canary delivery, and kill-switch proof.

## Storage And Engagement

### Cloudinary

- Backend signing, metadata verification, and deletion are implemented.
- Required evidence: separate environments, restricted credentials, upload format/size/dimension/folder policy, browser upload completion, tampered completion rejection, cleanup/delete retry, quota alert, backup/version retention, restore procedure, and key rotation.
- `CLOUDINARY_API_SECRET` is Railway-only. Vercel receives no Cloudinary secret.

### Resend And Email DNS

- Official source: [Resend Send Email API](https://resend.com/docs/api-reference/emails/send-email).
- Delivery UUID is the idempotency reference.
- Required evidence: verified sending domain, single SPF record, all DKIM selectors, return path, DMARC reporting, bounce/complaint suppression, recipient allowlist in staging, bilingual rendering, unknown/timeout behavior, quota/rate alerts, and API-key rotation.
- SMTP acceptance followed by connection loss is `unknown`; do not blindly resend. Current production policy requires Resend rather than SMTP.

### External SMS

- The adapter requires `SMS_CONFIGURED=true`, `SMS_DOCUMENTATION_VERIFIED=true`, a named provider, official documentation URL/version, and verified idempotency support.
- Required evidence: approved sender identity, Bangladesh delivery coverage, OTP latency, lifecycle templates, opt-out rules, delivery receipts, timeout/unknown behavior, rate/quota alerts, recipient allowlist in staging, key rotation, and provider incident contact.
- Generic mock SMS is local/CI only and cannot satisfy the OTP launch gate.

### Meta CAPI

- Official source: [Meta Conversions API](https://developers.facebook.com/docs/marketing-api/conversions-api/).
- Server delivery reuses the purchase event UUID used by browser Pixel for deduplication and requires current advertising consent.
- Required evidence: approved business/Pixel ownership, data processing/legal review, test-event results, event match/dedupe proof, consent withdrawal suppression, least-privilege token, quota/error alerts, and rotation.

### Assistant

- Real activation requires an approved OpenAI-compatible endpoint, DPA, explicit zero-retention approval, fixed model/version, `store=false` behavior where supported, grounded-tool tests, prompt-injection tests, redaction tests, rate/cost alerts, outage fallback, and key rotation.
- The assistant remains disabled if any legal or technical gate is incomplete.

## Per-Provider Evidence Record

Copy this table into the release/change record for every activated provider:

| Field                     | Required value                                                           |
| ------------------------- | ------------------------------------------------------------------------ |
| Provider and capability   | Name plus payment/courier/email/SMS/storage/analytics/assistant function |
| Owner and backup owner    | Named people/team                                                        |
| Official documentation    | URL, version/date, retrieval date                                        |
| Account/environment       | Sanitized merchant/account ID and sandbox/live                           |
| Credential location       | Secret-manager path/version, never the value                             |
| Allowed origins/callbacks | Exact HTTPS URLs and verified DNS/TLS evidence                           |
| Contract evidence         | Sanitized request/response fixtures and test run                         |
| Verification              | Signature/authentication, amount/resource matching, replay test          |
| Ambiguity handling        | Timeout/unknown query and reconciliation result                          |
| Failure handling          | Retry bounds, dead-letter path, alert, operator runbook                  |
| Kill switch               | Dated successful disable/fail-closed test                                |
| Rotation                  | Dated successful rotation/revocation test                                |
| Canary                    | Dated sandbox and live canary with provider reference redacted           |
| Approval                  | Engineering, security, operations, finance/legal as applicable           |
| Expiry/review date        | No more than 90 days after approval                                      |

## Operating Rules

- Monitor unknown attempts, webhook verification failures, processing/reconciliation lag, dead letters, refund failures, settlement mismatches, shipment lag, quota, and credential expiry.
- Invalid webhooks are rejected before insertion. Verified events deduplicate by kind, provider, and official event ID.
- Workers claim durable rows with leases and `FOR UPDATE SKIP LOCKED`; handlers remain idempotent under at-least-once execution.
- Rotate one credential/certificate version at a time, validate the official test path, and revoke the old version after the overlap window.
- Never place credentials, signatures, full payloads, or customer PII in logs, audit responses, CI artifacts, or provider evidence.
- Follow [OPERATIONS.md](OPERATIONS.md) for reconciliation/dead-letter procedures and [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md) for provider incidents.
