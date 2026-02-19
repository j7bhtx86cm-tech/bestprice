#!/usr/bin/env python3
"""
Prod-like auto-link verification: customers>=1, suppliers Integrita/Romax must exist,
each with links>=1 and API returning restaurant "Креветочная".
Env via scripts/_env.py. Writes evidence/AUTO_LINK_PRODLIKE.txt.
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
API_BASE_URL = BASE
API = f"{BASE}/api"

RESTAURANT_NAME = "Креветочная"
RESTAURANT_ADDRESS_SUBSTR = "Рубинштейна 38"
CANONICAL_EMAILS = {"Integrita": "integrita.supplier@example.com", "Romax": "romax.supplier@example.com"}
SUPPLIER_PASSWORDS = {"Integrita": "Integrita#2026", "Romax": "Romax#2026"}


def _email_candidates(name: str):
    local = "integrita.supplier" if name == "Integrita" else "romax.supplier"
    yield f"{local}@example.com"
    for i in range(1, 10):
        yield f"{local}+{i:03d}@example.com"


try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)


def req(method, path, **kwargs):
    return requests.request(method, f"{API}{path}", timeout=30, **kwargs)


def login(email: str, password: str):
    r = req("POST", "/auth/login", json={"email": email, "password": password})
    return r.json().get("access_token") if r.status_code == 200 else None


def main():
    from pymongo import MongoClient

    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    ts = datetime.now(timezone.utc).isoformat()
    lines = []
    lines.append("# Auto-link prod-like verification")
    lines.append(f"timestamp={ts}")
    lines.append(f"MONGO_URL={MONGO_URL}")
    lines.append(f"DB_NAME={DB_NAME}")
    lines.append(f"API_BASE_URL={API_BASE_URL}")
    lines.append("")

    customers_count = db.companies.count_documents({"type": "customer"})
    suppliers_count = db.companies.count_documents({"type": "supplier"})

    # 1) customers >= 1
    if customers_count < 1:
        lines.append("customers count: 0")
        lines.append("FAIL: restaurant should be created first.")
        lines.append("RESULT: FAIL (customers=0)")
        out_path = ROOT / "evidence" / "AUTO_LINK_PRODLIKE.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        print("FAIL: customers=0 — restaurant should be created first")
        sys.exit(1)

    lines.append(f"customers count: {customers_count}")
    lines.append(f"suppliers count: {suppliers_count}")
    lines.append("")

    # 2) Find Integrita and Romax (type=supplier)
    integrita_company = db.companies.find_one({"type": "supplier", "companyName": "Integrita"}, {"_id": 0, "id": 1, "userId": 1})
    romax_company = db.companies.find_one({"type": "supplier", "companyName": "Romax"}, {"_id": 0, "id": 1, "userId": 1})
    if not integrita_company:
        lines.append("FAIL: Integrita supplier company not found.")
        lines.append("RESULT: FAIL (Integrita missing)")
        out_path = ROOT / "evidence" / "AUTO_LINK_PRODLIKE.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        print("FAIL: Integrita not found")
        sys.exit(1)
    if not romax_company:
        lines.append("FAIL: Romax supplier company not found.")
        lines.append("RESULT: FAIL (Romax missing)")
        out_path = ROOT / "evidence" / "AUTO_LINK_PRODLIKE.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        print("FAIL: Romax not found")
        sys.exit(1)

    suppliers = [
        ("Integrita", integrita_company),
        ("Romax", romax_company),
    ]

    fail_reason = None

    for name, company in suppliers:
        company_id = company["id"]
        user_id = company.get("userId")
        # Resolve login email: prefer canonical; if user not with canonical, get user by company.userId (may be fallback)
        chosen_email = None
        if user_id:
            user = db.users.find_one({"id": user_id}, {"_id": 0, "email": 1})
            if user:
                chosen_email = user.get("email")
        if not chosen_email:
            # Try canonical then +001..+009 for any user linked to this company
            for cand in _email_candidates(name):
                u = db.users.find_one({"email": cand}, {"_id": 0, "id": 1})
                if u and u["id"] == user_id:
                    chosen_email = cand
                    break
            if not chosen_email:
                for cand in _email_candidates(name):
                    u = db.users.find_one({"email": cand}, {"_id": 0, "id": 1})
                    if u:
                        comp = db.companies.find_one({"userId": u["id"], "type": "supplier", "companyName": name})
                        if comp:
                            chosen_email = cand
                            break
        if not chosen_email:
            lines.append(f"{name}: chosen_email= (user not found)")
            lines.append(f"{name}: links_count=0")
            lines.append(f"{name}: api_restaurants_count=0")
            lines.append(f"{name}: found_krevetochna=false")
            fail_reason = f"{name} user/email not found"
            continue

        links_count = db.supplier_restaurant_settings.count_documents({"supplierId": company_id})
        if links_count < 1:
            lines.append(f"{name}: chosen_email={chosen_email}")
            lines.append(f"{name}: links_count={links_count} (FAIL: expected >=1)")
            lines.append(f"{name}: api_restaurants_count=0")
            lines.append(f"{name}: found_krevetochna=false")
            fail_reason = f"{name} has 0 links"
            continue

        password = SUPPLIER_PASSWORDS.get(name, "")
        token = login(chosen_email, password)
        if not token:
            lines.append(f"{name}: chosen_email={chosen_email}")
            lines.append(f"{name}: links_count={links_count}")
            lines.append(f"{name}: api_restaurants_count=0 (login failed)")
            lines.append(f"{name}: found_krevetochna=false")
            fail_reason = f"{name} login failed"
            continue

        r = req("GET", "/supplier/restaurant-documents", headers={"Authorization": f"Bearer {token}"})
        if r.status_code != 200:
            lines.append(f"{name}: chosen_email={chosen_email}")
            lines.append(f"{name}: links_count={links_count}")
            lines.append(f"{name}: api_restaurants_count=0 (API {r.status_code})")
            lines.append(f"{name}: found_krevetochna=false")
            fail_reason = f"{name} restaurant-documents {r.status_code}"
            continue

        items = r.json()
        api_restaurants_count = len(items)
        if api_restaurants_count < 1:
            lines.append(f"{name}: chosen_email={chosen_email}")
            lines.append(f"{name}: links_count={links_count}")
            lines.append(f"{name}: api_restaurants_count=0 (FAIL: expected >=1)")
            lines.append(f"{name}: found_krevetochna=false")
            fail_reason = f"{name} API returned 0 restaurants"
            continue

        krevetochna_item = None
        for it in items:
            if (it.get("restaurantName") or "") == RESTAURANT_NAME:
                krevetochna_item = it
                break
        found_krevetochna = krevetochna_item is not None
        if not found_krevetochna:
            lines.append(f"{name}: chosen_email={chosen_email}")
            lines.append(f"{name}: links_count={links_count}")
            lines.append(f"{name}: api_restaurants_count={api_restaurants_count}")
            lines.append(f"{name}: found_krevetochna=false (FAIL: '{RESTAURANT_NAME}' not in list)")
            fail_reason = f"{name} does not see '{RESTAURANT_NAME}'"
            continue

        # Optional: address contains "Рубинштейна 38"
        addr_ok = True
        if krevetochna_item:
            full = krevetochna_item.get("restaurantRequisitesFull") or {}
            preview = krevetochna_item.get("restaurantRequisitesPreview") or {}
            addr = (full.get("actualAddress") or full.get("legalAddress") or preview.get("actualAddress") or preview.get("legalAddress") or "")
            if RESTAURANT_ADDRESS_SUBSTR not in addr:
                addr_ok = False  # optional, don't fail

        lines.append(f"{name}: chosen_email={chosen_email}")
        lines.append(f"{name}: links_count={links_count}")
        lines.append(f"{name}: api_restaurants_count={api_restaurants_count}")
        lines.append(f"{name}: found_krevetochna=true")
        lines.append("")

    if fail_reason:
        lines.append("")
        lines.append(f"RESULT: FAIL ({fail_reason})")
        out_path = ROOT / "evidence" / "AUTO_LINK_PRODLIKE.txt"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            f.write("\n".join(lines))
        print(f"FAIL: {fail_reason}")
        sys.exit(1)

    lines.append("")
    lines.append("RESULT: PASS")

    out_path = ROOT / "evidence" / "AUTO_LINK_PRODLIKE.txt"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    print("AUTO_LINK_PRODLIKE: PASS")


if __name__ == "__main__":
    main()
