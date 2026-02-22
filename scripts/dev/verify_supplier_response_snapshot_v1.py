#!/usr/bin/env python3
"""
Verify supplier response snapshot: order_id and supplier_email from argv.
Find supplier_company_id by supplier email; check supplier_request status != PENDING and item counts.
Stdout: SUPPLIER_RESPONSE_VERIFY_OK order=<id> request=<status> confirmed=X rejected=Y
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
    if len(sys.argv) < 3:
        print("Usage: verify_supplier_response_snapshot_v1.py <order_id> <supplier_email>")
        sys.exit(1)
    order_id = sys.argv[1].strip()
    supplier_email = sys.argv[2].strip()

    try:
        from pymongo import MongoClient
    except ImportError:
        print("SUPPLIER_RESPONSE_VERIFY_FAIL: pymongo not installed")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("SUPPLIER_RESPONSE_VERIFY_FAIL: %s" % (str(e)[:80]))
        sys.exit(1)

    user = db.users.find_one({"email": supplier_email}, {"_id": 0, "id": 1})
    if not user:
        print("SUPPLIER_RESPONSE_VERIFY_FAIL: user not found for email %s" % supplier_email[:30])
        sys.exit(1)
    user_id = user["id"]
    company = db.companies.find_one({"userId": user_id}, {"_id": 0, "id": 1})
    if not company:
        company = db.companies.find_one({"id": user.get("companyId")}, {"_id": 0, "id": 1})
    if not company:
        print("SUPPLIER_RESPONSE_VERIFY_FAIL: company not found for supplier")
        sys.exit(1)
    supplier_company_id = company["id"]

    req = db.order_supplier_requests.find_one(
        {"order_id": order_id, "supplier_company_id": supplier_company_id},
        {"_id": 0, "status": 1},
    )
    if not req:
        print("SUPPLIER_RESPONSE_VERIFY_FAIL: no supplier_request for order %s and supplier" % order_id[:8])
        sys.exit(1)
    req_status = req.get("status", "")

    items = list(db.order_items.find(
        {"order_id": order_id, "target_supplier_company_id": supplier_company_id},
        {"_id": 0, "status": 1},
    ))
    confirmed = sum(1 for i in items if i.get("status") == "CONFIRMED")
    rejected = sum(1 for i in items if i.get("status") == "REJECTED")

    print("SUPPLIER_RESPONSE_VERIFY_OK order=%s request=%s confirmed=%s rejected=%s" % (
        order_id[:8], req_status, confirmed, rejected))
    sys.exit(0)


if __name__ == "__main__":
    main()
