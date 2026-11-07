# Bojro

Bojro (বজ্র) is a Bangla-first, mobile-first, single-brand commerce platform for Bangladesh. This repository is a pnpm monorepo with a Next.js storefront and a FastAPI API.

## Prerequisites

- Node.js 24.15+
- pnpm 10+
- Python 3.12
- [uv](https://docs.astral.sh/uv/) 0.11.23
- PostgreSQL 16 and Redis 7, or Docker with the Compose plugin

## First Run With Docker

```bash
cp infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/docker-compose.yml up --build
```

The API container applies migrations and seeds idempotently on startup. Open:

- Storefront: <http://localhost:3000/bn>
- English storefront: <http://localhost:3000/en>
- API documentation: <http://localhost:8000/docs>
- API health: <http://localhost:8000/health>
- Cart: <http://localhost:3000/en/cart>
- Checkout: <http://localhost:3000/en/checkout>
- Account login: <http://localhost:3000/en/account>
- Order tracking: <http://localhost:3000/en/track-order>
- Admin login: <http://localhost:3000/en/admin/login>

## Local Development

Start PostgreSQL and Redis, then:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
pnpm install
uv sync --project backend --all-groups
pnpm db:migrate
pnpm db:seed
pnpm api:generate
pnpm dev
```

The default local database URL expects PostgreSQL at `localhost:5432` with database, user, and password `bojro`. Redis is optional during development; readiness reports it as degraded when unavailable.

## Quality Gates

```bash
pnpm lint
pnpm format:check
pnpm typecheck
DATABASE_URL=postgresql+asyncpg://bojro:local-only-change-me@localhost:5432/bojro \
REDIS_URL=redis://localhost:6379/15 pnpm test
pnpm build
```

The database URL is required for the inventory, idempotency, coupon, migration-preflight, and no-overselling tests; skipping PostgreSQL intentionally cannot satisfy the enforced 85% backend coverage gate.

With the full Docker stack running, execute the browser golden path with:

```bash
pnpm exec playwright install chromium
PLAYWRIGHT_BASE_URL=http://localhost:3000 PLAYWRIGHT_SKIP_WEBSERVER=1 pnpm test:e2e
```

The example stack uses the explicit development-only mock OTP code from `infra/.env`. Production rejects the mock provider and requires an approved notification adapter.

The admin account is created only when `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` are set. The Compose stack also runs the ARQ worker for media cleanup, catalog/home revalidation outbox delivery, and courier reconciliation.

Install local Git hooks with `uv tool install pre-commit && pre-commit install`.

## Database

```bash
pnpm db:migrate
pnpm db:seed
```

The seed is idempotent and creates the Bangladesh geo hierarchy, demo catalog, reviews, coupons, flash sale, banners, homepage sections, and site settings. An admin is created only when both `SEED_ADMIN_EMAIL` and `SEED_ADMIN_PASSWORD` are supplied.

## API Client

OpenAPI is the contract. Regenerate the committed typed client after an API schema change:

```bash
pnpm api:generate
```

See `docs/ARCHITECTURE.md`, `docs/API.md`, and `docs/DEPLOYMENT.md` for details.
