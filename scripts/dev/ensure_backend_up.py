#!/usr/bin/env python3
"""
Dev: bring backend up on port 8001. Clears port, stops old pid from pidfile, starts uvicorn,
waits for /docs. On fail prints one line BACKEND_UP_FAIL: <reason>. Details in artifacts/dev_backend_8001.log.
"""
import os
import signal
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone

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
HEALTH_URL = "http://127.0.0.1:%s/docs" % PORT
WAIT_MAX_SEC = 25
WAIT_POLL_SEC = 0.8
ARTIFACTS = REPO_ROOT / "artifacts"
LOG_FILE = ARTIFACTS / "dev_backend_8001.log"
PID_FILE = ARTIFACTS / "dev_backend_8001.pid"


def log(msg):
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(msg + "\n")


def clear_pidfile_process():
    """If pidfile exists, check if process is alive; if so stop it (SIGTERM then SIGKILL), then remove pidfile."""
    if not PID_FILE.exists():
        return
    try:
        pid = int(PID_FILE.read_text().strip())
    except Exception:
        PID_FILE.unlink(missing_ok=True)
        return
    try:
        os.kill(pid, 0)
    except OSError:
        PID_FILE.unlink(missing_ok=True)
        return
    log("Stopping existing process from pidfile: pid=%s" % pid)
    for sig in [signal.SIGTERM, signal.SIGKILL]:
        try:
            os.kill(pid, sig)
        except OSError:
            break
        time.sleep(4 if sig == signal.SIGTERM else 1)
    PID_FILE.unlink(missing_ok=True)
    time.sleep(1)


def clear_port_8001():
    """On macOS: lsof -nP -iTCP:8001 -sTCP:LISTEN. If busy, log PIDs and kill (TERM then KILL), recheck."""
    try:
        out = subprocess.run(
            ["lsof", "-nP", "-iTCP:%s" % PORT, "-sTCP:LISTEN"],
            cwd=str(REPO_ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        return
    lines = (out.stdout or "").strip().splitlines()
    if not lines:
        return
    pids = set()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            pids.add(parts[1])
    if not pids:
        return
    log("PORT_8001_BUSY PIDs: %s" % ",".join(sorted(pids)))
    for pid in sorted(pids):
        for sig in ["TERM", "KILL"]:
            try:
                subprocess.run(
                    ["kill", "-%s" % sig, pid],
                    cwd=str(REPO_ROOT),
                    capture_output=True,
                    timeout=3,
                )
                time.sleep(4 if sig == "TERM" else 1)
            except Exception:
                pass
    time.sleep(1)
    out2 = subprocess.run(
        ["lsof", "-nP", "-iTCP:%s" % PORT, "-sTCP:LISTEN"],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        timeout=5,
    )
    if (out2.stdout or "").strip():
        log("PORT still busy after kill")
        raise RuntimeError("PORT_8001_BUSY")


def extract_reason_from_log(lines):
    """Take last ~40 lines, find most meaningful (Traceback, Error, Connection refused, etc.)."""
    if not lines:
        return "UNKNOWN"
    for line in reversed(lines[-40:]):
        s = line.strip()
        if not s:
            continue
        if "ModuleNotFoundError" in s or "ImportError" in s:
            return "UVICORN_IMPORT_ERROR: %s" % s[:120]
        if "Traceback" in s or "Error:" in s or "Exception:" in s:
            return "EXCEPTION: %s" % s[:120]
        if "refused" in s.lower() or "Connection" in s:
            return "MONGO_CONNECT_FAIL" if "mongo" in s.lower() or "27017" in s else ("EXCEPTION: %s" % s[:120])
    return lines[-1].strip()[:120] if lines else "UNKNOWN"


def main():
    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    start_marker = "=== ENSURE_BACKEND_UP START %s ===" % datetime.now(timezone.utc).isoformat()
    log(start_marker)

    backend_dir = REPO_ROOT / "backend"
    if not backend_dir.is_dir():
        log("=== BACKEND_UP_FAIL: BACKEND_DIR_MISSING ===")
        print("BACKEND_UP_FAIL: BACKEND_DIR_MISSING")
        sys.exit(1)

    try:
        clear_pidfile_process()
        clear_port_8001()
    except RuntimeError as e:
        reason = str(e)
        log("=== BACKEND_UP_FAIL: %s ===" % reason)
        print("BACKEND_UP_FAIL: %s" % reason)
        sys.exit(1)

    env = dict(os.environ)
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as logf:
            proc = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "backend.server:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(PORT),
                    "--reload",
                ],
                cwd=str(REPO_ROOT),
                stdout=logf,
                stderr=subprocess.STDOUT,
                env=env,
            )
    except Exception as e:
        reason = "EXCEPTION: %s" % str(e)[:100]
        log("=== BACKEND_UP_FAIL: %s ===" % reason)
        print("BACKEND_UP_FAIL: %s" % reason)
        sys.exit(1)

    with open(PID_FILE, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    deadline = time.monotonic() + WAIT_MAX_SEC
    last_status = None
    while time.monotonic() < deadline:
        time.sleep(WAIT_POLL_SEC)
        poll = proc.poll()
        if poll is not None:
            log("Process exited with code %s" % poll)
            time.sleep(0.5)
            with open(LOG_FILE, "r", encoding="utf-8") as f:
                all_lines = f.readlines()
            reason = extract_reason_from_log(all_lines)
            if "IMPORT" not in reason and "EXCEPTION" not in reason and "MONGO" not in reason:
                reason = "PROCESS_EXIT_CODE_%s" % poll
            log("=== BACKEND_UP_FAIL: %s ===" % reason)
            try:
                PID_FILE.unlink(missing_ok=True)
            except Exception:
                pass
            print("BACKEND_UP_FAIL: %s" % reason)
            sys.exit(1)
        try:
            req = urllib.request.Request(HEALTH_URL, method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                last_status = r.status
                if r.status == 200:
                    log("=== BACKEND_UP_OK ===")
                    print("BACKEND_UP_OK")
                    sys.exit(0)
        except urllib.error.HTTPError as e:
            last_status = e.code
            if e.code == 200:
                log("=== BACKEND_UP_OK ===")
                print("BACKEND_UP_OK")
                sys.exit(0)
        except Exception:
            last_status = None

    proc.terminate()
    time.sleep(2)
    try:
        proc.kill()
    except Exception:
        pass
    try:
        PID_FILE.unlink(missing_ok=True)
    except Exception:
        pass
    reason = "TIMEOUT_WAITING_DOCS"
    log("=== BACKEND_UP_FAIL: %s ===" % reason)
    print("BACKEND_UP_FAIL: %s" % reason)
    sys.exit(1)


if __name__ == "__main__":
    main()
