#!/usr/bin/env python3
"""
Воспроизведение GET /api/v12/catalog (customer). Сохраняет:
- artifacts/catalog_500_repro.txt при 500 (команда, статус, body, trace_id)
- artifacts/catalog_200_ok.txt при 200 (excerpt)
Пароль/токен в файлы не пишутся.
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
try:
    from _env import load_env
    load_env()
except Exception:
    pass

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
API = API_BASE_URL + "/api"
EMAIL = os.environ.get("CUSTOMER_EMAIL", "")
PASSWORD = os.environ.get("CUSTOMER_PASSWORD", "")

try:
    import requests
except ImportError:
    print("ERROR: pip install requests", file=sys.stderr)
    sys.exit(1)

ARTIFACTS = ROOT / "artifacts"
ARTIFACTS.mkdir(parents=True, exist_ok=True)


def main():
    if not EMAIL or not PASSWORD:
        print("Set CUSTOMER_EMAIL and CUSTOMER_PASSWORD")
        sys.exit(1)
    cmd = 'API_BASE_URL="%s" CUSTOMER_EMAIL="*" CUSTOMER_PASSWORD="*" python3 scripts/repro_catalog_500.py' % API_BASE_URL
    lines = ["# repro catalog", "command=" + cmd, ""]
    try:
        r = requests.post(API + "/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
        if r.status_code != 200:
            lines.extend(["login_status=" + str(r.status_code), "catalog_status=N/A", "RESULT=login_failed"])
            (ARTIFACTS / "catalog_500_repro.txt").write_text("\n".join(lines), encoding="utf-8")
            sys.exit(1)
        token = r.json().get("access_token") or r.json().get("token")
        headers = {"Authorization": "Bearer " + token}
        r2 = requests.get(API + "/v12/catalog", params={"skip": 0, "limit": 20}, headers=headers, timeout=15)
        status = r2.status_code
        body = r2.text or ""
        try:
            j = r2.json()
            trace_id = j.get("trace_id", "")
        except Exception:
            j = {}
            trace_id = ""
        lines.append("catalog_status=" + str(status))
        if status == 500:
            lines.append("trace_id=" + trace_id)
            import re
            body_safe = re.sub(r'"access_token"\s*:\s*"[^"]*"', '"access_token":"***"', body)
            body_safe = re.sub(r'"password"\s*:\s*"[^"]*"', '"password":"***"', body_safe)
            lines.append("body=" + body_safe[:1500])
            ARTIFACTS.mkdir(parents=True, exist_ok=True)
            (ARTIFACTS / "catalog_500_repro.txt").write_text("\n".join(lines), encoding="utf-8")
            print("500 saved to artifacts/catalog_500_repro.txt trace_id=" + trace_id)
            sys.exit(1)
        lines.append("total=" + str(j.get("total", "")))
        lines.append("items_count=" + str(len(j.get("items") or [])))
        lines.append("skip=" + str(j.get("skip", "")))
        lines.append("limit=" + str(j.get("limit", "")))
        lines.append("has_more=" + str(j.get("has_more", "")))
        (ARTIFACTS / "catalog_200_ok.txt").write_text("\n".join(lines), encoding="utf-8")
        print("200 saved to artifacts/catalog_200_ok.txt")
        sys.exit(0)
    except Exception as e:
        lines.append("error=" + str(e)[:500])
        (ARTIFACTS / "catalog_500_repro.txt").write_text("\n".join(lines), encoding="utf-8")
        raise


if __name__ == "__main__":
    main()
