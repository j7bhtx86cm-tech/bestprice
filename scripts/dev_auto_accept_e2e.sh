#!/bin/bash
# E2E for auto-accept: restaurant uploads doc -> supplier sees "Договор принят" without manual action.
# Requires: backend on 8001 with AUTO_ACCEPT_CONTRACTS=1 (or BESTPRICE_AUTO_ACCEPT_CONTRACTS=1).
# Example: AUTO_ACCEPT_CONTRACTS=1 bash scripts/run_backend.sh
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO"

export VERIFY_BASE_URL="${VERIFY_BASE_URL:-http://127.0.0.1:8001}"

echo "=== Dev Auto-Accept E2E ==="
echo "Note: Backend must be started with AUTO_ACCEPT_CONTRACTS=1"
echo ""

# Backend alive
if ! curl -s -o /dev/null -w "%{http_code}" "http://127.0.0.1:8001/docs" | grep -q "200\|301\|302"; then
  echo "FAIL: Backend not reachable on 8001. Start: AUTO_ACCEPT_CONTRACTS=1 bash scripts/run_backend.sh"
  exit 1
fi
echo "1. Backend OK"

# Run auto-accept E2E
echo "2. Running prove_auto_accept_e2e.py..."
python3 scripts/prove_auto_accept_e2e.py

# Write proof
mkdir -p evidence
cat > evidence/AUTO_ACCEPT_E2E_PROOF.txt << 'EOF'
# Auto-Accept E2E Proof

Run: scripts/dev_auto_accept_e2e.sh
Backend: started with AUTO_ACCEPT_CONTRACTS=1

Flow:
- Restaurant registered, uploaded document
- NO manual accept-contract by supplier
- Supplier listed restaurant-documents -> contractStatus=accepted
- Supplier downloaded document -> 200

PASS
EOF

echo ""
echo "E2E PASSED (auto-accept)"
echo "Proof: evidence/AUTO_ACCEPT_E2E_PROOF.txt"
exit 0
