#!/usr/bin/env python3
"""
Check Rules Pack v1: file exists with 4 sheets, sheet A >= 10 rows; DB counts after import.
"""
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

REQUIRED_SHEETS = ("GLOBAL_QUALITY_RULES", "CATEGORY_RULES", "CATEGORY_DICTIONARY", "TOKEN_ALIASES")
MIN_GLOBAL_ROWS = 10
MIN_GLOBAL_DB = 10
MIN_DICT_DB = 100
MIN_TOKEN_DB = 10
MIN_CATEGORY_RULES_DB = 1  # category_rules > 0 required


def _get_db():
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client[DB_NAME]
    except Exception:
        return None


def main():
    if not PACK_PATH.is_file():
        print("RULES_PACK_CHECK_FAIL: file not found path=%s" % PACK_PATH)
        return
    try:
        import pandas as pd
    except ImportError:
        print("RULES_PACK_CHECK_FAIL: pandas required")
        return
    xl = pd.ExcelFile(PACK_PATH)
    sheets = set(xl.sheet_names)
    for name in REQUIRED_SHEETS:
        if name not in sheets:
            print("RULES_PACK_CHECK_FAIL: missing sheet %s" % name)
            return
    df_a = pd.read_excel(PACK_PATH, sheet_name="GLOBAL_QUALITY_RULES")
    n_rows = len(df_a)
    if n_rows < MIN_GLOBAL_ROWS:
        print("RULES_PACK_CHECK_FAIL: sheet GLOBAL_QUALITY_RULES has %s rows, expected >= %s" % (n_rows, MIN_GLOBAL_ROWS))
        return
    db = _get_db()
    if db is None:
        print("RULES_PACK_CHECK_FAIL: cannot connect to Mongo")
        return
    c_global = db.global_quality_rules.count_documents({}) if "global_quality_rules" in db.list_collection_names() else 0
    c_dict = db.category_dictionary_entries.count_documents({}) if "category_dictionary_entries" in db.list_collection_names() else 0
    c_token = db.token_aliases.count_documents({}) if "token_aliases" in db.list_collection_names() else 0
    c_cat = 0
    for cname in ("category_rules", "category_quality_rules"):
        if cname in db.list_collection_names():
            c_cat = db[cname].count_documents({})
            break
    if c_global < MIN_GLOBAL_DB:
        print("RULES_PACK_CHECK_FAIL: global_quality_rules count=%s expected>=%s" % (c_global, MIN_GLOBAL_DB))
        return
    if c_dict < MIN_DICT_DB:
        print("RULES_PACK_CHECK_FAIL: category_dictionary_entries count=%s expected>=%s" % (c_dict, MIN_DICT_DB))
        return
    if c_token < MIN_TOKEN_DB:
        print("RULES_PACK_CHECK_FAIL: token_aliases count=%s expected>=%s" % (c_token, MIN_TOKEN_DB))
        return
    if c_cat < MIN_CATEGORY_RULES_DB:
        print("RULES_PACK_CHECK_FAIL: category_rules=0 expected>0")
        return
    print("RULES_PACK_CHECK_OK")


if __name__ == "__main__":
    main()
