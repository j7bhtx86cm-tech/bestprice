#!/usr/bin/env python3
"""Smoke: /docs then 3 logins (integrita, romax, gmfuel). Stdout 3 lines. Details in artifacts/auth_smoke_triple.log."""
import json
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOG_FILE = ROOT / "artifacts" / "auth_smoke_triple.log"
BASE = "http://127.0.0.1:8001"
DOCS_WAIT_SEC = 25

LOGINS = [
    ("integrita.supplier@example.com", "Integrita#2026", "INTEGRITA"),
    ("romax.supplier@example.com", "Romax#2026", "ROMAX"),
    ("gmfuel@gmail.com", "Krevetochna#2026", "GMFUEL"),
]


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def docs_200():
    try:
        req = urllib.request.Request(BASE + "/docs", method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")

    if not docs_200():
        log("Docs not 200, running ensure_backend_up.py")
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "dev" / "ensure_backend_up.py")],
            cwd=str(ROOT),
            capture_output=True,
            timeout=90,
        )
        deadline = time.monotonic() + DOCS_WAIT_SEC
        while time.monotonic() < deadline:
            if docs_200():
                break
            time.sleep(1)
        if not docs_200():
            print("DOCS_NOT_200")
            sys.exit(1)

    results = []
    for email, password, label in LOGINS:
        try:
            data = json.dumps({"email": email, "password": password}).encode("utf-8")
            req = urllib.request.Request(
                BASE + "/api/auth/login",
                data=data,
                method="POST",
                headers={"Content-Type": "application/json"},
            )
            with urllib.request.urlopen(req, timeout=10) as r:
                status = r.status
                body = json.loads(r.read().decode())
        except urllib.error.HTTPError as e:
            status = e.code
            try:
                body = json.loads(e.read().decode())
            except Exception:
                body = {}
        except Exception as e:
            status = 0
            body = {"detail": str(e)}
        log("%s status=%s" % (label, status))
        ok = status == 200 and body.get("access_token")
        results.append((label, ok, status))

    for label, ok, status in results:
        if ok:
            print("%s_LOGIN_OK" % label)
        else:
            print("%s_LOGIN_FAIL status=%s" % (label, status))

    if not all(ok for _, ok, _ in results):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
