#!/usr/bin/env python3
"""
Migration: ensure sku_price_history has partial unique index on (ruleset_version_id, sku_id, date).
1) Delete only broken docs: sku_id missing/null, sku_id not ObjectId, ruleset_version_id not ObjectId.
2) Drop old unique index (e.g. ruleset_version_id_1_sku_id_1_date_1*) if exists.
3) Create partial unique index with partialFilterExpression: sku_id and ruleset_version_id are objectId.
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
NEW_INDEX_NAME = "ruleset_version_id_1_sku_id_1_date_1_partial"


def main():
    client = MongoClient(get_mongo_url())
    db = client[get_db_name()]
    coll = db[COLL]

    # 1) Delete only broken: sku_id or ruleset_version_id not ObjectId (covers null/missing/string etc.)
    del_sku = coll.delete_many({"sku_id": {"$not": {"$type": "objectId"}}})
    del_rv = coll.delete_many({"ruleset_version_id": {"$not": {"$type": "objectId"}}})
    if del_sku.deleted_count or del_rv.deleted_count:
        print("cleaned sku_price_history: sku_id_not_objectId=%s ruleset_version_id_not_objectId=%s" % (
            del_sku.deleted_count, del_rv.deleted_count))

    # 2) Drop any existing index on (ruleset_version_id, sku_id, date) so we can recreate with new partial filter
    try:
        for idx in list(coll.list_indexes()):
            name = idx.get("name")
            key_pattern = list((idx.get("key") or {}).keys())
            if name and set(key_pattern) >= {"ruleset_version_id", "sku_id", "date"}:
                coll.drop_index(name)
                print("dropped %s" % name)
    except Exception as e:
        print("drop index (may not exist):", e)

    # 3) Partial unique index: sku_id and ruleset_version_id must be objectId
    partial_filter = {
        "sku_id": {"$type": "objectId"},
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
