#!/usr/bin/env python3
"""
Build docs/rules/ALL_RULES.md and ALL_RULES.json from MongoDB (read-only).
Source: rulesets, ruleset_versions, global_quality_rules, dict collections.
Last line on success: ALL_RULES_BUILD_OK
"""
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from _env import load_env

from bson import ObjectId


def _ser(obj):
    if isinstance(obj, ObjectId):
        return str(obj)
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, dict):
        return {k: _ser(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_ser(v) for v in obj]
    return obj


def get_db():
    load_env()
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "bestprice_local")
    from pymongo import MongoClient
    return MongoClient(mongo_url)[db_name]


def main():
    load_env()
    db = get_db()
    out_dir = ROOT / "docs" / "rules"
    out_dir.mkdir(parents=True, exist_ok=True)

    data = {
        "rulesets": [],
        "global_rules": [],
        "dictionaries": {},
        "category_summary": {"strict_categories": [], "soft_categories": [], "must_matrix": [], "why": ""},
    }
    md_lines = [
        "# ALL RULES (v1)",
        "",
        f"Generated: {datetime.now(timezone.utc).isoformat()}",
        "",
        "---",
        "",
    ]

    # 1) Ruleset versions
    md_lines.append("## 1. Ruleset versions")
    md_lines.append("")
    versions = []
    if "ruleset_versions" in db.list_collection_names():
        for rv in db.ruleset_versions.find({}).sort("created_at", -1):
            rv_id = str(rv.get("_id"))
            name = rv.get("version_name") or rv.get("version") or rv_id
            created = rv.get("created_at")
            created_str = created.isoformat() if hasattr(created, "isoformat") else str(created)
            active = rv.get("is_active", rv.get("status") == "active")
            versions.append({"id": rv_id, "name": name, "created_at": created_str, "active": active})
            md_lines.append(f"- **{name}** | id=`{rv_id}` | created={created_str} | active={active}")
    md_lines.append("")
    data["rulesets"] = versions

    # 2) Global quality rules (from active v1 or first available)
    md_lines.append("## 2. Global quality rules")
    md_lines.append("")
    rv_id = None
    if "rulesets" in db.list_collection_names():
        rs = db.rulesets.find_one({"name": "BestPrice Rules"})
        if rs and rs.get("active_version_id"):
            rv_id = rs["active_version_id"]
    if not rv_id and versions:
        for v in versions:
            if v.get("active"):
                try:
                    rv_id = ObjectId(v["id"])
                except Exception:
                    pass
                break
    if not rv_id and "ruleset_versions" in db.list_collection_names():
        rv = db.ruleset_versions.find_one({"$or": [{"is_active": True}, {"status": "active"}]})
        if rv:
            rv_id = rv["_id"]

    global_rules = []
    if rv_id and "global_quality_rules" in db.list_collection_names():
        for r in db.global_quality_rules.find({"ruleset_version_id": rv_id}).sort("severity", 1).sort("rule_code", 1):
            rule_code = r.get("rule_code", "")
            severity = r.get("severity", "")
            payload = _ser(r.get("payload") or {})
            global_rules.append({"rule_code": rule_code, "severity": severity, "payload": payload})
            md_lines.append(f"- **{rule_code}** | severity={severity} | payload={json.dumps(payload, ensure_ascii=False)}")
    md_lines.append("")
    data["global_rules"] = global_rules

    # 3) Dictionaries
    md_lines.append("## 3. Dictionaries (v1)")
    md_lines.append("")

    def dump_dict(name, coll_name, key_field, extra_fields=None):
        if coll_name not in db.list_collection_names():
            data["dictionaries"][name] = {"count": 0, "items": [], "note": "collection not found"}
            md_lines.append(f"### {name}: 0 (collection not found)")
            return
        cursor = db[coll_name].find({"ruleset_version_id": rv_id} if rv_id else {})
        items = list(cursor)
        out = []
        for d in items[:500]:  # cap for doc
            o = _ser({k: d[k] for k in (extra_fields or [key_field]) if k in d})
            if key_field in d and "_key" not in o:
                o["_key"] = d.get(key_field)
            out.append(o)
        data["dictionaries"][name] = {"count": len(items), "items": out, "sample_cap": 500}
        md_lines.append(f"### {name}: {len(items)} entries")
        for it in out[:15]:
            md_lines.append(f"  - {json.dumps(it, ensure_ascii=False)}")
        if len(out) > 15:
            md_lines.append(f"  - ... and {len(out) - 15} more")
        md_lines.append("")

    if rv_id:
        dump_dict("category_dictionary_entries", "category_dictionary_entries", "keyword", ["category_code", "keyword", "type", "weight", "scope"])
        dump_dict("base_product_dictionary_entries", "base_product_dictionary_entries", "keyword", ["category_code", "keyword", "type"])
        dump_dict("token_aliases", "token_aliases", "raw", ["field", "raw", "canonical"])
    if "seed_dict_rules" in db.list_collection_names():
        dump_dict("seed_dict_rules", "seed_dict_rules", "raw", ["raw", "canonical", "type"])
    if "brand_aliases" in db.list_collection_names():
        cursor = db.brand_aliases.find({})
        items = list(cursor)
        data["dictionaries"]["brand_aliases"] = {"count": len(items), "items": _ser([{k: d[k] for k in ["alias_norm", "brand_id"] if k in d} for d in items[:200]])}
        md_lines.append("### brand_aliases: " + str(len(items)) + " entries")
        md_lines.append("")

    # 4) Category summary (STRICT/SOFT matrix)
    md_lines.append("## 4. Category summary (STRICT / SOFT)")
    md_lines.append("")
    md_lines.append("STRICT categories require base_product (and often state/cut) to be parsed; otherwise item is HIDDEN (MISSING_MUST_FIELDS). "
                    "SOFT categories allow base_product_unknown and do not hide for missing base_product.")
    md_lines.append("")
    strict_cats = []
    soft_cats = ["grocery", "canned", "drinks", "bakery", "desserts", "sausages", "frozen_semi"]
    must_matrix = []
    if rv_id and "category_attribute_rules" in db.list_collection_names():
        cursor = db.category_attribute_rules.find({"ruleset_version_id": rv_id}).sort("category_code", 1).sort("attribute_code", 1)
        by_cat = {}
        for r in cursor:
            cat = r.get("category_code", "")
            attr = r.get("attribute_code", "")
            mode = r.get("must_mode", "")
            role = r.get("role", "")
            if cat not in by_cat:
                by_cat[cat] = []
            by_cat[cat].append({"attribute_code": attr, "must_mode": mode, "role": role})
        for cat, rules in sorted(by_cat.items()):
            base_rule = next((x for x in rules if x["attribute_code"] == "base_product"), None)
            if base_rule and base_rule.get("must_mode") == "ALWAYS":
                if cat not in soft_cats:
                    strict_cats.append(cat)
            elif cat not in strict_cats and cat not in soft_cats:
                soft_cats.append(cat)
            must_matrix.append({"category_code": cat, "rules": rules})
    data["category_summary"]["strict_categories"] = strict_cats
    data["category_summary"]["soft_categories"] = soft_cats
    data["category_summary"]["must_matrix"] = must_matrix
    data["category_summary"]["why"] = "STRICT: item hidden if required attributes missing. SOFT: unknown allowed, no hide for missing base_product."

    md_lines.append("| Category | base_product must_mode |")
    md_lines.append("|----------|------------------------|")
    for row in must_matrix:
        cat = row["category_code"]
        bp = next((r for r in row["rules"] if r["attribute_code"] == "base_product"), {})
        mode = bp.get("must_mode", "—")
        md_lines.append(f"| {cat} | {mode} |")
    md_lines.append("")
    md_lines.append("- **STRICT (must identify product):** " + ", ".join(strict_cats) if strict_cats else "- **STRICT:** (none in this export)")
    md_lines.append("")
    md_lines.append("- **SOFT (unknown allowed):** " + ", ".join(soft_cats))
    md_lines.append("")

    # Write files
    with open(out_dir / "ALL_RULES.md", "w", encoding="utf-8") as f:
        f.write("\n".join(md_lines))
    with open(out_dir / "ALL_RULES.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    print("ALL_RULES_BUILD_OK")


if __name__ == "__main__":
    main()
