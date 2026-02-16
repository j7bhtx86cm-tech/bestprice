#!/usr/bin/env python3
"""
E2E: Auto-accept contract when restaurant uploads document.
Requires: backend on 8001 with AUTO_ACCEPT_CONTRACTS=1 (or BESTPRICE_AUTO_ACCEPT_CONTRACTS=1).
Flow: register supplier + restaurant, NO manual accept-contract, upload doc,
      verify supplier sees contractStatus=accepted and can download.
Exits 0 on success.
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
    # 1. Register supplier
    r = req("POST", "/auth/register/supplier", json={
        "email": "auto_accept_sup@example.com",
        "password": "TestPass123!",
        "inn": "7700000021",
        "companyName": "Auto Accept Supplier",
        "legalAddress": "Москва",
        "ogrn": "1027700000021",
        "actualAddress": "Москва",
        "phone": "+79001234521",
        "companyEmail": "sup@auto.example.com",
        "contactPersonName": "Иванов",
        "contactPersonPosition": "Директор",
        "contactPersonPhone": "+79001234521",
        "dataProcessingConsent": True,
    })
    if r.status_code == 400 and "already registered" in (r.json().get("detail") or "").lower():
        r = req("POST", "/auth/login", json={"email": "auto_accept_sup@example.com", "password": "TestPass123!"})
    if r.status_code != 200:
        print(f"FAIL: supplier register/login {r.status_code} {r.text}")
        sys.exit(1)
    sup_token = r.json()["access_token"]
    sup_company = r.json().get("user", {}).get("companyId")
    if not sup_company:
        print("FAIL: no companyId in supplier response")
        sys.exit(1)
    headers_sup = {"Authorization": f"Bearer {sup_token}"}

    # 2. Register restaurant
    r = req("POST", "/auth/register/customer", json={
        "email": "auto_accept_rest@example.com",
        "password": "TestPass123!",
        "inn": "7700000022",
        "companyName": "Auto Accept Restaurant",
        "legalAddress": "Москва",
        "ogrn": "1027700000022",
        "actualAddress": "Москва",
        "phone": "+79001234522",
        "companyEmail": "rest@auto.example.com",
        "contactPersonName": "Петров",
        "contactPersonPosition": "Директор",
        "contactPersonPhone": "+79001234522",
        "deliveryAddresses": [],
        "dataProcessingConsent": True,
    })
    if r.status_code == 400 and "already registered" in (r.json().get("detail") or "").lower():
        r = req("POST", "/auth/login", json={"email": "auto_accept_rest@example.com", "password": "TestPass123!"})
    if r.status_code != 200:
        print(f"FAIL: restaurant register/login {r.status_code} {r.text}")
        sys.exit(1)
    rest_token = r.json()["access_token"]
    rest_company = r.json().get("user", {}).get("companyId")
    if not rest_company:
        print("FAIL: no companyId in restaurant response")
        sys.exit(1)
    headers_rest = {"Authorization": f"Bearer {rest_token}"}

    # 3. NO accept-contract - restaurant uploads directly
    pdf_path = ROOT / "tests" / "fixtures" / "sample.pdf"
    if not pdf_path.exists():
        pdf_path = ROOT / "backend" / "uploads" / "_auto_accept_sample.pdf"
        pdf_path.parent.mkdir(parents=True, exist_ok=True)
        pdf_path.write_bytes(b"%PDF-1.4 Auto-accept E2E\n")
    with open(pdf_path, "rb") as f:
        files = {"file": ("sample.pdf", f, "application/pdf")}
        data = {"document_type": "Договор"}
        r = req("POST", "/documents/upload", headers=headers_rest, files=files, data=data)
    if r.status_code not in (200, 201):
        print(f"FAIL: document upload {r.status_code} {r.text}")
        sys.exit(1)
    doc_id = r.json().get("id")
    if not doc_id:
        print("FAIL: no doc id in upload response")
        sys.exit(1)

    # 4. Supplier lists restaurant-documents — contractStatus must be "accepted" (auto-accepted)
    r = req("GET", "/supplier/restaurant-documents", headers=headers_sup)
    if r.status_code != 200:
        print(f"FAIL: restaurant-documents {r.status_code} {r.text}")
        sys.exit(1)
    items = r.json()
    by_rest = {x["restaurantId"]: x for x in items}
    if rest_company not in by_rest:
        print("FAIL: restaurant not in supplier restaurant-documents")
        sys.exit(1)
    status = by_rest[rest_company].get("contractStatus")
    if status != "accepted":
        print(f"FAIL: expected contractStatus=accepted, got {status} (AUTO_ACCEPT_CONTRACTS=1?)")
        sys.exit(1)

    # 5. Supplier downloads document
    r = req("GET", f"/documents/{doc_id}/download", headers=headers_sup)
    if r.status_code != 200:
        print(f"FAIL: supplier download {r.status_code}")
        sys.exit(1)

    print("E2E: auto-accept OK — restaurant upload -> supplier sees accepted + can download")


if __name__ == "__main__":
    main()
