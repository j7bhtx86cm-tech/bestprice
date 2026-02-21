#!/usr/bin/env python3
"""
Hard reset backend on 8001: kill processes on port, remove pidfile, run ensure_backend_up.
Stdout: HARD_RESET_BACKEND_OK or HARD_RESET_BACKEND_FAIL: <reason>.
"""
import os
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parents[2] if (SCRIPT_DIR.parents[2] / "backend").is_dir() else Path(
    subprocess.run(["git", "rev-parse", "--show-toplevel"], cwd=str(SCRIPT_DIR), capture_output=True, text=True, timeout=5).stdout.strip() or "."
).resolve()
PORT = 8001
ARTIFACTS = ROOT / "artifacts"
PID_FILE = ARTIFACTS / "dev_backend_8001.pid"
ENSURE_BACKEND = ROOT / "scripts" / "dev" / "ensure_backend_up.py"


def main():
    try:
        out = subprocess.run(
            ["lsof", "-nP", "-iTCP:%s" % PORT, "-sTCP:LISTEN"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=10,
        )
    except FileNotFoundError:
        print("HARD_RESET_BACKEND_FAIL: lsof not found")
        sys.exit(1)
    lines = (out.stdout or "").strip().splitlines()
    pids = set()
    for line in lines[1:]:
        parts = line.split()
        if len(parts) >= 2 and parts[1].isdigit():
            pids.add(parts[1])
    for pid in sorted(pids):
        for sig in ["TERM", "KILL"]:
            try:
                subprocess.run(["kill", "-%s" % sig, pid], capture_output=True, timeout=3)
            except Exception:
                pass
            time.sleep(4 if sig == "TERM" else 1)
    time.sleep(2)
    if PID_FILE.exists():
        try:
            PID_FILE.unlink()
        except Exception:
            pass
    if not ENSURE_BACKEND.exists():
        print("HARD_RESET_BACKEND_FAIL: ensure_backend_up.py not found")
        sys.exit(1)
    r = subprocess.run(
        [sys.executable, str(ENSURE_BACKEND)],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        timeout=90,
    )
    if r.returncode != 0 or "BACKEND_UP_OK" not in (r.stdout or ""):
        reason = (r.stdout or "").strip() or (r.stderr or "").strip() or "ensure_backend_up failed"
        if "BACKEND_UP_FAIL:" in reason:
            reason = reason.split("BACKEND_UP_FAIL:")[-1].strip()[:120]
        print("HARD_RESET_BACKEND_FAIL: %s" % reason[:120])
        sys.exit(1)
    print("HARD_RESET_BACKEND_OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
