#!/usr/bin/env python3
"""
Smoke: create PENDING order via HTTP checkout, then GET supplier detail and POST respond CUSTOM.
Uses backend/.env. Stdout: SUPPLIER_DETAIL_OK items=<n> request_status=PENDING
         SUPPLIER_RESPOND_OK request_status=<...> order_status=<...> confirmed=<n> rejected=<n>
"""
import json
import os
import re
import sys
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
BASE = os.environ.get("CHECKOUT_SMOKE_BASE", "http://127.0.0.1:8001")
API = "%s/api/v12" % BASE.rstrip("/")


def run_checkout_get_order_id():
    """Run checkout_smoke_curl.py and parse order_id from its stdout."""
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dev" / "checkout_smoke_curl.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if out.returncode != 0:
        print("SUPPLIER_RESPOND_SMOKE_FAIL: checkout failed: %s" % (out.stderr or out.stdout)[:200])
        sys.exit(1)
    match = re.search(r'"order_id":\s*"([^"]+)"', out.stdout)
    if not match:
        match = re.search(r"order_id=([a-f0-9-]{36})", out.stdout)
    if not match:
        print("SUPPLIER_RESPOND_SMOKE_FAIL: no order_id in checkout output")
        sys.exit(1)
    return match.group(1)


def main():
    try:
        from pymongo import MongoClient
        import urllib.request
        import urllib.error
    except ImportError as e:
        print("SUPPLIER_RESPOND_SMOKE_FAIL: %s" % str(e)[:80])
        sys.exit(1)

    order_id = run_checkout_get_order_id()

    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("SUPPLIER_RESPOND_SMOKE_FAIL: %s" % str(e)[:80])
        sys.exit(1)

    req_doc = db.order_supplier_requests.find_one({"order_id": order_id, "status": "PENDING"}, {"_id": 0, "supplier_company_id": 1})
    if not req_doc:
        print("SUPPLIER_RESPOND_SMOKE_FAIL: no PENDING supplier request for order %s" % order_id[:8])
        sys.exit(1)
    supplier_company_id = req_doc["supplier_company_id"]
    company = db.companies.find_one({"id": supplier_company_id}, {"_id": 0, "userId": 1})
    supplier_user_id = (company or {}).get("userId")
    if not supplier_user_id:
        print("SUPPLIER_RESPOND_SMOKE_FAIL: company %s has no userId" % supplier_company_id[:8])
        sys.exit(1)
    supplier_user = db.users.find_one({"id": supplier_user_id}, {"_id": 0, "email": 1})
    supplier_email = (supplier_user or {}).get("email") or ""

    def req(method, path, body=None):
        url = "%s%s" % (API, path)
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req_obj = urllib.request.Request(url, data=data, method=method)
        req_obj.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req_obj, timeout=15) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, (json.loads(e.read().decode()) if e.read() else {})

    status, detail = req("GET", "/supplier/orders/%s?user_id=%s" % (order_id, supplier_user_id))
    if status != 200 or (detail or {}).get("status") != "ok":
        print("SUPPLIER_RESPOND_SMOKE_FAIL: GET detail status=%s resp=%s" % (status, detail))
        sys.exit(1)
    items = detail.get("items") or []
    req_status = (detail.get("request") or {}).get("status", "PENDING")
    print("SUPPLIER_DETAIL_OK items=%s request_status=%s" % (len(items), req_status))

    if len(items) >= 2:
        payload = {
            "decision": "CUSTOM",
            "comment": None,
            "items": [
                {"item_id": items[0]["id"], "decision": "CONFIRM"},
                {"item_id": items[1]["id"], "decision": "REJECT", "reason_code": "OUT_OF_STOCK", "reason_text": "Нет в наличии"},
            ],
        }
    elif len(items) == 1:
        payload = {
            "decision": "CUSTOM",
            "comment": None,
            "items": [
                {"item_id": items[0]["id"], "decision": "REJECT", "reason_code": "OUT_OF_STOCK", "reason_text": "Нет в наличии"},
            ],
        }
    else:
        print("SUPPLIER_RESPOND_SMOKE_FAIL: no items for supplier in order")
        sys.exit(1)

    status2, resp = req("POST", "/supplier/orders/%s/respond?user_id=%s" % (order_id, supplier_user_id), payload)
    if status2 != 200 or (resp or {}).get("status") != "ok":
        print("SUPPLIER_RESPOND_SMOKE_FAIL: POST respond status=%s resp=%s" % (status2, resp))
        sys.exit(1)
    print("SUPPLIER_RESPOND_OK request_status=%s order_status=%s confirmed=%s rejected=%s updated=%s" % (
        resp.get("request_status", ""),
        resp.get("order_status", ""),
        resp.get("confirmed", 0),
        resp.get("rejected", 0),
        resp.get("updated", 0),
    ))
    print("ORDER_ID=%s SUPPLIER_USER_ID=%s SUPPLIER_EMAIL=%s" % (order_id, supplier_user_id, supplier_email))
    print("SUPPLIER_RESPOND_SMOKE_OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
