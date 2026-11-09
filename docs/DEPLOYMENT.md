# Deployment

This is the production and staging deployment runbook. A green CI run is necessary but is not authorization to deploy. Every production release also requires the evidence and sign-offs in [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).

## Target Topology

| Component  | Platform   | Network exposure                                       | Process                                                                  |
| ---------- | ---------- | ------------------------------------------------------ | ------------------------------------------------------------------------ |
| Storefront | Vercel     | Public HTTPS                                           | Next.js standalone/runtime                                               |
| API web    | Railway    | Public HTTPS at the API custom domain                  | `.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORT`             |
| Worker     | Railway    | No public port                                         | `.venv/bin/arq app.workers.review_photos.WorkerSettings`                 |
| PostgreSQL | Railway    | Private Railway network; operator access is restricted | Authoritative commerce and job state                                     |
| Redis      | Railway    | Private Railway network                                | Cache, rate limits, OTP challenge state, ARQ wakeups, and heartbeat only |
| Media      | Cloudinary | Signed direct upload and CDN delivery                  | Authoritative asset bytes; metadata remains in PostgreSQL                |

Vercel cannot reach Railway private networking. Both `NEXT_PUBLIC_API_URL` and `INTERNAL_API_URL` on Vercel must use the public custom API origin, such as `https://api.bojro.com.bd`. `INTERNAL_API_URL` is server-only, but it is not a private-network URL.

## Environment And Domains

Use separate Railway projects, databases, Redis instances, Cloudinary environments, Vercel environments, provider credentials, and encryption/signing keys.

| Environment | Storefront                     | API                                | Provider policy                                                                           |
| ----------- | ------------------------------ | ---------------------------------- | ----------------------------------------------------------------------------------------- |
| Production  | `https://bojro.com.bd`         | `https://api.bojro.com.bd`         | `live` or `disabled`; never `mock` or `sandbox`                                           |
| Staging     | `https://staging.bojro.com.bd` | `https://api-staging.bojro.com.bd` | Official sandbox/test accounts or `disabled`; never application mocks                     |
| Local/CI    | `http://localhost:3000`        | `http://localhost:8000`            | Explicit mocks are allowed; E2E/reset switches remain off unless the test command opts in |

Staging is production-like: secure cookies, separate real infrastructure, worker heartbeat, real signed Cloudinary uploads, real email/SMS test accounts with recipient allowlists, no seed data reset route, and no public E2E flags.

## DNS, TLS, And Email Authentication

Create records only from the current targets displayed by Vercel, Railway, and the email provider. Do not copy historical IP addresses from this document.

| Name              | Type                                       | Target and behavior                                                                                                                                      |
| ----------------- | ------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `@`               | Provider-required `A`, `ALIAS`, or `ANAME` | Exact Vercel production apex target                                                                                                                      |
| `www`             | `CNAME`                                    | Exact Vercel target; configure a permanent redirect to `https://bojro.com.bd`                                                                            |
| `api`             | `CNAME`                                    | Exact Railway API custom-domain target                                                                                                                   |
| `staging`         | Provider-required record                   | Exact Vercel staging target                                                                                                                              |
| `api-staging`     | `CNAME`                                    | Exact Railway staging API target                                                                                                                         |
| Email return path | Provider-required `CNAME`                  | Exact Resend bounce/return-path target                                                                                                                   |
| Email DKIM        | Provider-required `CNAME` or `TXT`         | Every selector supplied by Resend; never shorten the value                                                                                               |
| `@`               | `TXT`                                      | One SPF record only. Merge the provider's `include:` into any existing SPF record instead of publishing a second `v=spf1` record.                        |
| `_dmarc`          | `TXT`                                      | Start with `v=DMARC1; p=none; rua=mailto:<monitored-address>; adkim=s; aspf=s; pct=100`, review reports, then approve `quarantine` and finally `reject`. |

Before cutover, reduce DNS TTL to 300 seconds at least one prior TTL window in advance. Restore a normal TTL after 24 stable hours. Verify authoritative DNS, both certificate chains, hostname redirects, HSTS, provider callback URLs, SPF, DKIM, and DMARC from outside the deployment accounts. A mailbox used by `rua` must exist and be monitored.

## Vercel Frontend

Create one Vercel project with these settings:

| Setting           | Value                            |
| ----------------- | -------------------------------- |
| Root directory    | `frontend`                       |
| Framework         | Next.js                          |
| Node.js           | 24.x                             |
| Install command   | `pnpm install --frozen-lockfile` |
| Build command     | `pnpm build`                     |
| Production domain | `bojro.com.bd`                   |

Set variables using Vercel environment scope, not `.env` files:

| Variable                               | Production                             | Preview/staging                          | Secret           |
| -------------------------------------- | -------------------------------------- | ---------------------------------------- | ---------------- |
| `NEXT_PUBLIC_SITE_URL`                 | `https://bojro.com.bd`                 | Paired staging/preview storefront origin | No               |
| `NEXT_PUBLIC_API_URL`                  | `https://api.bojro.com.bd`             | `https://api-staging.bojro.com.bd`       | No               |
| `INTERNAL_API_URL`                     | `https://api.bojro.com.bd`             | `https://api-staging.bojro.com.bd`       | No, server-only  |
| `REVALIDATION_SECRET`                  | Same strong value as Railway           | Separate staging value                   | Yes              |
| `NEXT_PUBLIC_ERROR_REPORTING_ENDPOINT` | Approved browser-safe HTTPS ingest URL | Separate staging ingest URL or unset     | No               |
| `ERROR_REPORTING_ENDPOINT`             | Approved server-side HTTPS ingest URL  | Separate staging ingest URL or unset     | Yes, server-only |
| `NEXT_PUBLIC_FACEBOOK_URL`             | Approved public URL or unset           | Approved test value or unset             | No               |
| `NEXT_PUBLIC_INSTAGRAM_URL`            | Approved public URL or unset           | Approved test value or unset             | No               |
| `NEXT_PUBLIC_WHATSAPP_URL`             | Approved public URL or unset           | Approved test value or unset             | No               |

Never configure `NEXT_PUBLIC_E2E_STORAGE_MOCK`, `NEXT_PUBLIC_E2E_PROVIDER_MOCK`, `NEXT_PUBLIC_E2E_ENGAGEMENT_MOCK`, reset URLs, or reset tokens in Vercel staging or production. Preview deployments must not point at the production API. Unpaired `*.vercel.app` previews cannot use the production SameSite cookie flow; use the staging domain pair for authenticated acceptance.

## Railway Web And Worker

Create PostgreSQL, Redis, `web`, and `worker` services in each Railway project. Build both application services from repository root with `infra/backend.Dockerfile`. Do not attach persistent application volumes.

The Railway PostgreSQL URI must be exposed to the application with the required async driver scheme. Build `DATABASE_URL` from Railway reference variables as `postgresql+asyncpg://<user>:<password>@<private-host>:<port>/<database>`; do not pass an unmodified `postgresql://` URI. Use the private Redis URL.

When the data services are named `Postgres` and `Redis`, create these shared application variables on web and worker (URL-encode any credential characters that are not URI-safe):

```dotenv
DATABASE_URL=postgresql+asyncpg://${{Postgres.PGUSER}}:${{Postgres.PGPASSWORD}}@${{Postgres.PGHOST}}:${{Postgres.PGPORT}}/${{Postgres.PGDATABASE}}
REDIS_URL=${{Redis.REDIS_URL}}
```

Confirm the resolved hosts are Railway private hosts without printing the resolved credentials. Do not use `DATABASE_PUBLIC_URL` or a public Redis URL for normal application traffic.

| Service setting    | Web                                                               | Worker                                                                 |
| ------------------ | ----------------------------------------------------------------- | ---------------------------------------------------------------------- |
| Start command      | Uvicorn command above                                             | ARQ command above                                                      |
| Public domain      | API custom domain                                                 | None                                                                   |
| Health check       | `GET /ready`, 30-second timeout                                   | API readiness worker-heartbeat check plus an external heartbeat alert  |
| Replicas at launch | At least two web replicas after migration compatibility is proven | Exactly one scheduler/worker replica until job concurrency is reviewed |
| Restart policy     | On failure                                                        | On failure                                                             |

The web and worker must receive the same backend configuration revision. Scope the following to both services through Railway shared variables:

| Group             | Variables                                                                                                                                                                                                                              |
| ----------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Core              | `APP_ENV`, `DEBUG=false`, `LOG_LEVEL`, `DATABASE_URL`, `REDIS_URL`, `APP_SECRET_KEY`                                                                                                                                                   |
| Auth/signing      | `JWT_SECRET_KEY`, `ADMIN_JWT_SECRET_KEY`, `GUEST_IDENTITY_SECRET`, `QUOTE_TOKEN_SECRET`, `OTP_HMAC_SECRET`, `COOKIE_SECURE=true`, `COOKIE_SAME_SITE=lax`, `ADMIN_TOTP_ACTIVE_KEY_ID`, `ADMIN_TOTP_KEYRING`, `ADMIN_TOTP_REQUIRED=true` |
| Origins           | `PUBLIC_API_BASE_URL`, `PUBLIC_STOREFRONT_BASE_URL`, `CORS_ORIGINS`, `TRUSTED_HOSTS`, `REVALIDATION_URL`, `REVALIDATION_SECRET`                                                                                                        |
| Worker            | `WORKER_HEARTBEAT_KEY`, `WORKER_HEARTBEAT_MAX_AGE_SECONDS`, `WORKER_HEARTBEAT_REQUIRED=true`, `OUTBOX_BATCH_SIZE`, `OUTBOX_MAX_ATTEMPTS`                                                                                               |
| Observability     | `SENTRY_DSN`, `SENTRY_RELEASE=<immutable commit SHA>`, `SENTRY_TRACES_SAMPLE_RATE`; use the same release value on web and worker and a separate DSN per environment                                                                    |
| Retention         | `RETENTION_CLEANUP_BATCH_SIZE`, `NOTIFICATION_CONTENT_RETENTION_DAYS`, `NOTIFICATION_ATTEMPT_RETENTION_DAYS`, `ANALYTICS_EVENT_RETENTION_DAYS`, `ASSISTANT_RETENTION_DAYS`                                                             |
| Storage           | `STORAGE_PROVIDER=cloudinary`, `CLOUDINARY_CLOUD_NAME`, `CLOUDINARY_API_KEY`, `CLOUDINARY_API_SECRET`                                                                                                                                  |
| Provider modes    | `BKASH_MODE`, `NAGAD_MODE`, `SSLCOMMERZ_MODE`, `PATHAO_MODE`, `STEADFAST_MODE`, `REDX_MODE`, documentation/configuration gates, and only the credentials for enabled providers                                                         |
| Engagement keys   | `ENGAGEMENT_PII_ACTIVE_KEY_ID`, `ENGAGEMENT_PII_KEYRING`, `ENGAGEMENT_LOOKUP_HMAC_ACTIVE_KEY_ID`, `ENGAGEMENT_LOOKUP_HMAC_KEYRING`, `UNSUBSCRIBE_SIGNING_ACTIVE_KEY_ID`, `UNSUBSCRIBE_SIGNING_KEYRING`, `CONSENT_POLICY_VERSION`       |
| Messaging         | `EMAIL_PROVIDER=resend`, `EMAIL_FROM`, `RESEND_API_KEY`, external `SMS_*` provenance/idempotency settings, notification lease/batch/retention settings                                                                                 |
| Optional features | `META_CAPI_MODE` and credentials, `ASSISTANT_PROVIDER` and approved endpoint/model/credentials, `NEWSLETTER_ENABLED`, `WHATSAPP_ENABLED`, `WHATSAPP_PHONE`                                                                             |

`PORT` is web-only and supplied by Railway. Bootstrap credentials are one-shot web/operator variables: add `BOOTSTRAP_ADMIN_EMAIL` and `BOOTSTRAP_ADMIN_PASSWORD`, run the bootstrap command, confirm access, and remove both values. Do not set `SEED_ADMIN_*` on Railway.

Compare exported variable names, never secret values, between web and worker before every release. A missing worker provider or keyring variable is a no-go even when the web process is healthy.

## Cloudinary

Use a dedicated product environment per Bojro environment. The backend already signs uploads and verifies provider metadata; it does not accept arbitrary final URLs.

1. Create restricted credentials for the staging or production Cloudinary environment.
2. Set `STORAGE_PROVIDER=cloudinary` and all three `CLOUDINARY_*` variables on Railway web and worker.
3. Keep API secrets out of Vercel and every `NEXT_PUBLIC_*` variable.
4. Restrict upload formats, byte size, dimensions, folder prefixes, and transformations to the application contract.
5. Enable asset backup/version retention supported by the Cloudinary plan and record its retention in [BACKUP_RESTORE.md](BACKUP_RESTORE.md).
6. In staging, prove sign, browser upload, completion verification, rendering, moderation, delete, and failed-upload cleanup.
7. Configure quota, error-rate, and deletion-failure alerts. Record the Cloudinary account owner and break-glass access in the secret manager.

## Prohibited Staging And Production Settings

Deployment must fail when any of these are present or effective:

- `OTP_PROVIDER` or `OTP_EXTERNAL_*` (deprecated).
- `PHASE6_E2E_RESET_TOKEN`, `PHASE7_E2E_ENABLED=true`, or `PHASE7_E2E_RESET_TOKEN`.
- Any `NEXT_PUBLIC_E2E_*` variable or E2E reset URL/token.
- `STORAGE_PROVIDER=mock`, `COURIER_PROVIDER=mock`, `EMAIL_PROVIDER=mock`, `SMS_PROVIDER=mock`, `META_CAPI_MODE=mock`, or `ASSISTANT_PROVIDER=mock`.
- `BKASH_MODE=mock`, `NAGAD_MODE=mock`, `SSLCOMMERZ_MODE=mock`, `PATHAO_MODE=mock`, `STEADFAST_MODE=mock`, or `REDX_MODE=mock`.
- `sandbox` provider mode in production.
- `SEED_ADMIN_EMAIL`, `SEED_ADMIN_PASSWORD`, demo seed execution, local/example secrets, `.test` hosts, HTTP public origins, wildcard CORS/trusted hosts, or legal approval booleans set without linked approval evidence.

Disabled providers are valid. Do not enable a provider merely to satisfy a launch checklist; follow [PROVIDERS.md](PROVIDERS.md).

## Release Procedure

Use one immutable commit SHA across Vercel and both Railway services.

1. Confirm required GitHub checks, code-owner approval, production-environment approval, provider scope, change record, rollback owner, and incident channel.
2. Confirm Railway backup success and record a PITR timestamp. Run an off-platform logical backup when the change affects schema or critical data.
3. Deploy and verify backward-compatible database migrations once from a Railway one-off shell: `.venv/bin/alembic -c alembic.ini upgrade head`.
4. Run `.venv/bin/python -m scripts.bootstrap_admin` only when initial production bootstrap is required; remove its credentials immediately.
5. Deploy the worker revision first. Confirm a fresh heartbeat, no startup loop, and no unexpected dead letters or reconciliation backlog.
6. Deploy the web revision. From its Railway environment run `.venv/bin/python -m scripts.preflight`. Require exit zero and `/ready` status `ready`; an unexplained `degraded` state is a no-go.
7. Verify `GET /health` and `GET /ready` through the public API domain before changing the storefront.
8. Deploy the same SHA to Vercel. Confirm build-time public variables and runtime server variables are the approved environment values.
9. Run the `Release Verification` workflow with the target environment, immutable SHA, preflight evidence URL, and public origins.
10. Complete authenticated customer, guest checkout, admin login, worker delivery, upload, provider kill-switch, and monitoring smoke checks from [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).
11. Observe the release for at least 30 minutes. Close the change only after error, latency, worker, provider, and conversion indicators are stable.

## Post-Deploy Smoke

The public, read-only baseline is automated by:

```bash
API_URL=https://api.bojro.com.bd \
STOREFRONT_URL=https://bojro.com.bd \
scripts/postdeploy-smoke.sh
```

It verifies liveness, readiness, request IDs/security headers, both locales, robots, sitemap, and cross-origin response basics without using customer credentials or creating orders. Store the output with the release evidence. Complete state-changing smoke tests manually with dedicated canary identities and immediately reconcile/cancel test orders.

Also run the backend's bounded JSON verifier, which checks provider readiness, disabled production docs, and generic order-tracking disclosure:

```bash
POSTDEPLOY_BASE_URL=https://api.bojro.com.bd \
POSTDEPLOY_STOREFRONT_ORIGIN=https://bojro.com.bd \
POSTDEPLOY_ENVIRONMENT=production \
uv run --project backend python -m scripts.postdeploy_verify
```

## Rollback

1. Declare the rollback owner and incident/change reference; pause further deployments.
2. Disable affected optional providers or public features using audited kill switches before retrying external effects.
3. Roll Vercel back to the prior immutable deployment.
4. Roll Railway web and worker together to the prior image only when that image is compatible with the migrated schema.
5. Never run an Alembic downgrade as an automatic rollback. Several data-bearing downgrades intentionally refuse. Prefer a forward compatibility patch.
6. If data restoration is required, stop writers, preserve the failed database, restore into an isolated target, validate it, and obtain incident-commander plus data-owner approval before cutover. Follow [BACKUP_RESTORE.md](BACKUP_RESTORE.md).
7. Re-run preflight and all smoke checks, then monitor for another 30 minutes. Preserve logs and provider references for the postmortem.

Rollback is complete only when the storefront, API, worker heartbeat, job backlog, provider reconciliation, and data integrity checks are healthy. A frontend rollback alone is not sufficient.

## External GitHub Controls

Repository files cannot enforce GitHub branch or environment protection. Configure and capture evidence for these external settings:

- Protect `main`; require pull requests, at least one approval, code-owner review, stale-approval dismissal, resolved conversations, linear history, and all administrators to follow the rules.
- Require the stable Quality and Security checks listed in [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md); block force pushes and branch deletion.
- Limit Actions to approved/pinned actions and keep `GITHUB_TOKEN` read-only by default.
- Enable the dependency graph, Dependabot alerts/security updates, secret scanning/push protection where supported, and use this repository's advanced CodeQL workflow instead of a duplicate default CodeQL setup.
- Create `staging` and `production` GitHub environments. Production requires at least two reviewers, prevents self-review, limits deployment branches to protected `main`, and scopes every deployment secret to that environment.
- Save a dated settings export or screenshots with the launch evidence and re-audit quarterly.
