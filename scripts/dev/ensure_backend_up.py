#!/usr/bin/env python3
"""
Dev: bring backend up safely on port 8001.
- Works from any directory (uses git rev-parse --show-toplevel).
- Clears port 8001 before start, then starts uvicorn backend.server:app with cwd=repo_root on port 8001.
- Writes PID to artifacts/dev_backend_8001.pid, log to artifacts/dev_backend_8001.log.
- Health-check GET /docs until 200 (up to 60s) → BACKEND_UP_OK else BACKEND_UP_FAIL status=<code> exit 1.
"""
import subprocess
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path


PORT = 8001
HEALTH_URL = f"http://127.0.0.1:{PORT}/docs"
WAIT_MAX_SEC = 60
WAIT_POLL_SEC = 1.5


def get_repo_root():
    script_dir = Path(__file__).resolve().parent
    out = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=str(script_dir),
        capture_output=True,
        text=True,
        timeout=10,
    )
    if out.returncode != 0:
        print("REPO_ROOT_FAIL: not a git repo or git error", file=sys.stderr)
        sys.exit(1)
    return Path(out.stdout.strip()).resolve()


def clear_port_8001():
    """Find processes listening on :8001 and kill them (SIGTERM then SIGKILL)."""
    try:
        out = subprocess.run(
            ["lsof", "-i", f":{PORT}", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except FileNotFoundError:
        # lsof not available (e.g. some Windows); try netstat or skip
        return
    pids = (out.stdout or "").strip().split()
    for pid in pids:
        pid = pid.strip()
        if not pid:
            continue
        for sig in ["TERM", "KILL"]:
            try:
                subprocess.run(
                    ["kill", f"-{sig}", pid],
                    capture_output=True,
                    timeout=2,
                )
                time.sleep(0.5)
            except Exception:
                pass
    if pids:
        time.sleep(1)


def main():
    repo_root = get_repo_root()
    backend_dir = repo_root / "backend"
    artifacts_dir = repo_root / "artifacts"
    pid_file = artifacts_dir / "dev_backend_8001.pid"
    log_file = artifacts_dir / "dev_backend_8001.log"

    if not backend_dir.is_dir():
        print("BACKEND_DIR_MISSING", file=sys.stderr)
        sys.exit(1)

    clear_port_8001()
    print("PORT_8001_CLEARED_OK")

    artifacts_dir.mkdir(parents=True, exist_ok=True)

    with open(log_file, "w", encoding="utf-8") as logf:
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
            cwd=str(repo_root),
            stdout=logf,
            stderr=subprocess.STDOUT,
            env=dict(__import__("os").environ),
        )
    with open(pid_file, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    deadline = time.monotonic() + WAIT_MAX_SEC
    last_status = None
    while time.monotonic() < deadline:
        time.sleep(WAIT_POLL_SEC)
        try:
            req = urllib.request.Request(HEALTH_URL, method="GET")
            with urllib.request.urlopen(req, timeout=5) as r:
                last_status = r.status
                if r.status == 200:
                    print("BACKEND_UP_OK")
                    sys.exit(0)
        except urllib.error.HTTPError as e:
            last_status = e.code
            if e.code == 200:
                print("BACKEND_UP_OK")
                sys.exit(0)
        except Exception:
            last_status = None
    print(f"BACKEND_UP_FAIL status={last_status}")
    proc.terminate()
    time.sleep(1)
    try:
        proc.kill()
    except Exception:
        pass
    sys.exit(1)


if __name__ == "__main__":
    main()
