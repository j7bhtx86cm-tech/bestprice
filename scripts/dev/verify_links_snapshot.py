#!/usr/bin/env python3
"""Verify user↔company links: print table, then VERIFY_OK if companies=3, all 3 linked, gmfile absent."""
import os
import sys
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


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("VERIFY_FAIL: pymongo not installed")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("VERIFY_FAIL: %s" % (str(e)[:80]))
        sys.exit(1)

    n_companies = db.companies.count_documents({})
    gmfile = db.users.find_one({"email": "gmfile@gmail.com"}, {"_id": 1})

    print("email | role | company_id | company_name | company_type")
    print("-" * 60)
    all_linked = True
    for email in REQUIRED_EMAILS:
        u = db.users.find_one({"email": email}, {"_id": 0, "id": 1, "role": 1})
        if not u:
            print("%s | MISSING | - | - | -" % email)
            all_linked = False
            continue
        c = db.companies.find_one({"userId": u["id"]}, {"_id": 0, "id": 1, "companyName": 1, "type": 1})
        if not c:
            print("%s | %s | - | - | -" % (email, u.get("role", "")))
            all_linked = False
        else:
            print("%s | %s | %s | %s | %s" % (email, u.get("role", ""), c["id"], c.get("companyName", ""), c.get("type", "")))
    print("")
    if n_companies == 3 and all_linked and gmfile is None:
        print("VERIFY_OK")
        sys.exit(0)
    print("VERIFY_FAIL companies=%s all_linked=%s gmfile_absent=%s" % (n_companies, all_linked, gmfile is None))
    sys.exit(1)


if __name__ == "__main__":
    main()
