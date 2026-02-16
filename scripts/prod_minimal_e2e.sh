#!/bin/bash
# Minimal E2E: one command to verify core flow.
# Requires backend on 8001. Frontend optional.
#
# Modes:
#   (default) Standalone: creates test entities, runs ACL proof
#   --no-junk: After manual UI flow. Verifies 1/1/1/1, ACL with existing entities.
#              Requires SUPPLIER_EMAIL, RESTAURANT_EMAIL (default supplier@example.com, restaurant@example.com)
#              and TestPass123! as password.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

export VERIFY_BASE_URL="${VERIFY_BASE_URL:-http://127.0.0.1:8001}"

NO_JUNK=false
[ "${1:-}" = "--no-junk" ] && NO_JUNK=true

echo "=== Prod Minimal E2E ==="

# 1. Backend alive
if ! curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8001/docs" | grep -q "200\|301\|302"; then
  echo "FAIL: Backend not reachable on 8001. Start: bash scripts/run_backend.sh"
  exit 1
fi
echo "1. Backend OK"

if [ "$NO_JUNK" = true ]; then
  # 2a. Bootstrap minimal state (1/1/1/1 with full requisites)
  echo "2. Running bootstrap_minimal_requisites.py..."
  python3 scripts/bootstrap_minimal_requisites.py
  # 3a. No-junk assertions (1/1/1/1)
  echo "3. Running verify_no_junk.py..."
  python3 scripts/verify_no_junk.py
  # 4a. Contract suppliers match companies (no junk suppliers)
  echo "4. Running verify_contract_suppliers_match_companies.py..."
  python3 scripts/verify_contract_suppliers_match_companies.py
  # 5a. ACL proof with existing entities (removes temp supplier after)
  echo "5. Running collect_acl_proof.py --use-existing..."
  python3 scripts/collect_acl_proof.py --use-existing
  # 6a. Requisites preview/full API proof
  echo "6. Running collect_requisites_proof.py..."
  python3 scripts/collect_requisites_proof.py
else
  # 2. Run prove script (register, upload, supplier sees, newest first)
  echo "2. Running prove_new_restaurant_docs_e2e.py..."
  python3 scripts/prove_new_restaurant_docs_e2e.py
  # 3. ACL proof (creates acl_* entities)
  echo "3. Running collect_acl_proof.py..."
  python3 scripts/collect_acl_proof.py
fi

echo ""
echo "E2E PASSED"
exit 0
