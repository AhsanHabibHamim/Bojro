# Architecture

## System Context

Bojro is a single-brand commerce application. The Next.js App Router storefront deploys to Vercel. A public FastAPI web service and a non-public ARQ worker deploy from the same backend image to Railway, backed by PostgreSQL and Redis. Cloudinary stores media bytes. External payment, courier, messaging, analytics, and assistant providers remain behind explicit capability interfaces and activation gates.

```text
Browser -> Vercel storefront -> public HTTPS Railway API -> PostgreSQL
                                      |                -> Redis
                                      |                -> Cloudinary/providers
                                      -> Railway ARQ worker -> PostgreSQL/Redis/providers
```

Vercel is outside Railway private networking. Browser and server-rendered frontend API calls use the same public custom API origin. PostgreSQL and Redis stay on Railway private networking.

## Repository

- `frontend/`: Next.js, strict TypeScript, next-intl, Tailwind CSS, Vitest, and Playwright.
- `backend/`: FastAPI, Pydantic v2, async SQLAlchemy 2, Alembic, ARQ, and pytest.
- `infra/`: loopback-bound local Docker Compose and production-oriented Dockerfiles.
- `scripts/`: operator-safe validation, backup, restore-drill, and evidence helpers.
- `docs/`: contracts, decisions, deployment, recovery, operations, security, privacy, and launch evidence.

## Request And Transaction Boundaries

Requests flow from routers to services to repositories. Routers validate transport concerns, services own transactions and business invariants, and repositories own persistence queries. Unsafe cookie-authenticated operations require an exact allowed origin and synchronizer CSRF value. Ambiguous external effects use durable idempotency records and stable merchant references.

External provider commands persist intent before network I/O. Network calls happen outside database locks. Unknown outcomes are reconciled before retry. Verified webhook events and durable outbox jobs drive idempotent state-machine updates under row locks.

## Data Authority

| Store                    | Authority                                                                 | Loss behavior                                                                        | Recovery source                                         |
| ------------------------ | ------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ | ------------------------------------------------------- |
| PostgreSQL               | Orders, inventory, users, content, audit, provider attempts, durable jobs | Service is unavailable; do not reconstruct from Redis                                | Railway PITR/snapshot plus encrypted logical backup     |
| Cloudinary               | Original and derived media bytes                                          | Media may fail while metadata remains                                                | Cloudinary backup/version retention and asset inventory |
| Redis                    | Rate limits, OTP challenge state, caches, ARQ wakeups, heartbeat          | Sessions may require retry/login; caches rebuild; durable jobs sweep from PostgreSQL | Recreate empty; never restore as business truth         |
| Encrypted secret manager | Runtime secrets, keyrings, provider credentials                           | Deployment/preflight fails closed                                                    | Versioned secret-manager recovery with audited access   |

Monetary values are integer poisha with ISO currency `BDT`; floating-point money is prohibited. Public entities use UUIDv7 values. Timestamps are UTC `timestamptz`; clients display them in `Asia/Dhaka`.

## Caching And Rendering

Catalog, home, product, and category reads use bounded caching and tag-based on-demand revalidation. Search and account/admin/checkout flows are dynamic. Builds must not require a live API. Admin mutations commit revalidation events atomically with the business change; the worker retries delivery and dead-letters exhausted work.

## Worker Model

One ARQ process owns periodic sweeps and delivery work at launch: media cleanup, revalidation, payment/refund/shipment reconciliation, webhook processing, notification delivery, CAPI delivery, cart reminders, and retention cleanup. Redis improves wake latency, but PostgreSQL leases and sweeps provide durability. The worker writes a Redis heartbeat consumed by `/ready`; production requires a fresh heartbeat.

Run one scheduler replica until duplicate scheduler behavior and job concurrency are explicitly load-tested. Horizontal worker scaling must preserve `SKIP LOCKED`, lease, and idempotency invariants.

## Security And Privacy

Customer and admin authentication use separate JWT audiences, cookies, refresh sessions, CSRF values, and rate limits. Access tokens are short-lived; refresh tokens rotate. Cookies are host-only, HttpOnly, Secure in production, and SameSite=Lax on paired same-site custom domains. Passwords use Argon2id and admin TOTP seeds use versioned AES-GCM keyrings.

Engagement recipients, content, and context use versioned AES-GCM envelopes and domain-separated keyed lookup hashes. Notification, CAPI, and assistant work is stored in specialized encrypted tables. Consent is checked before optional collection and again immediately before marketing/CAPI delivery. Logs and API responses exclude raw provider secrets, request bodies, and unnecessary PII.

## Availability And Recovery

`/health` proves process liveness without dependencies. `/ready` reports required database, Redis, worker, provider, and configuration health and returns `503` when required components are unavailable. A `degraded` response is an operator signal, not blanket release approval. SLOs, alert thresholds, and runbooks are in [OPERATIONS.md](OPERATIONS.md); data recovery is in [BACKUP_RESTORE.md](BACKUP_RESTORE.md).

## Contract

FastAPI's OpenAPI document is the API source of truth. `pnpm api:generate` exports deterministic `backend/openapi.json` and generates `frontend/src/lib/api/schema.d.ts`. Generated files are committed and CI rejects tracked or untracked drift.

Deployment, environment, provider, and retention policy are source-controlled contracts, but platform approvals, DNS, backups, alerts, and branch protection are external controls whose dated evidence is required by [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).
