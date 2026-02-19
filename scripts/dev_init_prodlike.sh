#!/bin/bash
# Prod-like dev init: one command to get test restaurant + 2 suppliers + auto-link + evidence.
# Idempotent. Requires backend (and optionally frontend) running.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

. "$REPO/scripts/load_env.sh"
export VERIFY_BASE_URL="${VERIFY_BASE_URL:-http://127.0.0.1:8001}"
export API_BASE_URL="${API_BASE_URL:-$VERIFY_BASE_URL}"
export SUPPLIER_LOGIN_URL="${SUPPLIER_LOGIN_URL:-http://localhost:3000/supplier/auth}"

FRONTEND_URL="${FRONTEND_URL:-http://localhost:3000}"
EVIDENCE_DIR="$REPO/evidence"
TS=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
RESULT="PASS"
FAIL_REASON=""

echo "=== Prod-like dev init ==="
echo "MONGO_URL=$MONGO_URL DB_NAME=$DB_NAME"
echo ""

# 1) Check backend
if ! curl -s -o /dev/null -w "%{http_code}" "$VERIFY_BASE_URL/docs" | grep -q "200\|301\|302"; then
  echo "FAIL: Backend not reachable at $VERIFY_BASE_URL"
  echo "Start: bash scripts/run_backend.sh"
  RESULT="FAIL"
  FAIL_REASON="Backend not reachable"
else
  echo "Backend OK"
fi

# 2) Check frontend (optional)
if [ -z "$FAIL_REASON" ]; then
  if ! curl -s -o /dev/null -w "%{http_code}" "$FRONTEND_URL" | grep -q "200\|301\|302"; then
    echo "WARN: Frontend not reachable at $FRONTEND_URL (optional)"
  else
    echo "Frontend OK"
  fi
fi

# 3) Create/update test restaurant Креветочная
if [ -z "$FAIL_REASON" ]; then
  if ! bash scripts/dev_create_test_restaurant_krevetochna.sh; then
    RESULT="FAIL"
    FAIL_REASON="dev_create_test_restaurant_krevetochna failed"
  fi
fi

# 4) Create/update suppliers Integrita, Romax
if [ -z "$FAIL_REASON" ]; then
  if ! bash scripts/dev_create_2_test_suppliers.sh; then
    RESULT="FAIL"
    FAIL_REASON="dev_create_2_test_suppliers failed"
  fi
fi

# 5) Verify auto-link (customers>=1, links, API returns Креветочная)
if [ -z "$FAIL_REASON" ]; then
  if ! python3 scripts/verify_auto_link_prodlike.py; then
    RESULT="FAIL"
    FAIL_REASON="verify_auto_link_prodlike failed"
  fi
fi

# 6) Write main evidence DEV_INIT_PRODLIKE.txt
mkdir -p "$EVIDENCE_DIR"
{
  echo "# Prod-like dev init"
  echo "timestamp=$TS"
  echo "MONGO_URL=$MONGO_URL"
  echo "DB_NAME=$DB_NAME"
  echo ""
  echo "## Evidence files"
  echo "  - evidence/DEV_CREATE_TEST_RESTAURANT_KREVETOCHNA.txt"
  echo "  - evidence/DEV_CREATE_2_SUPPLIERS_INTEGRITA_ROMAX.txt"
  echo "  - evidence/AUTO_LINK_PRODLIKE.txt"
  echo "  - evidence/AUTO_LINK_NEW_SUPPLIER_PROOF.txt (from prod_auto_link_check if run)"
  echo ""
  echo "## UI smoke checklist (step-by-step)"
  echo ""
  echo "Supplier Integrita:"
  echo "  1. Open $SUPPLIER_LOGIN_URL"
  echo "  2. Log in with credentials from evidence/DEV_CREATE_2_SUPPLIERS_INTEGRITA_ROMAX.txt"
  echo "  3. Open section \"Документы\" / \"Документы от ресторанов\""
  echo "  4. Must see restaurant \"Креветочная\""
  echo ""
  echo "Supplier Romax: same steps (same URL, Romax creds from DEV_CREATE_2_SUPPLIERS_INTEGRITA_ROMAX.txt)."
  echo ""
  echo "Customer \"Креветочная\":"
  echo "  1. Open ${FRONTEND_URL}/customer/auth"
  echo "  2. Log in gmfuel@gmail.com / Krevetochna#2026"
  echo "  3. Cabinet main page must open"
  echo ""
  echo "Optional screenshots: evidence/screens/prodlike_smoke_*.png"
  echo ""
  if [ -n "$FAIL_REASON" ]; then
    echo "FAIL_REASON=$FAIL_REASON"
    echo ""
  fi
  echo "RESULT: $RESULT"
} > "$EVIDENCE_DIR/DEV_INIT_PRODLIKE.txt"

echo ""
echo "=== Dev init done ==="
echo "Evidence: $EVIDENCE_DIR/DEV_INIT_PRODLIKE.txt"
echo "RESULT: $RESULT"
[ -n "$FAIL_REASON" ] && echo "FAIL: $FAIL_REASON"

[ "$RESULT" = "PASS" ] && exit 0 || exit 1
