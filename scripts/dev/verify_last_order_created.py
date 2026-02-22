#!/usr/bin/env python3
"""
Verify last order created (orders + order_items + order_supplier_requests).
Uses backend/.env: MONGO_URL, DB_NAME.
Stdout: ORDER_VERIFY_OK order_id=... status=... items=... suppliers=...
        REQ <supplier_id>=<status> ...
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
    try:
        from pymongo import MongoClient
    except ImportError:
        print("ORDER_VERIFY_FAIL: pymongo not installed")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("ORDER_VERIFY_FAIL: %s" % (str(e)[:80]))
        sys.exit(1)

    order = db.orders.find_one(
        {},
        sort=[("created_at", -1)],
        projection={"id": 1, "status": 1, "customer_company_id": 1, "created_at": 1},
    )
    if not order:
        print("ORDER_VERIFY_OK order_id=(none) status=(no orders)")
        sys.exit(0)

    order_id = order.get("id", "")
    status = order.get("status", "")
    customer_company_id = order.get("customer_company_id", "") or "(empty)"
    created_at = order.get("created_at")
    created_str = str(created_at)[:19] if created_at else "None"

    items = list(db.order_items.find({"order_id": order_id}, {"id": 1}))
    items_count = len(items)

    reqs = list(
        db.order_supplier_requests.find(
            {"order_id": order_id},
            {"supplier_company_id": 1, "status": 1},
        )
    )
    suppliers_count = len(reqs)

    # Short supplier names for stdout (id prefix or company id)
    req_parts = []
    for r in reqs:
        sid = (r.get("supplier_company_id") or "")[:12]
        st = r.get("status", "?")
        req_parts.append("%s=%s" % (sid, st))

    print(
        "ORDER_VERIFY_OK order_id=%s status=%s customer_company_id=%s created_at=%s items=%s suppliers=%s"
        % (order_id, status, customer_company_id, created_str, items_count, suppliers_count)
    )
    if req_parts:
        print("REQ " + " ".join(req_parts))
    sys.exit(0)


if __name__ == "__main__":
    main()
