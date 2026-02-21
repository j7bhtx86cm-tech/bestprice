#!/usr/bin/env python3
"""Check rulesets/ruleset_versions counts and sample structure. No secrets in stdout."""
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
EXPECTED_RULES = 25


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("RULESETS rulesets=0 ruleset_versions=0")
        print("ASSERT_25_RULES=UNKNOWN expected=%s got=no_pymongo" % EXPECTED_RULES)
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("RULESETS rulesets=0 ruleset_versions=0")
        print("ASSERT_25_RULES=UNKNOWN expected=%s error=%s" % (EXPECTED_RULES, str(e)[:60]))
        sys.exit(1)

    n_rulesets = db.rulesets.count_documents({}) if "rulesets" in db.list_collection_names() else 0
    n_versions = db.ruleset_versions.count_documents({}) if "ruleset_versions" in db.list_collection_names() else 0
    print("RULESETS rulesets=%s ruleset_versions=%s" % (n_rulesets, n_versions))

    rules_len = None
    sample_keys = []
    name = version = "-"

    for coll_name in ("rulesets", "ruleset_versions"):
        if coll_name not in db.list_collection_names():
            continue
        coll = db[coll_name]
        doc = coll.find_one({})
        if not doc:
            continue
        keys = [k for k in doc.keys() if not k.startswith("_") and "pass" not in k.lower() and "hash" not in k.lower() and "token" not in k.lower()]
        sample_keys = keys[:15]
        name = doc.get("name") or doc.get("version_name") or doc.get("id") or "-"
        version = doc.get("version") or doc.get("version_name") or doc.get("_id") or "-"
        for field in ("rules", "items", "rules_list", "rules_registry", "rule_codes"):
            val = doc.get(field)
            if val is not None and isinstance(val, list):
                rules_len = len(val)
                break
        if rules_len is not None:
            break
        if isinstance(doc.get("params_json"), str):
            pass
        doc_id = doc.get("_id") or doc.get("id")
        break

    if rules_len is None and "ruleset_versions" in db.list_collection_names():
        import json
        for rv in db.ruleset_versions.find({}):
            p = rv.get("params_json")
            if p is None:
                continue
            if isinstance(p, str):
                try:
                    p = json.loads(p)
                except Exception:
                    continue
            if isinstance(p, dict) and "rules" in p and isinstance(p["rules"], list):
                rules_len = len(p["rules"])
                sample_keys = list(rv.keys())
                name = rv.get("version_name") or "-"
                version = str(rv.get("_id") or rv.get("id") or "-")
                break
            if isinstance(p, list):
                rules_len = len(p)
                sample_keys = list(rv.keys())
                name = rv.get("version_name") or "-"
                version = str(rv.get("_id") or "-")
                break
    if rules_len is None and (n_rulesets > 0 or n_versions > 0):
        rv = db.ruleset_versions.find_one({"is_active": True}) if "ruleset_versions" in db.list_collection_names() else None
        if rv:
            rv_id = rv.get("_id")
            rs = db.rulesets.find_one({"ruleset_version_id": rv_id}) if "rulesets" in db.list_collection_names() else None
            if not rs:
                rs = db.rulesets.find_one({}) if "rulesets" in db.list_collection_names() else None
            if rs:
                for field in ("rules", "items", "rules_list", "rules_registry"):
                    val = rs.get(field)
                    if val is not None and isinstance(val, list):
                        rules_len = len(val)
                        sample_keys = [k for k in rs.keys() if not k.startswith("_")]
                        name = rs.get("name") or rs.get("version_name") or "-"
                        version = str(rs.get("_id") or rs.get("ruleset_version_id") or "-")
                        break

    print("RULESET_SAMPLE keys=%s name=%s version=%s rules_len=%s" % (
        ",".join(sample_keys) if sample_keys else "-",
        name,
        version,
        rules_len if rules_len is not None else "N/A",
    ))

    if rules_len is not None:
        if rules_len == EXPECTED_RULES:
            print("ASSERT_25_RULES=OK expected=%s got=%s" % (EXPECTED_RULES, rules_len))
        else:
            print("ASSERT_25_RULES=FAIL expected=%s got=%s" % (EXPECTED_RULES, rules_len))
    else:
        print("ASSERT_25_RULES=UNKNOWN expected=%s got=no_array_field" % EXPECTED_RULES)
    sys.exit(0)


if __name__ == "__main__":
    main()
