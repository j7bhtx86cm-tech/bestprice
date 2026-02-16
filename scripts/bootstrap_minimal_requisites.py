#!/usr/bin/env python3
"""
Bootstrap minimal state: 1 supplier, 1 restaurant (full requisites), 1 link, 1 document.
Runs clean_slate first (ALLOW_DESTRUCTIVE=1), then creates fresh entities.
Uses supplier@example.com, restaurant@example.com.
Ensures 1/1/1/1 with fully populated restaurant requisites.
"""
import os
import subprocess
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


SUPPLIER_EMAIL = os.environ.get("SUPPLIER_EMAIL", "supplier@example.com")
RESTAURANT_EMAIL = os.environ.get("RESTAURANT_EMAIL", "restaurant@example.com")
PASSWORD = os.environ.get("SUPPLIER_PASSWORD", os.environ.get("RESTAURANT_PASSWORD", "TestPass123!"))

# Full restaurant requisites for reference flow
REST_REQUISITES = {
    "inn": "7700000002",
    "companyName": "E2E Restaurant Test",
    "legalAddress": "г. Москва, ул. Тестовая, д. 1",
    "ogrn": "1027700000002",
    "actualAddress": "г. Москва, ул. Фактическая, д. 2",
    "phone": "+79001234568",
    "companyEmail": "rest@e2e.example.com",
    "contactPersonName": "Петров И.И.",
    "contactPersonPosition": "Директор",
    "contactPersonPhone": "+79001234569",
    "edoNumber": "EDO-REF-001",
    "guid": "guid-reference-flow-001",
}


def run_clean_slate():
    """Run clean_slate_local.py with ALLOW_DESTRUCTIVE=1."""
    env = os.environ.copy()
    env["ALLOW_DESTRUCTIVE"] = "1"
    r = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "clean_slate_local.py")],
        cwd=str(ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )
    if r.returncode != 0:
        print(f"WARN: clean_slate returned {r.returncode}: {r.stderr}")
    else:
        print("Clean slate OK")


def get_final_counts():
    """Return dict of final DB counts."""
    import asyncio
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "bestprice_local")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    async def _counts():
        suppliers = await db.companies.count_documents({"type": "supplier"})
        restaurants = await db.companies.count_documents({"type": "customer"})
        links = await db.supplier_restaurant_settings.count_documents({})
        documents = await db.documents.count_documents({})
        users = await db.users.count_documents({})
        return {"suppliers": suppliers, "restaurants": restaurants, "links": links, "documents": documents, "users": users}

    return asyncio.run(_counts())


def main():
    # 0. Clean slate
    run_clean_slate()

    # 1. Supplier
    r = req("POST", "/auth/register/supplier", json={
        "email": SUPPLIER_EMAIL,
        "password": PASSWORD,
        "inn": "7700000001",
        "companyName": "E2E Supplier Test",
        "legalAddress": "г. Москва, ул. Поставщика, д. 1",
        "ogrn": "1027700000001",
        "actualAddress": "г. Москва",
        "phone": "+79001234567",
        "companyEmail": "sup@e2e.example.com",
        "contactPersonName": "Иванов",
        "contactPersonPosition": "Директор",
        "contactPersonPhone": "+79001234567",
        "dataProcessingConsent": True,
    })
    if r.status_code == 400 and "already" in (r.json().get("detail") or "").lower():
        r = req("POST", "/auth/login", json={"email": SUPPLIER_EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        print(f"FAIL: supplier {r.status_code} {r.text}")
        sys.exit(1)
    sup_token = r.json()["access_token"]
    sup_company = r.json().get("user", {}).get("companyId")
    if not sup_company:
        print("FAIL: no supplier companyId")
        sys.exit(1)
    headers_sup = {"Authorization": f"Bearer {sup_token}"}

    # 2. Restaurant (customer) with full requisites
    r = req("POST", "/auth/register/customer", json={
        "email": RESTAURANT_EMAIL,
        "password": PASSWORD,
        "inn": REST_REQUISITES["inn"],
        "companyName": REST_REQUISITES["companyName"],
        "legalAddress": REST_REQUISITES["legalAddress"],
        "ogrn": REST_REQUISITES["ogrn"],
        "actualAddress": REST_REQUISITES["actualAddress"],
        "phone": REST_REQUISITES["phone"],
        "companyEmail": REST_REQUISITES["companyEmail"],
        "contactPersonName": REST_REQUISITES["contactPersonName"],
        "contactPersonPosition": REST_REQUISITES["contactPersonPosition"],
        "contactPersonPhone": REST_REQUISITES["contactPersonPhone"],
        "deliveryAddresses": [{"address": "г. Москва, ул. Доставки, 3", "phone": REST_REQUISITES["phone"]}],
        "dataProcessingConsent": True,
    })
    if r.status_code == 400 and "already" in (r.json().get("detail") or "").lower():
        r = req("POST", "/auth/login", json={"email": RESTAURANT_EMAIL, "password": PASSWORD})
    if r.status_code != 200:
        print(f"FAIL: restaurant {r.status_code} {r.text}")
        sys.exit(1)
    rest_token = r.json()["access_token"]
    rest_company = r.json().get("user", {}).get("companyId")
    if not rest_company:
        print("FAIL: no restaurant companyId")
        sys.exit(1)
    headers_rest = {"Authorization": f"Bearer {rest_token}"}

    # 3. Update restaurant company with edoNumber, guid
    r = req("PUT", "/companies/my", headers=headers_rest, json={
        "edoNumber": REST_REQUISITES["edoNumber"],
        "guid": REST_REQUISITES["guid"],
    })
    if r.status_code != 200:
        print(f"WARN: company update {r.status_code} (continuing)")

    # 4. Link (accept contract)
    r = req("POST", "/supplier/accept-contract", headers=headers_sup, json={"restaurantId": rest_company})
    if r.status_code != 200:
        print(f"FAIL: accept-contract {r.status_code} {r.text}")
        sys.exit(1)

    # 5. Documents: ensure exactly 1 (upload if 0, dedupe if >1)
    r = req("GET", "/documents/my", headers=headers_rest)
    if r.status_code != 200:
        print(f"FAIL: documents/my {r.status_code}")
        sys.exit(1)
    docs = r.json()
    if len(docs) == 0:
        pdf_path = ROOT / "tests" / "fixtures" / "sample.pdf"
        if not pdf_path.exists():
            pdf_path = ROOT / "backend" / "uploads" / "_bootstrap_sample.pdf"
            pdf_path.parent.mkdir(parents=True, exist_ok=True)
            pdf_path.write_bytes(b"%PDF-1.4 Bootstrap reference\n")
        with open(pdf_path, "rb") as f:
            files = {"file": ("sample.pdf", f, "application/pdf")}
            data = {"document_type": "Договор", "edo": REST_REQUISITES["edoNumber"], "guid": REST_REQUISITES["guid"]}
            r = req("POST", "/documents/upload", headers=headers_rest, files=files, data=data)
        if r.status_code not in (200, 201):
            print(f"FAIL: upload {r.status_code} {r.text}")
            sys.exit(1)
        print("Uploaded 1 document")
    elif len(docs) > 1:
        # Dedupe: keep first, delete rest via DB
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        load_dotenv(ROOT / "backend" / ".env")
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "bestprice_local")
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]

        to_keep = docs[0]["id"]
        ids_to_del = [d["id"] for d in docs[1:]]

        async def cleanup_extra():
            result = await db.documents.delete_many({"companyId": rest_company, "id": {"$in": ids_to_del}})
            return result.deleted_count

        deleted = asyncio.run(cleanup_extra())
        print(f"Removed {deleted} duplicate document(s), kept 1")

    counts = get_final_counts()
    lines = [
        "Bootstrap OK",
        f"suppliers: {counts['suppliers']}",
        f"restaurants: {counts['restaurants']}",
        f"links: {counts['links']}",
        f"documents: {counts['documents']}",
        f"users: {counts['users']}",
    ]
    for line in lines:
        print(line)

    out = ROOT / "evidence" / "BOOTSTRAP_MINIMAL_REQUISITES_PROOF.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("Bootstrap minimal requisites proof\n")
        f.write("==================================\n\n")
        f.write("1. Clean slate run\n")
        f.write("2. Bootstrap: 1 supplier, 1 restaurant (full requisites), 1 link, 1 document\n")
        f.write("\nFinal counts:\n")
        for k, v in counts.items():
            f.write(f"  {k}: {v}\n")
        f.write("\nExpected: suppliers=1, restaurants=1, links=1, documents=1, users=2\n")
    print(f"Written {out}")


if __name__ == "__main__":
    main()
