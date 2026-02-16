#!/usr/bin/env python3
"""
Verify: new supplier is auto-linked to all restaurants.
- Clean slate, create 2 restaurants with documents
- Create 1 supplier
- Assert: supplier_restaurant_settings has 2 records
- Assert: GET /api/supplier/restaurant-documents returns both restaurants and their docs
- Clean up temp entities
- Write evidence/AUTO_LINK_NEW_SUPPLIER_PROOF.txt
"""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _env import load_env, get_mongo_url, get_db_name

load_env()
MONGO_URL = get_mongo_url()
DB_NAME = get_db_name()

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
    # Ensure subprocess and DB use same env
    run_env = os.environ.copy()
    run_env["ALLOW_DESTRUCTIVE"] = "1"
    run_env["MONGO_URL"] = MONGO_URL
    run_env["DB_NAME"] = DB_NAME

    print(f"MONGO_URL={MONGO_URL}")
    print(f"DB_NAME={DB_NAME}")

    # 1. Clean slate
    import subprocess
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "clean_slate_local.py")],
        cwd=str(ROOT), env=run_env, capture_output=True, text=True, timeout=60
    )
    if r.returncode != 0:
        print(f"WARN: clean_slate {r.returncode}: {r.stderr}")
    print("Clean slate OK")

    # 2. Create 2 restaurants with documents (API creates user + company)
    rest_ids = []
    rest_tokens = []
    for i in (1, 2):
        data = {
            "email": f"autolink_rest{i}@example.com",
            "password": "TestPass123!",
            "inn": f"770000000{i}",
            "companyName": f"E2E Restaurant {i}",
            "legalAddress": "Москва",
            "ogrn": f"102770000000{i}",
            "actualAddress": "Москва",
            "phone": f"+7900123456{i}",
            "companyEmail": f"r{i}@autolink.example.com",
            "contactPersonName": "Test",
            "contactPersonPosition": "Dir",
            "contactPersonPhone": f"+7900123456{i}",
            "deliveryAddresses": [{"address": "Москва", "phone": ""}],
            "dataProcessingConsent": True,
        }
        resp = req("POST", "/auth/register/customer", json=data)
        if resp.status_code not in (200, 201):
            print(f"FAIL: register rest{i} {resp.status_code} {resp.text}")
            sys.exit(1)
        rest_ids.append(resp.json()["user"]["companyId"])
        rest_tokens.append(resp.json()["access_token"])

    for i, token in enumerate(rest_tokens):
        pdf = ROOT / "backend" / "uploads" / f"_autolink_sample_{i}.pdf"
        pdf.parent.mkdir(parents=True, exist_ok=True)
        pdf.write_bytes(b"%PDF-1.4 AutoLink\n")
        with open(pdf, "rb") as f:
            resp = req("POST", "/documents/upload", headers={"Authorization": f"Bearer {token}"},
                      files={"file": ("doc.pdf", f, "application/pdf")}, data={"document_type": "Договор"})
        if resp.status_code not in (200, 201):
            print(f"FAIL: upload doc rest{i} {resp.status_code}")
            sys.exit(1)

    # 3. Create 1 supplier (triggers auto-link)
    resp = req("POST", "/auth/register/supplier", json={
        "email": "autolink_supplier@example.com",
        "password": "TestPass123!",
        "inn": "7700000099",
        "companyName": "AutoLink Supplier",
        "legalAddress": "Москва",
        "ogrn": "1027700000099",
        "actualAddress": "Москва",
        "phone": "+79009999999",
        "companyEmail": "s@autolink.example.com",
        "contactPersonName": "S",
        "contactPersonPosition": "D",
        "contactPersonPhone": "+79009999999",
        "dataProcessingConsent": True,
    })
    if resp.status_code not in (200, 201):
        print(f"FAIL: register supplier {resp.status_code} {resp.text}")
        sys.exit(1)
    sup_token = resp.json()["access_token"]
    sup_company = resp.json()["user"]["companyId"]

    # 4. Verify supplier_restaurant_settings and counts
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient

    client = AsyncIOMotorClient(MONGO_URL)
    db = client[DB_NAME]

    async def get_counts():
        customers = await db.companies.count_documents({"type": "customer"})
        suppliers = await db.companies.count_documents({"type": "supplier"})
        links = await db.supplier_restaurant_settings.count_documents({"supplierId": sup_company})
        docs = await db.documents.count_documents({})
        return customers, suppliers, links, docs

    customers, suppliers, links_count, docs_count = asyncio.run(get_counts())

    if customers != 2:
        print(f"FAIL: expected 2 customers (companies), got {customers}")
        sys.exit(1)
    if suppliers != 1:
        print(f"FAIL: expected 1 supplier, got {suppliers}")
        sys.exit(1)
    if links_count != 2:
        print(f"FAIL: expected 2 supplier_restaurant_settings, got {links_count}")
        sys.exit(1)
    if docs_count < 2:
        print(f"FAIL: expected >=2 documents, got {docs_count}")
        sys.exit(1)
    print("PASS: 2 auto-links, counts OK")

    # 5. GET /api/supplier/restaurant-documents — both restaurants, both with docs
    resp = req("GET", "/supplier/restaurant-documents", headers={"Authorization": f"Bearer {sup_token}"})
    if resp.status_code != 200:
        print(f"FAIL: restaurant-documents {resp.status_code} {resp.text}")
        sys.exit(1)
    items = resp.json()
    if len(items) != 2:
        print(f"FAIL: expected 2 restaurants from API, got {len(items)}")
        sys.exit(1)
    api_rest_ids = {item["restaurantId"] for item in items}
    if api_rest_ids != set(rest_ids):
        print(f"FAIL: API restaurant ids {api_rest_ids} != created {set(rest_ids)}")
        sys.exit(1)
    for item in items:
        docs = item.get("documents", [])
        if len(docs) < 1:
            print(f"FAIL: restaurant {item.get('restaurantName')} has no documents")
            sys.exit(1)
        if not item.get("restaurantRequisitesPreview"):
            print(f"FAIL: no preview for {item.get('restaurantName')}")
            sys.exit(1)
    print("PASS: API returned 2 restaurants with docs and preview")

    # 6. Write evidence (before cleanup)
    out = ROOT / "evidence" / "AUTO_LINK_NEW_SUPPLIER_PROOF.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("# Auto-link new supplier to all restaurants\n\n")
        f.write(f"MONGO_URL={MONGO_URL}\n")
        f.write(f"DB_NAME={DB_NAME}\n\n")
        f.write("Final counts (before cleanup):\n")
        f.write(f"  customers (companies type=customer): {customers}\n")
        f.write(f"  suppliers (companies type=supplier): {suppliers}\n")
        f.write(f"  supplier_restaurant_settings: {links_count}\n")
        f.write(f"  documents: {docs_count}\n\n")
        f.write("Steps: clean slate -> 2 restaurants + docs -> 1 supplier -> auto-link created 2 records\n")
        f.write("API: GET /api/supplier/restaurant-documents returned 2 restaurants with docs\n\n")
        f.write("RESULT: PASS\n")
    print(f"Written {out}")

    # 7. Clean up (no junk) — use sync pymongo to avoid event loop reuse
    from pymongo import MongoClient
    sync_db = MongoClient(MONGO_URL)[DB_NAME]
    sync_db.users.delete_many({"email": {"$in": ["autolink_rest1@example.com", "autolink_rest2@example.com", "autolink_supplier@example.com"]}})
    sync_db.companies.delete_many({"companyName": {"$in": ["E2E Restaurant 1", "E2E Restaurant 2", "AutoLink Supplier"]}})
    sync_db.supplier_restaurant_settings.delete_many({"supplierId": sup_company})
    sync_db.supplier_settings.delete_many({"supplierCompanyId": sup_company})
    sync_db.documents.delete_many({"companyId": {"$in": rest_ids}})
    for f in (ROOT / "backend" / "uploads").glob("_autolink_sample_*.pdf"):
        try:
            f.unlink()
        except OSError:
            pass
    print("Cleanup OK")


if __name__ == "__main__":
    main()
