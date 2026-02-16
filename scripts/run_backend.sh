#!/bin/bash
# Run backend on port 8001. Fails if port busy.
set -euo pipefail
PORT=8001
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND="$SCRIPT_DIR/../backend"
cd "$BACKEND"

if lsof -i :$PORT -t >/dev/null 2>&1; then
  echo "ERROR: Port $PORT is already in use. Stop the process or use another port." >&2
  exit 1
fi

echo "RUNNING backend on http://127.0.0.1:$PORT"
echo "Docs: http://127.0.0.1:$PORT/docs"
exec uvicorn server:app --host 0.0.0.0 --port $PORT
