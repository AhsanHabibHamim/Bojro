# Launch Checklist

Default status is **NO-GO**. A checkbox is valid only with a named owner, UTC date, and durable evidence URL/artifact. “Configured,” verbal confirmation, mock success, or an undated screenshot is not evidence.

## Launch Record

| Field                        | Value                    |
| ---------------------------- | ------------------------ |
| Launch/change ID             |                          |
| Environment                  | `staging` / `production` |
| Commit SHA                   |                          |
| Vercel deployment ID         |                          |
| Railway web deployment ID    |                          |
| Railway worker deployment ID |                          |
| Alembic revision             |                          |
| Planned start/end UTC        |                          |
| Incident/change channel      |                          |
| Launch commander             |                          |
| Rollback commander           |                          |
| Evidence index URL           |                          |

## Hard No-Go Conditions

Any item below is an immediate no-go:

- Missing backup/PITR evidence or failed/expired restore drill.
- Required CI/security check not green on the exact commit SHA.
- Unexpected `/ready` degradation, missing worker heartbeat, growing dead letters, or unresolved payment/refund/shipment unknowns.
- Any mock, E2E reset, deprecated OTP, placeholder secret/host, HTTP public origin, wildcard CORS/trusted host, or production sandbox provider.
- Unapproved provider, privacy/retention policy, legal/DPA condition, DNS/TLS/email authentication, or platform access.
- Accessibility blocker, Lighthouse gate failure, critical/high vulnerability without unexpired exception, or confirmed secret finding.
- Rollback incompatibility without an approved forward-fix/recovery plan.
- Unowned alert, incident response, customer support, or communications path.

## Governance And Access

- [ ] `main` protection requires pull request, at least one approval, code-owner review, stale approval dismissal, resolved conversations, linear history, and administrator enforcement.
- [ ] Force push and branch deletion are blocked.
- [ ] GitHub Actions are restricted to GitHub-owned and approved immutable-SHA actions.
- [ ] GitHub secret scanning and push protection are enabled where the repository plan supports them.
- [ ] Dependency graph, Dependabot alerts, and Dependabot security updates are enabled.
- [ ] Required checks are configured with their current stable names: `Quality / quality`, `Quality / compose-smoke`, `Security / CodeQL (javascript-typescript)`, `Security / CodeQL (python)`, `Security / Dependency review`, `Security / Secret scan`, and `Security / Container security and SBOM`.
- [ ] GitHub `production` environment requires at least two reviewers, prevents self-review, limits deployments to protected `main`, and contains only production-scoped secrets.
- [ ] Vercel, Railway, Cloudinary, DNS, GitHub, email/SMS, payment/courier, analytics, and assistant accounts enforce MFA and least privilege.
- [ ] Break-glass access has two owners, tested access, alerting, and post-use rotation/review.
- [ ] Quarterly access review owner/date/evidence is current.

## Build, Test, And Supply Chain

- [ ] Exact SHA has green lint, formatting, typecheck, tests, migration/seed checks, OpenAPI drift, build, Compose smoke, and full Playwright jobs.
- [ ] Backend coverage artifact meets the enforced 76% floor.
- [ ] Playwright HTML/test-results artifact exists on success and has no unexpected skipped required scenario.
- [ ] Lighthouse raw reports and summary exist for three BN/EN mobile runs per home/product route.
- [ ] CodeQL, dependency review, TruffleHog, and high/critical container scans are green.
- [ ] Backend and frontend CycloneDX SBOM artifacts are archived with the release.
- [ ] Dependabot/security advisories are triaged; every exception has owner, compensating control, approval, and expiry.
- [ ] All workflow action references are immutable SHAs and the review annotation/version is current.

## Security And Privacy

- [ ] Final configuration OWASP review and independent security test/penetration evidence are approved.
- [ ] Deployed security headers, CSP, HSTS, cookie prefixes/flags, CORS, trusted hosts, production docs/debug absence, and rate limits are verified.
- [ ] Customer/admin authorization, session expiry/revocation, CSRF, TOTP, object ownership, upload verification, webhook replay, and provider ambiguity tests pass in staging.
- [ ] Error tracking is enabled for frontend/backend with release SHA, redaction, alert routing, and approved source-map/session-replay policy.
- [ ] Privacy notice, consent copy/version, cookie behavior, processor list, data-subject workflow, and `PRIVACY_RETENTION.md` have legal approval.
- [ ] Retention jobs/manual controls, oldest-row evidence, Cloudinary deletion, and backup deletion-replay procedure pass.
- [ ] Keyrings use unique non-public material, active IDs exist, retiring read keys are retained, and rotation/revocation evidence is current.
- [ ] Logs, dashboards, CI artifacts, error tracking, analytics, and incident tools contain no prohibited PII/secrets.

## Backup And Recovery

- [ ] Railway plan and database show successful current backups, >=7-day PITR, and >=30-day daily retention, or approved stricter values.
- [ ] Latest encrypted off-platform logical backup has object version, size, SHA-256, retention expiry, and successful listing evidence.
- [ ] Monthly isolated `pg_restore` drill passed within 31 days and met RTO.
- [ ] Quarterly PITR clone drill passed within 92 days and met 15-minute RPO/four-hour RTO.
- [ ] Cloudinary backup/version retention and representative recovery test are current.
- [ ] Configuration/secret inventory can recreate staging without undocumented values.
- [ ] Redis loss/rebuild procedure was tested and did not treat Redis as commerce truth.

## Platform, DNS, And Environment

- [ ] Production and staging use separate Vercel/Railway/PostgreSQL/Redis/Cloudinary/provider resources and keys.
- [ ] Vercel root is `frontend`, Node is 24.x, install/build commands are frozen, and the exact SHA is deployed.
- [ ] `NEXT_PUBLIC_API_URL` and `INTERNAL_API_URL` use the public Railway API custom HTTPS origin; no Railway private URL is configured on Vercel.
- [ ] Railway web and worker use the same image SHA and environment-name set; differences are reviewed and limited to service process/port and one-shot operator values.
- [ ] Web `/ready` health check and external worker-heartbeat alert are healthy.
- [ ] Apex, `www`, API, staging, and API-staging authoritative DNS and TLS chains pass externally; canonical redirects are correct.
- [ ] SPF has exactly one record, every DKIM selector passes, return path passes, DMARC reports reach a monitored mailbox, and promotion from `p=none` is approved after review.
- [ ] Cloudinary sign/upload/complete/render/delete/cleanup and quota alerts pass in staging.
- [ ] `scripts/postdeploy-smoke.sh` passes against staging custom domains before production approval.

## Prohibited Configuration Review

- [ ] No `OTP_PROVIDER` or `OTP_EXTERNAL_*` variable exists.
- [ ] No Phase 6/7 E2E reset token/route enable and no `NEXT_PUBLIC_E2E_*` variable exists.
- [ ] Storage, email, SMS, Meta CAPI, assistant, and payment/courier modes are real approved values or disabled, never mock.
- [ ] Production provider modes are `live` or `disabled`, never sandbox.
- [ ] `SEED_ADMIN_*` and demo seed execution are absent; bootstrap credentials are removed after one-shot use.
- [ ] No default/example/reused secret, `.test`/localhost host, HTTP public origin, wildcard host/CORS, or unapproved legal boolean exists.

## Providers And Business Operations

- [ ] Initial provider scope matches `PROVIDERS.md`; COD/manual-only is the default unless each additional row is signed.
- [ ] Every enabled provider has official contract/version, account owner, credentials, DNS/callback, verification, dedupe, ambiguity/reconciliation, dead-letter, kill-switch, rotation, canary, settlement, and incident evidence.
- [ ] Dedicated canary customer/admin/order/provider identities exist and cannot access real customer data.
- [ ] Finance approves COD/payment/refund/settlement reconciliation and daily exception ownership.
- [ ] Fulfillment approves inventory reservation, packing, shipment/COD status, cancellation/refusal, returns, and courier escalation.
- [ ] Support has Bangla/English scripts for payment pending/unknown, delayed shipment, account/OTP, privacy request, and incident communications.
- [ ] Provider quotas, balances, sender identities, domains, callback allowlists, and emergency contacts are current.

## Observability And Incident Readiness

- [ ] Storefront/API availability, latency, checkout, database, Redis, worker, queue age, dead-letter, reconciliation, provider, Cloudinary, retention, and backup dashboards exist.
- [ ] Every alert threshold in `OPERATIONS.md` is routed to a primary and backup owner and was tested in staging plus one controlled production page.
- [ ] Synthetic probes cover two regions, API health/readiness, localized storefront, and a safe checkout/provider capability path.
- [ ] On-call schedule, incident commander, security/privacy, platform, provider, finance, support, legal, and communications contacts are current.
- [ ] SEV-1/SEV-2 incident process, status page, evidence store, and bilingual customer communication path were table-topped within 92 days.
- [ ] Rollback/forward-fix decision tree and database recovery owner are present for this release.

## Accessibility, Performance, And SEO

- [ ] `ACCESSIBILITY_PERFORMANCE.md` evidence record is complete, passed, and no older than 90 days.
- [ ] Current axe/equivalent staging scan has no critical/serious unresolved result.
- [ ] Keyboard, focus, dialog, screen-reader, 200%/400% reflow, contrast, reduced motion, touch, and Bangla rendering manual checks pass.
- [ ] Lighthouse median performance >=90, accessibility >=95, and LCP <2.5 seconds on each BN/EN home/product route.
- [ ] Staging/production deployed-origin performance check passes; local Docker results are retained only as regression evidence.
- [ ] Metadata, canonicals, hreflang, robots, sitemap, OpenGraph, Product/Breadcrumb/Organization structured data, errors/noindex, and Bangla-safe slugs are verified.
- [ ] No hydration/console error, required-resource failure, unexpected third-party request before consent, or PII-bearing analytics URL exists.

## Release Execution

- [ ] Release/change record, owner, observation window, rollback owner, incident channel, and customer-impact window are approved.
- [ ] Fresh backup/PITR timestamp is recorded before migration.
- [ ] Backward-compatible migration reaches the expected Alembic revision exactly once.
- [ ] Worker deploys first and has a fresh heartbeat with stable queue/dead-letter/reconciliation metrics.
- [ ] API deploys next; in-environment preflight exits zero and public `/ready` is `ready`, not unexpected `degraded`.
- [ ] Vercel deploys the same SHA after API compatibility is proven.
- [ ] `Release Verification` manual workflow passes with preflight evidence and public target origins.
- [ ] Guest/customer/admin/upload/provider/notification smoke checks pass with dedicated canaries and are reconciled/cleaned up.
- [ ] Thirty-minute observation shows stable errors, latency, database, worker, queue, provider, Cloudinary, and conversion indicators.

## Final Decision

| Approver            | Name | Decision       | UTC date | Evidence/signature |
| ------------------- | ---- | -------------- | -------- | ------------------ |
| Launch commander    |      | `GO` / `NO-GO` |          |                    |
| Engineering         |      | `GO` / `NO-GO` |          |                    |
| Operations/SRE      |      | `GO` / `NO-GO` |          |                    |
| Security/privacy    |      | `GO` / `NO-GO` |          |                    |
| Product/business    |      | `GO` / `NO-GO` |          |                    |
| Finance/fulfillment |      | `GO` / `NO-GO` |          |                    |

Final status: **NO-GO** until every mandatory item is checked and every required approver records `GO`. Any later material configuration, code, provider, DNS, key, migration, or incident change invalidates the relevant evidence and requires re-approval.
