#!/usr/bin/env python3
"""
Прогон smoke (логин + каталог) 10 раз. Лог: artifacts/smoke_10x_yesterday_stable.log.
Пароль/токен в лог не пишутся (дочерний скрипт не выводит их).
Env: API_BASE_URL, CUSTOMER_EMAIL, CUSTOMER_PASSWORD.
Итог: SMOKE_10X_OK при 10/10 успешных прогонов, иначе SMOKE_10X_FAIL + номера попыток и причины.
"""
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
N_RUNS = 10


def main():
    env = os.environ.copy()
    ARTIFACTS = ROOT / "artifacts"
    ARTIFACTS.mkdir(parents=True, exist_ok=True)

    if not SCRIPT.exists():
        line = f"SMOKE_10X_FAIL: script not found {SCRIPT}\n"
        LOG_FILE.write_text(line, encoding="utf-8")
        print(line.strip())
        sys.exit(1)

    lines = [
        f"# smoke 10x started {datetime.now(timezone.utc).isoformat()}",
        f"# API_BASE_URL={os.environ.get('API_BASE_URL', 'http://127.0.0.1:8001')}",
        "",
    ]
    failed_runs = []
    for i in range(1, N_RUNS + 1):
        proc = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=str(ROOT),
            env=env,
            capture_output=True,
            text=True,
            timeout=60,
        )
        out = (proc.stdout or "").strip()
        err = (proc.stderr or "").strip()
        combined = (out + "\n" + err).strip()
        for line in combined.splitlines():
            lines.append(line)
        if proc.returncode != 0:
            failed_runs.append((i, combined.splitlines()[-1] if combined else "exit " + str(proc.returncode)))
        lines.append("")

    lines.append(f"# finished {datetime.now(timezone.utc).isoformat()}")

    if failed_runs:
        lines.append("SMOKE_10X_FAIL")
        for run_num, reason in failed_runs:
            lines.append(f"  attempt_{run_num}: {reason[:200]}")
    else:
        lines.append("SMOKE_10X_OK")

    LOG_FILE.write_text("\n".join(lines), encoding="utf-8")

    if failed_runs:
        print("SMOKE_10X_FAIL")
        for run_num, reason in failed_runs:
            print(f"  attempt_{run_num}: {reason[:200]}")
        print(f"log={LOG_FILE}")
        sys.exit(1)
    print("SMOKE_10X_OK")
    print(f"log={LOG_FILE}")
    sys.exit(0)


if __name__ == "__main__":
    main()
