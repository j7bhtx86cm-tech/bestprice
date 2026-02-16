# Unified env for scripts. Source from prod_auto_link_check.sh etc.
# Loads backend/.env, exports MONGO_URL and DB_NAME with defaults.
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ -f "$REPO/backend/.env" ]; then
  set -a
  . "$REPO/backend/.env"
  set +a
fi
export MONGO_URL="${MONGO_URL:-mongodb://localhost:27017}"
export DB_NAME="${DB_NAME:-bestprice_local}"
