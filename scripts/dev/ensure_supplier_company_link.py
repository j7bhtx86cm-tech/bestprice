#!/usr/bin/env python3
"""
Ensure supplier user has a company (type=supplier) linked by userId.
TARGET_EMAIL from env, default same as E2E (supplier1@example.com).
Stdout: SUPPLIER_COMPANY_LINK_OK email=<masked> company_id=<id> or SUPPLIER_COMPANY_LINK_FAIL: <reason>.
"""
import os
import re
import sys
import uuid
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass
sys.path.insert(0, str(ROOT / "scripts"))
from _env import load_env, get_mongo_url, get_db_name
load_env()

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
TARGET_EMAIL = os.environ.get("TARGET_EMAIL", os.environ.get("SUPPLIER_EMAIL", "supplier1@example.com")).strip()


def _mask_email(email: str) -> str:
    if not email or "@" not in email:
        return "***"
    a, _, b = email.partition("@")
    return (a[:2] + "***@" + b) if len(a) > 2 else "***@" + b


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("SUPPLIER_COMPANY_LINK_FAIL: pymongo required")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("SUPPLIER_COMPANY_LINK_FAIL: %s" % str(e)[:80])
        sys.exit(1)
    user = db.users.find_one({"email": TARGET_EMAIL}, {"_id": 0, "id": 1, "role": 1})
    if not user:
        print("SUPPLIER_COMPANY_LINK_FAIL: user not found email=%s" % _mask_email(TARGET_EMAIL))
        sys.exit(1)
    user_id = user["id"]
    company = db.companies.find_one({"userId": user_id}, {"_id": 0, "id": 1, "type": 1})
    if company:
        if company.get("type") != "supplier":
            print("SUPPLIER_COMPANY_LINK_FAIL: company type is not supplier")
            sys.exit(1)
        print("SUPPLIER_COMPANY_LINK_OK email=%s company_id=%s" % (_mask_email(TARGET_EMAIL), company["id"]))
        sys.exit(0)
    company_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    company_doc = {
        "id": company_id,
        "type": "supplier",
        "userId": user_id,
        "inn": "0000000000",
        "ogrn": "0000000000000",
        "companyName": "E2E Supplier " + (TARGET_EMAIL.split("@")[0] or "supplier"),
        "legalAddress": "DEV",
        "actualAddress": "DEV",
        "phone": "+70000000000",
        "email": TARGET_EMAIL,
        "contractAccepted": True,
        "createdAt": now,
        "updatedAt": now,
    }
    db.companies.insert_one(company_doc)
    db.supplier_settings.insert_one({
        "id": str(uuid.uuid4()),
        "supplierCompanyId": company_id,
        "minOrderAmount": 0,
        "deliveryDays": [],
        "deliveryTime": "",
        "orderReceiveDeadline": "",
        "logisticsType": "own",
        "updatedAt": now,
    })
    print("SUPPLIER_COMPANY_LINK_OK email=%s company_id=%s" % (_mask_email(TARGET_EMAIL), company_id))
    sys.exit(0)


if __name__ == "__main__":
    main()
