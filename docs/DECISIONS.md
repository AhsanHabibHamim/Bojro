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
