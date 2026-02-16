#!/usr/bin/env python3
"""Clean slate: remove all test/dev data. Run via clean_slate_local.sh with ALLOW_DESTRUCTIVE=1."""
import asyncio
import os
from pathlib import Path

async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parent.parent / "backend" / ".env")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "bestprice_local")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    collections = [
        "users", "companies", "supplier_settings", "supplier_restaurant_settings",
        "documents", "orders", "price_lists", "supplier_items", "price_list_uploads",
        "orders_v12", "cart_intents", "cart_items_v12", "cart_plans_v12",
        "favorites_v12", "catalog_references", "pricelists", "products",
        "phone_otp",
    ]
    names = await db.list_collection_names()
    if "supplier_restaurant_links" in names:
        collections.append("supplier_restaurant_links")

    deleted = {}
    for c in collections:
        try:
            r = await db[c].delete_many({})
            deleted[c] = r.deleted_count
        except Exception as e:
            deleted[c] = str(e)

    for k, v in deleted.items():
        print(f"  {k}: {v}")

    # Clear uploads
    backend = Path(__file__).resolve().parent.parent / "backend"
    uploads = backend / "uploads"
    if uploads.exists():
        for f in uploads.glob("*"):
            if f.is_file():
                f.unlink()
                print(f"  uploads: removed {f.name}")

if __name__ == "__main__":
    asyncio.run(main())
