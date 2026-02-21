#!/usr/bin/env python3
"""
Core Engine v1 audit: read-only check of 8 blocks.
Output: FOUND | PARTIAL | NOT_FOUND per block, then CORE_ENGINE_V1_STATUS.
No DB writes, no .env changes, no secrets in stdout.
"""
import json
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

# Required columns for Rules Pack structure (subset: at least these)
RULES_PACK_COLUMNS = {"rule_code", "rule_type", "severity", "category", "condition", "must_flag"}
# Global rule code patterns
GLOBAL_RULE_PREFIXES = ("INVALID_", "HIDDEN_", "PRICE_REQUIRED", "PRICE_NORMALIZATION_REQUIRED")
MIN_GLOBAL_RULES = 5
# Category rule identifiers
CATEGORY_IDS = ("C", "H", "D", "MUST")
# Alias-related collections
ALIAS_COLLECTIONS = ("token_aliases", "aliases", "dict_aliases", "brand_aliases")
# Importer script names (without path)
IMPORTER_NAMES = ("import_rules", "rules_pack_import", "ensure_rules", "e2e_import_pipeline_v1")


def _get_db():
    try:
        from pymongo import MongoClient
    except ImportError:
        return None
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        return client[DB_NAME]
    except Exception:
        return None


def check_ruleset_v1(db) -> str:
    """1. Ruleset v1: rulesets + ruleset_versions, active_version_id, version_name, params_json, is_active=True."""
    if db is None:
        return "NOT_FOUND"
    colls = db.list_collection_names()
    if "rulesets" not in colls and "ruleset_versions" not in colls:
        return "NOT_FOUND"
    has_rulesets = "rulesets" in colls and db.rulesets.count_documents({}) > 0
    has_versions = "ruleset_versions" in colls and db.ruleset_versions.count_documents({}) > 0
    if not has_rulesets and not has_versions:
        return "NOT_FOUND"

    has_version_name = False
    has_params_json = False
    has_active = False
    has_active_version_id = False

    for doc in db.ruleset_versions.find({}).limit(5):
        if doc.get("version_name") is not None:
            has_version_name = True
        if doc.get("params_json") is not None:
            has_params_json = True
        if doc.get("is_active") is True:
            has_active = True
        if doc.get("active_version_id") is not None:
            has_active_version_id = True
    for doc in db.rulesets.find({}).limit(5):
        if doc.get("version_name") is not None:
            has_version_name = True
        if doc.get("params_json") is not None:
            has_params_json = True
        if doc.get("active_version_id") is not None:
            has_active_version_id = True
        if doc.get("ruleset_version_id") is not None:
            has_active_version_id = True  # treat as link to version

    required = sum([has_version_name, has_params_json or has_active_version_id, has_active])
    if has_versions and has_active and (has_version_name or has_params_json):
        return "FOUND"
    if has_rulesets or has_versions:
        return "PARTIAL"
    return "NOT_FOUND"


def _file_has_rules_pack_columns(path: Path) -> bool:
    """Check if file (csv/json) contains required column names."""
    try:
        text = path.read_bytes()[:8000].decode("utf-8", errors="ignore")
    except Exception:
        return False
    text_lower = text.lower()
    # CSV: header row
    if path.suffix.lower() == ".csv":
        first_line = text.split("\n")[0] if "\n" in text else text
        keys = {k.strip().lower() for k in first_line.replace(";", ",").split(",")}
        return RULES_PACK_COLUMNS.issubset(keys) or bool(RULES_PACK_COLUMNS & keys)
    if path.suffix.lower() == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        except Exception:
            return False
        if isinstance(data, list) and data:
            keys = set((data[0] if isinstance(data[0], dict) else {}).keys())
        elif isinstance(data, dict):
            keys = set(data.keys()) if not isinstance(next(iter(data.values()), None), (dict, list)) else set()
        else:
            return False
        return bool(RULES_PACK_COLUMNS & {k.lower() for k in keys})
    return False


def check_rules_pack_structure(_db, repo_root: Path) -> str:
    """2. Rules Pack v1: xlsx/csv/json with rule_code, rule_type, severity, category, condition, must_flag."""
    found_file = False
    for ext in ("*.xlsx", "*.csv", "*.json"):
        for path in repo_root.rglob(ext):
            if "node_modules" in path.parts or ".git" in path.parts or "venv" in path.parts:
                continue
            if _file_has_rules_pack_columns(path):
                return "FOUND"
            # For xlsx we can't easily check without openpyxl; check name hint
            if path.suffix.lower() == ".xlsx" and "rule" in path.name.lower():
                try:
                    import pandas as pd
                    df = pd.read_excel(path, nrows=1)
                    keys = {str(k).lower() for k in df.columns}
                    if RULES_PACK_COLUMNS & keys:
                        return "FOUND"
                except Exception:
                    pass
    # PARTIAL: registry with ~12 rules (in DB or code)
    if _db is not None:
        for cname in ("ruleset_versions", "rulesets"):
            if cname not in _db.list_collection_names():
                continue
            for doc in _db[cname].find({}).limit(3):
                for field in ("rules", "rules_registry", "rule_codes", "items"):
                    arr = doc.get(field) or (doc.get("params_json") if isinstance(doc.get("params_json"), dict) else {}).get("rules")
                    if isinstance(arr, list) and 10 <= len(arr) <= 20:
                        return "PARTIAL"
                p = doc.get("params_json")
                if isinstance(p, str):
                    try:
                        p = json.loads(p)
                    except Exception:
                        p = None
                if isinstance(p, dict) and isinstance(p.get("rules"), list) and 10 <= len(p["rules"]) <= 20:
                    return "PARTIAL"
    return "NOT_FOUND"


def _collect_rule_codes(db) -> list:
    """Collect all rule_code / code values from rulesets and ruleset_versions."""
    codes = []
    if db is None:
        return codes
    for cname in ("ruleset_versions", "rulesets"):
        if cname not in db.list_collection_names():
            continue
        for doc in db[cname].find({}):
            for field in ("rules", "rules_registry", "rule_codes", "items"):
                arr = doc.get(field)
                if not isinstance(arr, list):
                    continue
                for r in arr:
                    if isinstance(r, dict):
                        codes.append((r.get("rule_code") or r.get("code") or r.get("id") or "").upper())
                    elif isinstance(r, str):
                        codes.append(r.upper())
            p = doc.get("params_json")
            if isinstance(p, str):
                try:
                    p = json.loads(p)
                except Exception:
                    p = None
            if isinstance(p, dict):
                arr = p.get("rules") or p.get("rule_codes") or []
                for r in arr if isinstance(arr, list) else []:
                    if isinstance(r, dict):
                        codes.append((r.get("rule_code") or r.get("code") or "").upper())
                    elif isinstance(r, str):
                        codes.append(r.upper())
    return codes


def _collect_global_rule_codes_from_code(repo_root: Path) -> set:
    """Scan backend for INVALID_*, HIDDEN_*, PRICE_REQUIRED, PRICE_NORMALIZATION_REQUIRED."""
    import re
    found = set()
    backend = repo_root / "backend"
    if not backend.is_dir():
        return found
    pattern = re.compile(
        r"(?:INVALID_[A-Z_]+|HIDDEN_[A-Z_]+|PRICE_REQUIRED|PRICE_NORMALIZATION_REQUIRED|MISSING_PRICE)"
    )
    for py in backend.rglob("*.py"):
        try:
            for m in pattern.finditer(py.read_text(encoding="utf-8", errors="ignore")):
                found.add(m.group(0))
        except Exception:
            pass
    return found


def check_global_rules(db, repo_root: Path) -> str:
    """3. Global Quality Rules: >= 5 with INVALID_*, HIDDEN_*, PRICE_REQUIRED, PRICE_NORMALIZATION_REQUIRED."""
    global_set = set()
    if db is not None:
        codes = _collect_rule_codes(db)
        for c in codes:
            if not c:
                continue
            for prefix in GLOBAL_RULE_PREFIXES:
                if c == prefix or c.startswith(prefix.replace("_REQUIRED", "")):
                    global_set.add(c)
            if "INVALID" in c or "HIDDEN" in c or c == "PRICE_REQUIRED" or "PRICE_NORMALIZATION" in c:
                global_set.add(c)
    for c in _collect_global_rule_codes_from_code(repo_root):
        global_set.add(c)
    if len(global_set) >= MIN_GLOBAL_RULES:
        return "FOUND"
    if len(global_set) > 0:
        return "PARTIAL"
    return "NOT_FOUND"


def check_category_rules(db, repo_root: Path) -> str:
    """4. Category Rules: C, H, D, MUST present in DB or files."""
    found = set()
    if db is not None:
        for cname in db.list_collection_names():
            if "rule" not in cname.lower() and "category" not in cname.lower():
                continue
            for doc in db[cname].find({}).limit(50):
                for v in (doc.get("category") or doc.get("category_id") or doc.get("type") or "").split():
                    if v in CATEGORY_IDS:
                        found.add(v)
                for key in ("categories", "category_rules", "must"):
                    val = doc.get(key)
                    if isinstance(val, list):
                        for x in val:
                            if x in CATEGORY_IDS or (isinstance(x, dict) and (x.get("id") or x.get("code")) in CATEGORY_IDS):
                                found.add(x if isinstance(x, str) else (x.get("id") or x.get("code")))
                    elif isinstance(val, str) and val in CATEGORY_IDS:
                        found.add(val)
    for path in [repo_root / "backend", repo_root / "memory", repo_root / "docs"]:
        if not path.is_dir():
            continue
        for py in path.rglob("*.py"):
            try:
                t = py.read_text(encoding="utf-8", errors="ignore")
                for cat in CATEGORY_IDS:
                    if f'"{cat}"' in t or f"'{cat}'" in t or f"category.*{cat}" in t:
                        found.add(cat)
            except Exception:
                pass
        for md in path.rglob("*.md"):
            try:
                t = md.read_text(encoding="utf-8", errors="ignore")
                for cat in CATEGORY_IDS:
                    if f" {cat} " in t or f"({cat})" in t or f"category {cat}" in t.lower():
                        found.add(cat)
            except Exception:
                pass
    if found >= set(CATEGORY_IDS):
        return "FOUND"
    if found:
        return "PARTIAL"
    return "NOT_FOUND"


def check_category_dictionary(db) -> str:
    """5. category_dictionary_entries: count > 0."""
    if db is None:
        return "NOT_FOUND"
    if "category_dictionary_entries" not in db.list_collection_names():
        return "NOT_FOUND"
    n = db.category_dictionary_entries.count_documents({})
    return "FOUND" if n > 0 else "NOT_FOUND"


def check_token_aliases(db) -> str:
    """6. Token aliases: token_aliases / aliases / dict_aliases or any collection with 'alias' and data."""
    if db is None:
        return "NOT_FOUND"
    for cname in ALIAS_COLLECTIONS:
        if cname in db.list_collection_names() and db[cname].count_documents({}) > 0:
            return "FOUND"
    for cname in db.list_collection_names():
        if "alias" in cname.lower():
            if db[cname].count_documents({}) > 0:
                return "FOUND"
        else:
            try:
                doc = db[cname].find_one({}, {"_id": 0})
                if doc and "alias" in doc:
                    if db[cname].count_documents({}) > 0:
                        return "FOUND"
            except Exception:
                pass
    return "NOT_FOUND"


def check_rules_importer(repo_root: Path) -> str:
    """7. Importer Rules Pack -> DB: import_rules, rules_pack_import, ensure_rules, e2e_import_pipeline_v1."""
    found_dedicated = False
    found_e2e = False
    for path in [repo_root / "scripts", repo_root / "backend"]:
        if not path.is_dir():
            continue
        for f in path.rglob("*.py"):
            name = f.stem
            if name in IMPORTER_NAMES:
                if "e2e_import" in name:
                    # e2e runs pipeline; check if it also imports rules
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    if "ruleset" in text and ("insert" in text or "import" in text or "rules" in text):
                        found_e2e = True
                else:
                    found_dedicated = True
            if "import" in name and "rule" in name.lower():
                found_dedicated = True
    if found_dedicated:
        return "FOUND"
    if found_e2e:
        return "PARTIAL"
    # e2e_import_pipeline_v1 exists but may not import rules pack
    if (repo_root / "scripts" / "e2e_import_pipeline_v1.py").exists():
        return "PARTIAL"
    return "NOT_FOUND"


def check_pipeline(db, repo_root: Path) -> str:
    """8. Pipeline: backend/pipeline/, pipeline_runner, pipeline_runs > 0, sku matching/normalization."""
    pipeline_dir = repo_root / "backend" / "pipeline"
    runner = repo_root / "backend" / "bestprice_v12" / "pipeline_runner.py"
    if not pipeline_dir.is_dir() or not runner.is_file():
        return "NOT_FOUND"
    has_normalizer = (pipeline_dir / "normalizer.py").is_file() or (pipeline_dir / "unit_normalizer.py").is_file()
    has_sku_logic = "sku" in (runner.read_text(encoding="utf-8", errors="ignore")).lower() or has_normalizer
    runs = 0
    if db is not None and "pipeline_runs" in db.list_collection_names():
        runs = db.pipeline_runs.count_documents({})
    if runs > 0 and has_sku_logic:
        return "FOUND"
    if pipeline_dir.is_dir() and runner.is_file():
        return "PARTIAL"
    return "NOT_FOUND"


def main():
    db = _get_db()
    repo_root = ROOT

    r1 = check_ruleset_v1(db)
    r2 = check_rules_pack_structure(db, repo_root)
    r3 = check_global_rules(db, repo_root)
    r4 = check_category_rules(db, repo_root)
    r5 = check_category_dictionary(db)
    r6 = check_token_aliases(db)
    r7 = check_rules_importer(repo_root)
    r8 = check_pipeline(db, repo_root)

    results = [r1, r2, r3, r4, r5, r6, r7, r8]
    if all(r == "FOUND" for r in results):
        status = "READY"
    elif any(r == "FOUND" for r in results) or any(r == "PARTIAL" for r in results):
        status = "INCOMPLETE"
    else:
        status = "NOT_PRESENT"

    print("CORE_ENGINE_V1_AUDIT")
    print("RULESET_V1=%s" % r1)
    print("RULES_PACK_STRUCTURE=%s" % r2)
    print("GLOBAL_RULES=%s" % r3)
    print("CATEGORY_RULES=%s" % r4)
    print("CATEGORY_DICTIONARY=%s" % r5)
    print("TOKEN_ALIASES=%s" % r6)
    print("RULES_IMPORTER=%s" % r7)
    print("PIPELINE=%s" % r8)
    print("CORE_ENGINE_V1_STATUS=%s" % status)


if __name__ == "__main__":
    main()
