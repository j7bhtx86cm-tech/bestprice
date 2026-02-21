#!/usr/bin/env python3
"""
Locate "yesterday's" state: ruleset v1, ~25 rules, rules pack, dictionaries, aliases, importer, pipeline.
Read-only: no DB writes, no .env changes, no secrets in stdout.
Output: artifacts/yesterday_locator_report.md, .log, and compact stdout.
"""
import json
import os
import re
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
REPORT_MD = ROOT / "artifacts" / "yesterday_locator_report.md"
REPORT_LOG = ROOT / "artifacts" / "yesterday_locator_report.log"

# Rule array keys in params_json / JSON files
RULES_KEYS = ("rules", "rules_registry", "global_rules", "category_rules", "validations", "quality_rules")
RULE_CODE_KEYS = ("rule_code", "rule_type", "severity", "enabled", "category")


def _log(msg: str):
    REPORT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def _run(cmd, cwd=None, capture=True, timeout=30):
    cwd = str(cwd or ROOT)
    try:
        r = subprocess.run(
            cmd if isinstance(cmd, list) else cmd.split(),
            cwd=cwd,
            capture_output=capture,
            text=True,
            timeout=timeout,
        )
        return r.returncode, (r.stdout or "").strip(), (r.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)[:200]


def _rules_count_from_data(data) -> tuple:
    """Return (count, first_5_rule_codes). No secrets."""
    count = 0
    first_codes = []
    if isinstance(data, list):
        for i, item in enumerate(data):
            if isinstance(item, dict):
                code = item.get("rule_code") or item.get("code") or item.get("id")
                if code is not None and str(code).strip():
                    count += 1
                    if len(first_codes) < 5:
                        first_codes.append(str(code)[:80])
            elif isinstance(item, str) and item.strip():
                count += 1
                if len(first_codes) < 5:
                    first_codes.append(str(item)[:80])
        return count, first_codes
    if isinstance(data, dict):
        for key in RULES_KEYS:
            arr = data.get(key)
            if isinstance(arr, list):
                c, fc = _rules_count_from_data(arr)
                if c > count:
                    count = c
                    first_codes = fc
        return count, first_codes
    return 0, []


# ---------- A) Git ----------
def git_snapshot():
    """Current branch, HEAD sha, status count."""
    head_sha = ""
    branch = ""
    dirty = 0
    code, out, _ = _run(["git", "rev-parse", "--short", "HEAD"])
    if code == 0 and out:
        head_sha = out.splitlines()[0]
    code, out, _ = _run(["git", "rev-parse", "--abbrev-ref", "HEAD"])
    if code == 0 and out:
        branch = out.splitlines()[0]
    code, out, _ = _run(["git", "status", "--porcelain"])
    if code == 0 and out:
        dirty = 1 if out.strip() else 0
    return {"head": head_sha, "branch": branch, "dirty": dirty, "status_lines": out.count("\n") + (1 if out.strip() else 0)}


def git_candidates():
    """Tags (30), branches (50 then take 20), stash (up to 20). No network."""
    refs = []
    code, out, _ = _run(["git", "tag", "-l", "--sort=-creatordate"], timeout=15)
    if code == 0 and out:
        refs.extend(out.splitlines()[:30])
    code, out, _ = _run(["git", "branch", "-a", "--sort=-committerdate"], timeout=15)
    if code == 0 and out:
        lines = [x.strip().lstrip("* ") for x in out.splitlines() if x.strip()]
        refs.extend(lines[:20])
    code, out, _ = _run(["git", "stash", "list"], timeout=10)
    if code == 0 and out:
        for line in out.splitlines()[:20]:
            if ":" in line:
                refs.append(line.split(":")[0].strip())
    return refs


def git_probe_ref(ref: str) -> tuple:
    """Get file list for ref (no checkout). Returns (list of paths, success)."""
    code, out, _ = _run(["git", "ls-tree", "-r", ref, "--name-only"], timeout=10)
    if code != 0 or not out:
        return [], False
    return out.splitlines(), True


def git_show_file(ref: str, path: str) -> str:
    """Get file content at ref. Returns content or empty."""
    code, out, err = _run(["git", "show", f"{ref}:{path}"], timeout=5)
    if code != 0:
        return ""
    return out


def git_score_ref(ref: str, paths: list) -> tuple:
    """Score and signals for this ref. No checkout."""
    score = 0
    signals = []
    paths_lower = [p.lower() for p in paths]
    # +30 rulesets_export_*.zip or docs export/rules pack
    if any("artifacts/rulesets_export" in p and p.endswith(".zip") for p in paths_lower):
        score += 30
        signals.append("artifacts/rulesets_export_*.zip")
    for p in paths_lower:
        if "docs/" in p and ("export" in p or "rules pack" in p or "ruleset" in p):
            score += 30
            signals.append("docs export/rules pack")
            break
    # +30 rules_pack* or rulesets/ / registries/
    if any("rules_pack" in p and (p.endswith(".xlsx") or p.endswith(".csv") or p.endswith(".json")) for p in paths_lower):
        score += 30
        signals.append("rules_pack*.xlsx/csv/json")
    if any("rulesets/" in p or "/registries" in p for p in paths_lower):
        score += 30
        signals.append("rulesets/ or registries/")
    # +20 importrules* / rules_pack_import*
    if any("scripts/dev/" in p and ("importrule" in p or "rules_pack_import" in p) for p in paths_lower):
        score += 20
        signals.append("scripts/dev importrules/rules_pack_import")
    # +10 RUNBOOK rules
    if any("runbook" in p for p in paths_lower):
        runbook_path = next((p for p in paths if "runbook" in p.lower()), None)
        if runbook_path:
            content = git_show_file(ref, runbook_path)
            if content and ("rules" in content.lower() or "ruleset import" in content.lower()):
                score += 10
                signals.append("RUNBOOK rules/ruleset import")
    # +10 evidence rules/pack/25
    if any("evidence/" in p for p in paths_lower):
        for ep in paths:
            if "evidence/" not in ep:
                continue
            content = git_show_file(ref, ep)
            if content and ("rules" in content or "pack" in content or "25" in content):
                score += 10
                signals.append("evidence rules/pack/25")
                break
    # +20 rules list >= 20 in file
    for p in paths:
        if not (".json" in p or ".yaml" in p or ".yml" in p) or "rule" not in p.lower():
            continue
        content = git_show_file(ref, p)
        if not content:
            continue
        try:
            if p.endswith(".json"):
                data = json.loads(content)
            else:
                try:
                    import yaml
                    data = yaml.safe_load(content)
                except Exception:
                    continue
        except Exception:
            continue
        cnt, _ = _rules_count_from_data(data)
        if cnt >= 20:
            score += 20
            signals.append(f"rules_count={cnt}")
            break
    return score, signals


# ---------- B) MongoDB ----------
def mongo_db_candidates():
    """List all DBs (except admin/local/config), score each. Read-only."""
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
    results = []
    for db_name in dbs:
        db = client[db_name]
        score = 0
        counts = {}
        rules_len_max = 0
        first_codes = []
        try:
            if "rulesets" in db.list_collection_names():
                c = db.rulesets.count_documents({})
                counts["rulesets"] = c
                if c > 0:
                    score += 20
            if "ruleset_versions" in db.list_collection_names():
                c = db.ruleset_versions.count_documents({})
                counts["ruleset_versions"] = c
                if c > 0:
                    score += 20
                for doc in db.ruleset_versions.find({}).limit(10):
                    p = doc.get("params_json")
                    if p is None:
                        continue
                    if isinstance(p, str):
                        try:
                            p = json.loads(p)
                        except Exception:
                            continue
                    if not isinstance(p, dict):
                        continue
                    for key in RULES_KEYS:
                        arr = p.get(key)
                        if isinstance(arr, list) and len(arr) >= 20:
                            score += 40
                            cnt, fc = _rules_count_from_data(arr)
                            if cnt > rules_len_max:
                                rules_len_max = cnt
                                first_codes = fc
                    if rules_len_max == 0:
                        for key in RULES_KEYS:
                            arr = p.get(key)
                            if isinstance(arr, list):
                                cnt, fc = _rules_count_from_data(arr)
                                if cnt > rules_len_max:
                                    rules_len_max = cnt
                                    first_codes = fc
            if "category_dictionary_entries" in db.list_collection_names():
                c = db.category_dictionary_entries.count_documents({})
                counts["category_dictionary_entries"] = c
                if c > 0:
                    score += 20
            for coll in ("token_aliases", "aliases", "dict_aliases", "brand_aliases"):
                if coll in db.list_collection_names() and db[coll].count_documents({}) > 0:
                    counts[coll] = db[coll].count_documents({})
                    score += 15
                    break
            if "pipeline_runs" in db.list_collection_names():
                c = db.pipeline_runs.count_documents({})
                counts["pipeline_runs"] = c
                if c > 0:
                    score += 10
            si = db.supplier_items.count_documents({}) if "supplier_items" in db.list_collection_names() else 0
            pl = db.pricelists.count_documents({}) if "pricelists" in db.list_collection_names() else 0
            counts["supplier_items"] = si
            counts["pricelists"] = pl
            if si > 0 and pl > 0:
                score += 10
        except Exception as e:
            _log("DB %s error: %s" % (db_name, str(e)[:100]))
        results.append({
            "db_name": db_name,
            "score": score,
            "counts": counts,
            "rules_len_max": rules_len_max,
            "first_codes": first_codes[:5],
        })
    return sorted(results, key=lambda x: -x["score"])


# ---------- C) Artifacts ----------
def artifacts_scan():
    """Scan artifacts/ for rules-related files, count rules."""
    artifacts_dir = ROOT / "artifacts"
    if not artifacts_dir.is_dir():
        return [], 0
    findings = []
    rules_count_max = 0
    found_export_zip = False
    found_rules_pack = False
    for f in artifacts_dir.iterdir():
        if f.is_dir():
            continue
        name = f.name.lower()
        path_str = str(f)
        if not (".zip" in name or ".json" in name or ".xlsx" in name or ".csv" in name):
            continue
        if not any(k in name or k in path_str.lower() for k in ("rule", "ruleset", "export", "pack", "dict", "alias")):
            continue
        if "rulesets_export" in name and name.endswith(".zip"):
            found_export_zip = True
        if "rules_pack" in name or ("rule" in name and ("pack" in name or "registry" in name)):
            found_rules_pack = True
        entry = {"path": path_str, "rules_count": 0}
        if f.suffix.lower() == ".zip":
            try:
                with zipfile.ZipFile(f, "r") as z:
                    for zi in z.namelist():
                        if "rules" in zi.lower() or "registry" in zi.lower():
                            with z.open(zi) as fp:
                                raw = fp.read(50000).decode("utf-8", errors="ignore")
                                try:
                                    data = json.loads(raw)
                                    cnt, _ = _rules_count_from_data(data)
                                    if cnt > entry["rules_count"]:
                                        entry["rules_count"] = cnt
                                except Exception:
                                    pass
            except Exception:
                pass
        elif f.suffix.lower() == ".json":
            try:
                text = f.read_text(encoding="utf-8", errors="ignore")
                data = json.loads(text)
                cnt, _ = _rules_count_from_data(data)
                entry["rules_count"] = cnt
            except Exception:
                pass
        elif f.suffix.lower() in (".csv", ".xlsx"):
            try:
                import pandas as pd
                if f.suffix.lower() == ".csv":
                    df = pd.read_csv(f, nrows=100, sep=";")
                else:
                    df = pd.read_excel(f, nrows=100)
                if "rule_code" in df.columns or "rule_code" in [str(c).lower() for c in df.columns]:
                    cnt = df["rule_code"].count() if "rule_code" in df.columns else 0
                    if cnt == 0:
                        for c in df.columns:
                            if "rule" in str(c).lower():
                                cnt = df[c].count()
                                break
                    entry["rules_count"] = int(cnt)
            except Exception:
                pass
        if entry["rules_count"] > 0:
            findings.append(entry)
            rules_count_max = max(rules_count_max, entry["rules_count"])
    score = 0
    if rules_count_max >= 20:
        score += 50
    if found_rules_pack:
        score += 30
    if found_export_zip:
        score += 20
    return findings, rules_count_max, score


# ---------- Report ----------
def write_report(git_snap, git_top, db_top, art_findings, art_rules_max, art_score):
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Yesterday state locator report",
        "",
        "## 1. GIT_SNAPSHOT",
        "| Field | Value |",
        "|-------|-------|",
        "| repo_root | %s |" % ROOT,
        "| head | %s |" % git_snap.get("head", ""),
        "| branch | %s |" % git_snap.get("branch", ""),
        "| dirty | %s |" % git_snap.get("dirty", 0),
        "| status_porcelain_lines | %s |" % git_snap.get("status_lines", 0),
        "",
        "## 2. GIT_TOP_CANDIDATES",
        "| ref | score | signals_found |",
        "|-----|-------|---------------|",
    ]
    for r in git_top[:10]:
        lines.append("| %s | %s | %s |" % (r.get("ref", ""), r.get("score", 0), "; ".join(r.get("signals", [])) or "-"))
    if not git_top:
        lines.append("| (none) | 0 | - |")
    lines.extend([
        "",
        "## 3. DB_TOP_CANDIDATES",
        "| db_name | score | counts | rules_len_max |",
        "|---------|-------|--------|---------------|",
    ])
    for r in db_top[:10]:
        lines.append("| %s | %s | %s | %s |" % (
            r.get("db_name", ""),
            r.get("score", 0),
            json.dumps(r.get("counts", {}))[:60],
            r.get("rules_len_max", 0),
        ))
    if not db_top:
        lines.append("| (none) | 0 | - | 0 |")
    lines.extend([
        "",
        "## 4. ARTIFACTS_FINDINGS",
        "",
    ])
    for x in art_findings:
        lines.append("- %s rules_count=%s" % (x.get("path", ""), x.get("rules_count", 0)))
    if not art_findings:
        lines.append("- (none)")
    lines.append("")
    lines.append("rules_count_max=%s" % art_rules_max)
    lines.append("")
    best_git = git_top[0] if git_top else None
    best_db = db_top[0] if db_top else None
    best_artifact = (art_findings[0].get("path", "NONE") if art_findings else "NONE") if art_findings else ("artifacts (see list above)" if art_rules_max else "NONE")
    rec = "NEED_EXTERNAL_SOURCE_OR_IT_WAS_NEVER_COMMITTED"
    if best_git and best_git.get("score", 0) > 0:
        rec = "Try: git show %s --name-only (then restore needed files)" % best_git.get("ref", "")
    if best_db and best_db.get("score", 0) > 0:
        rec = "Set DB_NAME=%s in .env (manually) and run check_core_engine_v1" % best_db.get("db_name", "")
    if art_rules_max >= 20:
        rec = "Import from artifacts (rules pack/export) into test_database (separate task)"
    lines.extend([
        "## 5. BEST_GUESS",
        "",
        "| Key | Value |",
        "|-----|-------|",
        "| BEST_GIT_REF | %s |" % (best_git.get("ref", "") if best_git else "NONE"),
        "| BEST_DB | %s |" % (best_db.get("db_name", "") if best_db else "NONE"),
        "| BEST_ARTIFACT | %s |" % (best_artifact if best_artifact else "NONE"),
        "| RECOMMENDED_NEXT_STEP | %s |" % rec,
    ])
    REPORT_MD.write_text("\n".join(lines), encoding="utf-8")


def main():
    if REPORT_LOG.exists():
        REPORT_LOG.write_text("")
    _log("start locate_yesterday_state")
    git_snap = git_snapshot()
    _log("git_snap: %s" % git_snap)
    refs = git_candidates()
    _log("git refs count: %s" % len(refs))
    git_results = []
    for ref in refs:
        paths, ok = git_probe_ref(ref)
        if not ok:
            continue
        score, signals = git_score_ref(ref, paths)
        git_results.append({"ref": ref, "score": score, "signals": signals})
    git_top = sorted(git_results, key=lambda x: -x["score"])[:10]
    db_top = mongo_db_candidates()
    _log("db_top count: %s" % len(db_top))
    art_findings, art_rules_max, art_score = artifacts_scan()
    write_report(git_snap, git_top, db_top, art_findings, art_rules_max, art_score)
    best_git = git_top[0] if git_top else None
    best_db = db_top[0] if db_top else None
    rec = "NEED_EXTERNAL_SOURCE_OR_IT_WAS_NEVER_COMMITTED"
    if best_git and best_git.get("score", 0) > 0:
        rec = "Try git show %s then restore needed files" % best_git.get("ref", "")
    if best_db and best_db.get("score", 0) > 0:
        rec = "Set DB_NAME=%s (manually) and run check_core_engine_v1" % best_db.get("db_name", "")
    if art_rules_max >= 20:
        rec = "Import from artifacts into test_database (separate task)"
    print("LOCATOR_OK report=%s" % REPORT_MD)
    print("CURRENT head=%s branch=%s dirty=%s" % (git_snap.get("head", ""), git_snap.get("branch", ""), git_snap.get("dirty", 0)))
    print("BEST_GIT_REF=%s score=%s" % (best_git.get("ref", "NONE") if best_git else "NONE", best_git.get("score", 0) if best_git else 0))
    print("BEST_DB=%s score=%s rules_len_max=%s" % (
        best_db.get("db_name", "NONE") if best_db else "NONE",
        best_db.get("score", 0) if best_db else 0,
        best_db.get("rules_len_max", 0) if best_db else 0,
    ))
    best_art_str = "NONE"
    if art_findings and art_rules_max > 0:
        best_art_str = art_findings[0].get("path", "NONE")
    elif art_rules_max > 0:
        best_art_str = "artifacts (see report)"
    print("BEST_ARTIFACT=%s rules_count_max=%s" % (best_art_str, art_rules_max))
    print("RECOMMENDED=%s" % rec)


if __name__ == "__main__":
    main()
