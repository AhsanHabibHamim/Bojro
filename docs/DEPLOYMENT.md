# Deployment

## Local Containers

```bash
cp infra/.env.example infra/.env
docker compose --env-file infra/.env -f infra/docker-compose.yml up --build
```

Services expose the storefront on `3000`, API on `8000`, PostgreSQL on `5432`, and Redis on `6379`. Change all example passwords outside local development.

## Vercel Frontend

Use `frontend` as the project root and pnpm. Required variables are documented in `frontend/.env.example`. `NEXT_PUBLIC_API_URL` must be the public HTTPS Railway API URL. Configure `bojro.com.bd` only after DNS ownership and TLS are verified.

Set `INTERNAL_API_URL` to the Railway private/backend URL when available and provide the same strong `REVALIDATION_SECRET` to the trusted admin publisher and Vercel runtime. Never expose that secret through a `NEXT_PUBLIC_` variable.

## Railway Backend

Build with `infra/backend.Dockerfile` from repository root. Attach PostgreSQL and Redis, then configure all variables from `backend/.env.example`. Run `uv run alembic -c alembic.ini upgrade head` inside the image as a release command before starting web and worker processes.

Production payment, courier, notification, storage, analytics, and LLM credentials are intentionally absent in Phase 1. Later provider phases must use official sandbox credentials before production activation.
