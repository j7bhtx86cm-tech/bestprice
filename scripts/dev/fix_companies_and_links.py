#!/usr/bin/env python3
"""Fix companies and links: ensure 3 users exist, remove gmfile, clear companies, create 3 companies (Integrita, Romax, Krevetochna), link users via userId, clear pricelists/supplier_items."""
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

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

REQUIRED_EMAILS = [
    "integrita.supplier@example.com",
    "romax.supplier@example.com",
    "gmfuel@gmail.com",
]

# (email, company_display_name, type)
COMPANY_SPECS = [
    ("integrita.supplier@example.com", "Integrita", "supplier"),
    ("romax.supplier@example.com", "Romax", "supplier"),
    ("gmfuel@gmail.com", "Krevetochna", "customer"),
]


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("FIX_FAIL: pymongo not installed")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("FIX_FAIL: %s" % (str(e)[:80]))
        sys.exit(1)

    users_coll = db.users
    companies_coll = db.companies

    for email in REQUIRED_EMAILS:
        u = users_coll.find_one({"email": email}, {"_id": 0, "id": 1})
        if u is None:
            print("FIX_FAIL: MISSING_USER %s" % email)
            sys.exit(1)

    deleted_gmfile = 0
    r = users_coll.delete_one({"email": "gmfile@gmail.com"})
    if r.deleted_count:
        deleted_gmfile = 1

    companies_coll.delete_many({})

    cleared_pricelists = db.pricelists.count_documents({})
    cleared_supplier_items = db.supplier_items.count_documents({})
    db.pricelists.delete_many({})
    db.supplier_items.delete_many({})

    now = datetime.now(timezone.utc)
    now_iso = now.isoformat()
    company_ids = {}

    for email, company_name, ctype in COMPANY_SPECS:
        user = users_coll.find_one({"email": email}, {"_id": 0, "id": 1})
        user_id = user["id"]
        company_id = str(uuid.uuid4())
        company_ids[email] = company_id
        doc = {
            "id": company_id,
            "type": ctype,
            "userId": user_id,
            "inn": "7700000000",
            "ogrn": "1027700000000",
            "companyName": company_name,
            "legalAddress": "",
            "actualAddress": "",
            "phone": "+79000000000",
            "email": email,
            "contactPersonName": "",
            "contactPersonPosition": "",
            "contactPersonPhone": "",
            "contractAccepted": True,
            "created_at": now,
            "updated_at": now,
            "createdAt": now_iso,
            "updatedAt": now_iso,
        }
        if ctype == "customer":
            doc["deliveryAddresses"] = []
        companies_coll.insert_one(doc)

        if ctype == "supplier":
            settings = db.supplier_settings.find_one({"supplierCompanyId": company_id})
            if not settings:
                db.supplier_settings.insert_one({
                    "id": str(uuid.uuid4()),
                    "supplierCompanyId": company_id,
                    "minOrderAmount": 0,
                    "updatedAt": now_iso,
                })

    n_companies = companies_coll.count_documents({})
    n_users = users_coll.count_documents({})
    n_pl = db.pricelists.count_documents({})
    n_si = db.supplier_items.count_documents({})

    links_ok = True
    for email in REQUIRED_EMAILS:
        u = users_coll.find_one({"email": email}, {"_id": 0, "id": 1})
        c = companies_coll.find_one({"userId": u["id"]}, {"_id": 0, "id": 1, "companyName": 1})
        if not c:
            links_ok = False
            break

    print("FIX_OK db=%s companies=3 deleted_gmfile=%s cleared_pricelists=%s cleared_supplier_items=%s" % (
        DB_NAME, deleted_gmfile, cleared_pricelists, cleared_supplier_items))
    if links_ok:
        print("LINKS_OK integrita=OK romax=OK gmfuel=OK")
    else:
        print("LINKS_OK integrita=FAIL romax=FAIL gmfuel=FAIL")
    print("COUNTS companies=%s users=%s pricelists=%s supplier_items=%s" % (n_companies, n_users, n_pl, n_si))
    sys.exit(0)


if __name__ == "__main__":
    main()
