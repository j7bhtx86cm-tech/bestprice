#!/usr/bin/env python3
"""
Core Engine v1 — one-command selfcheck (self-contained).
- Ensures backend on 127.0.0.1:8001 is up (starts via ensure_backend_up.py if not).
- Runs E2E (e2e_import_pipeline_v1.py) with timeout; streams output to artifacts/core_engine_selfcheck_v1.log.
- Always stops backend in finally (stop_backend_8001.py).
- Stdout: exactly one line — ✅ CORE_ENGINE_OK or ❌ CORE_ENGINE_FAIL: <reason>.
"""
import json
import os
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ARTIFACTS = ROOT / "artifacts"
LOG_FILE = ARTIFACTS / "core_engine_selfcheck_v1.log"
E2E_SCRIPT = ROOT / "scripts" / "e2e_import_pipeline_v1.py"
E2E_OK_MARKER = "✅ E2E_PIPELINE_OK"
ENSURE_BACKEND = ROOT / "scripts" / "dev" / "ensure_backend_up.py"
STOP_BACKEND = ROOT / "scripts" / "dev" / "stop_backend_8001.py"
BACKEND_URL = "http://127.0.0.1:8001"
BACKEND_READY_TIMEOUT = 20
E2E_POLL_INTERVAL = 0.5
TERM_WAIT_SEC = 5

# Baseline supplier for selfcheck (never use supplier1@example.com)
DEFAULT_SUPPLIER_EMAIL = "integrita.supplier@example.com"
DEFAULT_SUPPLIER_PASSWORD = "Integrita#2026"


def supplier_auth_precheck(logf, email: str, password: str) -> bool:
    """POST /api/auth/login; return True if 200, else log reason and return False."""
    try:
        req = urllib.request.Request(
            BACKEND_URL.rstrip("/") + "/api/auth/login",
            data=json.dumps({"email": email, "password": password}).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=15) as r:
            if r.status == 200:
                return True
            logf.write("SUPPLIER_AUTH_PRECHECK status=%s\n" % r.status)
            logf.flush()
            return False
    except urllib.error.HTTPError as e:
        logf.write("SUPPLIER_AUTH_PRECHECK fail status=%s body=%s\n" % (e.code, (e.read().decode(errors="replace")[:200])))
        logf.flush()
        return False
    except Exception as e:
        logf.write("SUPPLIER_AUTH_PRECHECK error %s\n" % str(e)[:200])
        logf.flush()
        return False


def wait_backend_ready(url: str, timeout_s: int = 20) -> bool:
    """Poll GET {url}/docs every 0.5–1s; success = HTTP 200. Returns True if ready, False on timeout."""
    deadline = time.monotonic() + timeout_s
    check_url = url.rstrip("/") + "/docs"
    while time.monotonic() < deadline:
        try:
            req = urllib.request.Request(check_url, method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                if r.status == 200:
                    return True
        except urllib.error.HTTPError as e:
            if e.code == 200:
                return True
        except Exception:
            pass
        time.sleep(0.75)
    return False


def ensure_backend_up(logf):
    """Run ensure_backend_up.py (no stdout to console)."""
    if not ENSURE_BACKEND.exists():
        logf.write("ENSURE_BACKEND_SCRIPT_MISSING\n")
        logf.flush()
        return False
    r = subprocess.run(
        [sys.executable, str(ENSURE_BACKEND)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=90,
    )
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    logf.write("ensure_backend_up stdout: %s\n" % out)
    if err:
        logf.write("ensure_backend_up stderr: %s\n" % err)
    logf.flush()
    return r.returncode == 0 and "BACKEND_UP_OK" in out


def stop_backend():
    """Run stop_backend_8001.py and append BACKEND_STOPPED_OK or BACKEND_STOP_FAILED to log."""
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            if STOP_BACKEND.exists():
                r = subprocess.run(
                    [sys.executable, str(STOP_BACKEND)],
                    cwd=str(ROOT),
                    capture_output=True,
                    text=True,
                    timeout=15,
                )
                if r.returncode == 0 and "BACKEND_STOPPED_OK" in (r.stdout or ""):
                    f.write("BACKEND_STOPPED_OK\n")
                else:
                    f.write("BACKEND_STOPPED_FAIL\n")
            else:
                f.write("BACKEND_STOPPED_FAIL (script missing)\n")
    except Exception as e:
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write("BACKEND_STOPPED_FAIL: %s\n" % e)
        except Exception:
            pass


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    timeout_s = int(os.environ.get("CORE_ENGINE_SELFCHK_TIMEOUT", "420"))
    final_result = None  # (message, exit_code)

    try:
        events_log = ROOT / "artifacts" / "pipeline_events.log"
        if events_log.exists():
            try:
                with open(events_log, "w", encoding="utf-8"):
                    pass
            except Exception:
                pass
        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(LOG_FILE, "w", encoding="utf-8") as logf:
            # --- Backend ready ---
            if wait_backend_ready(BACKEND_URL, timeout_s=BACKEND_READY_TIMEOUT):
                logf.write("BACKEND_READY\n")
                logf.flush()
            else:
                logf.write("BACKEND_NOT_READY, starting ensure_backend_up...\n")
                logf.flush()
                if ensure_backend_up(logf) and wait_backend_ready(BACKEND_URL, timeout_s=BACKEND_READY_TIMEOUT):
                    logf.write("BACKEND_READY\n")
                    logf.flush()
                else:
                    logf.write("BACKEND_NOT_READY\n")
                    logf.flush()
                    final_result = ("BACKEND_NOT_READY", 1)

            if final_result is None:
                # Resolve supplier credentials: default Integrita (never supplier1@example.com)
                supplier_email = os.environ.get("SUPPLIER_EMAIL", "").strip()
                supplier_password = os.environ.get("SUPPLIER_PASSWORD", "")
                if not supplier_email:
                    supplier_email = DEFAULT_SUPPLIER_EMAIL
                    supplier_password = DEFAULT_SUPPLIER_PASSWORD
                    os.environ["SUPPLIER_EMAIL"] = supplier_email
                    os.environ["SUPPLIER_PASSWORD"] = supplier_password
                    logf.write("SELFCHK_SUPPLIER_EMAIL=integrita.supplier@example.com (default)\n")
                else:
                    if not supplier_password:
                        supplier_password = os.environ.get("SUPPLIER_PASSWORD", DEFAULT_SUPPLIER_PASSWORD)
                    logf.write("SELFCHK_SUPPLIER_EMAIL=<from env>\n")
                logf.flush()

                # Pre-check: supplier auth must succeed before long E2E
                if not supplier_auth_precheck(logf, supplier_email, supplier_password):
                    logf.write("SUPPLIER_AUTH_FAIL\n")
                    logf.flush()
                    final_result = ("SUPPLIER_AUTH_FAIL", 1)

            if final_result is None:
                logf.write("E2E_STARTED\n")
                logf.flush()

                proc = subprocess.Popen(
                    [sys.executable, str(E2E_SCRIPT)],
                    cwd=str(ROOT),
                    stdin=subprocess.DEVNULL,
                    stdout=logf,
                    stderr=subprocess.STDOUT,
                    env=dict(os.environ),
                )

                deadline = time.monotonic() + timeout_s
                while time.monotonic() < deadline:
                    ret = proc.poll()
                    if ret is not None:
                        break
                    time.sleep(E2E_POLL_INTERVAL)

                if proc.poll() is None:
                    proc.terminate()
                    time.sleep(TERM_WAIT_SEC)
                    try:
                        proc.kill()
                    except Exception:
                        pass
                    logf.write("\nE2E_TIMEOUT\n")
                    logf.flush()
                    final_result = ("E2E_TIMEOUT", 1)
                else:
                    logf.flush()

        if final_result is None:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()
            if E2E_OK_MARKER in content:
                final_result = (None, 0)
            else:
                reason = "E2E_NOT_OK"
                for line in reversed(content.splitlines()):
                    line = line.strip()
                    if line.startswith("E2E_FAIL:"):
                        reason = line[:200]
                        break
                final_result = (reason, 1)

    except Exception as e:
        final_result = (str(e)[:200], 1)
        try:
            with open(LOG_FILE, "a", encoding="utf-8") as f:
                f.write("CORE_ENGINE_ERROR: %s\n" % e)
        except Exception:
            pass
    finally:
        try:
            stop_backend()
        except Exception:
            pass

    if final_result is None:
        final_result = ("E2E_NOT_OK", 1)

    msg, code = final_result
    try:
        with open(LOG_FILE, "a", encoding="utf-8", errors="replace") as f:
            if code == 0:
                f.write("E2E_OK\n")
                # Append pipeline event lines so log contains PIPELINE_SCHEDULED + PIPELINE_RUN_CREATED
                events_log = ROOT / "artifacts" / "pipeline_events.log"
                if events_log.exists():
                    try:
                        with open(events_log, "r", encoding="utf-8", errors="replace") as el:
                            for line in el:
                                line = line.rstrip()
                                if "PIPELINE_SCHEDULED" in line or "PIPELINE_RUN_CREATED" in line:
                                    f.write(line + "\n")
                    except Exception:
                        pass
            elif msg == "E2E_TIMEOUT":
                f.write("E2E_TIMEOUT\n")
            else:
                f.write("E2E_NOT_OK: %s\n" % (msg or "E2E_NOT_OK"))
    except Exception:
        pass

    if code == 0:
        print("✅ CORE_ENGINE_OK")
    else:
        out_msg = (msg or "E2E_NOT_OK").strip()
        if out_msg == "SUPPLIER_AUTH_FAIL":
            print("❌ CORE_ENGINE_FAIL: SUPPLIER_AUTH_FAIL")
        elif not out_msg.startswith("E2E_FAIL:"):
            print("❌ CORE_ENGINE_FAIL: E2E_FAIL: %s" % out_msg)
        else:
            print("❌ CORE_ENGINE_FAIL: %s" % out_msg)
    sys.exit(code)


if __name__ == "__main__":
    main()
