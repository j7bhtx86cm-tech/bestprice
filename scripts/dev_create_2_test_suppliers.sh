#!/bin/bash
# Create 2 test suppliers (Integrita, Romax) with logins and auto-link to all restaurants.
# Idempotent. Requires backend reachable (default :8001). Writes evidence.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

. "$REPO/scripts/load_env.sh"
export VERIFY_BASE_URL="${VERIFY_BASE_URL:-http://127.0.0.1:8001}"
export API_BASE_URL="${API_BASE_URL:-$VERIFY_BASE_URL}"
export SUPPLIER_LOGIN_URL="${SUPPLIER_LOGIN_URL:-http://localhost:3000/supplier/auth}"

# Optional: ensure backend is up (no auto-start here to avoid changing prod_minimal)
if ! curl -s -o /dev/null -w "%{http_code}" "$VERIFY_BASE_URL/docs" | grep -q "200\|301\|302"; then
  echo "WARN: Backend not reachable at $VERIFY_BASE_URL. Start backend first (e.g. bash scripts/run_backend.sh)."
  exit 1
fi

python3 scripts/dev_create_2_test_suppliers.py
echo ""
echo "Done. Creds and proof in evidence/DEV_CREATE_2_SUPPLIERS_INTEGRITA_ROMAX.txt"
