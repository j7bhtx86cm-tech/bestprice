#!/bin/bash
# Create or update test restaurant (customer) "Креветочная". Idempotent. Writes evidence.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

. "$REPO/scripts/load_env.sh"
export VERIFY_BASE_URL="${VERIFY_BASE_URL:-http://127.0.0.1:8001}"
export API_BASE_URL="${API_BASE_URL:-$VERIFY_BASE_URL}"

if ! curl -s -o /dev/null -w "%{http_code}" "$VERIFY_BASE_URL/docs" | grep -q "200\|301\|302"; then
  echo "WARN: Backend not reachable at $VERIFY_BASE_URL. Start backend first (e.g. bash scripts/run_backend.sh)."
  exit 1
fi

python3 scripts/dev_create_test_restaurant_krevetochna.py
echo ""
echo "Done. Creds and proof in evidence/DEV_CREATE_TEST_RESTAURANT_KREVETOCHNA.txt"
