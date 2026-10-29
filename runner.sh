#!/usr/bin/env bash
# Rolodex runner: bring up a throwaway Docker stack, prove it works, tear it down.
# The last line of every run is a machine-readable RESULT line; the exit code says which step failed.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="python3"
# One project per checkout: two clones with the same folder name still get different stacks
DIR_NAME="$(basename "$ROOT_DIR" | tr '[:upper:]' '[:lower:]' | tr -cd 'a-z0-9_-')"
PROJECT="dxr-${DIR_NAME}-$(printf %s "$ROOT_DIR" | cksum | cut -d' ' -f1)"
START=$SECONDS

usage() {
  cat <<EOF
Usage: ./runner.sh <command>

  up     Start a fresh throwaway stack (own database), wait for /ready, run the smoke tests
  down   Stop the stack and delete its database and images
  smoke  Run the smoke tests against the running stack (rerun 'up' after editing code)
  test   up, then the failure-path checks, then down (what CI runs)

Exit codes: 0 pass, 1 tests failed, 2 Docker missing, 3 stack never became ready, 4 build failed.
Stack for this checkout: $PROJECT
EOF
}

compose() { docker compose -p "$PROJECT" -f "$ROOT_DIR/docker-compose.yml" "$@"; }

# The host port is assigned per container start, so look it up every time
base_url() {
  local hostport
  hostport="$(compose port app 5000 2>/dev/null)" || return 1
  [ -n "$hostport" ] || return 1
  echo "http://127.0.0.1:${hostport##*:}"
}

result_fail() {  # step exit_code message
  echo "runner: $3" >&2
  echo "RESULT: fail step=$1 project=$PROJECT elapsed=$((SECONDS - START))s cleanup=\"./runner.sh down\""
  exit "$2"
}

result_pass() {
  echo "RESULT: pass url=$(base_url) project=$PROJECT elapsed=$((SECONDS - START))s stop=\"./runner.sh down\" (the port changes if the app container restarts)"
}

preflight() {
  docker compose version >/dev/null 2>&1 ||
    result_fail preflight 2 "needs Docker Compose v2; install it, or run the app directly with DATABASE_URL=... python3 app.py"
  docker info >/dev/null 2>&1 ||
    result_fail preflight 2 "the Docker daemon isn't running; start it (for example: sudo systemctl start docker), then rerun ./runner.sh up"
}

start_stack() {
  preflight
  echo "runner: starting stack $PROJECT ..."
  # Always start from an empty database: no leftover data and no stale sign-in lockouts
  compose down -v --remove-orphans >/dev/null 2>&1 || true
  local log
  log="$(mktemp)"
  # An empty ROLODEX_PORT publishes an ephemeral host port; --build runs the code on disk
  if ! ROLODEX_PORT="${ROLODEX_PORT:-}" compose up -d --build >"$log" 2>&1; then
    tail -n 20 "$log" >&2
    rm -f "$log"
    result_fail build 4 "docker compose up failed (output above)"
  fi
  rm -f "$log"
}

wait_ready() {
  local url="" body="" i
  for i in $(seq 1 90); do
    if url="$(base_url)" && curl -sf -m 2 -o /dev/null "$url/ready"; then
      echo "runner: ready after $((SECONDS - START))s ($url/ready ok)"
      return 0
    fi
    sleep 1
  done
  [ -n "$url" ] && body="$(curl -s -m 2 "$url/ready" || true)"
  result_fail ready 3 "stack $PROJECT not ready after 90s; /ready said ${body:-nothing}. Next: docker compose -p $PROJECT logs app"
}

run_smoke() {
  local url rc=0
  url="$(base_url)" || result_fail smoke 3 "no running stack for this checkout; start one with ./runner.sh up"
  BASE_URL="$url" "$PY" "$ROOT_DIR/tests/api_integration_smoke.py" || rc=$?
  case "$rc" in
    0) ;;
    2) result_fail smoke 3 "the smoke tests found no server at $url; check: docker compose -p $PROJECT ps" ;;
    *) result_fail smoke 1 "smoke tests failed (failing tests marked ✗ above)" ;;
  esac
  curl -sf -o /dev/null "$url/vintage/" || result_fail smoke 1 "$url/vintage/ is not served"
}

# Production must refuse to start without ROLODEX_SECRET_KEY, before touching the database
check_prod_key_required() {
  local out rc=0
  out="$(compose run --rm --no-deps -e VERCEL=1 -e ROLODEX_SECRET_KEY= -e ROLODEX_DB_PORT=1 \
    app python3 -c 'import app' 2>&1)" || rc=$?
  if [ "$rc" -eq 0 ] ||
     [[ "$(printf '%s\n' "$out" | tail -n 1)" != *"ROLODEX_SECRET_KEY must be set in production"* ]] ||
     [[ "$out" == *"can't reach Postgres"* ]]; then
    printf '%s\n' "$out" | tail -n 5 >&2
    result_fail prod-key-check 1 "with VERCEL=1 and no ROLODEX_SECRET_KEY, importing app must fail before any database access"
  fi
  echo "  ✓ production refuses to start without ROLODEX_SECRET_KEY"
}

run_checks() {
  echo "runner: failure-path checks"
  check_prod_key_required
  "$PY" "$ROOT_DIR/tests/check_env_docs.py" || result_fail env-docs 1 "README is missing env vars the code reads (listed above)"
  PROJECT="$PROJECT" bash "$ROOT_DIR/tests/failure_paths.sh" || result_fail failure-paths 1 "failure-path checks failed (marked ✗ above)"
}

stop_stack() {
  compose down -v --rmi local --remove-orphans >/dev/null 2>&1 || true
  echo "runner: removed stack $PROJECT"
}

case "${1:-}" in
  up)    start_stack; wait_ready; run_smoke; result_pass ;;
  down)  stop_stack ;;
  smoke) run_smoke; result_pass ;;
  test)  start_stack; wait_ready; run_smoke; run_checks; url="$(base_url)"; stop_stack
         echo "RESULT: pass url=$url project=$PROJECT elapsed=$((SECONDS - START))s (stack removed)" ;;
  -h|--help|help) usage ;;
  *) usage >&2; exit 1 ;;
esac
