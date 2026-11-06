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
