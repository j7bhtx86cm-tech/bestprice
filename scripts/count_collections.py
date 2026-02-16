#!/usr/bin/env python3
"""Count documents in key collections. For CLEAN_SLATE before/after."""
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

    cols = [
        "users", "companies", "supplier_settings", "supplier_restaurant_settings",
        "documents", "orders", "orders_v12", "supplier_items", "cart_intents",
        "cart_items_v12", "cart_plans_v12", "favorites_v12",
    ]
    for c in cols:
        try:
            n = await db[c].count_documents({})
            print(f"{c}: {n}")
        except Exception as e:
            print(f"{c}: (error {e})")

if __name__ == "__main__":
    asyncio.run(main())
