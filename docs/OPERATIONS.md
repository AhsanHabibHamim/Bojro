# Operations

This document defines SLOs, monitoring, alerts, worker/reconciliation operations, and common runbooks. Monitoring configuration is external to the repository and must be evidenced in [LAUNCH_CHECKLIST.md](LAUNCH_CHECKLIST.md).

## Service Objectives

Measure production separately from synthetic/canary traffic. Publish a monthly report in `Asia/Dhaka` business context and UTC timestamps.

| SLI                              | SLO                                                                                                         | Error-budget window  |
| -------------------------------- | ----------------------------------------------------------------------------------------------------------- | -------------------- |
| Storefront successful navigation | 99.9% non-5xx for public storefront requests                                                                | Rolling 30 days      |
| API availability                 | 99.9% successful non-5xx responses excluding valid 4xx                                                      | Rolling 30 days      |
| Checkout platform success        | 99.5% of valid order-placement commands reach a definitive response or safe replay result                   | Rolling 30 days      |
| API latency                      | 95% of public read requests under 500 ms and mutation responses under 1.5 s, excluding hosted provider time | Rolling 7 days       |
| Worker freshness                 | 99.9% of minutes have heartbeat age below 180 seconds                                                       | Rolling 30 days      |
| Durable work                     | 99% of normal-priority rows leave queued/retry within 5 minutes; OTP priority within 15 seconds             | Rolling 7 days       |
| Reconciliation                   | 99% of due unknown provider resources resolve or produce an operator alert within 15 minutes                | Rolling 7 days       |
| Backup                           | PostgreSQL RPO <=15 minutes and validated recovery candidate RTO <=4 hours                                  | Every drill/incident |

Lighthouse performance >=90 and median LCP <2.5 seconds are release gates, not production availability SLO substitutes.

## Severity And Escalation

| Severity | Definition                                                                                                                  | Acknowledge      | Update cadence         | Escalation                                                                        |
| -------- | --------------------------------------------------------------------------------------------------------------------------- | ---------------- | ---------------------- | --------------------------------------------------------------------------------- |
| SEV-1    | Confirmed data loss/corruption, credential compromise, broad checkout outage, unauthorized access, or safety/privacy breach | 5 minutes        | Every 15 minutes       | Incident commander, engineering, security, operations, business owner immediately |
| SEV-2    | Sustained SLO breach, payment/courier ambiguity growth, worker outage, provider outage with material customer impact        | 15 minutes       | Every 30 minutes       | Primary on-call then backup/owner after 10 minutes                                |
| SEV-3    | Degraded optional feature, isolated failures, approaching capacity, non-urgent reconciliation backlog                       | 4 business hours | Daily until controlled | Owning team                                                                       |
| SEV-4    | Informational anomaly or maintenance item                                                                                   | 2 business days  | Change record          | Owning backlog                                                                    |

The on-call schedule, paging service, phone tree, status-page access, provider contacts, and backup owners are stored in the restricted operations directory, not source control.

## Required Telemetry

- Vercel and Railway request/error/latency metrics by environment, route template, method, and status class. Never label metrics with raw URLs, order numbers, phones, emails, or IDs.
- Backend/frontend error tracking with environment, release commit SHA, request ID, redacted route, and source-map association. Session replay is disabled on authenticated/account/admin/checkout pages unless separately privacy-approved.
- Structured Railway logs with request ID, event code, service, release SHA, provider name, safe state, and duration. Request/response bodies and raw provider payloads are prohibited.
- PostgreSQL connections, CPU, memory, storage, replication/backup state, slow queries, lock waits, transaction age, and pool saturation.
- Redis availability, memory/eviction, connection errors, latency, and worker heartbeat age.
- Durable queue counts/oldest age by type/status, lease-expiry reclaim count, retries, dead letters, and retention cleanup counts.
- Provider requests by normalized outcome, verification failures, unknown state, reconciliation attempts/age, settlement mismatch, and kill-switch state.
- Cloudinary storage/bandwidth quota, signed-upload failure, completion verification failure, missing referenced asset, and delete backlog.
- Privacy jobs: notification content erasure, analytics/assistant retention cleanup, newsletter suppression, and failed deletion requests.

## Alert Matrix

| Signal                                      | Threshold                                                 | Severity                                  |
| ------------------------------------------- | --------------------------------------------------------- | ----------------------------------------- |
| Public API `/health` fails from two regions | 2 consecutive minutes                                     | SEV-1                                     |
| `/ready` unavailable                        | 2 consecutive checks                                      | SEV-1 if broad; SEV-2 otherwise           |
| `/ready` degraded unexpectedly              | 5 minutes                                                 | SEV-2                                     |
| Storefront/API 5xx                          | >2% for 5 minutes or >5% for 2 minutes                    | SEV-1                                     |
| Checkout valid-command failure              | >2% over 10 minutes                                       | SEV-1                                     |
| Worker heartbeat age                        | >180 seconds                                              | SEV-1 for OTP/order work; otherwise SEV-2 |
| OTP queue oldest age                        | >15 seconds for 2 minutes                                 | SEV-1                                     |
| Normal durable queue oldest age             | >5 minutes                                                | SEV-2                                     |
| Any dead letter                             | Immediate ticket; page for OTP/payment/refund/webhook     | SEV-2 or SEV-1 by impact                  |
| Unknown payment/refund age                  | >10 minutes or count increases for 5 minutes              | SEV-2                                     |
| Webhook verification failures               | >5/minute/provider or any unexpected origin pattern       | SEV-2/security review                     |
| Reconciliation failure                      | 3 consecutive attempts or next attempt exceeds 15 minutes | SEV-2                                     |
| PostgreSQL storage                          | >80% warning, >90% page                                   | SEV-3 / SEV-1                             |
| PostgreSQL connection pool                  | >80% for 10 minutes or exhausted once                     | SEV-3 / SEV-1                             |
| Redis eviction                              | Any in production                                         | SEV-2                                     |
| Backup/PITR check                           | Missed or failed once                                     | SEV-1                                     |
| Cloudinary quota                            | >80% warning, >90% page                                   | SEV-3 / SEV-2                             |
| Retention cleanup                           | No successful run for 26 hours                            | SEV-2                                     |

Test every alert route in staging and page the production on-call with a controlled test before launch and quarterly. A dashboard without a routed, acknowledged alert is not an operational control.

## Worker Operations

The Railway worker command is `.venv/bin/arq app.workers.review_photos.WorkerSettings`. At launch, run one scheduler/worker replica. The worker writes `WORKER_HEARTBEAT_KEY`; web readiness requires freshness within `WORKER_HEARTBEAT_MAX_AGE_SECONDS`.

Before scaling workers:

1. Load-test duplicate cron invocation and concurrent claims.
2. Confirm every claimed table uses leases/row locks and idempotent handlers.
3. Confirm a killed worker's lease is reclaimed without duplicate external effects.
4. Confirm provider rate limits and database pools support the replica count.
5. Record the new maximum concurrency and rollback trigger.

Never clear a queue or reset attempts directly to make a dashboard green. Preserve the row and error history, diagnose the cause, use audited admin retry/cancel operations where exposed, and reconcile external truth first.

## Dead-Letter Runbook

1. Acknowledge the alert and capture release SHA, row/event ID, type, provider, first/last attempt, safe error code, and request ID. Do not copy encrypted content or raw payloads.
2. Classify the row as transient provider outage, bad configuration/credential, poison data, application defect, consent/privacy suppression, or confirmed external success with lost response.
3. Disable a provider or affected feature if retries can create financial, delivery, privacy, or duplicate-message harm.
4. For payment/refund/shipment work, query authoritative provider state by stable merchant reference before any retry.
5. Correct configuration/code/data through an approved change. Do not edit audit/idempotency/provider-reference fields ad hoc.
6. Use the admin API's capability-gated retry/reconcile/cancel action with its ETag and idempotency key. If no action is exposed, escalate to engineering rather than mutating SQL.
7. Verify the exact state transition, aggregate state, audit event, and absence of duplicate external effects.
8. Close with cause, impact, remediation, and prevention. Multiple similar rows trigger incident/problem management rather than manual repetition.

## Payment And Refund Reconciliation

1. Freeze blind retry and identify the internal attempt/refund plus stable merchant reference.
2. Query the official provider API or portal using a least-privilege operator account.
3. Match merchant reference, amount, currency, customer-safe order identity, and provider resource identity.
4. If provider state is definitive, invoke the API capability-gated reconciliation command with current ETag and a persisted idempotency key.
5. If still unknown, leave the resource unknown, preserve inventory/order safeguards, schedule the next bounded query, and communicate accurately to support.
6. A settlement mismatch, duplicate debit/refund, or amount/reference mismatch is SEV-1 and must not be manually forced to success.

## Webhook Reconciliation

1. Distinguish rejected unauthenticated traffic from verified processing failures.
2. For verification spikes, check provider status, secret/certificate rotation, clock skew, source ranges if officially documented, body limits, and replay timestamps.
3. For a verified dead letter, compare provider resource state before retry.
4. Retry only through the admin webhook action; confirm deduplication by provider/event identity and idempotent aggregate behavior.
5. Never accept a browser return or support screenshot as payment truth.

## Shipment Reconciliation

1. Query the courier using the stable consignment/merchant reference.
2. Map only documented statuses; an unknown new status remains unknown and alerts engineering.
3. Reconcile through the API action. Do not skip required order transitions or fabricate tracking events.
4. For cancellation ambiguity, verify whether booking exists before creating another shipment.
5. Escalate delivered/COD settlement mismatch to operations and finance.

## Common Runbooks

### Readiness Unavailable

1. Check the per-component readiness detail and release SHA.
2. Verify PostgreSQL and Redis platform status, then connection pool and credentials.
3. Verify the worker heartbeat and provider/config capability statuses.
4. Stop rollout. Roll back only when schema-compatible; otherwise roll forward.
5. Do not change required dependencies to optional to restore a green status.

### Worker Heartbeat Missing

1. Confirm Railway worker deployment, command, restart loop, memory, and Redis connectivity.
2. Confirm web and worker use identical heartbeat key, Redis, release SHA, keyrings, and provider configuration.
3. Restart one worker only after preserving logs. Watch lease reclaim, backlog age, and duplicate-effect indicators.
4. If OTP/order work is delayed, declare SEV-1 and disable affected customer actions if safe failure cannot be guaranteed.

### PostgreSQL Saturation

1. Stop rollout and identify connection, CPU, IO, storage, slow query, lock-wait, and transaction-age pressure.
2. Reduce nonessential worker batch/concurrency through an approved change; do not terminate unknown transactions blindly.
3. Preserve diagnostic query IDs and plans without PII literals.
4. Scale only after ruling out leaks, unbounded queries, and long locks.

### Cloudinary Failure

1. Disable new uploads through the approved feature/provider switch while keeping existing CDN assets readable.
2. Check quota, credentials, signature time, environment, and provider status.
3. Preserve pending owned upload rows for cleanup/retry. Do not accept arbitrary URLs as a bypass.
4. Reconcile missing/deletion-pending assets after recovery and notify moderators/customers where required.

### Redis Loss

Follow [BACKUP_RESTORE.md](BACKUP_RESTORE.md). Recreate Redis empty, expect transient login/OTP/cache impact, and let PostgreSQL-backed sweeps recover durable work.

## Change And Evidence

Every production change records immutable SHA, migration revision, web/worker/Vercel deployment IDs, preflight result, backup/PITR marker, smoke artifacts, dashboards before/after, alert state, owner, reviewer, rollback decision, and observation end time.

Operational evidence expires after 90 days unless a shorter interval is specified. Incident handling follows [INCIDENT_RESPONSE.md](INCIDENT_RESPONSE.md).
