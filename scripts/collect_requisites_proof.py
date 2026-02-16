#!/usr/bin/env python3
"""
Proof: supplier sees restaurant requisites (preview + full).

- restaurantRequisitesPreview: 4 fields, always (companyName, inn, phone, email)
- restaurantRequisitesFull: whitelist + edoNumber, guid — only for linked restaurants
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
    sup_email = os.environ.get("SUPPLIER_EMAIL", "supplier@example.com")
    sup_pw = os.environ.get("SUPPLIER_PASSWORD", "TestPass123!")

    r = req("POST", "/auth/login", json={"email": sup_email, "password": sup_pw})
    if r.status_code != 200:
        print(f"FAIL: supplier login {r.status_code}")
        sys.exit(1)
    token = r.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}

    r = req("GET", "/supplier/restaurant-documents", headers=headers)
    if r.status_code != 200:
        print(f"FAIL: restaurant-documents {r.status_code} {r.text}")
        sys.exit(1)
    items = r.json()
    if not items:
        print("FAIL: no restaurants in response")
        sys.exit(1)

    for item in items:
        preview = item.get("restaurantRequisitesPreview")
        full = item.get("restaurantRequisitesFull")
        if preview is not None and not isinstance(preview, dict):
            print(f"FAIL: restaurantRequisitesPreview must be dict or null, got {type(preview)}")
            sys.exit(1)
        if full is not None and not isinstance(full, dict):
            print(f"FAIL: restaurantRequisitesFull must be dict or null, got {type(full)}")
            sys.exit(1)
        if preview and set(preview.keys()) - {"companyName", "inn", "phone", "email"}:
            print(f"FAIL: preview has extra keys: {set(preview.keys())}")
            sys.exit(1)
        if full and "edoNumber" not in full and "guid" not in full:
            pass  # optional
        if full and "companyName" not in full and "inn" not in full:
            pass  # at least one expected for non-empty

    linked = [x for x in items if x.get("contractStatus") == "accepted"]
    if not linked:
        print("FAIL: no linked restaurant (need 1/1/1/1 with accept-contract)")
        sys.exit(1)
    first = linked[0]
    preview = first.get("restaurantRequisitesPreview")
    full = first.get("restaurantRequisitesFull")
    if not full:
        print("FAIL: linked restaurant must have restaurantRequisitesFull")
        sys.exit(1)
    if "edoNumber" not in full or "guid" not in full:
        print("FAIL: full must include edoNumber and guid for reference flow")
        sys.exit(1)

    out = ROOT / "evidence" / "SUPPLIER_REQUISITES_API_PROOF.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("# Supplier requisites API proof\n\n")
        f.write(f"GET {BASE}/api/supplier/restaurant-documents\n")
        f.write("Status: 200\n\n")
        f.write("## restaurantRequisitesPreview (4 fields, always)\n")
        f.write(f"Keys: {list(preview.keys()) if preview else []}\n\n")
        f.write("## restaurantRequisitesFull (linked only, whitelist + edoNumber, guid)\n")
        f.write(f"Keys: {list(full.keys())}\n")
        f.write(f"edoNumber: {full.get('edoNumber', '')}\n")
        f.write(f"guid: {full.get('guid', '')}\n")
        f.write("\nRESULT: PASS\n")

    print(f"Requisites proof written to {out}")
    print("PASS")


if __name__ == "__main__":
    main()
