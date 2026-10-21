#!/usr/bin/env bash
# Rolodex production runner — start/stop/test the app via gunicorn
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="python3"

start_server() {
  echo 'Starting Rolodex (gunicorn)...'
  cd "$ROOT_DIR"
  export ROLODEX_DEBUG="${ROLODEX_DEBUG:-0}"
  gunicorn -c gunicorn_config.py wsgi_entry:app &
  echo $! > /tmp/rolodex.pid
  # Wait for health check
  for i in $(seq 1 15); do
    if curl -sf http://localhost:5000/health > /dev/null 2>&1; then
      echo "Rolodex is healthy on port ${ROLODEX_PORT:-5000}"
      return 0
    fi
    sleep 1
  done
  echo 'ERROR: Rolodex failed to start'
  return 1
}

stop_server() {
  echo 'Stopping Rolodex...'
  if [ -f /tmp/rolodex.pid ]; then
    kill "$(cat /tmp/rolodex.pid)" 2>/dev/null || true
    rm -f /tmp/rolodex.pid
  fi
  pkill -f 'gunicorn.*wsgi_entry' 2>/dev/null || true
  sleep 1
  echo 'Stopped.'
}

run_smoke() {
  echo 'Running API smoke tests...'
  "$PY" "$ROOT_DIR/tests/api_integration_smoke.py"
}

run_all_tests() {
  start_server
  run_smoke
  stop_server
  echo 'All tests passed ✓'
}

case "${1:-""}" in
  start) start_server ;;
  stop) stop_server ;;
  smoke) run_smoke ;;
  test) run_all_tests ;;
  restart) stop_server; start_server ;;
  *)
    echo 'Usage: runner.sh {start|stop|restart|smoke|test}'
    exit 1
    ;;
esac
