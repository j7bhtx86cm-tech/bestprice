#!/usr/bin/env python3
"""
Locate Core Engine v1 state: find MongoDB DB + Git ref + artifact where ≥9/12 signals present.
Read-only: no DB writes, no .env changes, no secrets in stdout.
Output: artifacts/core_engine_v1_locator.md, .log, compact stdout.
"""
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")
REPORT_MD = ROOT / "artifacts" / "core_engine_v1_locator.md"
REPORT_LOG = ROOT / "artifacts" / "core_engine_v1_locator.log"

RULES_KEYS = ("rules", "rules_registry", "global_rules", "category_rules", "validations", "quality_rules")
GLOBAL_PATTERNS = ("INVALID", "HIDDEN", "PRICE_REQUIRED", "PRICE_NORMALIZATION")
CATEGORY_IDS = ("C", "H", "D", "MUST")
ALIAS_COLLECTIONS = ("token_aliases", "aliases", "dict_aliases", "brand_aliases")


def _log(msg: str):
    REPORT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def _mask_url(url: str) -> str:
    if not url or "@" not in url:
        return url
    return re.sub(r"://([^:]+):([^@]+)@", "://***:***@", url)


def _run(cmd, cwd=None, timeout=20):
    cwd = str(cwd or ROOT)
    try:
        r = subprocess.run(
            cmd if isinstance(cmd, list) else cmd.split(),
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)[:150]


def _count_global_rules_in_data(data) -> int:
    n = 0
    if isinstance(data, list):
        for r in data:
            if isinstance(r, dict):
                c = (r.get("rule_code") or r.get("code") or r.get("id") or "")
                if any(p in str(c).upper() for p in GLOBAL_PATTERNS):
                    n += 1
            elif isinstance(r, str) and any(p in r.upper() for p in GLOBAL_PATTERNS):
                n += 1
        return n
    if isinstance(data, dict):
        for k in RULES_KEYS:
            arr = data.get(k)
            if isinstance(arr, list):
                n += _count_global_rules_in_data(arr)
        return n
    return 0


def _has_category_must(doc, found: set) -> None:
    if not isinstance(doc, dict):
        return
    for k, v in doc.items():
        if v in CATEGORY_IDS:
            found.add(v)
        if isinstance(v, str) and "MUST" in v.upper():
            found.add("MUST")
        if k.lower() in ("must", "must_flag") and v:
            found.add("MUST")
        if isinstance(v, list):
            for x in v:
                if x in CATEGORY_IDS:
                    found.add(x)
                if isinstance(x, dict):
                    _has_category_must(x, found)


# ---------- 12 signals for one DB ----------
def _signal_1_ruleset_v1(db) -> tuple:
    """FOUND: rulesets + ruleset_versions, active, params_json with ≥3 keys. PARTIAL: collections only."""
    colls = db.list_collection_names() if db is not None else []
    if "rulesets" not in colls or "ruleset_versions" not in colls:
        return "NOT_FOUND", "missing collections"
    has_active = False
    params_keys = 0
    for doc in db.ruleset_versions.find({}).limit(5):
        if doc.get("is_active") is True:
            has_active = True
        p = doc.get("params_json")
        if isinstance(p, dict) and len(p) >= 3:
            params_keys = max(params_keys, len(p))
        if isinstance(p, str):
            try:
                p = json.loads(p)
                if isinstance(p, dict) and len(p) >= 3:
                    params_keys = max(params_keys, len(p))
            except Exception:
                pass
    for doc in db.rulesets.find({}).limit(5):
        if doc.get("active_version_id") is not None or doc.get("ruleset_version_id") is not None:
            has_active = True
    if has_active and params_keys >= 3:
        return "FOUND", "active + params"
    if db.rulesets.count_documents({}) > 0 or db.ruleset_versions.count_documents({}) > 0:
        return "PARTIAL", "collections exist"
    return "NOT_FOUND", "no data"


def _signal_2_rules_pack_structure(repo_root: Path, artifacts_dir: Path) -> tuple:
    """File-based: xlsx/csv/json with rule_code, rule_type, severity + (category|must|condition)."""
    required = {"rule_code", "rule_type", "severity"}
    optional = {"category", "must", "condition", "must_flag"}
    for d in (artifacts_dir, repo_root):
        if d is None or not d.is_dir():
            continue
        for ext in ("*.xlsx", "*.csv", "*.json"):
            for f in d.rglob(ext):
                if "node_modules" in f.parts or ".git" in f.parts:
                    continue
                try:
                    text = f.read_bytes()[:12000].decode("utf-8", errors="ignore")
                except Exception:
                    continue
                if f.suffix.lower() == ".csv":
                    line = text.split("\n")[0] if "\n" in text else text
                    keys = {k.strip().lower() for k in line.replace(";", ",").split(",")}
                elif f.suffix.lower() == ".json":
                    try:
                        data = json.loads(f.read_text(encoding="utf-8", errors="ignore"))
                        keys = set((data[0] if isinstance(data, list) and data else data).keys()) if isinstance(data, (list, dict)) else set()
                        keys = {str(k).lower() for k in keys}
                    except Exception:
                        continue
                else:
                    continue
                if required <= keys and (optional & keys):
                    return "FOUND", str(f)
                if required <= keys:
                    return "PARTIAL", "registry only " + str(f)
    return "NOT_FOUND", "no file"


def _signal_3_global_quality_rules(db) -> tuple:
    """FOUND: ≥5 rules with INVALID/HIDDEN/PRICE_REQUIRED/PRICE_NORMALIZATION."""
    total = 0
    if db is not None:
        for cname in ("ruleset_versions", "rulesets"):
            if cname not in db.list_collection_names():
                continue
            for doc in db[cname].find({}):
                p = doc.get("params_json")
                if isinstance(p, str):
                    try:
                        p = json.loads(p)
                    except Exception:
                        p = None
                if isinstance(p, dict):
                    total += _count_global_rules_in_data(p)
                for f in ("rules", "rules_registry", "rule_codes"):
                    total += _count_global_rules_in_data(doc.get(f) or [])
    if total >= 5:
        return "FOUND", str(total)
    if total > 0:
        return "PARTIAL", str(total)
    return "NOT_FOUND", "0"


def _signal_4_category_rules(db) -> tuple:
    """FOUND: C/H/D + MUST in DB."""
    found = set()
    if db is not None:
        for cname in db.list_collection_names():
            for doc in db[cname].find({}).limit(30):
                _has_category_must(doc, found)
                if found >= set(CATEGORY_IDS):
                    return "FOUND", "C/H/D+MUST"
    if found:
        return "PARTIAL", ",".join(sorted(found))
    return "NOT_FOUND", ""


def _signal_5_category_dictionary(db) -> tuple:
    """FOUND: category_dictionary_entries count>0. PARTIAL: similar name."""
    if db is None:
        return "NOT_FOUND", ""
    colls = db.list_collection_names()
    if "category_dictionary_entries" in colls:
        c = db.category_dictionary_entries.count_documents({})
        if c > 0:
            return "FOUND", str(c)
        return "PARTIAL", "0"
    for name in colls:
        if "category_dict" in name.lower() or "category_dictionary" in name.lower():
            if db[name].count_documents({}) > 0:
                return "PARTIAL", name
    return "NOT_FOUND", ""


def _signal_6_token_aliases(db) -> tuple:
    """FOUND: token_aliases/aliases/dict_aliases/brand_aliases count>0. PARTIAL: doc with alias."""
    if db is None:
        return "NOT_FOUND", ""
    for cname in ALIAS_COLLECTIONS:
        if cname in db.list_collection_names() and db[cname].count_documents({}) > 0:
            return "FOUND", cname
    for cname in db.list_collection_names():
        try:
            doc = db[cname].find_one({}, {"_id": 0})
            if doc and "alias" in doc and db[cname].count_documents({}) > 0:
                return "PARTIAL", cname
        except Exception:
            pass
    return "NOT_FOUND", ""


def _signal_7_importer(repo_root: Path) -> tuple:
    """File-based: script import_rules / rules_pack_import that writes to ruleset_versions."""
    for scripts_dir in (repo_root / "scripts", repo_root / "backend"):
        if not scripts_dir.is_dir():
            continue
        for f in scripts_dir.rglob("*.py"):
            name = f.stem.lower()
            if "import_rules" in name or "rules_pack_import" in name or "import_rules_pack" in name:
                t = f.read_text(encoding="utf-8", errors="ignore")
                if "ruleset_version" in t or "ruleset_versions" in t:
                    return "FOUND", str(f.name)
            if "e2e_import" in name and "pipeline" in name:
                return "PARTIAL", "e2e only"
    return "NOT_FOUND", ""


def _signal_8_pipeline(db, repo_root: Path) -> tuple:
    """FOUND: pipeline_runs>0 AND code has runner. PARTIAL: one of two."""
    has_code = (repo_root / "backend" / "pipeline").is_dir() or (repo_root / "backend" / "bestprice_v12" / "pipeline_runner.py").is_file()
    runs = 0
    if db is not None and "pipeline_runs" in db.list_collection_names():
        runs = db.pipeline_runs.count_documents({})
    if runs > 0 and has_code:
        return "FOUND", "runs=%s" % runs
    if runs > 0 or has_code:
        return "PARTIAL", "runs=%s code=%s" % (runs, has_code)
    return "NOT_FOUND", ""


def _signal_9_master(db) -> tuple:
    """FOUND: collection with master+fingerprint+hash/verified, count>0. PARTIAL: master+fingerprint."""
    if db is None:
        return "NOT_FOUND", ""
    for cname in ("masters", "master_links"):
        if cname not in db.list_collection_names():
            continue
        doc = db[cname].find_one({})
        if not doc:
            continue
        has_fp = "fingerprint" in doc
        has_verified = "verified" in doc or "verification_status" in doc or "hash" in doc
        c = db[cname].count_documents({})
        if c > 0 and has_fp and has_verified:
            return "FOUND", cname
        if c > 0 and has_fp:
            return "PARTIAL", cname
    return "NOT_FOUND", ""


def _signal_10_market_snapshot(db) -> tuple:
    """FOUND: collection with median/avg/mean + master/sku, count>0."""
    if db is None:
        return "NOT_FOUND", ""
    for cname in ("master_market_snapshot_current", "master_market_snapshot", "market_snapshot"):
        if cname not in db.list_collection_names():
            continue
        doc = db[cname].find_one({})
        if not doc:
            continue
        has_agg = "median" in doc or "avg" in doc or "mean" in doc
        has_ref = "master" in str(doc).lower() or "sku" in str(doc).lower()
        c = db[cname].count_documents({})
        if c > 0 and (has_agg or has_ref):
            return "FOUND", cname
        if c > 0:
            return "PARTIAL", cname
    return "NOT_FOUND", ""


def _signal_11_history(db) -> tuple:
    """FOUND: sku_price_history>0 AND master_market_history_daily>0."""
    if db is None:
        return "NOT_FOUND", ""
    c1 = db.sku_price_history.count_documents({}) if "sku_price_history" in db.list_collection_names() else 0
    c2 = db.master_market_history_daily.count_documents({}) if "master_market_history_daily" in db.list_collection_names() else 0
    if c1 > 0 and c2 > 0:
        return "FOUND", "sku=%s daily=%s" % (c1, c2)
    if c1 > 0 or c2 > 0:
        return "PARTIAL", "sku=%s daily=%s" % (c1, c2)
    return "NOT_FOUND", ""


def _signal_12_supplier_overrides(db) -> tuple:
    """FOUND: override + sku/article + fingerprint/supplier_item_id, count>0."""
    if db is None:
        return "NOT_FOUND", ""
    for cname in db.list_collection_names():
        if "override" not in cname.lower():
            continue
        doc = db[cname].find_one({})
        if not doc:
            continue
        has_override = "override" in doc
        has_sku = "sku" in doc or "article" in doc or "supplier_item_id" in doc
        has_fp = "fingerprint" in doc or "supplier_item_id" in doc
        c = db[cname].count_documents({})
        if c > 0 and has_override and has_sku and has_fp:
            return "FOUND", cname
        if c > 0 and has_override:
            return "PARTIAL", cname
    return "NOT_FOUND", ""


def _score_status(s: str) -> int:
    return 2 if s == "FOUND" else 1 if s == "PARTIAL" else 0


def scan_all_dbs():
    try:
        from pymongo import MongoClient
    except ImportError:
        return []
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=8000)
        client.admin.command("ping")
    except Exception:
        return []
    skip = {"admin", "local", "config"}
    dbs = [n for n in client.list_database_names() if n not in skip]
    repo_root = ROOT
    artifacts_dir = ROOT / "artifacts"
    results = []
    for db_name in dbs:
        db = client[db_name]
        signals = []
        counts = {}
        try:
            for coll in ("pipeline_runs", "supplier_items", "pricelists", "ruleset_versions", "rulesets",
                        "sku_price_history", "master_market_history_daily", "masters", "master_links",
                        "master_market_snapshot_current"):
                if coll in db.list_collection_names():
                    counts[coll] = db[coll].count_documents({})
        except Exception as e:
            _log("DB %s counts error: %s" % (db_name, str(e)[:80]))
        s1, r1 = _signal_1_ruleset_v1(db)
        signals.append(("1_Ruleset_v1", s1, r1))
        s2, r2 = _signal_2_rules_pack_structure(repo_root, artifacts_dir)
        signals.append(("2_Rules_Pack", s2, r2))
        s3, r3 = _signal_3_global_quality_rules(db)
        signals.append(("3_Global_Quality", s3, r3))
        s4, r4 = _signal_4_category_rules(db)
        signals.append(("4_Category_C_H_D_MUST", s4, r4))
        s5, r5 = _signal_5_category_dictionary(db)
        signals.append(("5_category_dictionary", s5, r5))
        s6, r6 = _signal_6_token_aliases(db)
        signals.append(("6_Token_Aliases", s6, r6))
        s7, r7 = _signal_7_importer(repo_root)
        signals.append(("7_Importer", s7, r7))
        s8, r8 = _signal_8_pipeline(db, repo_root)
        signals.append(("8_Pipeline", s8, r8))
        s9, r9 = _signal_9_master(db)
        signals.append(("9_MASTER", s9, r9))
        s10, r10 = _signal_10_market_snapshot(db)
        signals.append(("10_Market_Snapshot", s10, r10))
        s11, r11 = _signal_11_history(db)
        signals.append(("11_History", s11, r11))
        s12, r12 = _signal_12_supplier_overrides(db)
        signals.append(("12_Supplier_Overrides", s12, r12))
        score = sum(_score_status(s[1]) for s in signals)
        found_count = sum(1 for s in signals if s[1] == "FOUND")
        partial_count = sum(1 for s in signals if s[1] == "PARTIAL")
        not_count = sum(1 for s in signals if s[1] == "NOT_FOUND")
        results.append({
            "db_name": db_name,
            "score": score,
            "found_count": found_count,
            "partial_count": partial_count,
            "not_found_count": not_count,
            "counts": counts,
            "signals": signals,
        })
    return sorted(results, key=lambda x: -x["score"])


def git_top_refs():
    refs = []
    code, out, _ = _run(["git", "tag", "-l", "--sort=-creatordate"])
    if code == 0 and out:
        refs.extend(out.splitlines()[:20])
    code, out, _ = _run(["git", "branch", "-a", "--sort=-committerdate"])
    if code == 0 and out:
        refs.extend([x.strip().lstrip("* ") for x in out.splitlines()[:15]])
    code, out, _ = _run(["git", "stash", "list"])
    if code == 0 and out:
        for line in out.splitlines()[:10]:
            if ":" in line:
                refs.append(line.split(":")[0].strip())
    scored = []
    for ref in refs:
        code, out, _ = _run(["git", "ls-tree", "-r", ref, "--name-only"])
        if code != 0 or not out:
            continue
        paths = out.lower()
        sc = 0
        if "rulesets_export" in paths and ".zip" in paths:
            sc += 2
        if "rules_pack" in paths:
            sc += 2
        if "runbook_core_engine_lock" in paths or "RUNBOOK_CORE_ENGINE" in paths:
            sc += 1
        if sc > 0:
            scored.append((ref, sc))
    return sorted(scored, key=lambda x: -x[1])[:5]


def artifacts_findings():
    artifacts_dir = ROOT / "artifacts"
    if not artifacts_dir.is_dir():
        return []
    out = []
    for pat in ("rulesets_export*.zip", "rules_pack*.xlsx", "rules_pack*.csv", "rules_pack*.json"):
        for f in artifacts_dir.glob(pat):
            out.append(str(f))
    return list(dict.fromkeys(out))


def write_report(db_top, git_top, artifacts_list, best_db_detail):
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    mongo_display = _mask_url(MONGO_URL)
    lines = [
        "# Core Engine v1 state locator",
        "",
        "## CURRENT_ENV",
        "| Key | Value |",
        "|-----|-------|",
        "| MONGO_URL | %s |" % mongo_display,
        "| DB_NAME | %s |" % DB_NAME,
        "",
        "## DB_TOP5",
        "| db_name | score | found_count | partial_count | NOT_found_count | key_counts |",
        "|---------|-------|-------------|---------------|-----------------|------------|",
    ]
    for r in db_top[:5]:
        counts_str = json.dumps(r.get("counts", {}))[:70]
        lines.append("| %s | %s | %s | %s | %s | %s |" % (
            r.get("db_name", ""),
            r.get("score", 0),
            r.get("found_count", 0),
            r.get("partial_count", 0),
            r.get("not_found_count", 0),
            counts_str,
        ))
    if not db_top:
        lines.append("| (none) | 0 | 0 | 0 | 0 | - |")
    lines.append("")
    if best_db_detail:
        lines.append("## Best DB checklist (1..12)")
        for name, status, reason in best_db_detail.get("signals", []):
            lines.append("- **%s** %s — %s" % (name, status, reason))
        lines.append("")
    lines.append("## GIT_TOP5")
    for ref, sc in git_top:
        lines.append("- %s (score=%s)" % (ref, sc))
    if not git_top:
        lines.append("- (none)")
    lines.append("")
    lines.append("## ARTIFACTS findings")
    for p in artifacts_list:
        lines.append("- %s" % p)
    if not artifacts_list:
        lines.append("- (none)")
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    if REPORT_LOG.exists():
        REPORT_LOG.write_text("")
    _log("start locate_core_engine_v1_state")
    db_top = scan_all_dbs()
    _log("db_top count=%s" % len(db_top))
    git_top = git_top_refs()
    artifacts_list = artifacts_findings()
    best = db_top[0] if db_top else None
    if best:
        write_report(db_top, git_top, artifacts_list, best)
    else:
        write_report(db_top, git_top, artifacts_list, None)
    found_plus_partial = (best.get("found_count", 0) + best.get("partial_count", 0)) if best else 0
    if found_plus_partial >= 9:
        best_status = "FOUND"
    elif best and best.get("score", 0) > 0:
        best_status = "LIKELY"
    else:
        best_status = "NOT_FOUND"
    best_db = best.get("db_name", "NONE") if best else "NONE"
    best_git = git_top[0][0] if git_top else "NONE"
    best_artifact = artifacts_list[0] if artifacts_list else "NONE"
    rec = "Set DB_NAME to best DB and run pipeline if needed"
    if best_status == "NOT_FOUND" and not best_db or best_db == "NONE":
        rec = "No DB with ≥9/12 signals; check another Mongo or import from artifacts"
    if best_status == "FOUND":
        rec = "Use BEST_DB as DB_NAME; run check_core_engine_v1 to verify"
    print("LOCATOR_OK report=%s" % REPORT_MD)
    for i, r in enumerate(db_top[:5], 1):
        print("TOP_DB_%s name=%s score=%s found=%s partial=%s" % (
            i, r.get("db_name", ""), r.get("score", 0), r.get("found_count", 0), r.get("partial_count", 0)))
    print("BEST_DB=%s" % best_db)
    print("BEST_DB_STATUS=%s" % best_status)
    print("BEST_GIT_REF=%s" % best_git)
    print("BEST_ARTIFACT=%s" % best_artifact)
    print("RECOMMENDED_NEXT_STEP=%s" % rec)


if __name__ == "__main__":
    main()
