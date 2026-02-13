#!/usr/bin/env python3
"""
Dev utility: reset supplier-related data for a clean bulk import run.

This script truncates supplier/customer collections in the configured MongoDB
database.  It is intentionally explicit about what it removes and refuses to run
unless --force is provided (or you pass --yes).

Usage:
    python scripts/dev_reset_data.py --force

Environment variables are read from backend/.env (if present) so it respects the
same MONGO_URL / DB_NAME used by the FastAPI backend.
"""

from __future__ import annotations

import argparse
import os
from pathlib import Path
from typing import Dict

from dotenv import load_dotenv
from pymongo import MongoClient

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ENV = ROOT / "backend" / ".env"

if BACKEND_ENV.exists():
    load_dotenv(BACKEND_ENV)

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "test_database")

COLLECTIONS_TO_CLEAR = [
    "users",
    "companies",
    "supplier_items",
    "pricelists",
    "price_list_uploads",
    "supplier_settings",
    "orders",
    "documents",
    "matrices",
    "matrix_products",
]


def fmt_counts(counts: Dict[str, int]) -> str:
    lines = []
    for name, count in counts.items():
        lines.append(f"  - {name}: {count}")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Reset supplier/customer data for local development."
    )
    parser.add_argument(
        "--force",
        "--yes",
        dest="force",
        action="store_true",
        help="Actually perform the reset (required).",
    )
    args = parser.parse_args()

    if not args.force:
        print("⚠️  This will DELETE supplier/customer data in MongoDB.")
        print("    Re-run with --force to proceed.")
        return

    if "prod" in DB_NAME.lower():
        raise SystemExit(
            f"Refusing to run against database '{DB_NAME}' (looks like production)."
        )

    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]

    existing_counts = {
        name: db[name].estimated_document_count()
        for name in COLLECTIONS_TO_CLEAR
    }

    print("📊 Current document counts:")
    print(fmt_counts(existing_counts))

    for name in COLLECTIONS_TO_CLEAR:
        db[name].delete_many({})

    post_counts = {
        name: db[name].estimated_document_count()
        for name in COLLECTIONS_TO_CLEAR
    }

    print("\n🧹 Reset complete.")
    print(fmt_counts(post_counts))


if __name__ == "__main__":
    main()
