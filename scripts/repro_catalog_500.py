#!/usr/bin/env python3
"""
Repro GET /api/v12/catalog (customer). Prints catalog_status= and catalog_body= (first 2000 chars).
Does NOT print password or token. Exit 1 if catalog_status != 200.
Env: API_BASE_URL (default http://127.0.0.1:8001), CUSTOMER_EMAIL, CUSTOMER_PASSWORD.
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


def mask_secrets(s):
    if not s:
        return s
    s = re.sub(r'"access_token"\s*:\s*"[^"]*"', '"access_token":"***"', s)
    s = re.sub(r'"token"\s*:\s*"[^"]*"', '"token":"***"', s)
    s = re.sub(r'"password"\s*:\s*"[^"]*"', '"password":"***"', s)
    return s


def main():
    if not EMAIL or not PASSWORD:
        print("catalog_status=0")
        print("catalog_body=Set CUSTOMER_EMAIL and CUSTOMER_PASSWORD")
        sys.exit(1)
    try:
        r = requests.post(API + "/auth/login", json={"email": EMAIL, "password": PASSWORD}, timeout=15)
        if r.status_code != 200:
            print("catalog_status=0")
            print("catalog_body=login_failed status=" + str(r.status_code))
            sys.exit(1)
        token = r.json().get("access_token") or r.json().get("token")
        if not token:
            print("catalog_status=0")
            print("catalog_body=no token in login response")
            sys.exit(1)
        headers = {"Authorization": "Bearer " + token}
        requests.get(API + "/auth/me", headers=headers, timeout=10)
        r2 = requests.get(API + "/v12/catalog", params={"skip": 0, "limit": 20}, headers=headers, timeout=15)
        status = r2.status_code
        body = mask_secrets((r2.text or "")[:2000])
        print("catalog_status=" + str(status))
        print("catalog_body=" + body)
        if status != 200:
            sys.exit(1)
        sys.exit(0)
    except Exception as e:
        print("catalog_status=0")
        print("catalog_body=" + mask_secrets(str(e)[:500]))
        sys.exit(1)


if __name__ == "__main__":
    main()
