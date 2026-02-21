#!/usr/bin/env python3
"""
Clean to baseline: only Integrita + Romax (suppliers) and gmfuel (customer).
Remove supplier1-7 and all extra suppliers; clear catalog (pricelists, supplier_items, pipeline, etc.).
Do not touch: rulesets, ruleset_versions, category_dictionary_entries, token_aliases, global_quality_rules, category_rules.
Stdout: CLEAN_SUPPLIERS_OK ... CATALOG_CLEAN_OK BASELINE_COUNTS ...
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

KEEP_SUPPLIER_EMAILS = [
    "integrita.supplier@example.com",
    "romax.supplier@example.com",
]
KEEP_ALL_BASELINE_EMAILS = KEEP_SUPPLIER_EMAILS + ["gmfuel@gmail.com"]  # 1 customer (restaurant)


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("CLEAN_SUPPLIERS_FAIL: pymongo required")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("CLEAN_SUPPLIERS_FAIL: %s" % str(e)[:80])
        sys.exit(1)

    # --- Part 1: leave only Integrita and Romax suppliers ---
    supplier_users = list(db.users.find({"role": "supplier"}, {"_id": 0, "id": 1, "email": 1}))
    to_keep_ids = {u["id"] for u in supplier_users if u.get("email") in KEEP_SUPPLIER_EMAILS}
    to_delete_users = [u for u in supplier_users if u.get("email") not in KEEP_SUPPLIER_EMAILS]
    to_delete_user_ids = {u["id"] for u in to_delete_users}

    removed_company_ids = []
    for c in db.companies.find({"type": "supplier"}, {"_id": 0, "id": 1, "userId": 1}):
        if c.get("userId") in to_delete_user_ids:
            removed_company_ids.append(c["id"])

    deleted_links = 0
    if removed_company_ids:
        r = db.supplier_settings.delete_many({"supplierCompanyId": {"$in": removed_company_ids}})
        deleted_links += r.deleted_count
        r = db.supplier_restaurant_settings.delete_many({"supplierId": {"$in": removed_company_ids}})
        deleted_links += r.deleted_count

    r_companies = db.companies.delete_many({"type": "supplier", "id": {"$in": removed_company_ids}})
    deleted_companies = r_companies.deleted_count

    r_users = db.users.delete_many({"role": "supplier", "email": {"$nin": KEEP_SUPPLIER_EMAILS}})
    deleted_users = r_users.deleted_count

    # Also remove any other users/companies not in baseline (so we end up with exactly 3 users, 3 companies)
    keep_user_ids = {u["id"] for u in db.users.find({"email": {"$in": KEEP_ALL_BASELINE_EMAILS}}, {"_id": 0, "id": 1})}
    r_extra_users = db.users.delete_many({"email": {"$nin": KEEP_ALL_BASELINE_EMAILS}})
    deleted_users += r_extra_users.deleted_count
    r_extra_companies = db.companies.delete_many({"userId": {"$nin": list(keep_user_ids)}})
    deleted_companies += r_extra_companies.deleted_count

    print("CLEAN_SUPPLIERS_OK deleted_users=%s deleted_companies=%s deleted_links=%s" % (
        deleted_users, deleted_companies, deleted_links))

    # --- Part 2: clean catalog (do not touch rules*) ---
    db.pricelists.delete_many({})
    db.supplier_items.delete_many({})
    db.pipeline_runs.delete_many({})
    db.master_market_snapshot_current.delete_many({})
    db.sku_price_history.delete_many({})
    db.master_market_history_daily.delete_many({})
    print("CATALOG_CLEAN_OK")

    # --- Part 3: baseline counts ---
    n_users = db.users.count_documents({})
    n_companies = db.companies.count_documents({})
    n_pricelists = db.pricelists.count_documents({})
    n_supplier_items = db.supplier_items.count_documents({})
    n_pipeline_runs = db.pipeline_runs.count_documents({})
    print("BASELINE_COUNTS users=%s companies=%s pricelists=%s supplier_items=%s pipeline_runs=%s" % (
        n_users, n_companies, n_pricelists, n_supplier_items, n_pipeline_runs))
    sys.exit(0)


if __name__ == "__main__":
    main()
