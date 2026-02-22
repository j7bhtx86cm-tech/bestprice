#!/usr/bin/env python3
"""
Smoke: Order → submit → supplier responses (Integrita partial, Romax full).
Uses backend/.env (MONGO_URL, DB_NAME). No secrets in stdout.
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
sys.path.insert(0, str(ROOT / "scripts"))
from _env import load_env
load_env()

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

sys.path.insert(0, str(ROOT / "backend"))
from bestprice_v12.orders_service import (
    ensure_indexes,
    create_order,
    add_order_item,
    submit_order,
    supplier_respond,
)


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("ORDER_SMOKE_FAIL: pymongo required")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("ORDER_SMOKE_FAIL: %s" % str(e)[:80])
        sys.exit(1)

    ensure_indexes(db)

    krevetochna = db.companies.find_one({"companyName": "Krevetochna", "type": "customer"}, {"_id": 0, "id": 1, "userId": 1})
    integrita = db.companies.find_one({"companyName": "Integrita", "type": "supplier"}, {"_id": 0, "id": 1})
    romax = db.companies.find_one({"companyName": "Romax", "type": "supplier"}, {"_id": 0, "id": 1})
    if not krevetochna:
        print("ORDER_SMOKE_FAIL: company Krevetochna (customer) not found")
        sys.exit(1)
    if not integrita:
        print("ORDER_SMOKE_FAIL: company Integrita (supplier) not found")
        sys.exit(1)
    if not romax:
        print("ORDER_SMOKE_FAIL: company Romax (supplier) not found")
        sys.exit(1)

    customer_id = krevetochna["id"]
    integrita_id = integrita["id"]
    romax_id = romax["id"]
    created_by = krevetochna.get("userId") or customer_id

    order = create_order(db, customer_id, created_by)
    order_id = order["id"]
    print("ORDER_SMOKE_OK order=%s" % order_id[:8])

    add_order_item(db, order_id, integrita_id, "Product A", 10, "шт")
    add_order_item(db, order_id, integrita_id, "Product B", 5, "кг")
    add_order_item(db, order_id, romax_id, "Product C", 2, "л")
    items = list(db.order_items.find({"order_id": order_id}, {"id": 1, "target_supplier_company_id": 1}))
    integrita_item_ids = [x["id"] for x in items if x["target_supplier_company_id"] == integrita_id]
    romax_item_ids = [x["id"] for x in items if x["target_supplier_company_id"] == romax_id]

    res_submit = submit_order(db, order_id, created_by)
    print("SUBMIT_OK suppliers=%s items=%s order_status=%s" % (
        res_submit["suppliers_count"], res_submit["items_count"], res_submit["order_status"]))

    # Integrita: confirm first item, reject second with OUT_OF_STOCK
    integrita_resp = supplier_respond(
        db, order_id, integrita_id, created_by, "CONFIRM",
        items=[
            {"item_id": integrita_item_ids[0], "decision": "CONFIRM"},
            {"item_id": integrita_item_ids[1], "decision": "REJECT", "reason_code": "OUT_OF_STOCK", "reason_text": "Нет в наличии"},
        ],
    )
    print("INTEGRITA_RESP_OK status=%s confirmed=%s rejected=%s updated=%s order_status=%s" % (
        integrita_resp["supplier_request_status"],
        integrita_resp["counts"]["confirmed"],
        integrita_resp["counts"]["rejected"],
        integrita_resp["counts"]["updated"],
        integrita_resp["order_status"],
    ))

    # Romax: confirm all (no items list)
    romax_resp = supplier_respond(db, order_id, romax_id, created_by, "CONFIRM", items=None)
    print("ROMAX_RESP_OK status=%s confirmed=%s rejected=%s updated=%s order_status=%s" % (
        romax_resp["supplier_request_status"],
        romax_resp["counts"]["confirmed"],
        romax_resp["counts"]["rejected"],
        romax_resp["counts"]["updated"],
        romax_resp["order_status"],
    ))

    order_after = db.orders.find_one({"id": order_id}, {"_id": 0, "status": 1})
    reqs = list(db.order_supplier_requests.find({"order_id": order_id}, {"_id": 0, "supplier_company_id": 1, "status": 1}))
    req_map = {}
    for r in reqs:
        sid = r["supplier_company_id"]
        name = "integrita" if sid == integrita_id else "romax" if sid == romax_id else sid[:8]
        req_map[name] = r["status"]
    print("FINAL_OK order_status=%s supplier_requests=%s" % (order_after["status"], req_map))
    sys.exit(0)


if __name__ == "__main__":
    main()
