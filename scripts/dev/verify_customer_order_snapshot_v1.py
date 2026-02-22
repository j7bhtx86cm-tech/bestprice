#!/usr/bin/env python3
"""
Verify customer order snapshot: order_id from argv.
Check order has customer_company_id, supplier_requests count >=1, items count >=1.
Stdout: CUSTOMER_ORDER_VERIFY_OK order=<id> order_status=<...> suppliers=<n> pending=<n> confirmed=<n> partially=<n> rejected=<n> items=<n>
"""
import os
import sys
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


def main():
    if len(sys.argv) < 2:
        print("Usage: verify_customer_order_snapshot_v1.py <order_id>")
        sys.exit(1)
    order_id = sys.argv[1].strip()

    try:
        from pymongo import MongoClient
    except ImportError:
        print("CUSTOMER_ORDER_VERIFY_FAIL: pymongo not installed")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("CUSTOMER_ORDER_VERIFY_FAIL: %s" % (str(e)[:80]))
        sys.exit(1)

    order = db.orders.find_one({"id": order_id}, {"_id": 0, "customer_company_id": 1, "status": 1})
    if not order:
        print("CUSTOMER_ORDER_VERIFY_FAIL: order not found")
        sys.exit(1)
    if not (order.get("customer_company_id") or "").strip():
        print("CUSTOMER_ORDER_VERIFY_FAIL: customer_company_id empty")
        sys.exit(1)

    reqs = list(db.order_supplier_requests.find({"order_id": order_id}, {"_id": 0, "status": 1}))
    if len(reqs) < 1:
        print("CUSTOMER_ORDER_VERIFY_FAIL: no supplier_requests")
        sys.exit(1)
    pending = sum(1 for r in reqs if r.get("status") == "PENDING")
    confirmed = sum(1 for r in reqs if r.get("status") == "CONFIRMED")
    partially = sum(1 for r in reqs if r.get("status") == "PARTIALLY_CONFIRMED")
    rejected = sum(1 for r in reqs if r.get("status") == "REJECTED")

    items_count = db.order_items.count_documents({"order_id": order_id})
    if items_count < 1:
        print("CUSTOMER_ORDER_VERIFY_FAIL: no items")
        sys.exit(1)

    rejected_items_count = 0
    items_coll = list(db.order_items.find({"order_id": order_id}, {"_id": 0, "status": 1, "supplier_decision": 1}))
    for it in items_coll:
        if it.get("status") == "REJECTED":
            rejected_items_count += 1
            dec = it.get("supplier_decision") or {}
            if not (dec.get("reason_text") or "").strip():
                print("CUSTOMER_ORDER_VERIFY_FAIL: REJECTED item has empty reason_text")
                sys.exit(1)

    print("CUSTOMER_ORDER_VERIFY_OK order=%s status=%s suppliers=%s items=%s rejected=%s" % (
        order_id[:8],
        order.get("status", ""),
        len(reqs),
        items_count,
        rejected_items_count,
    ))
    sys.exit(0)


if __name__ == "__main__":
    main()
