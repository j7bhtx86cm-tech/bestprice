#!/usr/bin/env python3
"""
Verify order flow v1: counts, indexes, sample docs. Asserts unique and composite indexes.
Uses backend/.env. No secrets. Stdout <=25 lines, ends with VERIFY_ORDER_FLOW_OK.
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


def _index_keys(info):
    """Return list of index key names only (compact)."""
    return list(info.keys())


def _has_index_with_key(info, key_spec):
    """key_spec = [('order_id', 1), ('supplier_company_id', 1)]. Check if any index has this key."""
    key_list = list(key_spec)
    for name, spec in info.items():
        if spec.get("key") == key_list:
            return True
    return False


def _has_unique_index(info, key_spec):
    for name, spec in info.items():
        if spec.get("key") == list(key_spec) and spec.get("unique"):
            return True
    return False


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("VERIFY_FAIL: pymongo required")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("VERIFY_FAIL: %s" % str(e)[:60])
        sys.exit(1)

    co = db.orders.count_documents({})
    ci = db.order_items.count_documents({})
    cr = db.order_supplier_requests.count_documents({})
    print("counts orders=%s order_items=%s order_supplier_requests=%s" % (co, ci, cr))

    io = db.orders.index_information()
    ii = db.order_items.index_information()
    ir = db.order_supplier_requests.index_information()
    print("indexes orders=%s" % _index_keys(io))
    print("indexes order_items=%s" % _index_keys(ii))
    print("indexes order_supplier_requests=%s" % _index_keys(ir))

    # Sample from last created valid order (created_at set, customer_company_id non-empty)
    candidates = list(db.orders.find(
        {"created_at": {"$exists": True, "$ne": None}, "customer_company_id": {"$exists": True, "$nin": [None, ""]}}
    ).sort("created_at", -1).limit(1))
    so = candidates[0] if candidates else None
    if not so:
        print("VERIFY_FAIL: NO_VALID_ORDER_SAMPLE")
        sys.exit(1)
    sample_order_id = so["id"]
    print("sample order order_id=%s customer_company_id=%s status=%s created_at=%s" % (
        (sample_order_id or "")[:8], (so.get("customer_company_id") or "")[:8], so.get("status"), so.get("created_at")))
    si = db.order_items.find_one({"order_id": sample_order_id}, {"id": 1, "order_id": 1, "target_supplier_company_id": 1, "status": 1, "qty": 1})
    if si:
        print("sample item id=%s order_id=%s target_supplier_company_id=%s status=%s qty=%s" % (
            (si.get("id") or "")[:8], (si.get("order_id") or "")[:8], (si.get("target_supplier_company_id") or "")[:8],
            si.get("status"), si.get("qty")))
    else:
        print("sample item (none for this order)")
    sr = db.order_supplier_requests.find_one({"order_id": sample_order_id}, {"order_id": 1, "supplier_company_id": 1, "status": 1, "submitted_at": 1, "responded_at": 1})
    if sr:
        print("sample request order_id=%s supplier_company_id=%s status=%s submitted_at=%s responded_at=%s" % (
            (sr.get("order_id") or "")[:8], (sr.get("supplier_company_id") or "")[:8], sr.get("status"),
            sr.get("submitted_at"), sr.get("responded_at")))
    else:
        print("sample request (none for this order)")

    if not _has_unique_index(ir, [("order_id", 1), ("supplier_company_id", 1)]):
        print("VERIFY_FAIL: unique index (order_id, supplier_company_id) missing on order_supplier_requests")
        sys.exit(1)
    if not _has_index_with_key(ii, [("order_id", 1), ("target_supplier_company_id", 1)]):
        print("VERIFY_FAIL: composite index (order_id, target_supplier_company_id) missing on order_items")
        sys.exit(1)

    print("VERIFY_ORDER_FLOW_OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
