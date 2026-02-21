#!/usr/bin/env python3
"""Run smoke (login + catalog) 10 times. Log: artifacts/smoke_10x_yesterday_stable.log. Env: API_BASE_URL, CUSTOMER_EMAIL, CUSTOMER_PASSWORD."""
import os
import subprocess
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from _env import load_env
    load_env()
except Exception:
    pass

SCRIPT = ROOT / "scripts" / "smoke_customer_catalog.py"
LOG_FILE = ROOT / "artifacts" / "smoke_10x_yesterday_stable.log"

def main():
    (ROOT / "artifacts").mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    lines = ["# smoke 10x " + datetime.now(timezone.utc).isoformat(), "# API_BASE_URL=" + os.environ.get("API_BASE_URL", "http://127.0.0.1:8001"), ""]
    ok = 0
    for i in range(10):
        proc = subprocess.run([sys.executable, str(SCRIPT)], cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=60)
        out = (proc.stdout or "").strip()
        for line in (proc.stderr or "").strip().splitlines():
            lines.append(line)
        for line in out.splitlines():
            lines.append(line)
        if proc.returncode == 0 and "SMOKE_CUSTOMER_CATALOG_OK" in out:
            ok += 1
        lines.append("")
    lines.append("# finished " + datetime.now(timezone.utc).isoformat())
    if ok == 10:
        lines.append("SMOKE_10X_OK")
    else:
        lines.append("SMOKE_10X_FAIL ok=" + str(ok) + "/10")
    LOG_FILE.write_text("\n".join(lines), encoding="utf-8")
    print(lines[-1])
    print("log=" + str(LOG_FILE))
    sys.exit(0 if ok == 10 else 1)


if __name__ == "__main__":
    main()
