#!/usr/bin/env python3
"""Full audit: git, .env, MongoDB, backend runtime, code presence. Report to artifacts/audit_report.md. No secrets in output."""
import os
import re
import subprocess
import sys
import urllib.request
import urllib.error
import json
from pathlib import Path
from datetime import datetime, timezone

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2]
if not (ROOT / "backend").is_dir():
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=5,
    )
    if out.returncode == 0 and out.stdout:
        ROOT = Path(out.stdout.strip()).resolve()
REPORT_MD = ROOT / "artifacts" / "audit_report.md"
REPORT_LOG = ROOT / "artifacts" / "audit_report.log"

SAFE_ENV_KEYS = ("MONGO_URL", "DB_NAME", "DEV_AUTH_BYPASS", "CORS_ORIGINS", "APP_ENV")
REQUIRED_EMAILS = ["integrita.supplier@example.com", "romax.supplier@example.com", "gmfuel@gmail.com"]
EXCLUDED_EMAIL = "gmfile@gmail.com"

SKIP_DIRS = {".git", "node_modules", "venv", ".venv", "__pycache__", "dist", "build", ".next"}
CODE_KEYWORDS = [
    ("pipeline", "pipeline_run", "runtime", "scheduler", "job", "queue", "worker"),
    ("rules", "rule", "dict", "alias", "normalize", "classifier", "enrich"),
    ("auto", "generated", "engine", "core_engine", "mapping", "match"),
]
CHECK_FILES = [
    "docs/RUNBOOK_CORE_ENGINE_LOCK.md",
    "scripts/dev/ensure_backend_up.py",
    "scripts/dev/doctor_backend_8001.py",
    "scripts/dev/ensure_auth_fixtures.py",
    "scripts/dev/auth_smoke_triple.py",
]
CHECK_DIRS = ["pipeline", "backend/pipeline", "scripts/core_smoke"]


def log(msg):
    REPORT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def run(cmd, cwd=None, timeout=15):
    cwd = cwd or str(ROOT)
    try:
        out = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout)
        return out.returncode, (out.stdout or "").strip(), (out.stderr or "").strip()
    except Exception as e:
        return -1, "", str(e)


def env_snapshot():
    env_path = ROOT / "backend" / ".env"
    lines = []
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k = line.split("=")[0].strip()
                if k in SAFE_ENV_KEYS:
                    v = line.split("=", 1)[1].strip().strip("'\"").strip()
                    if "MONGO" in k and "localhost" not in v:
                        v = "***"
                    lines.append("%s=%s" % (k, v))
    return "\n".join(lines) if lines else "(no .env or no safe keys)"


def db_snapshot(mongo_url, db_name):
    try:
        from pymongo import MongoClient
    except ImportError:
        return None, "pymongo not available"
    try:
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[db_name]
    except Exception as e:
        return None, str(e)[:200]

    counts = {}
    for coll in ["users", "companies", "pricelists", "supplier_items", "pipeline_runs"]:
        try:
            counts[coll] = db[coll].count_documents({})
        except Exception:
            counts[coll] = 0

    for name in db.list_collection_names():
        if any(name.startswith(p) for p in ["dict", "rules", "aliases", "qa", "reference", "normalized", "catalog"]):
            try:
                counts[name] = db[name].count_documents({})
            except Exception:
                counts[name] = 0

    users_info = []
    for email in REQUIRED_EMAILS:
        u = db.users.find_one({"email": email}, {"_id": 0, "email": 1, "role": 1, "id": 1})
        if not u:
            users_info.append({"email": email, "role": "-", "company_id": False, "company_name": "-", "company_type": "-"})
            continue
        c = db.companies.find_one({"userId": u.get("id")}, {"_id": 0, "id": 1, "companyName": 1, "name": 1, "type": 1})
        if c:
            users_info.append({
                "email": email,
                "role": u.get("role", "-"),
                "company_id": True,
                "company_name": c.get("companyName") or c.get("name", "-"),
                "company_type": c.get("type", "-"),
            })
        else:
            users_info.append({"email": email, "role": u.get("role", "-"), "company_id": False, "company_name": "-", "company_type": "-"})

    gmfile_absent = db.users.find_one({"email": EXCLUDED_EMAIL}, {"_id": 1}) is None

    return {
        "counts": counts,
        "users_info": users_info,
        "gmfile_absent": gmfile_absent,
    }, None


def backend_snapshot():
    status_docs = None
    try:
        req = urllib.request.Request("http://127.0.0.1:8001/docs", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            status_docs = r.status
    except urllib.error.HTTPError as e:
        status_docs = e.code
    except Exception:
        status_docs = 0

    backend_up = status_docs == 200
    openapi_info = ""
    paths_count = 0
    if backend_up:
        try:
            req = urllib.request.Request("http://127.0.0.1:8001/openapi.json", method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                data = json.loads(r.read().decode())
                info = data.get("info", {})
                openapi_info = "title=%s version=%s" % (info.get("title", ""), info.get("version", ""))
                paths_count = len(data.get("paths", {}))
        except Exception:
            openapi_info = "fetch failed"
    return {
        "backend_up": backend_up,
        "docs_status": status_docs,
        "openapi_info": openapi_info,
        "paths_count": paths_count,
    }


def code_audit():
    results = []
    for group in CODE_KEYWORDS:
        found = []
        for keyword in group:
            for path in ROOT.rglob("*.py"):
                if any(s in path.parts for s in SKIP_DIRS):
                    continue
                try:
                    text = path.read_text(encoding="utf-8", errors="ignore")
                    if keyword in text:
                        rel = path.relative_to(ROOT)
                        for line in text.splitlines():
                            if keyword in line:
                                found.append("%s: %s" % (rel, line.strip()[:80]))
                                break
                        if len(found) >= 5:
                            break
                except Exception:
                    pass
            if len(found) >= 5:
                break
        results.append((group[0], found[:5]))

    files_found = []
    for rel in CHECK_FILES:
        p = ROOT / rel
        files_found.append("%s: %s" % (rel, "yes" if p.exists() else "no"))

    dirs_found = []
    for rel in CHECK_DIRS:
        p = ROOT / rel
        dirs_found.append("%s: %s" % (rel, "yes" if p.is_dir() else "no"))

    return {"keyword_matches": results, "files": files_found, "dirs": dirs_found}


def build_diagnosis(git_dirty, db_data, backend_data, code_data):
    code_state = "частично"
    if code_data:
        has_pipeline = any("pipeline" in str(m) for _, matches in code_data.get("keyword_matches", []) for m in matches)
        has_rules = any("rule" in str(m) for _, matches in code_data.get("keyword_matches", []) for m in matches)
        if has_pipeline and has_rules:
            code_state = "да"
        elif has_pipeline or has_rules:
            code_state = "частично"
        else:
            code_state = "нет"

    db_state = "нет данных"
    if db_data:
        c = db_data.get("counts", {})
        if (c.get("pricelists", 0) or c.get("supplier_items", 0) or c.get("companies", 0)) > 0:
            db_state = "есть данные (прайсы/товары/компании)"
        if c.get("pipeline_runs", 0) > 0:
            db_state += "; pipeline_runs>0"

    causes = []
    if git_dirty:
        causes.append("UNCOMMITTED_CHANGES_LOST")
    if db_data and db_data.get("counts", {}).get("pricelists", 0) == 0 and db_data.get("counts", {}).get("supplier_items", 0) == 0:
        causes.append("DATA_RESET_BY_FIXTURES")
    if db_data and not all(u.get("company_id") for u in db_data.get("users_info", [])):
        causes.append("UI_LINKS_NOT_CREATED_YET")
    if not causes:
        causes.append("NONE")

    manual = [
        "Проверить в UI: логин Integrita/Romax/gmfuel, наличие компаний.",
        "Проверить «Мои рестораны» у поставщика и список поставщиков у ресторана.",
        "Проверить загрузку прайсов и каталог.",
    ]
    return {
        "CODE_STATE": code_state,
        "DB_STATE": db_state,
        "MISMATCH_RISK": causes,
        "MANUAL_CHECK": manual[:3],
    }


def main():
    REPORT_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_LOG, "w", encoding="utf-8") as f:
        f.write("audit_everything.py started %s\n" % datetime.now(timezone.utc).isoformat())

    try:
        from dotenv import load_dotenv
        load_dotenv(ROOT / "backend" / ".env", override=False)
    except Exception:
        pass
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")

    sections = []

    # 1.1 GIT_SNAPSHOT
    git_lines = []
    for cmd, desc in [
        (["git", "rev-parse", "--show-toplevel"], "toplevel"),
        (["git", "branch", "--show-current"], "branch"),
        (["git", "rev-parse", "--short", "HEAD"], "short_head"),
        (["git", "log", "-1", "--oneline", "--decorate"], "log1"),
        (["git", "status", "--porcelain"], "status"),
        (["git", "tag", "--points-at", "HEAD"], "tags"),
        (["git", "reflog", "-n", "30", "--date=iso"], "reflog"),
        (["git", "log", "--since=2 days ago", "--oneline", "--decorate", "--graph", "-n", "80"], "log_2d"),
        (["git", "stash", "list"], "stash"),
    ]:
        code, out, err = run(cmd)
        git_lines.append("--- %s (exit %s) ---\n%s" % (desc, code, out or "(empty)"))
    sections.append("## GIT_SNAPSHOT\n\n%s" % "\n\n".join(git_lines))

    # 1.2 ENV_SNAPSHOT
    sections.append("## ENV_SNAPSHOT\n\n```\n%s\n```" % env_snapshot())

    # 1.3 DB_SNAPSHOT
    db_data, db_err = db_snapshot(mongo_url, db_name)
    if db_err:
        sections.append("## DB_SNAPSHOT\n\nError: %s" % db_err)
    else:
        lines = ["Counts:"]
        for k, v in sorted(db_data["counts"].items()):
            lines.append("  %s: %s" % (k, v))
        lines.append("\nUsers (3 required + gmfile absent):")
        for u in db_data["users_info"]:
            lines.append("  email=%s role=%s company_id=%s company_name=%s company_type=%s" % (
                u["email"], u["role"], u["company_id"], u["company_name"], u["company_type"]))
        lines.append("  gmfile@gmail.com absent: %s" % db_data["gmfile_absent"])
        sections.append("## DB_SNAPSHOT\n\n%s" % "\n".join(lines))

    # 1.4 BACKEND_SNAPSHOT
    be = backend_snapshot()
    sections.append("## BACKEND_SNAPSHOT\n\nbackend_up=%s docs_status=%s openapi=%s paths_count=%s" % (
        be["backend_up"], be["docs_status"], be["openapi_info"], be["paths_count"]))

    # 1.5 CODE_AUDIT
    code_data = code_audit()
    lines = ["Keyword groups (sample matches):"]
    for kw, matches in code_data["keyword_matches"]:
        lines.append("  [%s] %s" % (kw, matches[:3]))
    lines.append("\nFiles: " + "; ".join(code_data["files"]))
    lines.append("Dirs: " + "; ".join(code_data["dirs"]))
    sections.append("## CODE_AUDIT\n\n%s" % "\n".join(lines))

    # 1.6 DIAGNOSIS
    code, status_out, _ = run(["git", "status", "--porcelain"])
    git_dirty = 1 if (status_out and status_out.strip()) else 0
    diag = build_diagnosis(git_dirty, db_data, be, code_data)
    diag_lines = [
        "CODE_STATE: %s" % diag["CODE_STATE"],
        "DB_STATE: %s" % diag["DB_STATE"],
        "MISMATCH_RISK: %s" % ", ".join(diag["MISMATCH_RISK"]),
        "MANUAL_CHECK:",
    ] + ["  - %s" % m for m in diag["MANUAL_CHECK"]]
    sections.append("## DIAGNOSIS\n\n%s" % "\n".join(diag_lines))

    report_body = "# Audit report\n\nGenerated: %s\n\n%s" % (
        datetime.now(timezone.utc).isoformat(),
        "\n\n".join(sections),
    )
    REPORT_MD.parent.mkdir(parents=True, exist_ok=True)
    REPORT_MD.write_text(report_body, encoding="utf-8")
    log("Report written to %s" % REPORT_MD)

    # Stdout: 3-6 lines
    code, head_short, _ = run(["git", "rev-parse", "--short", "HEAD"])
    code2, branch, _ = run(["git", "branch", "--show-current"])
    head = head_short or "?"
    br = branch or "?"
    print("AUDIT_OK report=artifacts/audit_report.md")
    print("GIT_HEAD=%s branch=%s dirty=%s" % (head, br, git_dirty))
    if db_data:
        c = db_data["counts"]
        print("DB=%s users=%s companies=%s pricelists=%s supplier_items=%s pipeline_runs=%s" % (
            db_name,
            c.get("users", 0),
            c.get("companies", 0),
            c.get("pricelists", 0),
            c.get("supplier_items", 0),
            c.get("pipeline_runs", 0),
        ))
    else:
        print("DB=error %s" % (db_err or ""))
    print("BACKEND_UP=%s docs_status=%s" % (str(be["backend_up"]).lower(), be["docs_status"]))
    print("LIKELY_CAUSE=%s" % ", ".join(diag["MISMATCH_RISK"]))
    sys.exit(0)


if __name__ == "__main__":
    main()
