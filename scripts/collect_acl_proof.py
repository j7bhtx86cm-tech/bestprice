#!/usr/bin/env python3
"""
Collect ACL proof: document download 200 (linked), 403 (no token), 403 (unlinked supplier).

Modes:
  --use-existing: Use manually-created 1 supplier, 1 restaurant, 1 doc.
                  Requires SUPPLIER_EMAIL, SUPPLIER_PASSWORD, RESTAURANT_EMAIL, RESTAURANT_PASSWORD
                  (or defaults supplier@example.com / restaurant@example.com / TestPass123!).
                  Creates temporary unlinked supplier for 403 test, then removes it (no junk).
  default: Create acl_linked, acl_rest, acl_unlinked (for standalone E2E).

Output: evidence/ACL_PROOF.txt
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


def req(method, path, base_url=None, **kwargs):
    url = f"{(base_url or API)}{path}"
    return requests.request(method, url, timeout=30, **kwargs)


def run_with_existing(sup_email, sup_pw, rest_email, rest_pw):
    """Use manually-created entities. Create temp unlinked for 403, then delete it."""
    # 1. Login as supplier
    r = req("POST", "/auth/login", json={"email": sup_email, "password": sup_pw})
    if r.status_code != 200:
        print(f"FAIL: supplier login {r.status_code} (check {sup_email})")
        sys.exit(1)
    linked_token = r.json()["access_token"]

    # 2. Get doc_id from supplier/restaurant-documents
    r = req("GET", "/supplier/restaurant-documents", headers={"Authorization": f"Bearer {linked_token}"})
    if r.status_code != 200:
        print(f"FAIL: restaurant-documents {r.status_code}")
        sys.exit(1)
    docs = []
    for item in r.json():
        docs.extend(item.get("documents", []))
    if not docs:
        print("FAIL: no documents found. Upload a doc as restaurant first.")
        sys.exit(1)
    doc_id = docs[0].get("id")
    if not doc_id:
        print("FAIL: no doc id in response")
        sys.exit(1)

    # 3. Create temp unlinked supplier for 403 test
    r = req("POST", "/auth/register/supplier", json={
        "email": "acl_temp_unlinked@example.com",
        "password": "TestPass123!",
        "inn": "7700000099",
        "companyName": "ACL Temp Unlinked",
        "legalAddress": "Москва",
        "ogrn": "1027700000099",
        "actualAddress": "Москва",
        "phone": "+79009999999",
        "companyEmail": "temp@acl.example.com",
        "contactPersonName": "Т",
        "contactPersonPosition": "Д",
        "contactPersonPhone": "+79009999999",
        "dataProcessingConsent": True,
    })
    if r.status_code == 400:
        r = req("POST", "/auth/login", json={"email": "acl_temp_unlinked@example.com", "password": "TestPass123!"})
    if r.status_code != 200:
        print(f"FAIL: temp supplier {r.status_code}")
        sys.exit(1)
    unlinked_token = r.json()["access_token"]
    u = r.json().get("user", {})
    temp_user_id = u.get("id")
    temp_company_id = u.get("companyId")

    try:
        # 4. Run 3 ACL tests
        r1 = req("GET", f"/documents/{doc_id}/download", headers={"Authorization": f"Bearer {linked_token}"})
        r2 = req("GET", f"/documents/{doc_id}/download")
        r3 = req("GET", f"/documents/{doc_id}/download", headers={"Authorization": f"Bearer {unlinked_token}"})

        ok = r1.status_code == 200 and r2.status_code == 403 and r3.status_code == 403
        if not ok:
            print(f"FAIL: 200={r1.status_code} 403_no_token={r2.status_code} 403_unlinked={r3.status_code}")
            sys.exit(1)

        # 5. Write proof
        out = ROOT / "evidence" / "ACL_PROOF.txt"
        out.parent.mkdir(parents=True, exist_ok=True)
        with open(out, "w") as f:
            f.write("# ACL Proof — Document Download (use-existing mode)\n\n")
            f.write("## 1. 200 with linked supplier token\n\n")
            f.write(f"GET /api/documents/{doc_id}/download with Authorization: Bearer $SUPPLIER_TOKEN\n")
            f.write(f"Status: {r1.status_code}\n\n")
            f.write("## 2. 403 without token\n\n")
            f.write(f"GET /api/documents/{doc_id}/download (no Authorization)\n")
            f.write(f"Status: {r2.status_code}\n\n")
            f.write("## 3. 403 with unlinked supplier token\n\n")
            f.write(f"GET /api/documents/{doc_id}/download with Authorization: Bearer $UNLINKED_TOKEN\n")
            f.write(f"Status: {r3.status_code}\n")

        print(f"ACL proof written to {out}")
    finally:
        # 6. Remove temp supplier (no junk)
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient
        from dotenv import load_dotenv
        load_dotenv(ROOT / "backend" / ".env")
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "bestprice_local")
        client = AsyncIOMotorClient(mongo_url)
        db = client[db_name]

        async def cleanup():
            if temp_user_id:
                await db.users.delete_many({"id": temp_user_id})
            if temp_company_id:
                await db.companies.delete_many({"id": temp_company_id})
                await db.supplier_settings.delete_many({"supplierCompanyId": temp_company_id})

        asyncio.run(cleanup())
        print("Temp unlinked supplier removed (no junk).")


def run_standalone():
    """Create acl_* entities (for standalone E2E)."""
    # Register linked supplier + restaurant, link, upload
    r = req("POST", "/auth/register/supplier", json={
        "email": "acl_linked@example.com",
        "password": "TestPass123!",
        "inn": "7700000011",
        "companyName": "ACL Linked",
        "legalAddress": "Москва",
        "ogrn": "1027700000011",
        "actualAddress": "Москва",
        "phone": "+79001111111",
        "companyEmail": "l@acl.example.com",
        "contactPersonName": "И",
        "contactPersonPosition": "Д",
        "contactPersonPhone": "+79001111111",
        "dataProcessingConsent": True,
    })
    if r.status_code == 400:
        r = req("POST", "/auth/login", json={"email": "acl_linked@example.com", "password": "TestPass123!"})
    if r.status_code != 200:
        print(f"FAIL: linked supplier {r.status_code}")
        sys.exit(1)
    linked_token = r.json()["access_token"]

    r = req("POST", "/auth/register/customer", json={
        "email": "acl_rest@example.com",
        "password": "TestPass123!",
        "inn": "7700000012",
        "companyName": "ACL Rest",
        "legalAddress": "Москва",
        "ogrn": "1027700000012",
        "actualAddress": "Москва",
        "phone": "+79001111112",
        "companyEmail": "r@acl.example.com",
        "contactPersonName": "П",
        "contactPersonPosition": "Д",
        "contactPersonPhone": "+79001111112",
        "deliveryAddresses": [],
        "dataProcessingConsent": True,
    })
    if r.status_code == 400:
        r = req("POST", "/auth/login", json={"email": "acl_rest@example.com", "password": "TestPass123!"})
    if r.status_code != 200:
        print(f"FAIL: restaurant {r.status_code}")
        sys.exit(1)
    rest_company = r.json().get("user", {}).get("companyId")
    rest_token = r.json()["access_token"]

    req("POST", "/supplier/accept-contract", headers={"Authorization": f"Bearer {linked_token}"}, json={"restaurantId": rest_company})

    pdf = ROOT / "backend" / "uploads" / "_acl_sample.pdf"
    pdf.parent.mkdir(parents=True, exist_ok=True)
    if not pdf.exists():
        pdf.write_bytes(b"%PDF-1.4 ACL\n")
    with open(pdf, "rb") as f:
        r = req("POST", "/documents/upload", headers={"Authorization": f"Bearer {rest_token}"}, files={"file": ("a.pdf", f, "application/pdf")}, data={"document_type": "Договор"})
    if r.status_code not in (200, 201):
        print(f"FAIL: upload {r.status_code} {r.text}")
        sys.exit(1)
    doc_id = r.json()["id"]

    r = req("POST", "/auth/register/supplier", json={
        "email": "acl_unlinked@example.com",
        "password": "TestPass123!",
        "inn": "7700000013",
        "companyName": "ACL Unlinked",
        "legalAddress": "Москва",
        "ogrn": "1027700000013",
        "actualAddress": "Москва",
        "phone": "+79001111113",
        "companyEmail": "u@acl.example.com",
        "contactPersonName": "У",
        "contactPersonPosition": "Д",
        "contactPersonPhone": "+79001111113",
        "dataProcessingConsent": True,
    })
    if r.status_code == 400:
        r = req("POST", "/auth/login", json={"email": "acl_unlinked@example.com", "password": "TestPass123!"})
    if r.status_code != 200:
        print(f"FAIL: unlinked supplier {r.status_code}")
        sys.exit(1)
    unlinked_token = r.json()["access_token"]

    r1 = req("GET", f"/documents/{doc_id}/download", headers={"Authorization": f"Bearer {linked_token}"})
    r2 = req("GET", f"/documents/{doc_id}/download")
    r3 = req("GET", f"/documents/{doc_id}/download", headers={"Authorization": f"Bearer {unlinked_token}"})

    out = ROOT / "evidence" / "ACL_PROOF.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("# ACL Proof — Document Download (standalone)\n\n")
        f.write("## 1. 200 with linked supplier token\n\n")
        f.write(f"GET /api/documents/{doc_id}/download with Authorization: Bearer $LINKED_TOKEN\n")
        f.write(f"Status: {r1.status_code}\n\n")
        f.write("## 2. 403 without token\n\n")
        f.write(f"GET /api/documents/{doc_id}/download (no Authorization)\n")
        f.write(f"Status: {r2.status_code}\n\n")
        f.write("## 3. 403 with unlinked supplier token\n\n")
        f.write(f"GET /api/documents/{doc_id}/download with Authorization: Bearer $UNLINKED_TOKEN\n")
        f.write(f"Status: {r3.status_code}\n")

    ok = r1.status_code == 200 and r2.status_code == 403 and r3.status_code == 403
    if not ok:
        print(f"FAIL: 200={r1.status_code} 403_no_token={r2.status_code} 403_unlinked={r3.status_code}")
        sys.exit(1)
    print(f"ACL proof written to {out}")


def main():
    use_existing = "--use-existing" in sys.argv
    sup_email = os.environ.get("SUPPLIER_EMAIL", "supplier@example.com")
    sup_pw = os.environ.get("SUPPLIER_PASSWORD", "TestPass123!")
    rest_email = os.environ.get("RESTAURANT_EMAIL", "restaurant@example.com")
    rest_pw = os.environ.get("RESTAURANT_PASSWORD", "TestPass123!")

    if use_existing:
        run_with_existing(sup_email, sup_pw, rest_email, rest_pw)
    else:
        run_standalone()


if __name__ == "__main__":
    main()
