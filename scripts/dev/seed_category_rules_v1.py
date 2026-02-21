#!/usr/bin/env python3
"""
Seed CATEGORY_RULES (C/H/D + MUST) into RULES_PACK_v1.xlsx.
STRICT for C and MUST, SOFT for H and D. attribute_code=must_fields, rule_code=MUST_FIELDS.
Does not change other sheets. Run before import to get category_rules > 0.
BLOCKER: apply_rules_v1 (pipeline_runner) does not read category_rules from Mongo; data is for Pack/DB consistency and future use.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PACK_PATH = ROOT / "docs" / "rules_pack" / "RULES_PACK_v1.xlsx"

# C/H/D + MUST per spec; STRICT = must be satisfied, SOFT = best-effort
STRICT_CATEGORIES = ("C", "MUST")
SOFT_CATEGORIES = ("H", "D")
ATTRIBUTE_CODE = "must_fields"
RULE_CODE = "MUST_FIELDS"


def main():
    if not PACK_PATH.is_file():
        print("SEED_CATEGORY_RULES_FAIL: file not found path=%s" % PACK_PATH)
        return
    try:
        import pandas as pd
    except ImportError:
        print("SEED_CATEGORY_RULES_FAIL: pandas required")
        return
    rows = []
    for cat in STRICT_CATEGORIES:
        rows.append({
            "category_code": cat,
            "attribute_code": ATTRIBUTE_CODE,
            "must_mode": "STRICT",
            "condition_json": "{}",
            "rule_code": RULE_CODE,
            "enabled": True,
            "severity": "INVALID",
            "notes": "must_fields STRICT",
        })
    for cat in SOFT_CATEGORIES:
        rows.append({
            "category_code": cat,
            "attribute_code": ATTRIBUTE_CODE,
            "must_mode": "SOFT",
            "condition_json": "{}",
            "rule_code": RULE_CODE,
            "enabled": True,
            "severity": "WARN",
            "notes": "must_fields SOFT",
        })
    df_b = pd.DataFrame(rows, columns=["category_code", "attribute_code", "must_mode", "condition_json", "rule_code", "enabled", "severity", "notes"])
    df_a = pd.read_excel(PACK_PATH, sheet_name="GLOBAL_QUALITY_RULES")
    df_c = pd.read_excel(PACK_PATH, sheet_name="CATEGORY_DICTIONARY")
    df_d = pd.read_excel(PACK_PATH, sheet_name="TOKEN_ALIASES")
    with pd.ExcelWriter(PACK_PATH, engine="openpyxl") as w:
        df_a.to_excel(w, sheet_name="GLOBAL_QUALITY_RULES", index=False)
        df_b.to_excel(w, sheet_name="CATEGORY_RULES", index=False)
        df_c.to_excel(w, sheet_name="CATEGORY_DICTIONARY", index=False)
        df_d.to_excel(w, sheet_name="TOKEN_ALIASES", index=False)
    print("SEED_CATEGORY_RULES_OK path=%s rows=%s" % (PACK_PATH, len(rows)))


if __name__ == "__main__":
    main()
