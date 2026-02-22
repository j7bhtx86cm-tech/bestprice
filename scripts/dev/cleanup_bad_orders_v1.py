#!/usr/bin/env python3
"""
Remove orders where created_at is None or customer_company_id is empty; cascade delete order_items and order_supplier_requests.
Uses backend/.env. Stdout: CLEAN_BAD_ORDERS_OK deleted_orders=X deleted_items=Y deleted_requests=Z
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass
sys.path.insert(0, str(ROOT / "scripts"))
from _env import load_env
load_env()

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("CLEAN_BAD_ORDERS_FAIL: pymongo required")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("CLEAN_BAD_ORDERS_FAIL: %s" % str(e)[:60])
        sys.exit(1)

    bad = list(db.orders.find({
        "$or": [
            {"created_at": None},
            {"created_at": {"$exists": False}},
            {"customer_company_id": ""},
            {"customer_company_id": {"$exists": False}},
        ]
    }, {"_id": 0, "id": 1}))
    bad_ids = [o["id"] for o in bad if o.get("id")]

    deleted_items = 0
    deleted_requests = 0
    for oid in bad_ids:
        ri = db.order_items.delete_many({"order_id": oid})
        rr = db.order_supplier_requests.delete_many({"order_id": oid})
        deleted_items += ri.deleted_count
        deleted_requests += rr.deleted_count
    ro = db.orders.delete_many({"id": {"$in": bad_ids}})
    deleted_orders = ro.deleted_count

    print("CLEAN_BAD_ORDERS_OK deleted_orders=%s deleted_items=%s deleted_requests=%s" % (deleted_orders, deleted_items, deleted_requests))
    sys.exit(0)


if __name__ == "__main__":
    main()
