# Architecture Decision Log

## 2026-11-05: Locale-prefixed routes

**Decision:** Use explicit `/bn` and `/en` route prefixes and redirect `/` to `/bn`.

**Reason:** Stable, shareable URLs avoid cookie-only locale ambiguity and make Bangla the unambiguous default for users and search engines.

## 2026-11-05: UUIDv7 public identifiers

**Decision:** Generate RFC 9562 UUIDv7 identifiers with the tested application utility in `backend/app/utils/uuid7.py` while storing native PostgreSQL UUID values.

**Reason:** Python 3.12 lacks standard-library UUIDv7 support. The small local implementation avoids another runtime dependency while tests validate version, variant, ordering, and uniqueness; native UUID values retain good index locality without leaking sequential counts.

## 2026-11-05: uv for backend dependency locking

**Decision:** Keep the required pnpm workspace for JavaScript and use a committed `uv.lock` for Python.

**Reason:** uv provides reproducible Python 3.12 environments and fast local/container installs without weakening the monorepo boundary.

## 2026-11-05: Tailwind CSS v4 token bridge

**Decision:** Define brand primitives as CSS custom properties and expose the same primitives to Tailwind through `@theme inline`.

**Reason:** CSS variables support runtime theming and non-utility consumers while Tailwind tokens keep implementation consistent.

## 2026-11-05: Generated logo remains canonical in Phase 1

**Decision:** Preserve the supplied root `logo.jpg`, but use generated `public/logo.svg` and `public/icon.svg` placeholders through a single `Logo` component.

**Reason:** The brief explicitly defines the placeholder contract. Centralizing the asset path means the final artwork can replace it without touching callers.

## 2026-11-05: Redis is soft-required locally

**Decision:** Health remains live without Redis; readiness reports a degraded optional dependency in development and a failure in production.

**Reason:** This meets the graceful local fallback requirement without masking production infrastructure failures.

## 2026-11-05: Admin seed is opt-in

**Decision:** Create an admin only when `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` are both provided.

**Reason:** Shipping a known default password would violate the secret and account security requirements.

## 2026-11-06: On-demand locale ISR

**Decision:** Return no locale values from `generateStaticParams` and cache API reads with explicit entity tags. Search and filtered listing routes render dynamically; home, category, and product reads remain tag-cacheable and revalidate on demand.

**Reason:** Docker/Vercel builds must not depend on a live Railway API. The first request populates the Full Route/Data Cache while admin events can invalidate only affected entities.

## 2026-11-06: Generated contract adapter

**Decision:** Network response types come directly from `schema.d.ts`, then one centralized adapter maps API DTOs into frontend presentation models.

**Reason:** The API uses reusable normalized shapes such as nested price/stock models while components need view-specific shapes. One adapter preserves OpenAPI as the source of truth without leaking transport details or scattering handwritten fetches.

## 2026-11-06: Same-site API domain for auth

**Decision:** Production uses host-only secure cookies from `api.bojro.com.bd` while the storefront runs at `bojro.com.bd`; staging uses an equivalent pair of custom subdomains.

**Reason:** Vercel and Railway provider domains are cross-site, so browsers will not send SameSite=Lax cookies on credentialed storefront fetches. Same-site custom domains preserve CSRF defenses without weakening cookies to SameSite=None.

## 2026-11-06: Synchronizer CSRF token

**Decision:** Bind a random CSRF value into signed guest/access claims, return it through session/cart JSON, retain it only in frontend memory, and require it plus an exact Origin on unsafe requests.

**Reason:** This avoids a frontend-readable domain cookie that would expose CSRF material to every subdomain while still supporting separate same-site frontend/API origins.

## 2026-11-06: PostgreSQL-authoritative checkout

**Decision:** Redis supports OTPs and rate limits, but PostgreSQL row locks, scoped idempotency records, source-cart uniqueness, coupon ledgers, and order counters exclusively control order and inventory correctness.

**Reason:** Cache loss or duplicate requests must never oversell inventory, double-use a coupon, allocate duplicate order numbers, or create multiple orders from one cart.

## 2026-11-06: Client account guard, server authorization

**Decision:** Account pages use a client auth gate for routing UX while every account API query scopes ownership through a strict active-session customer dependency.

**Reason:** Host-only API cookies from `api.bojro.com.bd` are intentionally invisible to the Next.js server at `bojro.com.bd`. A server-rendered auth guard would be unreliable; the API remains the sole security boundary.

## 2026-11-06: Structured review-photo assets

**Decision:** Reviews reference owned upload records, never arbitrary customer-supplied URLs. Development/E2E uses an explicitly enabled signed mock provider; production rejects mock storage until the Cloudinary provider phase is configured.

**Reason:** Structured assets enforce ownership, type/size limits, lifecycle cleanup, moderation, and signature verification without proxying image bytes through FastAPI.

## 2026-11-07: Separate admin security domain

**Decision:** Admin access uses distinct token audiences/types, cookie names/paths, refresh sessions, CSRF state, rate limits, and optional encrypted TOTP/recovery codes.

**Reason:** An authenticated customer must never become an admin through token confusion, shared refresh rotation, or frontend route mistakes. Server-side role/session checks remain authoritative.

## 2026-11-07: Transactional audit and outbox

**Decision:** Every admin aggregate mutation commits its revision, idempotency result, minimal redacted diff, inventory movement where relevant, audit event, and revalidation/outbox row atomically. Workers perform network calls after commit.

**Reason:** External outages must not roll back valid business changes or leave catalog caches silently stale, while retries must never duplicate admin effects.

## 2026-11-07: Operational PDFs are not fiscal invoices

**Decision:** Generate immutable order-snapshot invoice and packing-slip PDFs for operations and label them non-fiscal.

**Reason:** A production tax/fiscal invoice requires jurisdiction-specific legal review beyond a generic commerce implementation.

## 2026-11-07: Unknown provider outcomes dominate retry

**Decision:** Timeouts or malformed provider responses produce a durable `unknown` attempt rather than `failed`. A query/reconciliation by stable merchant reference must resolve it before another create/refund/booking command.

**Reason:** A provider may have committed while its response was lost. Blind retry can double-charge, over-refund or create duplicate consignments.

## 2026-11-07: Verified events before mutation

**Decision:** Reject unauthenticated webhooks before insertion; store verified raw-body digests and provider event IDs; process normalized events asynchronously under resource locks.

**Reason:** Browser callbacks and unverified JSON cannot establish payment or delivery truth. Durable verified events support replay, ordering, reconciliation and dead-letter operations safely.

## 2026-11-07: Encrypted specialized engagement outboxes

**Decision:** Store encrypted recipient/content/context in notification, analytics and assistant-specific tables with versioned AES-GCM keys and domain-separated HMAC lookup keyrings; keep Redis as wake/rate-limit infrastructure only.

**Reason:** PostgreSQL provides durable retry/lease/dead-letter state while key rotation and terminal erasure limit the impact of database access. OTP challenges are atomic TTL-bound Redis records whose recoverable phone value is encrypted.

## 2026-11-07: Consent before optional telemetry

**Decision:** GA4 loads only after analytics consent; Pixel and CAPI require advertising consent. Purchase event IDs are generated transactionally by the server and reused across browser/server Meta delivery.

**Reason:** No optional analytics request or identifier should leave the browser/server before informed consent, and shared event IDs prevent browser/CAPI double counting.

## 2026-11-07: Grounded assistant tools only

**Decision:** The model receives a fixed prompt plus bounded, redacted outputs from allowlisted product/policy/order tools; it cannot select arbitrary tools, browse URLs, run SQL or receive raw order/phone/address data.

**Reason:** Store content is untrusted retrieval data, and sincere identity questions/order checks require deterministic server behavior rather than unconstrained model claims.

## 2026-11-08: Public Vercel-to-Railway API boundary

**Decision:** Both browser and Vercel server-rendered requests use the public Railway API custom domain. Railway private networking is limited to Railway services and data stores; `INTERNAL_API_URL` is server-only but not a private Railway URL.

**Reason:** Vercel does not participate in Railway's private network. A same-site storefront/API custom-domain pair preserves SameSite=Lax cookie behavior without claiming impossible private connectivity.

## 2026-11-08: Production-like staging and explicit test capability

**Decision:** Staging uses secure cookies, separate real infrastructure, Cloudinary, real provider sandbox/test accounts, worker heartbeat, and no application mocks or reset endpoints. Local and CI E2E capabilities default off and are enabled only by explicit command environment.

**Reason:** A permissive staging environment cannot prove production configuration, while ambient E2E reset routes and public mock switches create avoidable data and authorization risk.

## 2026-11-08: Forward-compatible releases instead of automatic schema downgrade

**Decision:** Release order is backup/PITR marker, backward-compatible migration, worker, API, then frontend. Application rollback is allowed only across a compatible schema. Database downgrade is never an automatic rollback; prefer a forward fix and use isolated restore/cutover only through incident approval.

**Reason:** Several migrations intentionally refuse lossy downgrade when live data exists. Coupling code rollback to destructive schema reversal would turn an application incident into a data-loss incident.

## 2026-11-08: Recovery objectives and authoritative stores

**Decision:** PostgreSQL targets a 15-minute RPO and four-hour RTO using Railway PITR plus encrypted off-platform logical backups. Cloudinary asset bytes require provider backup/version evidence. Redis is non-authoritative and is rebuilt empty.

**Reason:** Platform-local snapshots alone do not cover account compromise, provider outage, or logical corruption. Explicit authority and objectives make restore drills measurable and prevent stale Redis data from being treated as commerce truth.

## 2026-11-08: Retention survives backup and restore

**Decision:** Source data, logs, provider payloads, and backups follow the schedule in `PRIVACY_RETENTION.md`. Backups are immutable until expiry rather than edited in place; a restored copy remains isolated until deletion, suppression, and consent-withdrawal ledgers are replayed.

**Reason:** Recovery must not silently resurrect data that was deleted or suppressions that were applied after the recovery point. Immutable expiring backups plus pre-cutover replay preserve both recoverability and privacy obligations.

## 2026-11-08: Initial external-provider launch scope

**Decision:** Initial production launch is COD with audited manual fulfillment. Online payments, couriers, Meta CAPI, and the assistant remain disabled until each provider's signed evidence record is complete. Production email uses Resend and OTP uses a named documentation-verified idempotent SMS provider because the application requires those real delivery paths.

**Reason:** Adapter boundaries and mocks prove internal behavior, not merchant onboarding, live credentials, callback ownership, settlement, or legal approval. Disabled is safer than pretending an incomplete provider is production-ready.
