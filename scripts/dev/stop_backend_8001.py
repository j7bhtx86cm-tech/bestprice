#!/usr/bin/env python3
"""
Dev: stop backend on port 8001 safely.
- If artifacts/dev_backend_8001.pid exists, stop that PID.
- Else find processes on :8001 and kill them.
- Prints BACKEND_STOPPED_OK.
"""
import subprocess
import sys
import time
from pathlib import Path

PORT = 8001


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


def kill_pid(pid: int):
    for sig in ["TERM", "KILL"]:
        try:
            subprocess.run(
                ["kill", f"-{sig}", str(pid)],
                capture_output=True,
                timeout=2,
            )
            time.sleep(0.5)
        except Exception:
            pass


def main():
    repo_root = get_repo_root()
    pid_file = repo_root / "artifacts" / "dev_backend_8001.pid"

    stopped = False
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            kill_pid(pid)
            stopped = True
        except (ValueError, OSError):
            pass
        try:
            pid_file.unlink()
        except Exception:
            pass

    if not stopped:
        try:
            out = subprocess.run(
                ["lsof", "-i", f":{PORT}", "-t"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            pids = (out.stdout or "").strip().split()
            for pid in pids:
                pid = pid.strip()
                if pid and pid.isdigit():
                    kill_pid(int(pid))
                    stopped = True
        except FileNotFoundError:
            pass
        except Exception:
            pass

    time.sleep(0.3)
    print("BACKEND_STOPPED_OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
