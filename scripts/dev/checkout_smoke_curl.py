#!/usr/bin/env python3
"""
Smoke: repeat UI flow — seed cart + plan snapshot → POST checkout.
Uses backend/.env for DB. No secrets in stdout.
Prints HTTP status and response JSON. Then runs verify_last_order_created.

Curl-equivalent (after plan_id and user_id are known from GET /api/v12/cart/plan):
  curl -s -X POST "http://127.0.0.1:8001/api/v12/cart/checkout?user_id=USER_ID" \\
    -H "Content-Type: application/json" \\
    -d '{"plan_id": "PLAN_ID", "delivery_address_id": null}'
"""
import hashlib
import json
import os
import sys
import subprocess
import uuid
from datetime import datetime, timezone, timedelta
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


def compute_cart_hash_from_intents(intents_list):
    """Same logic as plan_snapshot.compute_cart_hash: hash of supplier_item_id:qty:locked."""
    parts = []
    for i in sorted(intents_list, key=lambda x: (x.get("supplier_item_id") or "")):
        part = "%s:%s:%s" % (i.get("supplier_item_id", ""), i.get("qty", 0), i.get("locked", False))
        parts.append(part)
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:32]


def main():
    try:
        from pymongo import MongoClient
        import urllib.request
        import urllib.error
        import urllib.parse
    except ImportError as e:
        print("CHECKOUT_SMOKE_FAIL: %s" % str(e)[:80])
        sys.exit(1)

    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("CHECKOUT_SMOKE_FAIL: %s" % str(e)[:80])
        sys.exit(1)

    # Customer user and company
    company = db.companies.find_one({"type": "customer"}, {"_id": 0, "id": 1, "userId": 1})
    if not company:
        user = db.users.find_one({"role": "customer"}, {"_id": 0, "id": 1})
        if not user:
            print("CHECKOUT_SMOKE_FAIL: no customer user/company in DB")
            sys.exit(1)
        user_id = user["id"]
        cid = "smoke-cust-%s" % user_id[:8]
        db.companies.update_one(
            {"userId": user_id},
            {"$set": {"userId": user_id, "type": "customer", "companyName": "SmokeCustomer"}, "$setOnInsert": {"id": cid}},
            upsert=True,
        )
    else:
        user_id = company.get("userId")
        if not user_id:
            print("CHECKOUT_SMOKE_FAIL: customer company has no userId")
            sys.exit(1)

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

    def get_req(path):
        url = "%s%s" % (API, path)
        req_obj = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req_obj, timeout=15) as r:
                return r.status, json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            return e.code, (json.loads(e.read().decode()) if e.read() else {})

    # One supplier + item for plan
    item = db.supplier_items.find_one(
        {"active": True, "price": {"$gt": 0}},
        {"_id": 0, "id": 1, "supplier_company_id": 1, "name_raw": 1, "unit_type": 1, "price": 1},
    )
    if not item:
        print("CHECKOUT_SMOKE_FAIL: no active supplier_item in DB")
        sys.exit(1)
    supplier_id = item["supplier_company_id"]
    supplier_item_id = item["id"]
    comp = db.companies.find_one({"id": supplier_id}, {"_id": 0, "companyName": 1, "name": 1})
    supplier_name = (comp or {}).get("companyName") or (comp or {}).get("name") or "Supplier"
    min_order = (comp or {}).get("min_order_amount") if isinstance(comp, dict) else None
    min_order = float(min_order) if min_order is not None else 10000.0
    price = float(item.get("price") or 0)
    qty = max(1.0, (min_order / price) if price else 1.0)
    subtotal = price * qty

    # Seed intents so cart hash matches
    db.cart_intents.delete_many({"user_id": user_id})
    intent_doc = {"user_id": user_id, "supplier_item_id": supplier_item_id, "qty": qty, "locked": False}
    db.cart_intents.insert_one(intent_doc)
    cart_hash = compute_cart_hash_from_intents([intent_doc])

    # Prefer GET /cart/plan (same as UI), fallback to local plan
    plan_id = None
    status_get, plan_resp = get_req("/cart/plan?user_id=%s" % urllib.parse.quote(user_id))
    if status_get == 200 and (plan_resp or {}).get("plan_id"):
        plan_id = plan_resp["plan_id"]
        print("GET plan ok plan_id=%s" % plan_id)
    if not plan_id:
        plan_id = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=60)
        plan_payload = {
            "success": True,
            "suppliers": [
                {
                    "supplier_id": supplier_id,
                    "supplier_name": supplier_name,
                    "items": [
                        {
                            "product_name": item.get("name_raw") or "Smoke item",
                            "final_qty": qty,
                            "unit_type": item.get("unit_type") or "WEIGHT",
                            "supplier_item_id": supplier_item_id,
                            "price": price,
                        }
                    ],
                    "subtotal": subtotal,
                }
            ],
            "total": subtotal,
        }
        min_order_map = {supplier_id: min_order}
        db.cart_plans_v12.delete_many({"user_id": user_id})
        db.cart_plans_v12.insert_one({
            "plan_id": plan_id,
            "user_id": user_id,
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat(),
            "cart_hash": cart_hash,
            "min_order_map": min_order_map,
            "plan_payload": plan_payload,
        })

    # POST checkout (same as UI)
    print("CUSTOMER_USER_ID=%s PLAN_ID=%s" % (user_id, plan_id))
    status3, resp3 = req("POST", "/cart/checkout?user_id=%s" % user_id, {"plan_id": plan_id, "delivery_address_id": None})
    print("HTTP status: %s" % status3)
    print("response: %s" % json.dumps(resp3, ensure_ascii=False))
    if status3 != 200:
        print("CHECKOUT_SMOKE_FAIL: checkout status=%s" % status3)
        sys.exit(1)
    if (resp3 or {}).get("status") != "ok":
        print("CHECKOUT_SMOKE_FAIL: checkout body not ok: %s" % (resp3.get("message") or resp3))
        sys.exit(1)
    order_id = (resp3 or {}).get("order_id")
    order_status = (resp3 or {}).get("order_status", "")
    suppliers_count = (resp3 or {}).get("suppliers_count", 0)
    items_count = (resp3 or {}).get("items_count", 0)
    if order_id:
        print("CURL_OK order_id=%s order_status=%s suppliers_count=%s items_count=%s" % (order_id, order_status, suppliers_count, items_count))

    out = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dev" / "verify_last_order_created.py")],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if out.stdout:
        print(out.stdout.strip())
    if out.returncode != 0 and out.stderr:
        print(out.stderr.strip())
    print("CHECKOUT_SMOKE_OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
