#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

usage() {
  cat <<'EOF'
Restore a custom-format dump into a pre-created empty isolated drill database.

Required environment:
  BACKUP_FILE          Existing .dump file.
  DRILL_DATABASE_URL   Target PostgreSQL libpq URI. The database name must
                       contain restore_drill. Keep passwords in PGPASSWORD or
                       .pgpass, not in the URI.
  CONFIRM_RESTORE_DRILL=RESTORE_TO_ISOLATED_TARGET

Remote target acknowledgement:
  ALLOW_REMOTE_ISOLATED_TARGET=I_ACKNOWLEDGE_THIS_IS_AN_EMPTY_ISOLATED_DATABASE

The script refuses non-empty targets. It never creates, drops, cleans, or
connects an application/worker to the target.
EOF
}

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  usage
  exit 0
fi

for command_name in pg_restore psql sha256sum date; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'error: required command not found: %s\n' "$command_name" >&2
    exit 1
  fi
done

: "${BACKUP_FILE:?BACKUP_FILE is required}"
: "${DRILL_DATABASE_URL:?DRILL_DATABASE_URL is required}"

if [[ ${CONFIRM_RESTORE_DRILL:-} != "RESTORE_TO_ISOLATED_TARGET" ]]; then
  printf 'error: explicit restore-drill confirmation is required\n' >&2
  exit 1
fi

if [[ ! -f $BACKUP_FILE || -L $BACKUP_FILE ]]; then
  printf 'error: BACKUP_FILE must be a regular, non-symlink file\n' >&2
  exit 1
fi

if [[ ! $DRILL_DATABASE_URL =~ ^postgres(ql)?:// ]]; then
  printf 'error: DRILL_DATABASE_URL must be a PostgreSQL libpq URI\n' >&2
  exit 1
fi

if [[ $DRILL_DATABASE_URL =~ ^postgres(ql)?://[^/@]+:[^/@]*@ ]]; then
  printf 'error: keep the drill password in PGPASSWORD or .pgpass, not the URI/process list\n' >&2
  exit 1
fi

if [[ $DRILL_DATABASE_URL != *localhost* && $DRILL_DATABASE_URL != *127.0.0.1* && $DRILL_DATABASE_URL != *"[::1]"* ]]; then
  if [[ ${ALLOW_REMOTE_ISOLATED_TARGET:-} != "I_ACKNOWLEDGE_THIS_IS_AN_EMPTY_ISOLATED_DATABASE" ]]; then
    printf 'error: remote drill targets require the exact isolation acknowledgement\n' >&2
    exit 1
  fi
fi

pg_restore --list "$BACKUP_FILE" >/dev/null

checksum_file="${BACKUP_FILE}.sha256"
if [[ -f $checksum_file ]]; then
  read -r expected_checksum _ <"$checksum_file"
  actual_output=$(sha256sum "$BACKUP_FILE")
  actual_checksum=${actual_output%% *}
  if [[ $actual_checksum != "$expected_checksum" ]]; then
    printf 'error: backup checksum does not match sidecar\n' >&2
    exit 1
  fi
  printf 'Checksum verified: %s\n' "$actual_checksum"
else
  printf 'warning: checksum sidecar is absent; record this evidence gap\n' >&2
fi

drill_database_url=$DRILL_DATABASE_URL
export PGAPPNAME=bojro-restore-drill
export PSQLRC=/dev/null

database_name=$(psql --dbname="$drill_database_url" -X --set=ON_ERROR_STOP=1 --tuples-only --no-align --command='SELECT current_database()')
if [[ $database_name != *restore_drill* && $database_name != *restore-drill* ]]; then
  printf 'error: target database name must contain restore_drill\n' >&2
  exit 1
fi

table_count=$(psql --dbname="$drill_database_url" -X --set=ON_ERROR_STOP=1 --tuples-only --no-align --command="
  SELECT count(*)
  FROM pg_catalog.pg_class AS c
  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('r', 'p')
    AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    AND n.nspname !~ '^pg_toast';
")
if [[ $table_count != "0" ]]; then
  printf 'error: target is not empty (%s application tables); refusing restore\n' "$table_count" >&2
  exit 1
fi

started_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)
printf 'Restoring into isolated database %s at %s\n' "$database_name" "$started_at"
pg_restore \
  --dbname="$DRILL_DATABASE_URL" \
  --exit-on-error \
  --single-transaction \
  --no-owner \
  --no-acl \
  "$BACKUP_FILE"

restored_tables=$(psql --dbname="$drill_database_url" -X --set=ON_ERROR_STOP=1 --tuples-only --no-align --command="
  SELECT count(*)
  FROM pg_catalog.pg_class AS c
  JOIN pg_catalog.pg_namespace AS n ON n.oid = c.relnamespace
  WHERE c.relkind IN ('r', 'p')
    AND n.nspname NOT IN ('pg_catalog', 'information_schema')
    AND n.nspname !~ '^pg_toast';
")
alembic_revision=$(psql --dbname="$drill_database_url" -X --set=ON_ERROR_STOP=1 --tuples-only --no-align --command="
  SELECT CASE
    WHEN to_regclass('public.alembic_version') IS NULL THEN 'missing'
    ELSE (SELECT version_num FROM public.alembic_version LIMIT 1)
  END;
")
finished_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)

unset DRILL_DATABASE_URL drill_database_url

printf 'Restore completed: %s\n' "$finished_at"
printf 'Application tables: %s\n' "$restored_tables"
printf 'Alembic revision: %s\n' "$alembic_revision"
printf 'Next: run the integrity/privacy checks in docs/BACKUP_RESTORE.md, record evidence, then destroy the target.\n'
