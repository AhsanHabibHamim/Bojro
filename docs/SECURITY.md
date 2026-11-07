# Security Baseline

## Phase 1 Controls

- Secrets are environment-only and example values are explicitly non-production.
- API CORS is an explicit allowlist; wildcard credentials are forbidden.
- Security headers include CSP, HSTS in production, frame denial, MIME sniff protection, and a conservative referrer policy.
- Request IDs and JSON logs exclude request bodies and personal data.
- PostgreSQL access uses SQLAlchemy-bound parameters; no raw user interpolation is present.
- Pydantic settings reject malformed origins and production startup fails with placeholder secrets.
- Admin creation requires operator-provided credentials and Argon2id hashing.
- Auth uses short access JWTs and rotating hashed refresh sessions in host-only HttpOnly cookies; guest and quote tokens use separate signing secrets.
- Unsafe commerce/auth mutations require exact-Origin validation and an in-memory synchronizer CSRF token bound to the signed identity.
- OTP values are HMAC-protected in Redis with TTL, attempt, resend, phone, and IP limits; the deterministic mock is forbidden in production.
- Checkout uses scoped idempotency, signed quote fingerprints, row locks, and server-only integer-poisha recomputation.
- Account resources require a live access session and scope ownership in SQL; UUID unpredictability is never authorization.
- Revisioned customer resources use strong ETags, mandatory If-Match, and idempotency keys for ambiguous creates/messages.
- Review photos use server-issued owned upload IDs and verified provider metadata; arbitrary final URLs are rejected.
- Customer support queries exclude internal messages and internal activity metadata.
- Admin and customer tokens/cookies use separate audiences, names, paths, session kinds, and CSRF values.
- TOTP seeds use versioned AES-GCM encryption keys; recovery codes are hashed and timestep replay is rejected.
- CSV imports use fixed columns, size/row limits, full validation-before-commit, and spreadsheet-formula neutralization on export.
- Audit diffs redact sensitive keys/PII, and database triggers maintain tamper-evident hashes and append-only behavior.
- Provider HTTP clients use fixed official origins, TLS verification, no redirects, bounded payloads and strict connect/read/write/pool timeouts.
- Online payment redirects are API-supplied and allowlisted; Bojro never collects provider card/PIN/OTP credentials.
- Webhooks require provider verification or official validation calls before storage/processing, and provider payloads remain database-only/redacted.
- Unknown payment/refund/courier outcomes are reconciled before retry to prevent duplicate external effects.

## Pending Feature Reviews

Feature-specific OWASP reviews will accompany authentication, checkout, uploads, webhooks, chat, and the admin panel in their respective phases. Each documented provider will require signature validation, replay protection, timeouts, and redacted logging before activation.

## OWASP Top 10 Review

| Risk | Phase 1 evidence | Residual work |
| --- | --- | --- |
| A01 Broken Access Control | No privileged feature routes ship in Phase 1; the admin seed is explicit and secret-backed. | Enforce object- and role-level policies on customer/admin routes as they are introduced. |
| A02 Cryptographic Failures | Argon2id hashes seeded credentials; production cookies and TLS are architecture requirements; secrets never enter source. | Add rotating JWT/refresh keys and provider credential rotation in the owning phases. |
| A03 Injection | Pydantic validates settings/input and SQLAlchemy emits bound parameters; no interpolated SQL is used. | Add hostile-input integration coverage for search, filters, coupons, and admin editors. |
| A04 Insecure Design | Service/repository boundaries, integer money, UUIDv7 IDs, order state rules, and audit tables encode core invariants. | Threat-model checkout, payments, courier webhooks, chat grounding, and account recovery before release. |
| A05 Security Misconfiguration | CORS is allowlisted; CSP and defensive response headers are centralized; infrastructure examples bind data services to loopback. | Replace local secrets, enforce production origins, and validate Railway/Vercel headers during launch. |
| A06 Vulnerable Components | Lockfiles and CI quality/build checks provide reproducible dependency review. | Enable automated dependency alerts and triage before launch. |
| A07 Identification and Authentication Failures | No default admin password exists; phone normalization and password hashing primitives are tested. | Implement OTP throttling, rotating refresh tokens, CSRF checks, optional TOTP, and session revocation in auth phases. |
| A08 Software and Data Integrity Failures | OpenAPI drift is rejected; migrations and the idempotent seed execute in CI; images build from pinned major runtimes. | Verify webhook signatures/deduplication and signed Cloudinary uploads with contract tests. |
| A09 Security Logging and Monitoring Failures | Structured logs and request IDs omit bodies and PII; audit/event tables exist. | Connect env-gated Sentry, alerting, retention, and admin audit viewers. |
| A10 Server-Side Request Forgery | Phase 1 has no user-controlled outbound requests. | Provider clients and chat retrieval must use fixed allowlisted origins, timeouts, size limits, and redirect restrictions. |
