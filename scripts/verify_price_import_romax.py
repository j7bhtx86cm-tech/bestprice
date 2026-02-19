#!/usr/bin/env python3
"""
Verify Romax price list import: upload test file as Romax supplier, check imported > 0
and supplier_items (price list) count > 0. Writes evidence/PRICE_IMPORT_ROMAX_PROOF.txt.
Requires: backend running, Romax supplier exists (run dev_create_2_test_suppliers.sh first).
Test file: ROMAX_PRICE_FILE env or first arg or tests/fixtures/romax_price.xlsx or import_data/romax_*.xlsx.
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

BASE = os.environ.get("VERIFY_BASE_URL", os.environ.get("API_BASE_URL", "http://127.0.0.1:8001")).rstrip("/")
API = f"{BASE}/api"

ROMAX_EMAIL = os.environ.get("ROMAX_EMAIL", "romax.supplier@example.com")
ROMAX_PASSWORD = os.environ.get("ROMAX_PASSWORD", "Romax#2026")

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)


def req(method, path, **kwargs):
    return requests.request(method, f"{API}{path}", timeout=60, **kwargs)


def main():
    file_path = os.environ.get("ROMAX_PRICE_FILE") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not file_path:
        for candidate in [
            ROOT / "import_data" / "romax_price.xlsx",
            ROOT / "tests" / "fixtures" / "romax_price.xlsx",
            ROOT / "tests" / "fixtures" / "romax_price.csv",
        ]:
            if candidate.exists():
                file_path = str(candidate)
                break
        if not file_path:
            try:
                file_path = str(next(ROOT.glob("import_data/romax_*")))
            except StopIteration:
                pass
    if not file_path or not Path(file_path).exists():
        print("SKIP: No Romax price file. Put file at import_data/romax_price.xlsx or set ROMAX_PRICE_FILE=<path>")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("timestamp=" + datetime.now(timezone.utc).isoformat() + "\n")
            f.write("MONGO_URL=" + MONGO_URL + "\nDB_NAME=" + DB_NAME + "\n")
            f.write("ROMAX_PRICE_FILE= (not set, file not found)\n")
            f.write("RESULT: SKIP (no test file). Put test file at import_data/romax_price.xlsx or set env ROMAX_PRICE_FILE.\n")
        sys.exit(0)

    ts = datetime.now(timezone.utc).isoformat()
    lines = ["# Romax price list import proof", "timestamp=" + ts, f"MONGO_URL={MONGO_URL}", f"DB_NAME={DB_NAME}", f"file={file_path}", ""]

    r = req("POST", "/auth/login", json={"email": ROMAX_EMAIL, "password": ROMAX_PASSWORD})
    if r.status_code != 200:
        lines.append("FAIL: Romax login failed")
        lines.append("RESULT: FAIL")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        print("FAIL: Romax login failed")
        sys.exit(1)

    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f, "application/octet-stream")}
        data = {"replace": "true"}
        imp = req("POST", "/price-lists/import", headers=headers, files=files, data=data)
    if imp.status_code not in (200, 201):
        lines.append(f"FAIL: import returned {imp.status_code}")
        try:
            err_body = imp.json()
            if isinstance(err_body.get("detail"), dict):
                d = err_body["detail"]
                lines.append("detail.message=" + str(d.get("message", "")))
                lines.append("diagnostic_summary=" + str(d.get("diagnostic_summary", "")))
                r = d.get("skipped_reasons") or {}
                lines.append("breakdown: empty_name=%s price_parse_failed=%s price_le_zero=%s other=%s" % (
                    r.get("empty_name", 0), r.get("price_parse_failed", 0), r.get("price_le_zero", 0), r.get("other", 0)))
            else:
                lines.append(str(imp.text[:500]) if imp.text else "")
        except Exception:
            lines.append(str(imp.text[:500]) if imp.text else "")
        lines.append("RESULT: FAIL")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        print("FAIL: import failed", imp.status_code, imp.text[:200])
        sys.exit(1)

    body = imp.json()
    imported = body.get("importedCount", 0)
    total = body.get("total_rows_read", 0)
    skipped = body.get("skipped", 0)
    lines.append(f"supplier={ROMAX_EMAIL}")
    lines.append(f"total_rows_read={total}")
    lines.append(f"imported={imported}")
    lines.append(f"skipped={skipped}")
    reasons = body.get("skipped_reasons") or {}
    lines.append("breakdown: empty_name=%s price_parse_failed=%s price_le_zero=%s empty_or_invalid_unit=%s other=%s" % (
        reasons.get("empty_name", 0), reasons.get("price_parse_failed", 0),
        reasons.get("price_le_zero", 0), reasons.get("empty_or_invalid_unit", 0), reasons.get("other", 0)))

    from pymongo import MongoClient
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    romax_company = db.companies.find_one({"type": "supplier", "companyName": "Romax"}, {"_id": 0, "id": 1})
    if not romax_company:
        lines.append("FAIL: Romax company not found in DB")
        lines.append("RESULT: FAIL (Romax company not in DB)")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        sys.exit(1)
    sid = romax_company["id"]
    count = db.supplier_items.count_documents({"supplier_company_id": sid})
    lines.append(f"supplier_company_id={sid}")
    lines.append(f"price_list_items(Romax)={count}")

    if imported <= 0:
        lines.append("RESULT: FAIL (imported <= 0)")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        print("FAIL: no rows imported")
        sys.exit(1)
    if count <= 0:
        lines.append("RESULT: FAIL (price_list_items <= 0)")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        sys.exit(1)

    lines.append("")
    lines.append("RESULT: PASS")

    out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_PROOF.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print("PRICE_IMPORT_ROMAX_PROOF: PASS", "imported=", imported, "supplier_items=", count)


if __name__ == "__main__":
    main()
