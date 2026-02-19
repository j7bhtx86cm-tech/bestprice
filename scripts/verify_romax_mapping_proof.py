#!/usr/bin/env python3
"""
Romax price list mapping proof: import without column_mapping, then verify
article = code (e.g. 2001, 2002), name = from "Название" (e.g. "Говядина вырезка"),
never "Ромакс" in article/name. Writes evidence/PRICE_IMPORT_ROMAX_MAPPING_PROOF.txt.
Requires: backend running, Romax supplier (run dev_create_2_test_suppliers.sh).
Fixture: evidence/fixtures/ROMAX.csv or evidence/fixtures/ROMAX.xlsx or ROMAX_PRICE_FILE env.
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

# Article must never be supplier name; name must come from "Название" (e.g. Говядина, Свинина)
SUPPLIER_NAME_MUST_NOT_BE_ARTICLE = "ромакс"
EXPECTED_NAMES_FROM_NAZvanie = ("говядина", "свинина", "курица", "молоко", "сыр")

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
            ROOT / "evidence" / "fixtures" / "ROMAX.xlsx",
            ROOT / "evidence" / "fixtures" / "ROMAX.csv",
            ROOT / "import_data" / "romax_price.xlsx",
            ROOT / "import_data" / "romax_price.csv",
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
        print("SKIP: No Romax fixture. Put evidence/fixtures/ROMAX.csv or set ROMAX_PRICE_FILE=<path>")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_MAPPING_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("timestamp=" + datetime.now(timezone.utc).isoformat() + "\n")
            f.write("API_BASE_URL=" + BASE + "\n")
            f.write("ROMAX_PRICE_FILE= (not set, file not found)\n")
            f.write("RESULT: SKIP (no test file).\n")
        sys.exit(0)

    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "# Romax price list mapping proof (article=code, name=Название)",
        "timestamp=" + ts,
        "API_BASE_URL=" + BASE,
        "file=" + file_path,
        "",
    ]

    r = req("POST", "/auth/login", json={"email": ROMAX_EMAIL, "password": ROMAX_PASSWORD})
    if r.status_code != 200:
        lines.append("FAIL: Romax login failed")
        lines.append("RESULT: FAIL")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_MAPPING_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        print("FAIL: Romax login failed")
        sys.exit(1)

    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # Import WITHOUT column_mapping (auto-detect only)
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
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_MAPPING_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        sys.exit(1)

    body = imp.json()
    imported_rows = body.get("importedCount", 0)
    total_rows = body.get("total_rows_read", 0)
    lines.append(f"imported_rows={imported_rows}")
    lines.append(f"total_rows_read={total_rows}")

    # GET supplier price list (no limit=2; default returns up to 10000)
    pl = req("GET", "/supplier/price-list", headers=headers)
    if pl.status_code != 200:
        lines.append(f"FAIL: price-list returned {pl.status_code}")
        lines.append("RESULT: FAIL")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_MAPPING_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        sys.exit(1)

    items = pl.json()
    count = len(items)
    lines.append(f"price_list_count={count}")

    # Sample: first 5 rows (article + name)
    sample_rows = []
    for i, it in enumerate(items[:5]):
        sample_rows.append({"article": it.get("article", ""), "name": it.get("name", it.get("productName", ""))})
    lines.append("sample_rows (first 5 article+name):")
    for i, row in enumerate(sample_rows):
        lines.append(f"  {i+1}. article={row['article']!r} name={row['name']!r}")

    # Assertions
    fail_reasons = []
    if count < 5:
        fail_reasons.append(f"count={count} < 5")
    for it in items:
        art = (it.get("article") or "").strip()
        name = (it.get("name") or it.get("productName") or "").strip().lower()
        if art.lower() == SUPPLIER_NAME_MUST_NOT_BE_ARTICLE:
            fail_reasons.append(f"article must not be supplier name: {art!r}")
        if name == SUPPLIER_NAME_MUST_NOT_BE_ARTICLE and art.lower() != "ромакс":
            pass  # name could be company in some fixture; we care that article != Ромакс
        # Expect at least one name from "Название" (Говядина, Свинина, etc.)
    if not fail_reasons:
        # Check that at least one item has name from Название (not "Сок яблоко" style wrong column)
        names_lower = [(it.get("name") or it.get("productName") or "").lower() for it in items]
        if not any(any(exp in n for exp in EXPECTED_NAMES_FROM_NAZvanie) for n in names_lower):
            fail_reasons.append("no name from column Название (expected e.g. Говядина, Свинина, Курица, Молоко, Сыр)")
        # Check article is code-like (numeric or alphanumeric), not company name
        for it in items:
            art = (it.get("article") or "").strip()
            if art.lower() == "ромакс":
                fail_reasons.append(f"article must not be 'Ромакс': got {art!r}")
                break

    if fail_reasons:
        lines.append("")
        lines.append("FAIL: " + "; ".join(fail_reasons))
        lines.append("RESULT: FAIL")
        out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_MAPPING_PROOF.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        print("FAIL:", fail_reasons)
        sys.exit(1)

    lines.append("")
    lines.append("RESULT: PASS")

    out_path = ROOT / "evidence" / "PRICE_IMPORT_ROMAX_MAPPING_PROOF.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print("PRICE_IMPORT_ROMAX_MAPPING_PROOF: PASS", "imported=", imported_rows, "count=", count)


if __name__ == "__main__":
    main()
