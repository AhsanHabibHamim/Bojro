# Architecture

## System Context

Bojro is a single-brand commerce application. The Next.js App Router frontend deploys to Vercel. The FastAPI service and ARQ workers deploy to Railway, backed by PostgreSQL and Redis. Catalog content is rendered with Server Components and will use tag-based ISR invalidation in Phase 2; cart, checkout, account, and admin flows remain dynamic.

## Repository

- `frontend/`: Next.js, TypeScript, next-intl, Tailwind CSS, Vitest.
- `backend/`: FastAPI, Pydantic v2, async SQLAlchemy 2, Alembic, pytest.
- `infra/`: local Docker Compose and production-oriented Dockerfiles.
- `docs/`: contracts, decisions, operations, and security notes.

## Backend Boundaries

Requests flow from routers to services to repositories. Routers validate transport concerns, services own transactions and business invariants, and repositories own persistence queries. External providers are injected through protocols so production, sandbox, and mock implementations remain interchangeable.

## Data

PostgreSQL is authoritative. Monetary values are integer poisha with ISO currency `BDT`; floating-point money is prohibited. Public entities use UUIDv7 values. All timestamps are UTC `timestamptz`; clients display them in `Asia/Dhaka`.

Redis supports rate limits, OTPs, cart sessions, catalog caching, and ARQ. Development remains usable without Redis; features explicitly requiring it report a degraded state instead of crashing.

## Security

Authentication will use short access JWTs and rotating refresh tokens in `httpOnly`, `Secure`, `SameSite=Lax` cookies with a CSRF token for mutations. Passwords use Argon2id. CORS is allowlisted, request IDs are returned, logs are structured, and secrets are environment-only.

## Contract

FastAPI's OpenAPI document is the source of truth. `pnpm api:generate` exports a deterministic schema to `backend/openapi.json` and generates `frontend/src/lib/api/schema.d.ts`. Application API helpers must consume that type surface rather than scatter handwritten response types.
