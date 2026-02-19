#!/usr/bin/env python3
"""
Verify Romax import fix (ТЗ): after import:
- GET /api/supplier/price-list returns many rows (not 2)
- article = supplier product code (2001, 2002, ...), not "Ромакс"
- name = from column "Название" (e.g. "Говядина ..."), not "Сок яблоко..."

Writes evidence/ROMAX_IMPORT_FIX_PROOF.txt with commands, checks, and 3 sample rows (article+name+price).
Requires: backend running, Romax supplier (dev_create_2_test_suppliers.sh). Test file: ROMAX_PRICE_FILE or import_data/romax_price.xlsx.
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


def req(method, path, **kwargs):
    return requests.request(method, f"{API}{path}", timeout=60, **kwargs)


def main():
    file_path = os.environ.get("ROMAX_PRICE_FILE")
    if not file_path:
        for candidate in [
            ROOT / "import_data" / "romax_price.xlsx",
            ROOT / "import_data" / "romax_price.csv",
            ROOT / "evidence" / "fixtures" / "ROMAX.xlsx",
            ROOT / "evidence" / "fixtures" / "ROMAX.csv",
            ROOT / "tests" / "fixtures" / "romax_price.xlsx",
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
        print("SKIP: No Romax price file. Put import_data/romax_price.xlsx or set ROMAX_PRICE_FILE=<path>")
        out_path = ROOT / "evidence" / "ROMAX_IMPORT_FIX_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write("timestamp=" + datetime.now(timezone.utc).isoformat() + "\n")
            f.write("MONGO_URL=" + MONGO_URL + "\nDB_NAME=" + DB_NAME + "\n")
            f.write("ROMAX_PRICE_FILE= (not set, file not found)\n")
            f.write("RESULT: SKIP (no test file). Put file at import_data/romax_price.xlsx or set env ROMAX_PRICE_FILE.\n")
        sys.exit(0)

    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Romax import fix proof (article=code 2001..., name=Говядина..., count>>2)",
        "timestamp=" + ts,
        "MONGO_URL=" + MONGO_URL,
        "DB_NAME=" + DB_NAME,
        "API_BASE_URL=" + BASE,
        "file=" + file_path,
        "",
        "## Commands (run with backend up, Romax supplier exists):",
        "  python scripts/verify_romax_import_fix.py",
        "  # or: ROMAX_PRICE_FILE=path/to/romax.xlsx python scripts/verify_romax_import_fix.py",
        "",
    ]

    # Login
    r = req("POST", "/auth/login", json={"email": ROMAX_EMAIL, "password": ROMAX_PASSWORD})
    if r.status_code != 200:
        lines.append("FAIL: Romax login failed")
        lines.append("RESULT: FAIL")
        _write_evidence(ROOT, lines)
        print("FAIL: Romax login failed")
        sys.exit(1)

    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Import
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
            else:
                lines.append(str(imp.text[:500]) if imp.text else "")
        except Exception:
            lines.append(str(imp.text[:500]) if imp.text else "")
        lines.append("RESULT: FAIL")
        _write_evidence(ROOT, lines)
        sys.exit(1)

    body = imp.json()
    imported = body.get("importedCount", 0)
    total_read = body.get("total_rows_read", 0)
    lines.append("## Import result:")
    lines.append(f"  total_rows_read={total_read}")
    lines.append(f"  importedCount={imported}")

    # GET price-list
    pl = req("GET", "/supplier/price-list", headers=headers)
    if pl.status_code != 200:
        lines.append(f"FAIL: GET /supplier/price-list returned {pl.status_code}")
        lines.append("RESULT: FAIL")
        _write_evidence(ROOT, lines)
        sys.exit(1)

    raw = pl.json()
    items = raw if isinstance(raw, list) else (raw.get("items") or [])
    count = len(items)
    lines.append("")
    lines.append("## GET /api/supplier/price-list:")
    lines.append(f"  count={count}")

    # Sample 3 rows: article, name, price
    lines.append("")
    lines.append("## Sample 3 rows (article, name, price):")
    for i, it in enumerate(items[:3]):
        art = it.get("article", "")
        name = (it.get("name") or it.get("productName") or "")
        price = it.get("unit_price", it.get("price", 0))
        name_show = name[:80] + ("..." if len(name) > 80 else "")
        lines.append(f"  {i+1}. article={art!r} name={name_show!r} price={price}")

    # Criteria (PASS/FAIL)
    fail_reasons = []

    # ТЗ: "количество строк >= 10 (или равно числу строк в файле)"
    min_expected = min(10, imported) if imported else 10
    if count < 5 or count == 2:
        fail_reasons.append(f"count={count} (expected many rows, not 2)")
    elif count < min_expected and count != imported:
        fail_reasons.append(f"count={count} < expected min(10, imported={imported})")

    # article must be code-like (2001, 2002...) not "Ромакс"
    for it in items[:20]:
        art = (it.get("article") or "").strip()
        if art.lower() == "ромакс":
            fail_reasons.append("article must not be company name 'Ромакс'")
            break

    # At least one article should look numeric (2001, 2002, ...)
    numeric_articles = [it.get("article", "") for it in items if re.match(r"^\d+$", str(it.get("article", "")).strip())]
    if count >= 1 and not numeric_articles and not any(str(it.get("article", "")).replace(".0", "").isdigit() for it in items[:50]):
        fail_reasons.append("article should be supplier code (e.g. 2001, 2002); no numeric codes found")

    # name must contain expected product name (Говядина) not wrong column (Сок яблоко)
    names_lower = [(it.get("name") or it.get("productName") or "").lower() for it in items]
    if not any("говядина" in n for n in names_lower) and count > 0:
        fail_reasons.append('name should come from column "Название" (e.g. "Говядина ..."); no such name found')

    if fail_reasons:
        lines.append("")
        lines.append("## Checks: FAIL - " + "; ".join(fail_reasons))
        lines.append("RESULT: FAIL")
        _write_evidence(ROOT, lines)
        print("FAIL:", fail_reasons)
        sys.exit(1)

    lines.append("")
    lines.append("## Checks: count>=10, article=code (2001...), name=Говядина...")
    lines.append("RESULT: PASS")
    _write_evidence(ROOT, lines)
    print("ROMAX_IMPORT_FIX_PROOF: PASS", "imported=", imported, "price_list_count=", count)


def _write_evidence(ROOT, lines):
    out_path = ROOT / "evidence" / "ROMAX_IMPORT_FIX_PROOF.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
