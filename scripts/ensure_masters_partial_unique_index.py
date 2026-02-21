#!/usr/bin/env python3
"""
One-time: ensure masters has partial unique index on (ruleset_version_id, fingerprint)
so that null fingerprint does not break uniqueness.
Drops index ruleset_version_id_1_fingerprint_1 if exists, creates partial unique index.
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

def main():
    client = MongoClient(get_mongo_url())
    db = client[get_db_name()]
    coll = db.masters
    try:
        for idx in coll.list_indexes():
            if idx.get("name") == "ruleset_version_id_1_fingerprint_1":
                coll.drop_index("ruleset_version_id_1_fingerprint_1")
                print("dropped ruleset_version_id_1_fingerprint_1")
                break
    except Exception as e:
        print("drop index (may not exist):", e)
    coll.create_index(
        [("ruleset_version_id", ASCENDING), ("fingerprint", ASCENDING)],
        unique=True,
        partialFilterExpression={"fingerprint": {"$type": "string"}},
        name="ruleset_version_id_1_fingerprint_1_partial",
    )
    print("created partial unique index ruleset_version_id_1_fingerprint_1_partial")
    print("MASTERS_INDEX_OK")
    sys.exit(0)

if __name__ == "__main__":
    main()
