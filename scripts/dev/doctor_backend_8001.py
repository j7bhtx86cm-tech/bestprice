#!/usr/bin/env python3
"""Diagnose backend on 8001: port listener, /docs, .env, last 60 lines of backend log. Stdout: DOCTOR_OK or DOCTOR_FAIL: <reason>. Details in artifacts/doctor_backend_8001.log."""
import os
import subprocess
import sys
import urllib.request
import urllib.error
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent


def _repo_root():
    cand = SCRIPT_DIR.parents[2]
    if (cand / "backend").is_dir():
        return cand
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(SCRIPT_DIR),
        capture_output=True,
        text=True,
        timeout=5,
    )
    if out.returncode == 0 and out.stdout:
        return Path(out.stdout.strip()).resolve()
    return cand


REPO_ROOT = _repo_root()
PORT = 8001
DOCS_URL = "http://127.0.0.1:%s/docs" % PORT
DOCTOR_LOG = REPO_ROOT / "artifacts" / "doctor_backend_8001.log"
BACKEND_LOG = REPO_ROOT / "artifacts" / "dev_backend_8001.log"
ENV_FILE = REPO_ROOT / "backend" / ".env"


def log(msg):
    DOCTOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DOCTOR_LOG, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def main():
    DOCTOR_LOG.parent.mkdir(parents=True, exist_ok=True)
    with open(DOCTOR_LOG, "w", encoding="utf-8") as f:
        f.write("")  # truncate

    docs_ok = False
    reason = None

    # 1) Who listens on 8001
    try:
        out = subprocess.run(
            ["lsof", "-nP", "-iTCP:%s" % PORT, "-sTCP:LISTEN"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if out.stdout and out.stdout.strip():
            log("Port %s listeners:\n%s" % (PORT, out.stdout.strip()))
        else:
            log("Port %s: no listeners" % PORT)
    except FileNotFoundError:
        log("lsof not available")
    except Exception as e:
        log("lsof error: %s" % e)

    # 2) GET /docs — only this determines DOCTOR_OK
    try:
        req = urllib.request.Request(DOCS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            if r.status == 200:
                log("/docs: 200 OK")
                docs_ok = True
            else:
                log("/docs: status=%s" % r.status)
                reason = "DOCS_STATUS_%s" % r.status
    except urllib.error.HTTPError as e:
        log("/docs: HTTPError %s" % e.code)
        reason = "DOCS_HTTP_%s" % e.code
    except Exception as e:
        log("/docs: %s" % e)
        reason = "DOCS_REQUEST_FAIL"

    # 3) backend/.env and MONGO_URL, DB_NAME
    if not ENV_FILE.exists():
        log("backend/.env: missing")
        if not docs_ok and reason is None:
            reason = "ENV_FILE_MISSING"
    else:
        log("backend/.env: exists")
        env_content = ENV_FILE.read_text(encoding="utf-8")
        env_vars = {}
        for line in env_content.splitlines():
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, _, v = line.partition("=")
                env_vars[k.strip()] = v.strip().strip('"').strip("'")
        if "MONGO_URL" not in env_vars or not env_vars.get("MONGO_URL"):
            log("MONGO_URL: missing or empty")
            if not docs_ok and reason is None:
                reason = "MISSING_ENV: MONGO_URL"
        else:
            log("MONGO_URL: set")
        if "DB_NAME" not in env_vars or not env_vars.get("DB_NAME"):
            log("DB_NAME: missing or empty")
            if not docs_ok and reason is None:
                reason = "MISSING_ENV: DB_NAME"
        else:
            log("DB_NAME: %s" % env_vars.get("DB_NAME", ""))

    # 4) Last 60 lines of dev_backend_8001.log
    if BACKEND_LOG.exists():
        lines = BACKEND_LOG.read_text(encoding="utf-8").splitlines()
        last60 = lines[-60:] if len(lines) > 60 else lines
        log("--- last 60 lines of dev_backend_8001.log ---")
        for line in last60:
            log(line)
    else:
        log("artifacts/dev_backend_8001.log: missing")

    if docs_ok:
        print("DOCTOR_OK")
        sys.exit(0)
    print("DOCTOR_FAIL: %s" % (reason or "UNKNOWN"))
    sys.exit(1)


if __name__ == "__main__":
    main()
