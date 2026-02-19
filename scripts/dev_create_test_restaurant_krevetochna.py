#!/usr/bin/env python3
"""
Create or update test restaurant (customer) "Креветочная" with fixed fields.
Idempotent: if user with email exists, update company name/address/phone and ensure password; else register via API.
Writes evidence/DEV_CREATE_TEST_RESTAURANT_KREVETOCHNA.txt
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _env import load_env, get_mongo_url, get_db_name

load_env()
MONGO_URL = get_mongo_url()
DB_NAME = get_db_name()

BASE = os.environ.get("VERIFY_BASE_URL", os.environ.get("API_BASE_URL", "http://127.0.0.1:8001")).rstrip("/")
API = f"{BASE}/api"

# Hardcoded data for Креветочная
RESTAURANT_NAME = "Креветочная"
RESTAURANT_ADDRESS = "Рубинштейна 38"
RESTAURANT_PHONE = "+79213643475"
RESTAURANT_EMAIL = "gmfuel@gmail.com"
RESTAURANT_PASSWORD = "Krevetochna#2026"

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)


def req(method, path, **kwargs):
    return requests.request(method, f"{API}{path}", timeout=30, **kwargs)


def register_customer_api(data: dict) -> dict:
    resp = req("POST", "/auth/register/customer", json=data)
    if resp.status_code in (200, 201):
        return resp.json()
    return None


def login_api(email: str, password: str) -> dict:
    resp = req("POST", "/auth/login", json={"email": email, "password": password})
    if resp.status_code != 200:
        return None
    return resp.json()


def main():
    from pymongo import MongoClient

    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    ts = datetime.now(timezone.utc).isoformat()
    lines = []
    lines.append("# DEV: test restaurant Креветочная")
    lines.append(f"timestamp={ts}")
    lines.append(f"MONGO_URL={MONGO_URL}")
    lines.append(f"DB_NAME={DB_NAME}")
    lines.append("")

    existing_user = db.users.find_one({"email": RESTAURANT_EMAIL})
    company_id = None
    created = False

    if existing_user:
        company = db.companies.find_one({"userId": existing_user["id"], "type": "customer"})
        if company:
            company_id = company["id"]
            # Idempotent: update name/address/phone to match required values
            db.companies.update_one(
                {"id": company_id},
                {"$set": {
                    "companyName": RESTAURANT_NAME,
                    "legalAddress": RESTAURANT_ADDRESS,
                    "actualAddress": RESTAURANT_ADDRESS,
                    "phone": RESTAURANT_PHONE,
                    "email": RESTAURANT_EMAIL,
                    "updatedAt": datetime.now(timezone.utc).isoformat()
                }}
            )
        # Ensure password works for login
        try:
            import bcrypt
            new_hash = bcrypt.hashpw(RESTAURANT_PASSWORD.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
            db.users.update_one(
                {"email": RESTAURANT_EMAIL},
                {"$set": {"passwordHash": new_hash, "updatedAt": datetime.now(timezone.utc).isoformat()}}
            )
        except Exception:
            pass
    else:
        # Register via API
        data = {
            "email": RESTAURANT_EMAIL,
            "password": RESTAURANT_PASSWORD,
            "inn": "7700333303",
            "companyName": RESTAURANT_NAME,
            "legalAddress": RESTAURANT_ADDRESS,
            "ogrn": "1027700333303",
            "actualAddress": RESTAURANT_ADDRESS,
            "phone": RESTAURANT_PHONE,
            "companyEmail": RESTAURANT_EMAIL,
            "contactPersonName": "Креветочная",
            "contactPersonPosition": "Директор",
            "contactPersonPhone": RESTAURANT_PHONE,
            "deliveryAddresses": [{"address": RESTAURANT_ADDRESS, "phone": RESTAURANT_PHONE}],
            "dataProcessingConsent": True,
        }
        out = register_customer_api(data)
        if not out:
            print(f"FAIL: Could not register customer {RESTAURANT_EMAIL}")
            sys.exit(1)
        company_id = out["user"]["companyId"]
        created = True

    # Reload company for evidence
    company = db.companies.find_one({"email": RESTAURANT_EMAIL, "type": "customer"}, {"_id": 0})
    if not company:
        print("FAIL: DB check: no company with email gmfuel@gmail.com")
        sys.exit(1)

    # Console output
    print(f"EMAIL={RESTAURANT_EMAIL}")
    print(f"PASSWORD={RESTAURANT_PASSWORD}")
    print(f"name={company.get('companyName')}")
    print(f"address={company.get('actualAddress') or company.get('legalAddress')}")
    print(f"phone={company.get('phone')}")
    print("")

    # Evidence: creds and final fields
    lines.append("## Creds")
    lines.append(f"EMAIL={RESTAURANT_EMAIL}")
    lines.append(f"PASSWORD={RESTAURANT_PASSWORD}")
    lines.append("")
    lines.append("## Final restaurant fields")
    lines.append(f"name (companyName)={company.get('companyName')}")
    lines.append(f"address (actualAddress/legalAddress)={company.get('actualAddress') or company.get('legalAddress')}")
    lines.append(f"phone={company.get('phone')}")
    lines.append(f"email={company.get('email')}")
    lines.append("")

    # DB checks
    customers_count = db.companies.count_documents({"type": "customer"})
    krevetochna = db.companies.find_one({"type": "customer", "email": RESTAURANT_EMAIL})
    if not krevetochna:
        print("FAIL: DB check: no customer with email gmfuel@gmail.com")
        sys.exit(1)
    lines.append("## DB checks")
    lines.append(f"companies (type=customer) count: {customers_count} (>=1)")
    lines.append(f"customer with email gmfuel@gmail.com: OK")
    lines.append("")

    # API checks: login + GET /auth/me
    token = login_api(RESTAURANT_EMAIL, RESTAURANT_PASSWORD)
    if not token:
        print("FAIL: API check: customer login failed")
        lines.append("## API checks")
        lines.append("customer login: FAILED")
        sys.exit(1)
    access_token = token.get("access_token")
    me = req("GET", "/auth/me", headers={"Authorization": f"Bearer {access_token}"})
    if me.status_code != 200:
        print(f"FAIL: API check: GET /auth/me returned {me.status_code}")
        lines.append("## API checks")
        lines.append(f"login: OK, GET /auth/me: {me.status_code}")
        sys.exit(1)
    lines.append("## API checks")
    lines.append("customer login: OK")
    lines.append("GET /auth/me: OK")
    lines.append("")

    lines.append("RESULT: PASS")
    lines.append("")
    lines.append("После создания ресторана перезапусти bash scripts/dev_create_2_test_suppliers.sh (он idempotent) — чтобы достроились supplier_restaurant_settings и поставщики увидели новый ресторан.")

    out_path = ROOT / "evidence" / "DEV_CREATE_TEST_RESTAURANT_KREVETOCHNA.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Written {out_path}")


if __name__ == "__main__":
    main()
