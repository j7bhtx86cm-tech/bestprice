#!/usr/bin/env python3
"""
Auth smoke: check supplier and admin/restaurant login via API (no browser).
Prints env diagnostic, then SUPPLIER_LOGIN_OK/FAIL and ADMIN_LOGIN_OK/FAIL.
No secrets in output (only status and short reason on fail).
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))
from _env import load_env, get_mongo_url, get_db_name

load_env()
# Also load backend/.env so we see same DB as backend
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass

API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
DB_NAME = os.environ.get("DB_NAME", "bestprice_local")
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
JWT_SECRET = "set" if os.environ.get("JWT_SECRET_KEY") else "missing"
APP_ENV = os.environ.get("APP_ENV", os.environ.get("NODE_ENV", ""))

# Credentials: supplier (Integrita), admin/restaurant (restaurant)
SUPPLIER_EMAIL = os.environ.get("SUPPLIER_EMAIL", "integrita.supplier@example.com")
SUPPLIER_PASSWORD = os.environ.get("SUPPLIER_PASSWORD", "Integrita#2026")
ADMIN_EMAIL = os.environ.get("RESTAURANT_EMAIL", os.environ.get("ADMIN_EMAIL", "restaurant@example.com"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "TestPass123!")

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)


def main():
    # A) Env diagnostic
    print("API_BASE_URL=%s" % API_BASE_URL)
    print("DB_NAME=%s" % DB_NAME)
    print("MONGO_URL=%s" % (MONGO_URL if "localhost" in MONGO_URL else "***"))
    print("JWT_SECRET_KEY=%s" % JWT_SECRET)
    print("APP_ENV=%s" % (APP_ENV or "(empty)"))

    # B) Check user exists in DB (same DB backend uses)
    try:
        from pymongo import MongoClient
        client = MongoClient(get_mongo_url())
        db = client[get_db_name()]
        user = db.users.find_one({"email": SUPPLIER_EMAIL}, {"_id": 0, "email": 1, "role": 1})
        if user:
            has_hash = bool(db.users.find_one({"email": SUPPLIER_EMAIL}, {"passwordHash": 1}))
            print("USER_IN_DB=%s role=%s has_password=%s" % (SUPPLIER_EMAIL, user.get("role"), has_hash))
        else:
            print("USER_NOT_IN_DB=%s" % SUPPLIER_EMAIL)
    except Exception as e:
        print("DB_CHECK_FAIL=%s" % str(e)[:80])

    api = "%s/api" % API_BASE_URL

    # Supplier login
    try:
        r = requests.post(
            "%s/auth/login" % api,
            json={"email": SUPPLIER_EMAIL, "password": SUPPLIER_PASSWORD},
            timeout=15,
        )
        if r.status_code == 200:
            print("SUPPLIER_LOGIN_OK")
        else:
            body = r.text[:200] if r.text else ""
            try:
                j = r.json()
                detail = j.get("detail") or j.get("message") or body
            except Exception:
                detail = body
            print("SUPPLIER_LOGIN_FAIL: status=%s detail=%s" % (r.status_code, str(detail)[:150]))
    except Exception as e:
        print("SUPPLIER_LOGIN_FAIL: %s" % str(e)[:150])

    # Admin/restaurant login
    try:
        r = requests.post(
            "%s/auth/login" % api,
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            timeout=15,
        )
        if r.status_code == 200:
            print("ADMIN_LOGIN_OK")
        else:
            body = r.text[:200] if r.text else ""
            try:
                j = r.json()
                detail = j.get("detail") or j.get("message") or body
            except Exception:
                detail = body
            print("ADMIN_LOGIN_FAIL: status=%s detail=%s" % (r.status_code, str(detail)[:150]))
    except Exception as e:
        print("ADMIN_LOGIN_FAIL: %s" % str(e)[:150])


if __name__ == "__main__":
    main()
