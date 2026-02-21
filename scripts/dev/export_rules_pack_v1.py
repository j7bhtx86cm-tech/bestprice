#!/usr/bin/env python3
"""
Export Rules Pack v1: DB → docs/rules_pack/RULES_PACK_v1.xlsx.
Reads MONGO_URL, DB_NAME from backend/.env. Creates 4 sheets.
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
OUT_PATH = ROOT / "docs" / "rules_pack" / "RULES_PACK_v1.xlsx"


def _get_db():
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
        return client[DB_NAME]
    except Exception:
        return None


def main():
    db = _get_db()
    if db is None:
        print("RULES_PACK_EXPORT_FAIL: cannot connect to Mongo")
        return
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    try:
        import pandas as pd
    except ImportError:
        print("RULES_PACK_EXPORT_FAIL: pandas required")
        return

    n_global = 0
    n_category_dict = 0
    n_token = 0
    n_category_rules = 0

    # Sheet A: GLOBAL_QUALITY_RULES
    rows_a = []
    if "global_quality_rules" in db.list_collection_names():
        for doc in db.global_quality_rules.find({}):
            payload = doc.get("payload")
            payload_json = json.dumps(payload) if payload is not None else ""
            rows_a.append({
                "rule_code": doc.get("rule_code", ""),
                "rule_type": doc.get("rule_type", ""),
                "severity": doc.get("severity", ""),
                "enabled": bool(doc.get("enabled", True)),
                "description": doc.get("description", ""),
                "payload_json": payload_json,
                "source": doc.get("source", "exported_from_db"),
                "notes": doc.get("notes", ""),
            })
            n_global += 1
    df_a = pd.DataFrame(rows_a, columns=["rule_code", "rule_type", "severity", "enabled", "description", "payload_json", "source", "notes"])

    # Sheet B: CATEGORY_RULES
    rows_b = []
    for cname in ("category_rules", "category_quality_rules"):
        if cname in db.list_collection_names():
            for doc in db[cname].find({}):
                cond = doc.get("condition") or doc.get("condition_json")
                rows_b.append({
                    "category_code": doc.get("category_code", ""),
                    "attribute_code": doc.get("attribute_code", ""),
                    "must_mode": doc.get("must_mode", "SOFT"),
                    "condition_json": json.dumps(cond) if isinstance(cond, dict) else (cond or ""),
                    "rule_code": doc.get("rule_code", ""),
                    "enabled": doc.get("enabled", True),
                    "severity": doc.get("severity", ""),
                    "notes": doc.get("notes", ""),
                })
                n_category_rules += 1
            break
    df_b = pd.DataFrame(rows_b, columns=["category_code", "attribute_code", "must_mode", "condition_json", "rule_code", "enabled", "severity", "notes"])

    # Sheet C: CATEGORY_DICTIONARY
    rows_c = []
    if "category_dictionary_entries" in db.list_collection_names():
        for doc in db.category_dictionary_entries.find({}):
            rows_c.append({
                "category_code": doc.get("category_code", ""),
                "keyword": doc.get("keyword", ""),
                "type": doc.get("type", "include"),
                "weight": doc.get("weight", 1),
                "scope": doc.get("scope", "category"),
                "enabled": doc.get("enabled", True),
                "notes": doc.get("comment", "") or doc.get("notes", ""),
            })
            n_category_dict += 1
    df_c = pd.DataFrame(rows_c, columns=["category_code", "keyword", "type", "weight", "scope", "enabled", "notes"])

    # Sheet D: TOKEN_ALIASES
    rows_d = []
    if "token_aliases" in db.list_collection_names():
        for doc in db.token_aliases.find({}):
            rows_d.append({
                "field": doc.get("field", ""),
                "raw": doc.get("raw", ""),
                "canonical": doc.get("canonical", ""),
                "enabled": doc.get("enabled", True),
                "notes": doc.get("comment", "") or doc.get("notes", ""),
            })
            n_token += 1
    df_d = pd.DataFrame(rows_d, columns=["field", "raw", "canonical", "enabled", "notes"])

    with pd.ExcelWriter(OUT_PATH, engine="openpyxl") as w:
        df_a.to_excel(w, sheet_name="GLOBAL_QUALITY_RULES", index=False)
        df_b.to_excel(w, sheet_name="CATEGORY_RULES", index=False)
        df_c.to_excel(w, sheet_name="CATEGORY_DICTIONARY", index=False)
        df_d.to_excel(w, sheet_name="TOKEN_ALIASES", index=False)

    print("RULES_PACK_EXPORT_OK path=%s sheets=4" % OUT_PATH)
    print("COUNTS global_quality_rules=%s category_dictionary=%s token_aliases=%s category_rules=%s" % (n_global, n_category_dict, n_token, n_category_rules))


if __name__ == "__main__":
    main()
