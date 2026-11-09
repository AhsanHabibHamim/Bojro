# Bojro

Bojro (বজ্র) is a Bangla-first, mobile-first, single-brand commerce platform for Bangladesh. It is a pnpm monorepo with a Next.js storefront, FastAPI API, ARQ worker, PostgreSQL, and Redis.

## Prerequisites

- Node.js 24.15+
- pnpm 11.5.2
- Python 3.12
- [uv](https://docs.astral.sh/uv/) 0.13.4
- PostgreSQL 16 and Redis 7, or Docker with the Compose plugin

## First Run With Docker

```bash
cp infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/docker-compose.yml up --build --wait
```

The local API container applies migrations and the idempotent demo seed on startup. This Compose behavior is for development and CI only; production uses the safe bootstrap and release sequence in `docs/DEPLOYMENT.md`.

- Storefront: <http://localhost:3000/bn>
- English storefront: <http://localhost:3000/en>
- API documentation: <http://localhost:8000/docs>
- API liveness: <http://localhost:8000/health>
- API readiness: <http://localhost:8000/ready>
- Admin login: <http://localhost:3000/en/admin/login>

PostgreSQL and Redis bind to loopback. Example secrets and mock providers are local-only. E2E reset routes and browser mock switches are off by default.

## Local Development

Start PostgreSQL and Redis, then:

```bash
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
pnpm install --frozen-lockfile
uv sync --project backend --frozen --all-groups
pnpm db:migrate
pnpm db:seed
pnpm api:generate
pnpm dev
```

The default database URL expects PostgreSQL at `localhost:5432`. Redis is optional only during development; readiness reports it as degraded when unavailable.

## Quality Gates

```bash
pnpm lint
pnpm format:check
pnpm typecheck
DATABASE_URL=postgresql+asyncpg://bojro:local-only-change-me@localhost:5432/bojro \
REDIS_URL=redis://localhost:6379/15 pnpm test
pnpm build
```

PostgreSQL is required for the complete backend suite. The enforced backend coverage floor is 76%; launch evidence records the measured value rather than claiming a higher threshold.

With a normal local stack running, install Chromium and run browser tests that do not need reset fixtures:

```bash
pnpm exec playwright install chromium
PLAYWRIGHT_BASE_URL=http://localhost:3000 \
PLAYWRIGHT_SKIP_WEBSERVER=1 \
pnpm test:e2e
```

The complete provider/engagement E2E suite is intentionally explicit. Start a fresh disposable Compose stack with every mock and reset capability opted in:

```bash
APP_ENV=test \
BKASH_MODE=mock NAGAD_MODE=mock SSLCOMMERZ_MODE=mock \
PATHAO_MODE=mock STEADFAST_MODE=mock REDX_MODE=mock \
COURIER_PROVIDER=mock EMAIL_PROVIDER=mock SMS_PROVIDER=mock \
META_CAPI_MODE=mock ASSISTANT_PROVIDER=mock ASSISTANT_PUBLIC_ENABLED=true \
META_PIXEL_ID=123456789012345 GOOGLE_ANALYTICS_ID=G-E2EBOJRO \
WHATSAPP_ENABLED=true WHATSAPP_PHONE=+8801700000000 \
PHASE6_E2E_RESET_TOKEN=local-phase6-e2e-reset-token \
PHASE7_E2E_ENABLED=true \
PHASE7_E2E_RESET_TOKEN=local-phase7-e2e-reset-token \
NEXT_PUBLIC_E2E_STORAGE_MOCK=1 \
NEXT_PUBLIC_E2E_PROVIDER_MOCK=1 \
NEXT_PUBLIC_E2E_ENGAGEMENT_MOCK=1 \
SEED_ADMIN_EMAIL=admin-e2e@bojro.test \
SEED_ADMIN_PASSWORD='E2E-only-admin-password-47!' \
docker compose --env-file infra/.env -f infra/docker-compose.yml up --build --wait
```

Then run:

```bash
PLAYWRIGHT_BASE_URL=http://localhost:3000 \
PLAYWRIGHT_SKIP_WEBSERVER=1 \
E2E_API_URL=http://localhost:8000 \
E2E_OTP_CODE=123456 \
E2E_ADMIN_EMAIL=admin-e2e@bojro.test \
E2E_ADMIN_PASSWORD='E2E-only-admin-password-47!' \
E2E_ADMIN_ORDER_NUMBER=BJ-2099-900002 \
NEXT_PUBLIC_E2E_STORAGE_MOCK=1 \
NEXT_PUBLIC_E2E_PROVIDER_MOCK=1 \
NEXT_PUBLIC_E2E_ENGAGEMENT_MOCK=1 \
NEXT_PUBLIC_E2E_SEED_RESET_URL=http://localhost:8000/api/v1/e2e/phase6/reset \
PHASE6_E2E_RESET_TOKEN=local-phase6-e2e-reset-token \
NEXT_PUBLIC_E2E_PHASE7_RESET_URL=http://localhost:8000/api/v1/e2e/phase7/reset \
PHASE7_E2E_RESET_TOKEN=local-phase7-e2e-reset-token \
pnpm test:e2e
```

Use only disposable data. Production and staging reject or prohibit these switches.

## Database And Admin Bootstrap

```bash
pnpm db:migrate
pnpm db:seed
```

The demo seed creates geo, catalog, reviews, offers, content, settings, and deterministic test fixtures. It is for local development and CI. Never run it in production.

Production uses environment-supplied `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD` with:

```bash
uv run --project backend python -m scripts.bootstrap_admin
```

Remove the bootstrap credentials after the one-shot action. The script does not load demo commerce data or silently rewrite an existing password.

## API Contract

OpenAPI is the source of truth. Regenerate the committed typed client after an API change:

```bash
pnpm api:generate
```

CI regenerates both artifacts and rejects tracked or untracked drift.

## Operations

- [Architecture](docs/ARCHITECTURE.md)
- [API contract](docs/API.md)
- [Deployment and rollback](docs/DEPLOYMENT.md)
- [Provider activation register](docs/PROVIDERS.md)
- [Security review](docs/SECURITY.md)
- [Backup and restore](docs/BACKUP_RESTORE.md)
- [Operations, SLOs, alerts, and runbooks](docs/OPERATIONS.md)
- [Incident response](docs/INCIDENT_RESPONSE.md)
- [Privacy and retention](docs/PRIVACY_RETENTION.md)
- [Accessibility and performance evidence](docs/ACCESSIBILITY_PERFORMANCE.md)
- [Launch go/no-go checklist](docs/LAUNCH_CHECKLIST.md)
- [Architecture decisions](docs/DECISIONS.md)

Install local Git hooks with `uv tool install pre-commit && pre-commit install`.
