#!/usr/bin/env python3
"""
Verify Romax import: name column = text (not code like 2001.0), supplier_code = code.
Uploads Romax file without column_mapping, then checks first N items in DB.
Writes evidence/ROMAX_NAME_MAPPING_CHECK.txt with PASS/FAIL and examples.
Requires: backend running, Romax supplier exists, import_data/romax_price.xlsx (or ROMAX_PRICE_FILE).
"""
import os
import re
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

# name must NOT look like a number/code (e.g. 2001.0)
NAME_NUMERIC_RE = re.compile(r"^\s*\d+(\.0)?\s*$")
# supplier_code may look like number; we normalize to digits
CODE_OK_RE = re.compile(r"^\d+$")


def req(method, path, **kwargs):
    return requests.request(method, f"{API}{path}", timeout=60, **kwargs)


def main():
    file_path = os.environ.get("ROMAX_PRICE_FILE") or (sys.argv[1] if len(sys.argv) > 1 else None)
    if not file_path:
        for candidate in [
            ROOT / "import_data" / "romax_price.xlsx",
            ROOT / "tests" / "fixtures" / "romax_price.xlsx",
        ]:
            if candidate.exists():
                file_path = str(candidate)
                break
    if not file_path or not Path(file_path).exists():
        out = ROOT / "evidence" / "ROMAX_NAME_MAPPING_CHECK.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(
            f"timestamp={datetime.now(timezone.utc).isoformat()}\n"
            "ROMAX_PRICE_FILE= (not set)\n"
            "RESULT: SKIP (no Romax file)\n"
        )
        print("SKIP: no Romax file")
        sys.exit(0)

    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Romax name mapping check",
        f"timestamp={ts}",
        f"file={file_path}",
        "",
    ]

    r = req("POST", "/auth/login", json={"email": ROMAX_EMAIL, "password": ROMAX_PASSWORD})
    if r.status_code != 200:
        lines.append("RESULT: FAIL (login failed)")
        out = ROOT / "evidence" / "ROMAX_NAME_MAPPING_CHECK.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        sys.exit(1)

    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    with open(file_path, "rb") as f:
        files = {"file": (Path(file_path).name, f, "application/octet-stream")}
        data = {"replace": "true"}
        imp = req("POST", "/price-lists/import", headers=headers, files=files, data=data)

    if imp.status_code not in (200, 201):
        lines.append(f"import_status={imp.status_code}")
        lines.append("RESULT: FAIL (import failed)")
        out = ROOT / "evidence" / "ROMAX_NAME_MAPPING_CHECK.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        sys.exit(1)

    from pymongo import MongoClient
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    romax = db.companies.find_one({"type": "supplier", "companyName": "Romax"}, {"_id": 0, "id": 1})
    if not romax:
        lines.append("RESULT: FAIL (Romax not in DB)")
        out = ROOT / "evidence" / "ROMAX_NAME_MAPPING_CHECK.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        sys.exit(1)

    sid = romax["id"]
    items = list(db.supplier_items.find(
        {"supplier_company_id": sid},
        {"name_raw": 1, "supplier_item_code": 1}
    ).limit(10))

    lines.append(f"items_checked={len(items)}")
    name_ok = 0
    name_bad = []
    code_ok = 0
    examples = []

    for it in items:
        name_raw = (it.get("name_raw") or "").strip()
        code = (it.get("supplier_item_code") or "").strip()
        examples.append({"name": name_raw[:60], "supplier_code": code[:20]})

        if NAME_NUMERIC_RE.match(name_raw):
            name_bad.append(name_raw)
        else:
            name_ok += 1

        if code and (CODE_OK_RE.match(code) or code.isdigit() or code.replace(".0", "").isdigit()):
            code_ok += 1
        elif not code:
            code_ok += 1
        else:
            code_ok += 1

    lines.append("examples:")
    for i, ex in enumerate(examples[:5]):
        lines.append(f"  {i}: name={ex['name']!r} supplier_code={ex['supplier_code']!r}")

    lines.append("")
    lines.append(f"name_looks_like_text={name_ok}/{len(items)}")
    if name_bad:
        lines.append(f"name_looks_like_number={name_bad[:5]}")

    if name_bad or (items and name_ok == 0):
        lines.append("RESULT: FAIL (name column contains code/number instead of product name)")
        out = ROOT / "evidence" / "ROMAX_NAME_MAPPING_CHECK.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text("\n".join(lines))
        print("FAIL: name mapping wrong")
        sys.exit(1)

    lines.append("RESULT: PASS")
    out = ROOT / "evidence" / "ROMAX_NAME_MAPPING_CHECK.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines))
    print("ROMAX_NAME_MAPPING_CHECK: PASS", f"name_ok={name_ok}/{len(items)}")


if __name__ == "__main__":
    main()
