#!/bin/bash
# BestPrice dev pipeline: reset -> seed -> verify
# Usage: ./scripts/dev_pipeline.sh
# Requires: MongoDB running (docker compose up -d), backend running (uvicorn)

set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

echo "=== 1/4 Reset data ==="
python3 scripts/dev_reset_data.py --force

echo ""
echo "=== 2/4 Seed data ==="
python3 backend/seed_data.py

echo ""
echo "=== 3/4 Verify E2E (API) ==="
VERIFY_BASE_URL="${VERIFY_BASE_URL:-http://127.0.0.1:8000}" python3 scripts/verify_e2e.py

echo ""
echo "=== 4/4 Done ==="
echo "Backend: http://localhost:8000"
echo "Frontend: http://localhost:3000"
echo "Supplier login: http://localhost:3000/supplier/auth"
echo "  supplier1@example.com / password123"
echo "  supplier2@example.com / password123"
echo "Customer login: http://localhost:3000/customer/auth"
echo "  restaurant1@example.com / password123"
echo "  restaurant2@example.com / password123"
