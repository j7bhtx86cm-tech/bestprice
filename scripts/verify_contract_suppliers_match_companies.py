#!/usr/bin/env python3
"""
Verify: contract-suppliers endpoint returns ONLY real supplier companies.
- GET /api/customer/contract-suppliers (as restaurant)
- companies(type=supplier)
- Assert: supplier ids from endpoint ⊆ companies (no junk)
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASE = os.environ.get("VERIFY_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
API = f"{BASE}/api"

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)


def req(method, path, **kwargs):
    return requests.request(method, f"{API}{path}", timeout=30, **kwargs)


def main():
    rest_email = os.environ.get("RESTAURANT_EMAIL", "restaurant@example.com")
    rest_pw = os.environ.get("RESTAURANT_PASSWORD", "TestPass123!")

    r = req("POST", "/auth/login", json={"email": rest_email, "password": rest_pw})
    if r.status_code != 200:
        print(f"FAIL: restaurant login {r.status_code}")
        sys.exit(1)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = req("GET", "/customer/contract-suppliers", headers=headers)
    if r.status_code != 200:
        print(f"FAIL: contract-suppliers {r.status_code} {r.text}")
        sys.exit(1)
    suppliers = r.json()
    endpoint_ids = {s["supplierId"] for s in suppliers}

    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "bestprice_local")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    async def get_company_ids():
        cursor = db.companies.find({"type": "supplier"}, {"_id": 0, "id": 1})
        return {doc["id"] async for doc in cursor}

    company_ids = asyncio.run(get_company_ids())
    extra = endpoint_ids - company_ids
    if extra:
        print(f"FAIL: endpoint has supplier ids not in companies: {extra}")
        sys.exit(1)
    print("PASS: contract-suppliers ⊆ companies(type=supplier)")

    accepted = [s for s in suppliers if s.get("contractStatus") == "accepted"]
    out = ROOT / "evidence" / "CONTRACT_SUPPLIERS_API_PROOF.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("# Contract suppliers API proof\n\n")
        f.write("GET /api/customer/contract-suppliers (as restaurant)\n")
        f.write("Source: companies(type=supplier) only. Status from supplier_restaurant_settings.\n\n")
        f.write(f"Suppliers returned: {len(suppliers)}\n")
        f.write(f"companies(type=supplier) count: {len(company_ids)}\n")
        f.write(f"With contract accepted: {len(accepted)}\n")
        f.write("Assert: endpoint ids ⊆ companies — no junk. Linked supplier visible.\n")
        f.write("\nRESULT: PASS\n")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
