#!/usr/bin/env python3
"""
30 подряд GET /api/v12/catalog?skip=0&limit=20. Все должны быть 200.
При любой ошибке печатать только detail и trace_id (без пароля/токена).
Env: API_BASE_URL, CUSTOMER_EMAIL, CUSTOMER_PASSWORD.
"""
import os
import re
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


def mask(s):
    if not s:
        return s
    s = re.sub(r'"access_token"\s*:\s*"[^"]*"', '"access_token":"***"', s)
    s = re.sub(r'"password"\s*:\s*"[^"]*"', '"password":"***"', s)
    return s


def main():
    if not EMAIL or not PASSWORD:
        print("Set CUSTOMER_EMAIL and CUSTOMER_PASSWORD")
        sys.exit(1)
    r = requests.post(API + "/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
    if r.status_code != 200:
        print("login failed", r.status_code, mask((r.text or "")[:300]))
        sys.exit(1)
    token = r.json().get("access_token") or r.json().get("token")
    headers = {"Authorization": "Bearer " + token}
    n = 30
    for i in range(1, n + 1):
        r2 = requests.get(API + "/v12/catalog", params={"skip": 0, "limit": 20}, headers=headers, timeout=15)
        if r2.status_code != 200:
            j = r2.json() if r2.headers.get("content-type", "").startswith("application/json") else {}
            detail = j.get("detail", r2.text or "")[:200]
            trace_id = j.get("trace_id", "")
            print("catalog request %d/%d: status=%s detail=%s trace_id=%s" % (i, n, r2.status_code, mask(detail), trace_id))
            sys.exit(1)
    print("CATALOG_30X_OK: all 30 requests returned 200")
    sys.exit(0)


if __name__ == "__main__":
    main()
