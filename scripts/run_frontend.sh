#!/bin/bash
# Run frontend on port 3000. Fails if port busy.
set -euo pipefail
PORT=3000
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FRONTEND="$SCRIPT_DIR/../frontend"
cd "$FRONTEND"

if lsof -i :$PORT -t >/dev/null 2>&1; then
  echo "ERROR: Port $PORT is already in use. Stop the process or use another port." >&2
  exit 1
fi

echo "RUNNING frontend on http://localhost:$PORT"
exec npm start
