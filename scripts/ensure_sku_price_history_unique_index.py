#!/usr/bin/env python3
"""
Migration: ensure sku_price_history has partial unique index on (ruleset_version_id, sku_id, date).
1) Delete docs that violate: sku_id is null/missing, or ruleset_version_id not ObjectId.
2) Drop old unique index (e.g. ruleset_version_id_1_sku_id_1_date_1) if exists.
3) Create partial unique index: only when sku_id exists and is string, ruleset_version_id is objectId.
Output: SKU_PRICE_HISTORY_INDEX_OK
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _env import load_env, get_mongo_url, get_db_name

load_env()

try:
    from pymongo import MongoClient
    from pymongo import ASCENDING
except ImportError:
    print("pip install pymongo")
    sys.exit(1)

COLL = "sku_price_history"
OLD_INDEX_NAME = "ruleset_version_id_1_sku_id_1_date_1"
NEW_INDEX_NAME = "ruleset_version_id_1_sku_id_1_date_1_partial"


def main():
    client = MongoClient(get_mongo_url())
    db = client[get_db_name()]
    coll = db[COLL]

    # 1) Delete broken: sku_id null or missing
    del_null = coll.delete_many({"sku_id": None})
    del_missing = coll.delete_many({"sku_id": {"$exists": False}})
    # Delete: ruleset_version_id stored as string (e.g. "v1")
    del_str_rv = coll.delete_many({"ruleset_version_id": {"$type": "string"}})
    if del_null.deleted_count or del_missing.deleted_count or del_str_rv.deleted_count:
        print("cleaned sku_price_history: sku_id null=%s missing=%s ruleset_version_id string=%s" % (
            del_null.deleted_count, del_missing.deleted_count, del_str_rv.deleted_count))

    # 2) Drop old index if exists
    try:
        for idx in coll.list_indexes():
            if idx.get("name") == OLD_INDEX_NAME:
                coll.drop_index(OLD_INDEX_NAME)
                print("dropped %s" % OLD_INDEX_NAME)
                break
    except Exception as e:
        print("drop index (may not exist):", e)

    # 3) Partial unique index: sku_id exists and is string; ruleset_version_id is objectId
    partial_filter = {
        "sku_id": {"$exists": True, "$type": "string"},
        "ruleset_version_id": {"$type": "objectId"},
    }
    index_spec = [
        ("ruleset_version_id", ASCENDING),
        ("sku_id", ASCENDING),
        ("date", ASCENDING),
    ]
    coll.create_index(
        index_spec,
        unique=True,
        partialFilterExpression=partial_filter,
        name=NEW_INDEX_NAME,
    )
    print("created partial unique index: name=%s partialFilterExpression=%s" % (NEW_INDEX_NAME, partial_filter))
    print("SKU_PRICE_HISTORY_INDEX_OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
