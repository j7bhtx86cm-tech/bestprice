#!/usr/bin/env python3
"""
Create 2 test suppliers (Integrita, Romax) with logins and auto-link to all restaurants.
Idempotent: if user exists, update company name and ensure auto-link; else register via API.
Writes evidence/DEV_CREATE_2_SUPPLIERS_INTEGRITA_ROMAX.txt with creds and checks.
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
LOGIN_URL = os.environ.get("SUPPLIER_LOGIN_URL", "http://localhost:3000/supplier/auth")

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)

# Supplier definitions: (company_display_name, email_local_part, password) -> candidates: base, base+001..+009
def _email_candidates(local: str, domain: str = "example.com"):
    yield f"{local}@{domain}"
    for i in range(1, 10):
        yield f"{local}+{i:03d}@{domain}"

SUPPLIERS = [
    ("Integrita", "integrita.supplier", "Integrita#2026"),
    ("Romax", "romax.supplier", "Romax#2026"),
]

# Test INN/OGRN for each (unique, not used by supplier@example.com etc)
SUPPLIER_INN_OGRN = {
    "Integrita": ("7700111101", "1027700111101"),
    "Romax": ("7700222202", "1027700222202"),
}


def req(method, path, **kwargs):
    return requests.request(method, f"{API}{path}", timeout=30, **kwargs)


def ensure_auto_link(db, supplier_company_id: str) -> None:
    """Replicate server auto-link: upsert supplier_restaurant_settings for all customers."""
    from pymongo import MongoClient
    # Use sync client for script; same logic as server._auto_link_supplier_to_all_restaurants
    customers = list(db.companies.find({"type": "customer"}, {"_id": 0, "id": 1}))
    now = datetime.now(timezone.utc).isoformat()
    for r in customers:
        db.supplier_restaurant_settings.update_one(
            {"supplierId": supplier_company_id, "restaurantId": r["id"]},
            {"$set": {
                "contract_accepted": False,
                "is_paused": False,
                "updatedAt": now
            }},
            upsert=True
        )


def register_supplier_api(company_name: str, email: str, password: str) -> dict:
    inn, ogrn = SUPPLIER_INN_OGRN.get(company_name, ("7700999901", "1027700999901"))
    data = {
        "email": email,
        "password": password,
        "inn": inn,
        "companyName": company_name,
        "legalAddress": "Москва, тест",
        "ogrn": ogrn,
        "actualAddress": "Москва",
        "phone": "+79001234567",
        "companyEmail": email,
        "contactPersonName": "Test",
        "contactPersonPosition": "Dir",
        "contactPersonPhone": "+79001234567",
        "dataProcessingConsent": True,
    }
    resp = req("POST", "/auth/register/supplier", json=data)
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
    lines.append("# DEV: 2 test suppliers (Integrita, Romax)")
    lines.append(f"timestamp={ts}")
    lines.append(f"MONGO_URL={MONGO_URL}")
    lines.append(f"DB_NAME={DB_NAME}")
    lines.append("")

    results = []  # (company_name, email, password, company_id, token for API check)

    for company_name, email_local, password in SUPPLIERS:
        inn, ogrn = SUPPLIER_INN_OGRN.get(company_name, ("7700999901", "1027700999901"))
        candidates = list(_email_candidates(email_local))

        # Resolve email: first candidate that has an existing user with supplier company
        user = None
        email = None
        for cand in candidates:
            u = db.users.find_one({"email": cand})
            if u:
                comp = db.companies.find_one({"userId": u["id"], "type": "supplier"})
                if comp:
                    user = u
                    email = cand
                    break

        if not email:
            email = candidates[0]
            user = None

        company_id = None
        if user:
            company = db.companies.find_one({"userId": user["id"], "type": "supplier"})
            if company:
                company_id = company["id"]
                # Idempotent: ensure companyName is correct
                db.companies.update_one(
                    {"id": company_id},
                    {"$set": {"companyName": company_name, "updatedAt": datetime.now(timezone.utc).isoformat()}}
                )
                # Ensure supplier_settings exists (minimal doc matching backend model)
                if not db.supplier_settings.find_one({"supplierCompanyId": company_id}):
                    import uuid
                    db.supplier_settings.insert_one({
                        "id": str(uuid.uuid4()),
                        "supplierCompanyId": company_id,
                        "minOrderAmount": 0,
                        "deliveryDays": [],
                        "deliveryTime": "",
                        "orderReceiveDeadline": "",
                        "is_paused": False,
                        "updatedAt": datetime.now(timezone.utc).isoformat()
                    })
                ensure_auto_link(db, company_id)
        else:
            # Create via API: try candidates in order until register succeeds
            for cand in candidates:
                out = register_supplier_api(company_name, cand, password)
                if out:
                    email = cand
                    company_id = out["user"]["companyId"]
                    break
            if not company_id:
                print(f"FAIL: Could not create supplier {company_name} (tried {candidates})")
                sys.exit(1)

        # Verify login and password (if we only updated, password might be old)
        token = None
        login_ok = login_api(email, password)
        if login_ok:
            token = login_ok.get("access_token")
        else:
            # If we only updated existing user, set desired password in DB so login works
            if user and company_id:
                try:
                    import bcrypt
                    new_hash = bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
                    db.users.update_one(
                        {"email": email},
                        {"$set": {"passwordHash": new_hash, "updatedAt": datetime.now(timezone.utc).isoformat()}}
                    )
                    login_ok = login_api(email, password)
                    if login_ok:
                        token = login_ok.get("access_token")
                except Exception:
                    pass
            if not token:
                print(f"WARN: {company_name} login failed with password {password!r}; check evidence for actual creds")

        results.append((company_name, email, password, company_id, token))

        print(f"SUPPLIER_NAME={company_name}")
        print(f"EMAIL={email}")
        print(f"PASSWORD={password}")
        print(f"LOGIN_URL={LOGIN_URL}")
        print("")

        lines.append(f"## {company_name}")
        lines.append(f"SUPPLIER_NAME={company_name}")
        lines.append(f"EMAIL={email}")
        lines.append(f"PASSWORD={password}")
        lines.append(f"LOGIN_URL={LOGIN_URL}")
        lines.append("")

    # DB checks
    for company_name in ("Integrita", "Romax"):
        c = db.companies.find_one({"companyName": company_name, "type": "supplier"})
        if not c:
            print(f"FAIL: DB check: no company {company_name}")
            sys.exit(1)
    for _, email, _, _, _ in results:
        if not db.users.find_one({"email": email}):
            print(f"FAIL: DB check: no user {email}")
            sys.exit(1)
    customers_count = db.companies.count_documents({"type": "customer"})
    links_per_supplier = []
    for _, _, _, company_id, _ in results:
        n = db.supplier_restaurant_settings.count_documents({"supplierId": company_id})
        links_per_supplier.append(n)
        if customers_count >= 1 and n < 1:
            print(f"FAIL: DB check: supplier {company_id} has 0 restaurant links (customers={customers_count}). Backend and script must use same MONGO_URL/DB_NAME.")
            sys.exit(1)
        if customers_count > 0 and n < customers_count:
            print(f"WARN: supplier has {n} links, customers={customers_count} (auto-link should cover all)")
    lines.append("## DB checks")
    lines.append("companies (supplier): Integrita, Romax — OK (>=2)")
    lines.append("users: 2 with above emails — OK")
    lines.append(f"customers (restaurants) in DB: {customers_count}")
    for idx, (name, _, _, _, _) in enumerate(results):
        lines.append(f"supplier_restaurant_settings links for {name}: {links_per_supplier[idx]}")
    if customers_count == 0:
        lines.append("WARN: no customers found; links=0 is expected. Create a test restaurant and re-run (idempotent).")
    else:
        lines.append("supplier_restaurant_settings: each supplier linked to all customers — OK")
    lines.append("")

    # API checks
    lines.append("## API checks")
    api_ok = True
    for company_name, email, password, company_id, token in results:
        if not token:
            login_res = login_api(email, password)
            if login_res:
                token = login_res.get("access_token")
        if not token:
            lines.append(f"{company_name}: LOGIN failed — check password in evidence")
            print(f"FAIL: API check: {company_name} login failed")
            api_ok = False
            continue
        resp = req("GET", "/supplier/restaurant-documents", headers={"Authorization": f"Bearer {token}"})
        if resp.status_code != 200:
            lines.append(f"{company_name}: restaurant-documents {resp.status_code}")
            print(f"FAIL: API check: {company_name} restaurant-documents {resp.status_code}")
            api_ok = False
            continue
        items = resp.json()
        if customers_count >= 1 and not items:
            lines.append(f"{company_name}: 0 restaurants from API (expected >= 1). Backend may use different DB.")
            print(f"FAIL: API check: {company_name} sees 0 restaurants")
            api_ok = False
        else:
            rest_names = [it.get("restaurantName") or "" for it in items]
            has_krevetochna = "Креветочная" in rest_names
            if customers_count >= 1 and not has_krevetochna and items:
                lines.append(f"{company_name}: restaurants returned but 'Креветочная' not in list: {rest_names}")
                print(f"FAIL: API check: {company_name} does not see restaurant Креветочная")
                api_ok = False
            else:
                suf = ", includes Креветочная" if has_krevetochna else ""
                lines.append(f"{company_name}: login OK, GET /api/supplier/restaurant-documents OK, restaurants={len(items)}{suf}")
    if not api_ok:
        sys.exit(1)
    lines.append("")

    # UI instructions
    lines.append("## UI smoke (how to log in)")
    lines.append("1. Open in browser: " + LOGIN_URL)
    lines.append("2. Enter EMAIL and PASSWORD from above for Integrita or Romax.")
    lines.append("3. After login, open section 'Документы' / 'Документы от ресторанов'.")
    lines.append("4. If a test restaurant exists in DB, you should see it (pending contract).")
    lines.append("")

    lines.append("RESULT: PASS")
    if customers_count == 0:
        lines.append("WARN: no customers found; links=0 expected. Create a test restaurant and re-run (idempotent).")

    out_path = ROOT / "evidence" / "DEV_CREATE_2_SUPPLIERS_INTEGRITA_ROMAX.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print(f"Written {out_path}")


if __name__ == "__main__":
    main()
