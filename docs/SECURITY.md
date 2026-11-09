# Security Review

Last reviewed: 2026-11-08. Scope: storefront, customer/admin APIs, PostgreSQL/Redis, worker, media, payment/courier webhooks, engagement providers, CI, deployment, recovery, and operator access.

This document records implemented controls and launch obligations. It is not a penetration-test report. Unchecked external controls in [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md) keep the release at no-go.

## Implemented Baseline

- Secrets are environment-only; examples contain non-production placeholders and production settings reject known defaults.
- CORS and trusted hosts are explicit allowlists. Production requires HTTPS origins and secure host-only cookies.
- Security headers include CSP, HSTS in production, frame denial, MIME-sniff protection, and a conservative referrer policy.
- Request IDs and structured logs omit request bodies, credentials, and deliberate PII fields.
- SQLAlchemy-bound queries, Pydantic validation, bounded uploads/payloads, and fixed provider origins reduce injection and SSRF exposure.
- Customer and admin sessions use separate JWT audiences, cookie names/paths, refresh records, CSRF values, and rate limits.
- Access sessions are short-lived; refresh sessions rotate and are revocable. Passwords use Argon2id.
- Unsafe cookie-authenticated requests require an exact allowed `Origin` and identity-bound synchronizer CSRF token.
- OTP values are HMAC-protected in Redis; recipient state is encrypted, attempts/resends are bounded, and production delivery requires an idempotent documentation-verified SMS provider.
- Checkout recomputes integer-poisha totals under row locks and uses signed quote fingerprints plus scoped idempotency.
- Customer/admin object access is scoped in database queries. UUID unpredictability is never treated as authorization.
- Revisioned resources use strong ETags, mandatory `If-Match`, and replay-safe idempotency keys.
- Admin mutations append redacted tamper-evident audit records and durable outbox rows in the business transaction.
- Uploads use owned server-issued records, signed provider operations, bounded types/sizes, verified metadata, and asynchronous cleanup.
- Provider HTTP clients use fixed official origins, TLS verification, no redirects, strict timeouts, and response-size limits.
- Browser payment returns are hints only. Verified webhooks, official validation/query, or reconciliation establish provider truth.
- Unknown payment/refund/courier outcomes are reconciled before retry.
- Engagement PII uses versioned AES-GCM keyrings and domain-separated HMAC lookup keyrings.
- Optional analytics defaults denied and is collected/delivered only with the required current consent.
- Newsletter action tokens are single-use POST credentials transported in URL fragments rather than query strings.
- Assistant input is redacted before encrypted retention/provider calls and grounded through fixed read-only tools.
- Production rejects mock storage, payment/courier/engagement providers, E2E reset tokens, placeholder hosts, and deprecated OTP settings.

## OWASP Top 10 Review

| Risk                                           | Current evidence                                                                                                               | Required launch evidence or residual risk                                                                                               |
| ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------ | --------------------------------------------------------------------------------------------------------------------------------------- |
| A01 Broken Access Control                      | Server-side customer ownership, separate admin dependency/audience, opaque cross-owner semantics, audit logs                   | Execute horizontal/vertical authorization tests and review Railway/Vercel access lists quarterly.                                       |
| A02 Cryptographic Failures                     | TLS-only production origins, Secure/HttpOnly cookies, Argon2id, AES-GCM keyrings, HMAC lookup/signing keys, secret redaction   | Prove key generation, distinct material, secret-manager versioning, rotation, revocation, and encrypted backup access.                  |
| A03 Injection                                  | Pydantic input contracts, parameterized SQLAlchemy queries, structured rich documents, CSV formula neutralization              | Preserve hostile-input coverage for search, admin editors, CSV, provider payloads, and assistant content.                               |
| A04 Insecure Design                            | Transactional inventory/idempotency, explicit state machines, unknown outcome handling, consent recheck, fixed assistant tools | Threat-model every newly enabled provider and any change to checkout, recovery, or support disclosure.                                  |
| A05 Security Misconfiguration                  | Fail-closed production settings, allowlisted hosts/origins, security headers, loopback local data ports                        | Verify deployed headers, cookie prefixes, no debug/docs, no E2E variables, and platform least privilege after every environment change. |
| A06 Vulnerable Components                      | Frozen pnpm/uv locks, Dependabot, dependency review, CodeQL, Trivy, SBOM, and container scans                                  | Security owner triages alerts to the SLA below; exceptions require expiry and compensating controls.                                    |
| A07 Identification And Authentication Failures | Rate-limited OTP/login, rotating refresh sessions, CSRF, admin TOTP/recovery, logout-all/session revocation                    | Test expiry, replay, theft/revocation, cross-tab principal changes, account disable, and break-glass access in staging.                 |
| A08 Software And Data Integrity Failures       | OpenAPI drift check, migration checks, idempotent jobs, verified webhooks, pinned CI actions                                   | Enforce protected branches/environments and provenance from one reviewed commit SHA across all services.                                |
| A09 Security Logging And Monitoring Failures   | Request IDs, structured redacted logs, admin audit, readiness, dead-letter state                                               | Configure external error tracking, uptime/synthetic checks, alert routing, retention, and a tested page before go-live.                 |
| A10 Server-Side Request Forgery                | Fixed provider endpoints, no arbitrary assistant fetch/SQL, no redirects, bounded network clients                              | Re-review any configurable URL, proxy, rich-media resolver, or new provider before activation.                                          |

## CI And Supply Chain

The `Security` workflow performs CodeQL for Python and JavaScript/TypeScript, pull-request dependency review, a commit-pinned TruffleHog scan, SBOM generation, and high/critical container scanning. Dependabot covers GitHub Actions, npm, Python, and Docker inputs. Action references are pinned to immutable SHAs and annotated with their reviewed release.

Local release evidence on 2026-11-08: `pip-audit` reports no known vulnerability after upgrading `cryptography` to 50.x. `pnpm audit` reports no high or critical issue; one moderate `minimatch` advisory remains only in the ESLint development graph and is absent from production images/runtime bundles. Dependabot owns that upgrade under the medium-severity SLA below.

Required controls outside source control:

- Enable GitHub secret scanning and push protection when the repository plan supports them.
- Limit Actions to GitHub-owned and explicitly allowlisted third-party actions.
- Protect `main`, require code-owner review and Security/Quality checks, and disable force push/deletion.
- Require independent approval on the GitHub `production` environment and prevent self-review.
- Review the SBOM for every release and retain it with the deployment evidence.

## Vulnerability Handling

| Severity                               | Initial response                            | Remediation target                        |
| -------------------------------------- | ------------------------------------------- | ----------------------------------------- |
| Critical, exploited, leaked credential | Immediate P1 incident; revoke/contain first | Same day before normal operation resumes  |
| High                                   | Security owner within one business day      | 7 calendar days                           |
| Medium                                 | Triage within 5 business days               | 30 calendar days                          |
| Low                                    | Normal backlog review                       | 90 calendar days or documented acceptance |

An exception records the affected component, advisory/CVE, exploitability, data exposure, compensating control, owner, approval, and expiry. Exceptions never suppress secret findings or known exploitation.

## Provider And Webhook Review

Each enabled provider must have official contract provenance, credential owner, sandbox evidence, callback verification, amount/resource matching, replay/deduplication tests, timeout/unknown-outcome behavior, reconciliation, a kill switch, credential rotation, and log-redaction evidence. The status register is [PROVIDERS.md](PROVIDERS.md).

Raw signatures, authorization headers, credentials, complete provider payloads, OTP values, full phone/email/address data, and assistant plaintext are prohibited in logs, audit diffs, CI artifacts, support tickets, and incident chat.

## Data Protection

The authoritative retention and deletion schedule is [PRIVACY_RETENTION.md](PRIVACY_RETENTION.md). Recovery copies are encrypted, access-logged, and expire on schedule. Restoring an older backup never revives a deleted account directly into production; deletion/suppression ledgers are replayed before cutover.

Key rotation uses overlapping keyrings: add the new key, change the active key ID, re-encrypt/reindex on the approved path, retain old read keys for the documented window, then destroy retired material with evidence. Never reuse JWT, quote, OTP, admin TOTP, engagement encryption, lookup HMAC, unsubscribe, provider, or revalidation secrets.

## Launch-Blocking External Controls

The following are intentionally not claimed as code-complete and require evidence before go-live:

- External frontend/backend error tracking with release association and source-map policy.
- Uptime, readiness, synthetic checkout, worker heartbeat, queue/dead-letter, provider, Cloudinary quota, and backup alerts.
- An independent security review or penetration test for the final public configuration.
- Railway/Vercel/Cloudinary/GitHub MFA, least-privilege roles, break-glass ownership, and quarterly access review.
- Legal approval of privacy notice, consent copy, retention schedule, email/SMS terms, assistant DPA/zero-retention, and provider agreements.
- A successful isolated restore drill and incident tabletop within the validity windows in the launch checklist.

Security incidents follow [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md). Operational alerts and escalation follow [OPERATIONS.md](OPERATIONS.md).
