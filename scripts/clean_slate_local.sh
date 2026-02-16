#!/bin/bash
# Clean slate: remove all test/dev data. DESTRUCTIVE.
# Requires ALLOW_DESTRUCTIVE=1 and local/dev environment.
set -euo pipefail

if [ "${ALLOW_DESTRUCTIVE:-0}" != "1" ]; then
  echo "Clean slate requires ALLOW_DESTRUCTIVE=1"
  echo "Usage: ALLOW_DESTRUCTIVE=1 bash scripts/clean_slate_local.sh"
  exit 1
fi

DB_HOST="${MONGO_URL:-mongodb://localhost:27017}"
if [[ "$DB_HOST" == *"localhost"* ]] || [[ "$DB_HOST" == *"127.0.0.1"* ]]; then
  :
else
  echo "REFUSED: MONGO_URL does not look local. Clean slate only for local/dev."
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$SCRIPT_DIR/.."
cd "$REPO"

echo "Clean slate: deleting test data..."
python3 scripts/clean_slate_local.py
echo "Done."
