#!/usr/bin/env python3
"""
Один прогон smoke: логин (customer) + /auth/me + GET /api/v12/catalog.
Пароль/токен в stdout не выводятся. Для 10 прогонов используйте run_smoke_10x.py.

Env: API_BASE_URL (default http://127.0.0.1:8001), CUSTOMER_EMAIL, CUSTOMER_PASSWORD.
Exit 0 = OK, 1 = FAIL.
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


def main():
    def log(msg: str) -> None:
        print(msg, flush=True)

    if not EMAIL or not PASSWORD:
        log("SMOKE_10X_FAIL: set CUSTOMER_EMAIL and CUSTOMER_PASSWORD")
        sys.exit(1)

    try:
        try:
            h = requests.get(API + "/health", timeout=5)
            if h.status_code == 200:
                sha = (h.json() or {}).get("build_sha", "?")
                log("backend version build_sha=" + str(sha))
        except Exception:
            pass
        r = requests.post(
            API + "/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=15,
        )
        log(f"POST {API}/auth/login → {r.status_code}")
        if r.status_code != 200:
            import re
            body = (r.text or "")[:200].replace("\n", " ")
            body = re.sub(r'"access_token"\s*:\s*"[^"]*"', '"access_token":"***"', body)
            body = re.sub(r'"password"\s*:\s*"[^"]*"', '"password":"***"', body)
            log(f"SMOKE_10X_FAIL: login {r.status_code} body={body}")
            sys.exit(1)
        data = r.json()
        token = data.get("access_token") or data.get("token")
        if not token:
            log("SMOKE_10X_FAIL: no token in login response")
            sys.exit(1)
        headers = {"Authorization": f"Bearer {token}"}

        r2 = requests.get(API + "/auth/me", headers=headers, timeout=10)
        log(f"GET {API}/auth/me → {r2.status_code}")
        if r2.status_code != 200:
            log(f"SMOKE_10X_FAIL: auth/me {r2.status_code}")
            sys.exit(1)

        for _ in range(3):
            r3 = requests.get(
                API + "/v12/catalog",
                params={"skip": 0, "limit": 20},
                headers=headers,
                timeout=15,
            )
            j = r3.json() if r3.headers.get("content-type", "").startswith("application/json") else {}
            total = j.get("total", 0)
            returned = len(j.get("items") or [])
            log(f"GET {API}/v12/catalog?skip=0&limit=20 → {r3.status_code} total={total} returned={returned}")
            if r3.status_code != 200:
                log(f"SMOKE_10X_FAIL: catalog {r3.status_code}")
                sys.exit(1)
            if total > 0 and returned == 0:
                log("SMOKE_10X_FAIL: total>0 but items.length==0")
                sys.exit(1)

        log("✅ SMOKE_CUSTOMER_CATALOG_OK")
        sys.exit(0)
    except Exception as e:
        log(f"SMOKE_10X_FAIL: {type(e).__name__}: {str(e)[:200]}")
        sys.exit(1)


if __name__ == "__main__":
    main()
