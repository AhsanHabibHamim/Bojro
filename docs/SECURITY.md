# Security Baseline

## Phase 1 Controls

- Secrets are environment-only and example values are explicitly non-production.
- API CORS is an explicit allowlist; wildcard credentials are forbidden.
- Security headers include CSP, HSTS in production, frame denial, MIME sniff protection, and a conservative referrer policy.
- Request IDs and JSON logs exclude request bodies and personal data.
- PostgreSQL access uses SQLAlchemy-bound parameters; no raw user interpolation is present.
- Pydantic settings reject malformed origins and production startup fails with placeholder secrets.
- Admin creation requires operator-provided credentials and Argon2id hashing.

## Pending Feature Reviews

Feature-specific OWASP reviews will accompany authentication, checkout, uploads, webhooks, chat, and the admin panel in their respective phases. Each documented provider will require signature validation, replay protection, timeouts, and redacted logging before activation.
