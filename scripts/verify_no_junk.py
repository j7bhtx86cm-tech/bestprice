#!/usr/bin/env python3
"""
Verify exactly 1 supplier, 1 restaurant, 1 link, 1 document. No junk.
Exits 0 if all counts match, 1 otherwise. Writes evidence/NO_JUNK_ASSERTIONS.txt
"""
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


async def main():
    from motor.motor_asyncio import AsyncIOMotorClient
    from dotenv import load_dotenv

    load_dotenv(ROOT / "backend" / ".env")
    mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
    db_name = os.environ.get("DB_NAME", "bestprice_local")
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]

    suppliers = await db.companies.count_documents({"type": "supplier"})
    restaurants = await db.companies.count_documents({"type": "customer"})
    links = await db.supplier_restaurant_settings.count_documents({})
    documents = await db.documents.count_documents({})
    users = await db.users.count_documents({})

    lines = [
        "NO JUNK ASSERTIONS",
        "==================",
        f"suppliers (companies type=supplier): {suppliers} (expected 1)",
        f"restaurants (companies type=customer): {restaurants} (expected 1)",
        f"links (supplier_restaurant_settings): {links} (expected 1)",
        f"documents: {documents} (expected 1)",
        f"users: {users} (expected 2: 1 supplier + 1 restaurant)",
        "",
    ]

    ok = suppliers == 1 and restaurants == 1 and links == 1 and documents == 1
    if ok:
        lines.append("RESULT: PASS - exactly 1/1/1/1")
    else:
        lines.append("RESULT: FAIL - counts do not match expected 1/1/1/1")

    out = ROOT / "evidence" / "NO_JUNK_ASSERTIONS.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        f.write("\n".join(lines))

    for line in lines:
        print(line)

    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
