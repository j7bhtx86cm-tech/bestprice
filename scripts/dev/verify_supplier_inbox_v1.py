#!/usr/bin/env python3
"""
Verify supplier inbox: count PENDING order_supplier_requests for Integrita and Romax.
Uses backend/.env (MONGO_URL, DB_NAME). Stdout: INBOX_VERIFY_OK integrita_pending=X romax_pending=Y
Exit 1 if both counts are 0.
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
        print("INBOX_VERIFY_FAIL: pymongo not installed")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("INBOX_VERIFY_FAIL: %s" % (str(e)[:80]))
        sys.exit(1)

    integrita = db.companies.find_one({"companyName": "Integrita"}, {"_id": 0, "id": 1})
    romax = db.companies.find_one({"companyName": "Romax"}, {"_id": 0, "id": 1})
    if not integrita:
        integrita = db.companies.find_one({"name": "Integrita"}, {"_id": 0, "id": 1})
    if not romax:
        romax = db.companies.find_one({"name": "Romax"}, {"_id": 0, "id": 1})

    integrita_id = (integrita or {}).get("id")
    romax_id = (romax or {}).get("id")

    pending_integrita = (
        db.order_supplier_requests.count_documents({"supplier_company_id": integrita_id, "status": "PENDING"})
        if integrita_id else 0
    )
    pending_romax = (
        db.order_supplier_requests.count_documents({"supplier_company_id": romax_id, "status": "PENDING"})
        if romax_id else 0
    )

    print("INBOX_VERIFY_OK integrita_pending=%s romax_pending=%s" % (pending_integrita, pending_romax))
    if pending_integrita == 0 and pending_romax == 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
