#!/usr/bin/env python3
"""
Initialize supplier users and settings for BestPrice.

- Ensures each of the 9 supplier companies has a user (for login) and supplier_settings.
- Generates passwords (stored hashed in users; plain only in Excel export).
- Idempotent: safe to run multiple times (skips existing users/settings).
- Exports supplier_accesses.xlsx to _exports/ (supplier_email, password_plain, company_id, user_id, role, login_url).

Usage:
    python scripts/init_suppliers.py [--base-url http://127.0.0.1:8000]
    python scripts/init_suppliers.py --dry-run

Environment: load backend/.env for MONGO_URL, DB_NAME.
"""

from __future__ import annotations

import argparse
import os
import secrets
import string
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ENV = ROOT / "backend" / ".env"
EXPORTS_DIR = ROOT / "_exports"
EXCEL_PATH = EXPORTS_DIR / "supplier_accesses.xlsx"

# All 9 supplier emails; we match company to email by name prefix
SUPPLIER_EMAIL_BY_PREFIX = {
    "aifrut": "aifrut.1-00001@company.com",
    "alati": "alati.1-00002@company.com",
    "vostok": "vostok-zapad.1-00003@company.com",
    "integrita": "integrita.1-00004@company.com",
    "nordiko": "nordiko.1-00005@company.com",
    "praimfuds": "praimfuds.1-00006@company.com",
    "rbd": "rbd.1-00007@company.com",
    "romaks": "romaks.1-00008@company.com",
    "sladkaya": "sladkaya.zhizn-00010@company.com",
}
SUPPLIER_EMAILS = list(SUPPLIER_EMAIL_BY_PREFIX.values())


def hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def generate_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))


def main() -> None:
    parser = argparse.ArgumentParser(description="Init supplier users and export accesses Excel")
    parser.add_argument("--dry-run", action="store_true", help="Do not write to DB or Excel (still connects to Mongo to list companies)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000", help="Base API URL for login_url")
    args = parser.parse_args()

    if BACKEND_ENV.exists():
        load_dotenv(BACKEND_ENV)
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "test_database")
    login_url = f"{args.base_url.rstrip('/')}/api/auth/login"

    client = MongoClient(mongo_url)
    db = client[db_name]

    companies = list(
        db.companies.find({"type": "supplier"}, {"_id": 0, "id": 1, "userId": 1, "companyName": 1, "email": 1})
    )
    companies.sort(key=lambda c: (c.get("id") or ""))

    def email_for_company(c: dict) -> str:
        name = (c.get("companyName") or c.get("email") or "").lower()
        for prefix, em in SUPPLIER_EMAIL_BY_PREFIX.items():
            if prefix in name or name.startswith(prefix[:4]):
                return em
        return c.get("email") or f"supplier-{c.get('id', '')}@company.com"

    rows = []
    for company in companies:
        company_id = company.get("id")
        email = email_for_company(company)
        existing_user = db.users.find_one({"email": email}, {"_id": 0, "id": 1, "email": 1})
        if existing_user:
            user_id = existing_user["id"]
            password_plain = "(unchanged; set manually if needed)"
            if not args.dry_run:
                db.companies.update_one({"id": company_id}, {"$set": {"userId": user_id}})
        else:
            user_id = str(__import__("uuid").uuid4())
            password_plain = generate_password()
            password_hash = hash_password(password_plain)
            if not args.dry_run:
                now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
                db.users.insert_one({
                    "id": user_id,
                    "email": email,
                    "passwordHash": password_hash,
                    "role": "supplier",
                    "createdAt": now,
                    "updatedAt": now,
                })
                db.companies.update_one({"id": company_id}, {"$set": {"userId": user_id}})

        existing_settings = db.supplier_settings.find_one({"supplierCompanyId": company_id}, {"_id": 0, "id": 1})
        if not existing_settings and not args.dry_run:
            now = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
            db.supplier_settings.insert_one({
                "id": str(__import__("uuid").uuid4()),
                "supplierCompanyId": company_id,
                "minOrderAmount": 0,
                "deliveryDays": [],
                "deliveryTime": "",
                "orderReceiveDeadline": "",
                "logisticsType": "own",
                "updatedAt": now,
            })

        rows.append({
            "supplier_email": email,
            "password_plain": password_plain,
            "company_id": company_id,
            "user_id": user_id,
            "role": "supplier",
            "login_url": login_url,
            "notes": company.get("companyName", ""),
        })

    if not rows:
        print("No supplier companies found in DB. Nothing to do.")
        return

    print(f"Processed {len(rows)} suppliers.")
    if args.dry_run:
        for r in rows:
            print(f"  {r['supplier_email']} -> company_id={r['company_id']}")
        return

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    try:
        from openpyxl import Workbook
    except ImportError:
        print("ERROR: openpyxl required for Excel export. Install: pip install openpyxl")
        raise SystemExit(1)
    wb = Workbook()
    ws = wb.active
    ws.title = "Supplier accesses"
    headers = ["supplier_email", "password_plain", "company_id", "user_id", "role", "login_url", "notes"]
    ws.append(headers)
    for r in rows:
        ws.append([r.get(h, "") for h in headers])
    wb.save(EXCEL_PATH)
    print("_exports/supplier_accesses.xlsx")
    print("✅ EXPORTED")


if __name__ == "__main__":
    main()
