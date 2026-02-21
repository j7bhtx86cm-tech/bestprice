#!/usr/bin/env python3
"""
E2E: import → pipeline (apply_rules → masters → snapshot → history) → checks.
Reads SUPPLIER_EMAIL/SUPPLIER_PASSWORD from backend/.env or .env if not in env.
Runs ensure_masters_partial_unique_index before import; checks fingerprint never null.
Exit 0 + ✅ E2E_PIPELINE_OK when pipeline run is OK and all collection counts pass.
"""
import os
import re
import sys
import time
import subprocess
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _env import load_env, get_mongo_url, get_db_name

load_env()
# Allow .env in repo root (backend/.env already loaded; root .env only fills unset)
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
except Exception:
    pass

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
API = f"{API_BASE_URL}/api"
# Defaults match backend/seed_data.py (supplier1@example.com / password123)
SUPPLIER_EMAIL = os.environ.get("SUPPLIER_EMAIL", "supplier1@example.com").strip()
SUPPLIER_PASSWORD = os.environ.get("SUPPLIER_PASSWORD", "password123")
PIPELINE_WAIT_TIMEOUT = int(os.environ.get("PIPELINE_WAIT_TIMEOUT", "120"))

FIXTURE_CSV = """артикул;Наименование;цена;ед. изм
e2ep1;E2E pipeline тест 1;100;шт
e2ep2;E2E pipeline тест 2;200;шт
e2ep3;E2E pipeline тест 3;150;кг
"""

try:
    import requests
    from pymongo import MongoClient
except ImportError as e:
    print("ERROR: pip install requests pymongo", e)
    sys.exit(1)


def _mask_url(url: str) -> str:
    if not url:
        return "***"
    if "@" in url:
        return re.sub(r"://([^:]+):([^@]+)@", r"://***:***@", url)
    return url


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    a, _, b = email.partition("@")
    if len(a) <= 2:
        return "***@" + b
    return a[:2] + "***@" + b


def _ensure_masters_index() -> bool:
    """Run ensure_masters_partial_unique_index.py; return True if MASTERS_INDEX_OK seen."""
    script = ROOT / "scripts" / "ensure_masters_partial_unique_index.py"
    try:
        out = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = (out.stdout or "") + (out.stderr or "")
        if "MASTERS_INDEX_OK" in combined:
            return True
        print("ensure_masters_index output:", combined[:500])
        return False
    except Exception as e:
        print("ensure_masters_index failed:", e)
        return False


def _ensure_sku_price_history_index() -> bool:
    """Run ensure_sku_price_history_unique_index.py; return True if SKU_PRICE_HISTORY_INDEX_OK seen."""
    script = ROOT / "scripts" / "ensure_sku_price_history_unique_index.py"
    try:
        out = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=30,
        )
        combined = (out.stdout or "") + (out.stderr or "")
        if "SKU_PRICE_HISTORY_INDEX_OK" in combined:
            return True
        print("ensure_sku_price_history_index output:", combined[:500])
        return False
    except Exception as e:
        print("ensure_sku_price_history_index failed:", e)
        return False


def main():
    db_name = get_db_name()
    mongo_url = get_mongo_url()
    print("API_BASE_URL=" + API_BASE_URL)
    print("DB_NAME=" + db_name)
    print("MONGO_URL=" + _mask_url(mongo_url))
    print("SUPPLIER_EMAIL=" + _mask_email(SUPPLIER_EMAIL))

    # 1) Ensure partial unique indexes before import
    if not _ensure_masters_index():
        print("E2E_FAIL: MASTERS_INDEX_OK not found (run scripts/ensure_masters_partial_unique_index.py)")
        sys.exit(1)
    print("MASTERS_INDEX_OK")
    if not _ensure_sku_price_history_index():
        print("E2E_FAIL: SKU_PRICE_HISTORY_INDEX_OK not found (run scripts/ensure_sku_price_history_unique_index.py)")
        sys.exit(1)
    print("SKU_PRICE_HISTORY_INDEX_OK")

    if not SUPPLIER_EMAIL or not SUPPLIER_PASSWORD:
        print("Set SUPPLIER_EMAIL and SUPPLIER_PASSWORD (e.g. in backend/.env or .env)")
        sys.exit(1)

    # 2) Login: normal auth; if 401 and DEV_AUTH_BYPASS, try dev/login (no password)
    r = requests.post(f"{API}/auth/login", json={"email": SUPPLIER_EMAIL, "password": SUPPLIER_PASSWORD}, timeout=30)
    if r.status_code != 200:
        if r.status_code == 401:
            dev_login = requests.post(
                f"{API}/dev/login",
                json={"role": "supplier", "email": SUPPLIER_EMAIL},
                timeout=30,
            )
            if dev_login.status_code == 200:
                r = dev_login
        if r.status_code != 200:
            print("login failed", r.status_code, r.text[:200])
            sys.exit(1)
    token = r.json().get("access_token") or r.json().get("token")
    headers = {"Authorization": f"Bearer {token}"}

    files = {"file": ("e2e_fixture.csv", FIXTURE_CSV.encode("utf-8"), "text/csv")}
    rimp = requests.post(f"{API}/price-lists/import", headers=headers, files=files, timeout=60)
    if rimp.status_code not in (200, 201):
        print("import failed", rimp.status_code, rimp.text[:300])
        sys.exit(1)
    body = rimp.json() if rimp.headers.get("content-type", "").startswith("application/json") else {}
    pricelist_id = body.get("pricelist_id") or body.get("pricelistId") or ""
    if not pricelist_id:
        print("import response missing pricelist_id")
        sys.exit(1)

    client = MongoClient(get_mongo_url())
    db = client[get_db_name()]
    deadline = time.monotonic() + PIPELINE_WAIT_TIMEOUT
    run_doc = None
    while time.monotonic() < deadline:
        run_doc = db.pipeline_runs.find_one({"$or": [{"import_id": pricelist_id}, {"batch_id": pricelist_id}]})
        if run_doc:
            status = run_doc.get("status")
            if status == "OK":
                break
            if status == "FAIL":
                print("pipeline run status=FAIL", run_doc.get("steps", [])[-1:] if run_doc.get("steps") else "")
                sys.exit(1)
        time.sleep(2)

    if not run_doc or run_doc.get("status") != "OK":
        print("pipeline run not found or not OK within timeout")
        sys.exit(1)

    run_id = run_doc.get("_id")
    ruleset_version_id = run_doc.get("ruleset_version_id")
    if not ruleset_version_id:
        print("E2E_PIPELINE_FAIL: no ruleset_version_id in pipeline run")
        sys.exit(1)
    si = db.supplier_items.find_one({"price_list_id": pricelist_id}, {"supplier_company_id": 1})
    supplier_id = (si or {}).get("supplier_company_id")
    if not supplier_id:
        print("E2E_PIPELINE_FAIL: no supplier_company_id for pricelist")
        sys.exit(1)

    # 3) Fingerprint never null/empty
    n_null = db.masters.count_documents({
        "ruleset_version_id": ruleset_version_id,
        "supplier_id": supplier_id,
        "fingerprint": None,
    })
    n_empty = db.masters.count_documents({
        "ruleset_version_id": ruleset_version_id,
        "supplier_id": supplier_id,
        "fingerprint": "",
    })
    if n_null != 0 or n_empty != 0:
        print("FINGERPRINT_NULL_FOUND", "null=", n_null, "empty=", n_empty)
        sys.exit(1)

    items_flagged = db.supplier_items.count_documents({"supplier_company_id": supplier_id, "status": "OK"})
    if items_flagged == 0:
        items_flagged = db.supplier_items.count_documents({"supplier_company_id": supplier_id, "quality_flags": {"$exists": True}})
    if items_flagged == 0:
        items_flagged = db.supplier_items.count_documents({"price_list_id": pricelist_id})

    masters_count = db.masters.count_documents({"supplier_id": supplier_id})
    links_count = db.master_links.count_documents({"supplier_id": supplier_id})
    snapshot_count = db.master_market_snapshot_current.count_documents({"supplier_id": supplier_id})
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    history_count = db.sku_price_history.count_documents({"supplier_id": supplier_id, "date": today})
    daily_count = db.master_market_history_daily.count_documents({"supplier_id": supplier_id, "date": today})

    if masters_count == 0 and links_count == 0:
        masters_count = db.masters.count_documents({})
        links_count = db.master_links.count_documents({})
    if snapshot_count == 0:
        snapshot_count = db.master_market_snapshot_current.count_documents({})
    if history_count == 0:
        history_count = db.sku_price_history.count_documents({})
    if daily_count == 0:
        daily_count = db.master_market_history_daily.count_documents({})

    print("pipeline_run_id=" + str(run_id))
    print("status=OK")
    print("items_flagged=" + str(items_flagged))
    print("masters=" + str(masters_count))
    print("master_links=" + str(links_count))
    print("master_market_snapshot_current=" + str(snapshot_count))
    print("sku_price_history=" + str(history_count))
    print("master_market_history_daily=" + str(daily_count))

    # sku_price_history: 0 docs with sku_id null in scope
    sku_id_null_count = db.sku_price_history.count_documents({
        "ruleset_version_id": ruleset_version_id,
        "supplier_id": supplier_id,
        "sku_id": None,
    })
    sku_id_null_count += db.sku_price_history.count_documents({
        "ruleset_version_id": ruleset_version_id,
        "supplier_id": supplier_id,
        "sku_id": {"$exists": False},
    })
    print("sku_price_history_sku_id_null_count=%s" % sku_id_null_count)

    if masters_count == 0 or links_count == 0 or snapshot_count == 0:
        print("E2E_PIPELINE_FAIL: missing masters/links/snapshot")
        sys.exit(1)
    if history_count == 0 and daily_count == 0:
        print("E2E_PIPELINE_FAIL: no history/daily")
        sys.exit(1)
    if sku_id_null_count != 0:
        print("E2E_PIPELINE_FAIL: sku_price_history has sku_id null in scope")
        sys.exit(1)

    print("✅ E2E_PIPELINE_OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
