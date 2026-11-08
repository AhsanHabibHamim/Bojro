# Deployment

## Local Containers

```bash
cp infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/docker-compose.yml up --build
```

Services expose the storefront on `3000`, API on `8000`, PostgreSQL on `5432`, and Redis on `6379`. Change all example passwords outside local development.

## Vercel Frontend

Use `frontend` as the project root and pnpm. Required variables are documented in `frontend/.env.example`. Production must use `https://bojro.com.bd` for the storefront and a Railway custom domain such as `https://api.bojro.com.bd` for `NEXT_PUBLIC_API_URL`; the bare `*.railway.app` hostname is cross-site and incompatible with the required SameSite=Lax auth cookies. Configure both domains only after DNS ownership and TLS are verified.

Set `INTERNAL_API_URL` to the Railway private/backend URL when available and provide the same strong `REVALIDATION_SECRET` to the trusted admin publisher and Vercel runtime. Never expose that secret through a `NEXT_PUBLIC_` variable.

## Railway Backend

Build with `infra/backend.Dockerfile` from repository root. Attach PostgreSQL and Redis, then configure all variables from `backend/.env.example`. Run `uv run alembic -c alembic.ini upgrade head` inside the image as a release command before starting web and worker processes.

Production payment, courier, notification, storage, analytics, and LLM credentials are intentionally absent in Phase 1. Later provider phases must use official sandbox credentials before production activation.

Vercel preview domains cannot validate production cookie auth against Railway. Use paired custom staging domains such as `staging.bojro.com.bd` and `api-staging.bojro.com.bd`, or a same-origin BFF. Set four independent 32+ character secrets for JWT, guest identity, checkout quotes, and OTP HMAC; never reuse `APP_SECRET_KEY` for them. The mock OTP provider is development/test-only and production startup rejects it.

`STORAGE_PROVIDER=mock` and `NEXT_PUBLIC_E2E_STORAGE_MOCK=true` are limited to local development and CI. Production must omit the public E2E flag and will fail closed until the Cloudinary provider credentials and verification adapter are delivered in the provider-integration phase.

Run a separate Railway worker service with `arq app.workers.review_photos.WorkerSettings`. Production readiness should require its Redis health heartbeat. Configure independent `ADMIN_JWT_SECRET_KEY`, versioned `ADMIN_TOTP_KEYRING`, revalidation URL/secret, and a real storage/courier provider before enabling those features; local `mock` providers are rejected in production.

Use `backend/scripts/bootstrap_admin.py` after migrations for an existing production database. It provisions only one environment-supplied admin and required system defaults; it never loads the demo catalog or rewrites an existing admin password.

Configure stable public HTTPS API/storefront callback origins before enabling any provider. Each payment/courier has an independent `disabled|mock|sandbox|live` mode; production rejects mock/sandbox and incomplete credentials. Follow `docs/PROVIDERS.md` for the evidence and activation gate. Monitor unknown attempts, reconciliation lag, verification failures, refund errors, shipment lag and dead letters.

Phase 7 production requires explicit engagement AES/HMAC/unsubscribe keyrings, a real idempotent SMS provider for OTP/lifecycle traffic, an approved email provider, current consent policy version, worker heartbeat readiness and retention jobs. Meta CAPI requires a bound Pixel/token; the assistant requires an approved zero-retention/DPA configuration. Mock engagement providers and the E2E reset endpoint are rejected outside local/CI.
