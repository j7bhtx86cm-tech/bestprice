#!/usr/bin/env python3
"""
Smoke: create order via HTTP checkout, then customer list/detail (before), supplier respond, customer detail (after).
Stdout: CUSTOMER_LIST_OK total>=1, CUSTOMER_DETAIL_BEFORE_OK, SUPPLIER_RESP_OK, CUSTOMER_DETAIL_AFTER_OK, CUSTOMER_FLOW_SMOKE_OK.
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
    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dev" / "checkout_smoke_curl.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=60,
    )
    if out.returncode != 0:
        print("CUSTOMER_FLOW_SMOKE_FAIL: checkout failed")
        sys.exit(1)
    match = re.search(r'"order_id":\s*"([^"]+)"', out.stdout) or re.search(r"order_id=([a-f0-9-]{36})", out.stdout)
    if not match:
        print("CUSTOMER_FLOW_SMOKE_FAIL: no order_id")
        sys.exit(1)
    return match.group(1)


def main():
    try:
        from pymongo import MongoClient
        import urllib.request
        import urllib.error
    except ImportError as e:
        print("CUSTOMER_FLOW_SMOKE_FAIL: %s" % str(e)[:80])
        sys.exit(1)

    order_id = run_checkout_get_order_id()

    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("CUSTOMER_FLOW_SMOKE_FAIL: %s" % str(e)[:80])
        sys.exit(1)

    customer_user = db.users.find_one({"email": "gmfuel@gmail.com"}, {"_id": 0, "id": 1})
    if not customer_user:
        customer_user = db.users.find_one({"email": re.compile("gmfuel|gmfile", re.I)}, {"_id": 0, "id": 1})
    if not customer_user:
        company = db.companies.find_one({"type": "customer"}, {"_id": 0, "userId": 1})
        customer_user = {"id": company["userId"]} if company and company.get("userId") else None
    if not customer_user:
        print("CUSTOMER_FLOW_SMOKE_FAIL: customer user (gmfuel) not found")
        sys.exit(1)
    customer_user_id = customer_user["id"]

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

    status_list, list_resp = req("GET", "/customer/orders?user_id=%s&status=ANY&limit=50" % customer_user_id)
    if status_list != 200 or (list_resp or {}).get("status") != "ok":
        print("CUSTOMER_FLOW_SMOKE_FAIL: list status=%s" % status_list)
        sys.exit(1)
    total = list_resp.get("total", 0)
    order_ids_in_list = [x.get("order_id") for x in (list_resp.get("items") or [])]
    has_order = 1 if order_id in order_ids_in_list else 0
    print("CUSTOMER_LIST_OK total=%s has_order=%s" % (total, has_order))
    if total < 1:
        print("CUSTOMER_FLOW_SMOKE_FAIL: no orders for customer")
        sys.exit(1)

    status_before, detail_before = req("GET", "/customer/orders/%s?user_id=%s" % (order_id, customer_user_id))
    if status_before != 200 or (detail_before or {}).get("status") != "ok":
        print("CUSTOMER_FLOW_SMOKE_FAIL: detail before status=%s" % status_before)
        sys.exit(1)
    suppliers_before = detail_before.get("suppliers") or []
    items_before = sum(len(b.get("items") or []) for b in (detail_before.get("items_by_supplier") or []))
    print("CUSTOMER_DETAIL_BEFORE_OK order=%s suppliers=%s items=%s" % (order_id[:8], len(suppliers_before), items_before))

    req_doc = db.order_supplier_requests.find_one({"order_id": order_id, "status": "PENDING"}, {"_id": 0, "supplier_company_id": 1})
    if not req_doc:
        print("CUSTOMER_FLOW_SMOKE_FAIL: no PENDING supplier request")
        sys.exit(1)
    company = db.companies.find_one({"id": req_doc["supplier_company_id"]}, {"_id": 0, "userId": 1})
    supplier_user_id = (company or {}).get("userId")
    if not supplier_user_id:
        print("CUSTOMER_FLOW_SMOKE_FAIL: supplier has no userId")
        sys.exit(1)

    items = list(db.order_items.find({"order_id": order_id, "target_supplier_company_id": req_doc["supplier_company_id"]}, {"_id": 0, "id": 1}))
    if not items:
        print("CUSTOMER_FLOW_SMOKE_FAIL: no items for supplier")
        sys.exit(1)
    payload = {
        "decision": "CUSTOM",
        "comment": None,
        "items": [{"item_id": items[0]["id"], "decision": "REJECT", "reason_code": "OUT_OF_STOCK", "reason_text": "Нет в наличии"}],
    }
    status_resp, resp_body = req("POST", "/supplier/orders/%s/respond?user_id=%s" % (order_id, supplier_user_id), payload)
    if status_resp != 200 or (resp_body or {}).get("status") != "ok":
        print("CUSTOMER_FLOW_SMOKE_FAIL: supplier respond status=%s" % status_resp)
        sys.exit(1)
    print("SUPPLIER_RESP_OK request_status=%s order_status=%s rejected=%s" % (
        resp_body.get("request_status", ""),
        resp_body.get("order_status", ""),
        resp_body.get("rejected", 0),
    ))

    status_after, detail_after = req("GET", "/customer/orders/%s?user_id=%s" % (order_id, customer_user_id))
    if status_after != 200 or (detail_after or {}).get("status") != "ok":
        print("CUSTOMER_FLOW_SMOKE_FAIL: detail after status=%s" % status_after)
        sys.exit(1)
    order_status_after = (detail_after.get("order") or {}).get("status", "")
    rejected_items = 0
    reason_present = 0
    for block in detail_after.get("items_by_supplier") or []:
        for it in block.get("items") or []:
            if it.get("status") == "REJECTED":
                rejected_items += 1
                if (it.get("reason_text") or "").strip():
                    reason_present = 1
    print("CUSTOMER_DETAIL_AFTER_OK order=%s status=%s rejected_items=%s reason_present=%s" % (
        order_id[:8], order_status_after, rejected_items, reason_present,
    ))

    print("ORDER_ID=%s" % order_id)
    print("CUSTOMER_FLOW_SMOKE_OK order=%s GMFUEL_USER_ID=%s" % (order_id[:8], customer_user_id))
    sys.exit(0)


if __name__ == "__main__":
    main()
