#!/usr/bin/env python3
"""Auth smoke v2: ensure backend up, then POST login for supplier and restaurant. Stdout: two lines. Details in artifacts/auth_smoke_v2.log."""
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
DOCS_URL = "http://127.0.0.1:8001/docs"
WAIT_DOCS_SEC = 20
LOG_FILE = ROOT / "artifacts" / "auth_smoke_v2.log"

SUPPLIER_EMAIL = "integrita.supplier@example.com"
SUPPLIER_PASSWORD = "Integrita#2026"
RESTAURANT_EMAIL = "gmfile@gmail.com"
RESTAURANT_PASSWORD = "Krevetochna#2026"


def log(msg):
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def docs_ok():
    try:
        import urllib.request
        req = urllib.request.Request(DOCS_URL, method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def ensure_backend_up():
    subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "dev" / "ensure_backend_up.py")],
        cwd=str(ROOT),
        capture_output=True,
        timeout=90,
    )
    deadline = time.monotonic() + WAIT_DOCS_SEC
    while time.monotonic() < deadline:
        if docs_ok():
            return True
        time.sleep(1)
    return False


def login(email, password):
    import urllib.request
    import urllib.error
    import json
    try:
        data = json.dumps({"email": email, "password": password}).encode("utf-8")
        req = urllib.request.Request(
            API_BASE_URL + "/api/auth/login",
            data=data,
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode())
        except Exception:
            body = {"detail": str(e.code)}
        return e.code, body
    except Exception as e:
        return 0, {"detail": str(e)}


def main():
    LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "w", encoding="utf-8") as f:
        f.write("")  # truncate

    if not docs_ok():
        log("Docs not responding, running ensure_backend_up.py")
        if not ensure_backend_up():
            log("ensure_backend_up / docs wait failed")
            print("SUPPLIER_LOGIN_FAIL: status=backend_not_up detail=docs_not_200")
            print("RESTAURANT_LOGIN_FAIL: status=backend_not_up detail=docs_not_200")
            sys.exit(1)

    # Supplier login
    status_s, body_s = login(SUPPLIER_EMAIL, SUPPLIER_PASSWORD)
    log("Supplier login: status=%s body=%s" % (status_s, body_s))
    if status_s == 200 and body_s.get("access_token"):
        print("SUPPLIER_LOGIN_OK")
    else:
        print("SUPPLIER_LOGIN_FAIL: status=%s detail=%s" % (status_s, body_s.get("detail", body_s)))

    # Restaurant login
    status_r, body_r = login(RESTAURANT_EMAIL, RESTAURANT_PASSWORD)
    log("Restaurant login: status=%s body=%s" % (status_r, body_r))
    if status_r == 200 and body_r.get("access_token"):
        print("RESTAURANT_LOGIN_OK")
    else:
        print("RESTAURANT_LOGIN_FAIL: status=%s detail=%s" % (status_r, body_r.get("detail", body_r)))

    if (status_s != 200) or (status_r != 200):
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
