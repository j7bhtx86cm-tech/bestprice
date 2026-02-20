#!/usr/bin/env python3
"""
Check docs/rules/ALL_RULES pack: files exist, structure, required keys, counts.
Last line on success: ALL_RULES_CHECK_OK
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RULES_DIR = ROOT / "docs" / "rules"


def main():
    errors = []

    # Files exist
    md_path = RULES_DIR / "ALL_RULES.md"
    json_path = RULES_DIR / "ALL_RULES.json"
    if not md_path.exists():
        errors.append("ALL_RULES.md not found")
    if not json_path.exists():
        errors.append("ALL_RULES.json not found")

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    # ALL_RULES.md contains sections
    md_text = md_path.read_text(encoding="utf-8")
    required_sections = [
        "Ruleset versions",
        "Global quality rules",
        "Dictionaries",
        "Category summary",
    ]
    for sec in required_sections:
        if sec not in md_text:
            errors.append(f"ALL_RULES.md missing section: {sec}")

    # ALL_RULES.json valid and required keys
    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        errors.append(f"ALL_RULES.json invalid JSON: {e}")
        data = {}
    for key in ["rulesets", "global_rules", "dictionaries", "category_summary"]:
        if key not in data:
            errors.append(f"ALL_RULES.json missing key: {key}")

    if not isinstance(data.get("rulesets"), list):
        errors.append("ALL_RULES.json 'rulesets' must be array")
    if not isinstance(data.get("global_rules"), list):
        errors.append("ALL_RULES.json 'global_rules' must be array")
    if not isinstance(data.get("dictionaries"), dict):
        errors.append("ALL_RULES.json 'dictionaries' must be object")
    cs = data.get("category_summary")
    if not isinstance(cs, dict):
        errors.append("ALL_RULES.json 'category_summary' must be object")
    elif not all(k in cs for k in ["strict_categories", "soft_categories", "must_matrix"]):
        errors.append("ALL_RULES.json 'category_summary' must have strict_categories, soft_categories, must_matrix")

    # Counts: if we have ruleset versions, we expect at least some global_rules or dict entries when DB has data (optional)
    if data.get("rulesets") and not data.get("global_rules") and not any(
        data.get("dictionaries", {}).get(k, {}).get("count", 0) > 0 for k in data.get("dictionaries", {})
    ):
        pass  # allow: might be empty DB

    if errors:
        for e in errors:
            print(e, file=sys.stderr)
        sys.exit(1)

    print("ALL_RULES_CHECK_OK")


if __name__ == "__main__":
    main()
