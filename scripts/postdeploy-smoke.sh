#!/usr/bin/env bash
set -Eeuo pipefail

usage() {
  cat <<'EOF'
Run read-only public post-deploy smoke checks.

Required environment:
  API_URL         API origin, for example https://api.bojro.com.bd
  STOREFRONT_URL  Storefront origin, for example https://bojro.com.bd

HTTP is refused unless ALLOW_HTTP_LOCALHOST=1 and both origins are localhost.
The script creates no user, cart, order, upload, or provider effect.
EOF
}

if [[ ${1:-} == "--help" || ${1:-} == "-h" ]]; then
  usage
  exit 0
fi

for command_name in curl grep mktemp; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    printf 'error: required command not found: %s\n' "$command_name" >&2
    exit 1
  fi
done

: "${API_URL:?API_URL is required}"
: "${STOREFRONT_URL:?STOREFRONT_URL is required}"

API_URL=${API_URL%/}
STOREFRONT_URL=${STOREFRONT_URL%/}

validate_origin() {
  local name=$1
  local value=$2
  if [[ $value == *'@'* || $value == *'?'* || $value == *'#'* ]]; then
    printf 'error: %s must be a credential-free origin without query or fragment\n' "$name" >&2
    exit 1
  fi
  if [[ $value =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?$ ]]; then
    return
  fi
  if [[ ${ALLOW_HTTP_LOCALHOST:-} == "1" && $value =~ ^http://(localhost|127\.0\.0\.1)(:[0-9]+)?$ ]]; then
    return
  fi
  printf 'error: %s must be an HTTPS origin (or explicit local HTTP)\n' "$name" >&2
  exit 1
}

validate_origin API_URL "$API_URL"
validate_origin STOREFRONT_URL "$STOREFRONT_URL"

work_dir=$(mktemp -d)
cleanup() {
  rm -rf -- "$work_dir"
}
trap cleanup EXIT INT TERM

request() {
  local label=$1
  local url=$2
  local headers_file="$work_dir/${label}.headers"
  local body_file="$work_dir/${label}.body"
  local http_status
  shift 2
  http_status=$(curl \
    --silent \
    --show-error \
    --fail \
    --max-time 20 \
    --retry 3 \
    --retry-all-errors \
    --dump-header "$headers_file" \
    --output "$body_file" \
    --write-out '%{http_code}' \
    "$@" \
    "$url")
  if [[ ! $http_status =~ ^2[0-9][0-9]$ ]]; then
    printf 'error: %s returned HTTP %s without following redirects\n' "$label" "$http_status" >&2
    exit 1
  fi
  printf 'PASS %s %s\n' "$label" "$url"
}

require_header() {
  local label=$1
  local header_name=$2
  if ! grep --ignore-case --quiet "^${header_name}:" "$work_dir/${label}.headers"; then
    printf 'error: %s response is missing %s\n' "$label" "$header_name" >&2
    exit 1
  fi
}

request api-health "$API_URL/health"
request api-ready "$API_URL/ready"
if ! grep --extended-regexp --quiet '"status"[[:space:]]*:[[:space:]]*"ready"' "$work_dir/api-ready.body"; then
  printf 'error: API readiness is not exactly ready\n' >&2
  exit 1
fi
require_header api-health x-request-id
require_header api-health x-content-type-options
require_header api-health x-frame-options

request api-cors "$API_URL/api/v1/health" --header "Origin: $STOREFRONT_URL"
if ! grep --ignore-case --quiet "^access-control-allow-origin: ${STOREFRONT_URL}" "$work_dir/api-cors.headers"; then
  printf 'error: API CORS does not allow the exact storefront origin\n' >&2
  exit 1
fi

request storefront-bn "$STOREFRONT_URL/bn"
request storefront-en "$STOREFRONT_URL/en"
request robots "$STOREFRONT_URL/robots.txt"
request sitemap "$STOREFRONT_URL/sitemap.xml"

if ! grep --ignore-case --extended-regexp --quiet '<html[^>]+lang="bn"' "$work_dir/storefront-bn.body"; then
  printf 'error: Bangla storefront does not declare lang="bn"\n' >&2
  exit 1
fi
if ! grep --ignore-case --extended-regexp --quiet '<html[^>]+lang="en"' "$work_dir/storefront-en.body"; then
  printf 'error: English storefront does not declare lang="en"\n' >&2
  exit 1
fi

if [[ $API_URL == https://* ]]; then
  require_header api-health strict-transport-security
fi
if [[ $STOREFRONT_URL == https://* ]]; then
  require_header storefront-bn strict-transport-security
fi

printf 'All read-only post-deploy smoke checks passed.\n'
