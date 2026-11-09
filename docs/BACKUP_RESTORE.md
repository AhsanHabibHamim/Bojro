# Backup And Restore

This runbook covers Railway PostgreSQL backup/PITR, logical backups, Cloudinary assets, configuration, Redis loss, privacy handling, and restore drills. A backup is not accepted until a restore has proved it usable.

## Recovery Objectives

| Data/service                      | RPO                                                           | RTO                                | Recovery method                                                                 |
| --------------------------------- | ------------------------------------------------------------- | ---------------------------------- | ------------------------------------------------------------------------------- |
| PostgreSQL                        | 15 minutes                                                    | 4 hours                            | Railway point-in-time recovery plus encrypted off-platform logical backup       |
| Cloudinary original assets        | 24 hours for inventory; provider durability per approved plan | 8 hours for critical product media | Cloudinary backup/version retention, asset inventory, and provider recovery     |
| Runtime configuration and secrets | Last approved change                                          | 2 hours                            | Versioned secret manager and platform configuration export                      |
| Redis                             | No business-data RPO                                          | 30 minutes to recreate             | Provision empty Redis; PostgreSQL sweeps and user retry rebuild transient state |

If the Railway plan cannot provide a tested PITR window that meets the 15-minute RPO, production is no-go. Daily logical dumps alone provide, at best, a 24-hour RPO.

## Ownership And Cadence

| Control                              | Cadence                                           | Required owner/evidence                                                           |
| ------------------------------------ | ------------------------------------------------- | --------------------------------------------------------------------------------- |
| Railway automated backup/PITR status | Daily automated check; monthly human review       | Operations owner, successful timestamp, retention/window screenshot or API export |
| Encrypted logical PostgreSQL backup  | Daily and immediately before schema/data releases | Operations owner, object URI, SHA-256, size, PostgreSQL version, expiry           |
| Isolated logical restore drill       | Monthly and before first launch                   | Database owner, duration, checks, discrepancies, destruction evidence             |
| PITR clone drill                     | Quarterly                                         | Database owner, requested/actual timestamp, achieved RPO/RTO, integrity checks    |
| Cloudinary inventory/backup review   | Daily inventory; monthly review                   | Media owner, asset count, orphan/missing report, provider retention evidence      |
| Configuration recovery review        | Every release and quarterly restore               | Platform owner, version IDs and access test; never secret values                  |

Every backup and drill failure pages the operations owner and opens an incident/change record. Two consecutive failures are a launch or change freeze.

## Railway PostgreSQL

Before production traffic:

1. Confirm the active Railway plan's documented backup and point-in-time recovery capabilities.
2. Configure a PITR window of at least seven days and daily backup retention of at least 30 days, or a stricter approved policy.
3. Confirm backups are encrypted at rest and access is restricted to the database recovery role plus break-glass owner.
4. Configure alerts for failed/stale backups and storage/retention exhaustion.
5. Record region, PostgreSQL major version, extensions, database name, timezone, and the current Alembic revision.
6. Create an off-platform encrypted backup destination in a separate administrative/account boundary.
7. Do not expose the database publicly for routine backups. Use an approved Railway tunnel/operator session or a short-lived restricted public endpoint, then remove it.

Before every migration or high-risk data change, record a fresh successful backup and a PITR timestamp in the release record.

## Logical Backup

`scripts/backup-postgres.sh` creates a compressed custom-format dump, verifies its table of contents, sets mode `0600`, and writes a SHA-256 sidecar. It never embeds a credential or overwrites an existing backup. Run it only on an encrypted filesystem and transfer the result to the approved encrypted object store immediately.

```bash
DATABASE_URL='postgresql://<short-lived-backup-user>@<approved-host>/<database>' \
BACKUP_DIR='/encrypted/bojro-backups' \
BACKUP_DESTINATION_ENCRYPTED=YES \
scripts/backup-postgres.sh
```

The backup role needs consistent read access but no schema mutation, user administration, or provider-secret access beyond data already stored in the database. Prefer a short-lived credential. Do not paste the URI into tickets, chat, shell history, or evidence.

Required post-run evidence:

- UTC start/end, PostgreSQL client/server major versions, source environment, Alembic revision, dump size, and SHA-256.
- Encrypted object-store URI/version ID, retention/immutability expiry, and successful upload status.
- `pg_restore --list` success. A listing is format validation, not a restore drill.
- Deletion of local plaintext after the encrypted upload and checksum verification.

## Isolated `pg_restore` Drill

Never restore into production, staging, or a shared development database. Provision an empty isolated PostgreSQL instance with the same major version and required extensions. Its database name must contain `restore_drill`.

```bash
BACKUP_FILE='/encrypted/bojro-backups/bojro-<timestamp>.dump' \
DRILL_DATABASE_URL='postgresql://<drill-user>@localhost:5432/bojro_restore_drill' \
CONFIRM_RESTORE_DRILL=RESTORE_TO_ISOLATED_TARGET \
scripts/restore-drill.sh
```

The script refuses a non-empty target and does not create, drop, or clean a database. A remote isolated target additionally requires the explicit acknowledgement documented by `scripts/restore-drill.sh --help`.

After the dump is loaded, run the application's read-only, bounded schema/constraint/index/invariant verifier. Supply expected critical table counts from the backup manifest when available:

```bash
APP_ENV=staging \
RESTORE_DATABASE_URL='postgresql+asyncpg://<ephemeral-drill-user>@localhost:5432/bojro_restore_drill' \
RESTORE_EXPECTED_COUNTS_JSON='{"orders":123,"users":45}' \
uv run --project backend python -m scripts.restore_verify
```

Store its `bojro.restore-verification.v1` JSON with the drill evidence. A verifier failure is a failed drill; do not weaken expected counts or omit unexplained failures.

After restore:

1. Confirm the expected Alembic revision exists and `alembic check` reports no ungenerated operations.
2. Run application integrity checks with all outbound providers disabled and no worker/web public exposure.
3. Compare row counts and invariants for users, products/variants, inventory movements, orders/items, payments/refunds, shipments, webhook events, admin audit events, and durable outboxes against the backup manifest.
4. Sample encrypted columns only through application decryption with the recovery keyring; never export plaintext samples.
5. Confirm no duplicate active carts, order numbers, provider event identities, idempotency scopes, or default addresses.
6. Start an isolated API/worker only after outbound DNS is blocked or providers are disabled. Confirm `/ready` and a read-only catalog/order-admin query.
7. Record restore duration, validation duration, achieved RPO/RTO, failures, operator, reviewer, and artifact links.
8. Destroy the drill database, temporary credentials, decrypted files, logs containing connection metadata, and any cloned media after evidence is approved.

## Point-In-Time Recovery Drill

1. Choose a timestamp after a known canary insert and before a known canary delete/update.
2. Create a new Railway database/clone at that timestamp; never rewind the active database in place.
3. Keep application services disconnected and external providers disabled.
4. Verify the canary boundary, Alembic revision, invariants, and critical counts.
5. Measure from incident declaration to validated recovery candidate.
6. Destroy the clone after review.

The actual recovered timestamp must be no more than 15 minutes older than the requested safe point, and the validated candidate must be available within four hours. Otherwise record the missed objective and block launch/high-risk releases until remediation is tested.

## Cloudinary

PostgreSQL backups contain Cloudinary identifiers and verified metadata, not asset bytes.

- Enable the Cloudinary plan's original-asset backup/version retention and record the exact retention, restore limitations, and account owner.
- Export a daily asset inventory containing non-secret public ID, resource type, version, bytes, digest where available, created time, moderation state, and database ownership reference.
- Store the inventory with the database backup evidence in an encrypted separate account.
- Reconcile database-ready assets against Cloudinary daily. Alert on missing referenced assets, unexpected public assets, deletion backlog, quota, or backup failure.
- Test recovery of representative product, category, review, and content media quarterly without overwriting current public IDs.
- Treat transformation caches as reproducible; protect original assets and configuration.

If the Cloudinary plan cannot recover originals, maintain an approved encrypted export of original assets with the same access, retention, and PII controls as the database backup.

## Configuration And Secrets

Back up names, scopes, version IDs, and non-secret values for Vercel, Railway web/worker, Railway data services, Cloudinary, DNS, GitHub environments, alerts, and provider modes. Store secret values only in the approved versioned secret manager.

Quarterly, reconstruct a blank staging environment from source control plus the configuration inventory. Prove that active keyring IDs and all retiring read keys are available. Recovery evidence must never contain secret values.

## Redis Is Non-Authoritative

Do not restore Redis as commerce truth. On Redis loss:

1. Provision an empty compatible Redis instance and rotate its connection credential if compromise is suspected.
2. Restart web and worker after updating both services atomically.
3. Expect OTP challenges, rate-limit counters, cache entries, and transient guest/session state to expire or restart.
4. Let PostgreSQL-backed workers sweep durable jobs; do not reconstruct job truth from an old Redis snapshot.
5. Verify worker heartbeat, queues, readiness, login/OTP retry behavior, and cache repopulation.

Redis persistence may reduce disruption but does not change its non-authoritative classification.

## PII And Backup Expiry

- Encrypt every backup in transit and at rest, use a separate account boundary, deny public access, and log reads/restores/deletes.
- Backup retention follows [PRIVACY_RETENTION.md](PRIVACY_RETENTION.md). Do not keep indefinite manual copies.
- Do not edit immutable backups to remove one subject. Record deletion/suppression in the live ledger and let backups expire on schedule.
- A restore stays isolated until all deletion, newsletter suppression, consent withdrawal, disabled-account, and credential-revocation events after the recovery point are replayed.
- Never reconnect a restored worker to providers until replay and validation are complete.
- A legal hold is documented, access-restricted, approved by legal/security, and removed promptly when the hold ends.

## Drill Evidence Template

| Field                                   | Value |
| --------------------------------------- | ----- |
| Drill ID and environment                |       |
| Backup/PITR source timestamp            |       |
| Backup object version and SHA-256       |       |
| PostgreSQL and Alembic versions         |       |
| Operator and independent reviewer       |       |
| Started / validated / destroyed UTC     |       |
| Achieved RPO / RTO                      |       |
| Integrity checks and row-count artifact |       |
| Privacy-ledger replay result            |       |
| Cloudinary/config recovery result       |       |
| Exceptions and remediation owner/date   |       |
| Final result (`PASS` or `FAIL`)         |       |

A blank, partial, simulated, or production-target restore record is `FAIL`.

## Local Script Validation Evidence

This is development tooling evidence only, not the required staging/PITR launch drill:

- Date: 2026-11-08 UTC.
- Source: local PostgreSQL 16.15 at Alembic `0015_phase8_hardening`.
- Backup: custom format, 501,489 bytes, SHA-256 verified; plaintext artifact deleted after the drill.
- Restore: isolated empty `bojro_restore_drill` database, single transaction, 61 application tables.
- `backend/scripts/restore_verify.py`: PASS for schema head, tables, counts, foreign keys, indexes, representative queries, and read-only verification transaction.
- Restored counts included 8 divisions, 64 districts, 495 upazilas, 49 products, 90 variants, 31 orders/31 items, and 126 audit records.
- Target database was destroyed after evidence capture.

The launch checklist remains blocked until the same procedure succeeds against an approved Railway staging backup/PITR source with named operator, independent reviewer, measured RPO/RTO, Cloudinary/config restoration, privacy-ledger replay and retained artifacts.
