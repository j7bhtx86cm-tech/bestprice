#!/usr/bin/env python3
"""Seed cart intents for the same customer used by checkout smoke. No checkout. Use before ui_checkout_click_proof_v1.js."""
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
    from pymongo import MongoClient
    client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
    client.admin.command("ping")
    db = client[DB_NAME]
    company = db.companies.find_one({"type": "customer"}, {"_id": 0, "userId": 1})
    if not company:
        user = db.users.find_one({"role": "customer"}, {"_id": 0, "id": 1})
        if not user:
            print("SEED_FAIL: no customer")
            sys.exit(1)
        user_id = user["id"]
    else:
        user_id = company.get("userId")
        if not user_id:
            print("SEED_FAIL: no userId")
            sys.exit(1)
    item = db.supplier_items.find_one(
        {"active": True, "price": {"$gt": 0}},
        {"_id": 0, "id": 1}
    )
    if not item:
        print("SEED_FAIL: no item")
        sys.exit(1)
    qty = max(1.0, 10000.0 / float(item.get("price") or 1))
    db.cart_intents.delete_many({"user_id": user_id})
    db.cart_intents.insert_one({"user_id": user_id, "supplier_item_id": item["id"], "qty": qty, "locked": False})
    print("SEED_OK user_id=%s" % user_id)

if __name__ == "__main__":
    main()
