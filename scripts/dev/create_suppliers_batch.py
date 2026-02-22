#!/usr/bin/env python3
"""
Create supplier users and companies for scaling. Idempotent (upsert): no duplicates.
Does not touch existing integrita / romax. Stdout: SUPPLIERS_BATCH_OK created_users=X created_companies=Y linked=Z
"""
import os
import sys
import uuid
from datetime import datetime, timezone
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

suppliers = [
    "supplier1@example.com",
    "supplier2@example.com",
    "supplier3@example.com",
    "supplier4@example.com",
    "supplier5@example.com",
    "supplier6@example.com",
    "supplier7@example.com",
]


def _hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("SUPPLIERS_BATCH_FAIL: pymongo required")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("SUPPLIERS_BATCH_FAIL: %s" % str(e)[:80])
        sys.exit(1)

    dev_password_hash = _hash_password("Supplier#2026")
    now = datetime.now(timezone.utc).isoformat()
    created_users = 0
    created_companies = 0
    linked = 0

    for email in suppliers:
        user = db.users.find_one({"email": email}, {"_id": 0, "id": 1, "companyId": 1})
        if not user:
            user_id = str(uuid.uuid4())
            db.users.insert_one({
                "id": user_id,
                "email": email,
                "passwordHash": dev_password_hash,
                "role": "supplier",
                "createdAt": now,
                "updatedAt": now,
            })
            created_users += 1
            user = {"id": user_id, "companyId": None}
        user_id = user["id"]
        company = db.companies.find_one({"userId": user_id}, {"_id": 0, "id": 1, "type": 1})
        if company:
            if company.get("type") != "supplier":
                continue
            company_id = company["id"]
        else:
            company_id = str(uuid.uuid4())
            db.companies.insert_one({
                "id": company_id,
                "type": "supplier",
                "userId": user_id,
                "inn": "0000000000",
                "ogrn": "0000000000000",
                "companyName": "Supplier " + (email.split("@")[0] or "supplier"),
                "legalAddress": "DEV",
                "actualAddress": "DEV",
                "phone": "+70000000000",
                "email": email,
                "contractAccepted": True,
                "createdAt": now,
                "updatedAt": now,
            })
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
            created_companies += 1
        if user.get("companyId") != company_id:
            db.users.update_one({"email": email}, {"$set": {"companyId": company_id, "updatedAt": now}})
            linked += 1

    print("SUPPLIERS_BATCH_OK created_users=%s created_companies=%s linked=%s" % (created_users, created_companies, linked))
    sys.exit(0)


if __name__ == "__main__":
    main()
