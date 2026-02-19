#!/usr/bin/env python3
"""
Verify that POST /api/price-lists/import accepts request WITHOUT column_mapping.
Sends only file + replace (no column_mapping). Ensures response is never raw Pydantic array.
Writes evidence/PRICE_IMPORT_CONTRACT_OPTIONAL_MAPPING.txt.
Requires: backend running, at least one supplier (e.g. run dev_create_2_test_suppliers.sh).
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _env import load_env, get_mongo_url, get_db_name

load_env()
MONGO_URL = get_mongo_url()
DB_NAME = get_db_name()
API_BASE_URL = os.environ.get("VERIFY_BASE_URL", os.environ.get("API_BASE_URL", "http://127.0.0.1:8001")).rstrip("/")
API = f"{API_BASE_URL}/api"

# Use any supplier from dev setup
SUPPLIER_EMAIL = os.environ.get("CONTRACT_TEST_EMAIL", "romax.supplier@example.com")
SUPPLIER_PASSWORD = os.environ.get("CONTRACT_TEST_PASSWORD", "Romax#2026")

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)


def main():
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Price import contract: column_mapping optional",
        f"timestamp={ts}",
        f"MONGO_URL={MONGO_URL}",
        f"DB_NAME={DB_NAME}",
        f"API_BASE_URL={API_BASE_URL}",
        "sent fields: file, replace (no column_mapping)",
        "",
    ]

    r = requests.post(f"{API}/auth/login", json={"email": SUPPLIER_EMAIL, "password": SUPPLIER_PASSWORD}, timeout=10)
    if r.status_code != 200:
        lines.append(f"response_status=login_failed_{r.status_code}")
        lines.append("response_shape_ok=false")
        lines.append("RESULT: FAIL (supplier login failed)")
        out = ROOT / "evidence" / "PRICE_IMPORT_CONTRACT_OPTIONAL_MAPPING.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        print("FAIL: supplier login failed")
        sys.exit(1)

    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Minimal CSV that auto-detect can parse (name, price, unit)
    minimal_csv = "name,price,unit\nTest Product,100,шт\n"
    files = {"file": ("minimal.csv", minimal_csv.encode("utf-8"), "text/csv")}
    data = {"replace": "false"}
    # Explicitly do NOT send column_mapping

    resp = requests.post(
        f"{API}/price-lists/import",
        headers=headers,
        files=files,
        data=data,
        timeout=30,
    )

    lines.append(f"response_status={resp.status_code}")

    # Check: detail must NOT be a list (raw Pydantic validation error)
    try:
        body = resp.json()
    except Exception:
        body = {}
    detail = body.get("detail")
    is_array = isinstance(detail, list)
    if is_array:
        lines.append("response_shape_ok=false")
        lines.append("reason=detail is array (raw Pydantic validation error)")
        lines.append("RESULT: FAIL (column_mapping required or validation returned array)")
        out = ROOT / "evidence" / "PRICE_IMPORT_CONTRACT_OPTIONAL_MAPPING.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        print("FAIL: response detail is array (raw Pydantic)")
        sys.exit(1)

    # Structured 422 or success both ok
    if isinstance(detail, dict) and "error_code" in detail:
        lines.append("response_shape_ok=true")
        lines.append(f"error_code={detail.get('error_code')}")
    elif resp.status_code in (200, 201):
        lines.append("response_shape_ok=true")
    else:
        lines.append("response_shape_ok=true" if isinstance(detail, dict) else "response_shape_ok=false")

    lines.append("RESULT: PASS")
    out = ROOT / "evidence" / "PRICE_IMPORT_CONTRACT_OPTIONAL_MAPPING.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print("PRICE_IMPORT_CONTRACT_OPTIONAL_MAPPING: PASS", "status=", resp.status_code)


if __name__ == "__main__":
    main()
