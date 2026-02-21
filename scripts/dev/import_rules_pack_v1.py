#!/usr/bin/env python3
"""
Import Rules Pack v1: docs/rules_pack/RULES_PACK_v1.xlsx → DB (idempotent upsert).
Reads MONGO_URL, DB_NAME from backend/.env. Uses active ruleset_version_id.
"""
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
PACK_PATH = ROOT / "docs" / "rules_pack" / "RULES_PACK_v1.xlsx"


def _get_db():
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
        return client[DB_NAME]
    except Exception:
        return None


def _get_active_ruleset_version_id(db):
    rv = db.ruleset_versions.find_one({"is_active": True}) if "ruleset_versions" in db.list_collection_names() else None
    if rv is not None:
        return rv["_id"]
    if "rulesets" in db.list_collection_names():
        rs = db.rulesets.find_one({})
        if rs is not None:
            return rs.get("ruleset_version_id") or rs.get("active_version_id")
    return None


def main():
    if not PACK_PATH.is_file():
        print("RULES_PACK_IMPORT_FAIL: file not found path=%s" % PACK_PATH)
        return
    db = _get_db()
    if db is None:
        print("RULES_PACK_IMPORT_FAIL: cannot connect to Mongo")
        return
    rv_id = _get_active_ruleset_version_id(db)
    if rv_id is None:
        print("RULES_PACK_IMPORT_FAIL: no active ruleset version")
        return

    try:
        import pandas as pd
    except ImportError:
        print("RULES_PACK_IMPORT_FAIL: pandas required")
        return

    from datetime import datetime, timezone
    now = datetime.now(timezone.utc)

    upsert_global = 0
    upsert_dict = 0
    upsert_token = 0
    upsert_category = 0

    # Sheet A: GLOBAL_QUALITY_RULES — upsert by (ruleset_version_id, rule_code)
    df_a = pd.read_excel(PACK_PATH, sheet_name="GLOBAL_QUALITY_RULES")
    if "global_quality_rules" not in db.list_collection_names():
        db.create_collection("global_quality_rules")
    for _, row in df_a.iterrows():
        rule_code = str(row.get("rule_code", "")).strip()
        if not rule_code:
            continue
        payload_json = row.get("payload_json", "")
        payload = None
        if isinstance(payload_json, str) and payload_json.strip():
            try:
                payload = json.loads(payload_json)
            except Exception:
                payload = {}
        doc = {
            "ruleset_version_id": rv_id,
            "rule_code": rule_code,
            "rule_type": str(row.get("rule_type", "")),
            "severity": str(row.get("severity", "")),
            "payload": payload,
            "updated_at": now,
        }
        if "enabled" in row and pd.notna(row["enabled"]):
            doc["enabled"] = bool(row["enabled"])
        if "description" in row and pd.notna(row["description"]):
            doc["description"] = str(row["description"])
        if "source" in row and pd.notna(row["source"]):
            doc["source"] = str(row["source"])
        db.global_quality_rules.update_one(
            {"ruleset_version_id": rv_id, "rule_code": rule_code},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        upsert_global += 1

    # Sheet B: CATEGORY_RULES — upsert by (ruleset_version_id, category_code, attribute_code) or (ruleset_version_id, category_code, rule_code)
    if "CATEGORY_RULES" in pd.ExcelFile(PACK_PATH).sheet_names:
        df_b = pd.read_excel(PACK_PATH, sheet_name="CATEGORY_RULES")
        cname = "category_rules"
        if cname not in db.list_collection_names():
            db.create_collection(cname)
        for _, row in df_b.iterrows():
            cat = str(row.get("category_code", "")).strip()
            if not cat:
                continue
            attr = str(row.get("attribute_code", "")).strip()
            cond_json = row.get("condition_json", "")
            cond = None
            if isinstance(cond_json, str) and cond_json.strip():
                try:
                    cond = json.loads(cond_json)
                except Exception:
                    pass
            doc = {
                "ruleset_version_id": rv_id,
                "category_code": cat,
                "attribute_code": attr,
                "must_mode": str(row.get("must_mode", "SOFT")),
                "condition": cond,
                "rule_code": str(row.get("rule_code", "")),
                "enabled": bool(row.get("enabled", True)),
                "severity": str(row.get("severity", "")),
                "updated_at": now,
            }
            filter_q = {"ruleset_version_id": rv_id, "category_code": cat, "attribute_code": attr}
            db[cname].update_one(filter_q, {"$set": doc, "$setOnInsert": {"created_at": now}}, upsert=True)
            upsert_category += 1

    # Sheet C: CATEGORY_DICTIONARY — upsert by (ruleset_version_id, category_code, keyword, type)
    df_c = pd.read_excel(PACK_PATH, sheet_name="CATEGORY_DICTIONARY")
    if "category_dictionary_entries" not in db.list_collection_names():
        db.create_collection("category_dictionary_entries")
    for _, row in df_c.iterrows():
        cat = str(row.get("category_code", "")).strip()
        keyword = str(row.get("keyword", "")).strip()
        typ = str(row.get("type", "include")).strip()
        if not keyword:
            continue
        doc = {
            "ruleset_version_id": rv_id,
            "category_code": cat,
            "keyword": keyword,
            "type": typ,
            "weight": float(row.get("weight", 1)) if pd.notna(row.get("weight")) else 1,
            "scope": str(row.get("scope", "category")),
            "enabled": bool(row.get("enabled", True)),
            "comment": str(row.get("notes", "")),
            "updated_at": now,
        }
        db.category_dictionary_entries.update_one(
            {"ruleset_version_id": rv_id, "category_code": cat, "keyword": keyword, "type": typ},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        upsert_dict += 1

    # Sheet D: TOKEN_ALIASES — upsert by (ruleset_version_id, field, raw)
    df_d = pd.read_excel(PACK_PATH, sheet_name="TOKEN_ALIASES")
    if "token_aliases" not in db.list_collection_names():
        db.create_collection("token_aliases")
    for _, row in df_d.iterrows():
        field = str(row.get("field", "")).strip()
        raw = str(row.get("raw", "")).strip()
        if not raw:
            continue
        doc = {
            "ruleset_version_id": rv_id,
            "field": field or "name_raw",
            "raw": raw,
            "canonical": str(row.get("canonical", "")),
            "enabled": bool(row.get("enabled", True)),
            "comment": str(row.get("notes", "")),
            "updated_at": now,
        }
        db.token_aliases.update_one(
            {"ruleset_version_id": rv_id, "field": doc["field"], "raw": raw},
            {"$set": doc, "$setOnInsert": {"created_at": now}},
            upsert=True,
        )
        upsert_token += 1

    print("RULES_PACK_IMPORT_OK")
    print("UPSERT global_quality_rules=%s category_dictionary=%s token_aliases=%s category_rules=%s" % (upsert_global, upsert_dict, upsert_token, upsert_category))


if __name__ == "__main__":
    main()
