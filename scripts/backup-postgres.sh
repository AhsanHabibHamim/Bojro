#!/usr/bin/env bash
set -Eeuo pipefail

umask 077

usage() {
  cat <<'EOF'
Create and verify a non-destructive PostgreSQL custom-format backup.

Required environment:
  DATABASE_URL                  Source PostgreSQL libpq URI.
  BACKUP_DIR                   Existing encrypted destination directory.
  BACKUP_DESTINATION_ENCRYPTED Must equal YES.
  BACKUP_ENVIRONMENT           Safe label such as staging or production.

Optional environment:
  BACKUP_PREFIX                Filename prefix (default: bojro).

The script never creates the destination directory, overwrites a file, or
prints the database URI. It writes a .dump and matching .sha256 sidecar.
EOF
}

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  usage
  exit 0
fi

for command_name in pg_dump pg_restore psql sha256sum date mv chmod wc; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'error: required command not found: %s\n' "$command_name" >&2
    exit 1
  fi
done

: "${DATABASE_URL:?DATABASE_URL is required}"
: "${BACKUP_DIR:?BACKUP_DIR is required}"
: "${BACKUP_ENVIRONMENT:?BACKUP_ENVIRONMENT is required}"

if [[ ${BACKUP_DESTINATION_ENCRYPTED:-} != "YES" ]]; then
  printf 'error: set BACKUP_DESTINATION_ENCRYPTED=YES only after verifying encrypted storage\n' >&2
  exit 1
fi

if [[ ! -d $BACKUP_DIR ]]; then
  printf 'error: BACKUP_DIR must already exist: %s\n' "$BACKUP_DIR" >&2
  exit 1
fi

if [[ ! -w $BACKUP_DIR ]]; then
  printf 'error: BACKUP_DIR is not writable: %s\n' "$BACKUP_DIR" >&2
  exit 1
fi

if [[ ! $DATABASE_URL =~ ^postgres(ql)?:// ]]; then
  printf 'error: DATABASE_URL must be a PostgreSQL libpq URI\n' >&2
  exit 1
fi

if [[ ! $BACKUP_ENVIRONMENT =~ ^[a-z0-9][a-z0-9_-]{0,31}$ ]]; then
  printf 'error: BACKUP_ENVIRONMENT contains unsafe characters\n' >&2
  exit 1
fi

backup_prefix=${BACKUP_PREFIX:-bojro}
if [[ ! $backup_prefix =~ ^[a-zA-Z0-9][a-zA-Z0-9_-]{0,31}$ ]]; then
  printf 'error: BACKUP_PREFIX contains unsafe characters\n' >&2
  exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
backup_path="${BACKUP_DIR%/}/${backup_prefix}-${BACKUP_ENVIRONMENT}-${timestamp}.dump"
checksum_path="${backup_path}.sha256"
partial_path="${backup_path}.partial.$$"
checksum_partial="${checksum_path}.partial.$$"

cleanup() {
  [[ -z ${partial_path:-} ]] || rm -f -- "$partial_path"
  [[ -z ${checksum_partial:-} ]] || rm -f -- "$checksum_partial"
}
trap cleanup EXIT INT TERM

if [[ -e $backup_path || -e $checksum_path ]]; then
  printf 'error: refusing to overwrite an existing backup\n' >&2
  exit 1
fi

source_database_url=$DATABASE_URL
export PGAPPNAME=bojro-backup
export PSQLRC=/dev/null

server_version=$(psql --dbname="$source_database_url" -X --set=ON_ERROR_STOP=1 --tuples-only --no-align --command='SHOW server_version')
alembic_revision=$(psql --dbname="$source_database_url" -X --set=ON_ERROR_STOP=1 --tuples-only --no-align --command='SELECT version_num FROM alembic_version')

printf 'Creating PostgreSQL backup for %s at %s\n' "$BACKUP_ENVIRONMENT" "$timestamp"
pg_dump \
  --dbname="$source_database_url" \
  --format=custom \
  --compress=9 \
  --no-owner \
  --no-acl \
  --serializable-deferrable \
  --lock-wait-timeout=60s \
  --file="$partial_path"

pg_restore --list "$partial_path" >/dev/null
chmod 0600 "$partial_path"
mv -- "$partial_path" "$backup_path"
partial_path=

checksum_output=$(sha256sum "$backup_path")
checksum=${checksum_output%% *}
printf '%s  %s\n' "$checksum" "${backup_path##*/}" >"$checksum_partial"
chmod 0600 "$checksum_partial"
mv -- "$checksum_partial" "$checksum_path"
checksum_partial=

backup_bytes=$(wc -c <"$backup_path")
unset DATABASE_URL source_database_url

printf 'Backup verified: %s\n' "$backup_path"
printf 'Bytes: %s\n' "$backup_bytes"
printf 'SHA-256: %s\n' "$checksum"
printf 'PostgreSQL version: %s\n' "$server_version"
printf 'Alembic revision: %s\n' "$alembic_revision"
printf 'Next: upload both files to approved encrypted immutable storage, verify, then delete local plaintext.\n'
