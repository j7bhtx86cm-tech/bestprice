#!/bin/bash
# Verify auto-link: new supplier sees all restaurants and their documents.
# Runs separately from prod_minimal_e2e.sh --no-junk (does not affect 1/1/1/1).
# Self-contained: starts backend with same env if not running.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

# Single source of truth for MONGO_URL / DB_NAME (same as backend and verify)
. "$REPO/scripts/load_env.sh"
echo "MONGO_URL=$MONGO_URL DB_NAME=$DB_NAME"

# Use dedicated port to guarantee backend uses our MONGO_URL/DB_NAME
PORT="${AUTO_LINK_PORT:-18002}"
export VERIFY_BASE_URL="http://127.0.0.1:$PORT"
BACKEND_PID=""

# Start our own backend with same env (deterministic, no env mismatch)
echo "Starting backend on :$PORT (MONGO_URL=$MONGO_URL DB_NAME=$DB_NAME)..."
cd "$REPO/backend"
MONGO_URL="$MONGO_URL" DB_NAME="$DB_NAME" uvicorn server:app --host 0.0.0.0 --port $PORT 2>/dev/null &
BACKEND_PID=$!
cd "$REPO"
for i in $(seq 1 30); do
  if curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/docs" | grep -q "200\|301\|302"; then
    echo "Backend ready."
    break
  fi
  if ! kill -0 $BACKEND_PID 2>/dev/null; then
    echo "FAIL: Backend process exited (port $PORT may be in use)"
    exit 1
  fi
  sleep 1
done
if ! curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:$PORT/docs" | grep -q "200\|301\|302"; then
  echo "FAIL: Backend not ready after 30s"
  kill $BACKEND_PID 2>/dev/null || true
  exit 1
fi

echo "=== Auto-link check ==="
python3 scripts/verify_auto_link_new_supplier_all_restaurants.py
R=$?

if [ -n "$BACKEND_PID" ]; then
  kill $BACKEND_PID 2>/dev/null || true
  wait $BACKEND_PID 2>/dev/null || true
fi

if [ $R -ne 0 ]; then
  exit $R
fi
echo ""
echo "Auto-link check PASSED"
