# Bojro

Bojro (বজ্র) is a Bangla-first, mobile-first, single-brand commerce platform for Bangladesh. This repository is a pnpm monorepo with a Next.js storefront and a FastAPI API.

## Prerequisites

- Node.js 22+
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
pnpm test
pnpm build
```

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
