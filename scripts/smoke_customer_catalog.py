#!/usr/bin/env python3
"""One smoke run: login → me → catalog x3. Env: API_BASE_URL, CUSTOMER_EMAIL, CUSTOMER_PASSWORD. Exit 0=OK, 1=FAIL."""
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


def main():
    if not EMAIL or not PASSWORD:
        print("SMOKE_FAIL: set CUSTOMER_EMAIL and CUSTOMER_PASSWORD")
        sys.exit(1)
    try:
        r = requests.post(API + "/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
        if r.status_code != 200:
            print("SMOKE_FAIL: login " + str(r.status_code))
            sys.exit(1)
        token = r.json().get("access_token") or r.json().get("token")
        headers = {"Authorization": "Bearer " + token}
        requests.get(API + "/auth/me", headers=headers, timeout=10)
        for _ in range(3):
            r3 = requests.get(API + "/v12/catalog", params={"skip": 0, "limit": 20}, headers=headers, timeout=15)
            if r3.status_code != 200:
                print("SMOKE_FAIL: catalog " + str(r3.status_code))
                sys.exit(1)
            j = r3.json() if r3.headers.get("content-type", "").startswith("application/json") else {}
            if j.get("total", 0) > 0 and len(j.get("items") or []) == 0:
                print("SMOKE_FAIL: total>0 but items empty")
                sys.exit(1)
        print("SMOKE_CUSTOMER_CATALOG_OK")
        sys.exit(0)
    except Exception as e:
        print("SMOKE_FAIL: " + str(e)[:200])
        sys.exit(1)


if __name__ == "__main__":
    main()
