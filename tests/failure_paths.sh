#!/usr/bin/env bash
# Failure-path checks against the running ./runner.sh stack (throwaway database only).
# Run by `./runner.sh test` after `up`; PROJECT names that stack.
set -euo pipefail
: "${PROJECT:?run this through ./runner.sh test}"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
JAR="$TMP/cookies"
EMAIL="failure-paths-$$-$RANDOM@example.test"
FAILED=0

compose() { docker compose -p "$PROJECT" -f "$ROOT_DIR/docker-compose.yml" "$@"; }
psql_db() { compose exec -T db psql -U "${ROLODEX_DB_USER:-rolodex}" -d "${ROLODEX_DB_NAME:-rolodex}" -Atc "$1"; }
# The host port changes whenever the app container restarts, so resolve it on every call
base_url() { local hp; hp="$(compose port app 5000)"; echo "http://127.0.0.1:${hp##*:}"; }
status_of() { curl -s -o "$TMP/body" -w '%{http_code}' -b "$JAR" "$(base_url)$1"; }

wait_ready() {
  local i
  for i in $(seq 1 60); do
    curl -sf -m 2 -o /dev/null "$(base_url 2>/dev/null)/ready" 2>/dev/null && return 0
    sleep 1
  done
  echo "  ✗ stack did not become ready again within 60s" >&2
  return 1
}

check() {  # name command...
  local name="$1"; shift
  if "$@"; then echo "  ✓ $name"; else echo "  ✗ $name"; FAILED=1; fi
}

curl -sf -o /dev/null -c "$JAR" -H 'Content-Type: application/json' \
  -d "{\"email\":\"$EMAIL\",\"password\":\"correct-horse-battery\"}" "$(base_url)/api/v1/auth/signup"

# Runs before the env-key check: that one empties app_settings, and a restart then would mint a new key
session_survives_restart() {
  [ "$(status_of /api/v1/contacts)" = 200 ] || return 1
  compose restart app >/dev/null 2>&1
  wait_ready && [ "$(status_of /api/v1/contacts)" = 200 ]
}

env_key_writes_no_row() {
  local saved count
  saved="$(psql_db "SELECT value FROM app_settings WHERE key = 'secret_key'")"
  psql_db "DELETE FROM app_settings" >/dev/null
  compose run --rm --no-deps -e ROLODEX_SECRET_KEY=from-env app python3 -c 'import app' >/dev/null 2>&1
  count="$(psql_db "SELECT count(*) FROM app_settings")"
  psql_db "INSERT INTO app_settings (key, value) VALUES ('secret_key', '$saved')" >/dev/null
  [ "$count" = 0 ]
}

startup_names_the_database() {
  local out
  out="$(compose run --rm --no-deps -e ROLODEX_DB_PORT=1 app python3 -c 'import app' 2>&1 || true)"
  [[ "$(printf '%s\n' "$out" | tail -n 1)" == *"can't reach Postgres at db:1"* ]]
}

db_down_gives_json_errors() {
  local ok=0 contacts ready
  compose stop db >/dev/null 2>&1
  contacts="$(status_of /api/v1/contacts)"
  grep -q '"internal error"' "$TMP/body" && grep -q '"id"' "$TMP/body" && [ "$contacts" = 500 ] || ok=1
  ready="$(status_of /ready)"
  [ "$ready" = 503 ] && grep -q 'database unreachable' "$TMP/body" &&
    ! grep -qE 'could not|connection to server|"db"' "$TMP/body" || ok=1
  compose start db >/dev/null 2>&1
  wait_ready || ok=1
  return "$ok"
}

smoke_without_server_exits_2() {
  local rc=0
  BASE_URL=http://127.0.0.1:1 python3 "$ROOT_DIR/tests/api_integration_smoke.py" >/dev/null 2>&1 || rc=$?
  [ "$rc" = 2 ]
}

claim_orphans_round_trip() {
  local out rc=0
  psql_db "INSERT INTO contacts (id, name, created_at, updated_at) VALUES ('orphan-check', 'Orphan Check', now(), now())" >/dev/null
  # Same recipe the README gives for compose deployments; mixed case proves the email is normalized
  out="$(compose run --rm --no-deps -v "$ROOT_DIR/migrate_to_postgres.py:/app/migrate_to_postgres.py:ro,z" \
    app python3 migrate_to_postgres.py --claim-orphans --owner "$(echo "$EMAIL" | tr a-z A-Z)" 2>&1)"
  [[ "$out" == *"assigned 1 "* ]] || return 1
  [ "$(status_of /api/v1/contacts)" = 200 ] && grep -q 'Orphan Check' "$TMP/body" || return 1
  compose run --rm --no-deps -v "$ROOT_DIR/migrate_to_postgres.py:/app/migrate_to_postgres.py:ro,z" \
    app python3 migrate_to_postgres.py --claim-orphans --owner nobody@example.test >/dev/null 2>&1 || rc=$?
  [ "$rc" = 2 ]
}

env_docs_catch_a_missing_row() {
  local rc=0
  grep -v '`ROLODEX_VINTAGE_DIR`' "$ROOT_DIR/README.md" > "$TMP/README.md"
  python3 "$ROOT_DIR/tests/check_env_docs.py" "$TMP/README.md" 2>"$TMP/err" >/dev/null || rc=$?
  [ "$rc" = 1 ] && grep -q ROLODEX_VINTAGE_DIR "$TMP/err"
}

check 'session survives an app restart (key stored in Postgres)' session_survives_restart
check 'ROLODEX_SECRET_KEY set: no key written to the database' env_key_writes_no_row
check 'startup without a database names it in one line' startup_names_the_database
check 'database down: /api returns JSON 500 with an id, /ready 503 without hostnames' db_down_gives_json_errors
check 'smoke suite with no server exits 2' smoke_without_server_exits_2
check 'migrate --claim-orphans adopts ownerless contacts; unknown email exits 2' claim_orphans_round_trip
check 'env docs check catches a missing README row' env_docs_catch_a_missing_row

exit "$FAILED"
