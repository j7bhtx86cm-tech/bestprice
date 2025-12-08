"""
Migrate delivery addresses from string format to object format with phone numbers
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

async def migrate():
    """Migrate delivery addresses from old string format to new object format"""
    print("🔄 Starting delivery address migration...")
    
    # Get all companies
    companies = await db.companies.find({}).to_list(1000)
    
    migrated_count = 0
    for company in companies:
        if 'deliveryAddresses' in company and company['deliveryAddresses']:
            needs_migration = False
            new_addresses = []
            
            for addr in company['deliveryAddresses']:
                if isinstance(addr, str):
                    # Convert string to object format
                    new_addresses.append({
                        'address': addr,
                        'phone': '',
                        'additionalPhone': ''
                    })
                    needs_migration = True
                elif isinstance(addr, dict):
                    # Already in new format, keep as is
                    new_addresses.append(addr)
            
            if needs_migration:
                # Update the company
                await db.companies.update_one(
                    {'id': company['id']},
                    {'$set': {'deliveryAddresses': new_addresses}}
                )
                migrated_count += 1
                print(f"✅ Migrated {company.get('companyName', company['id'])}")
    
    print(f"\n🎉 Migration complete! Migrated {migrated_count} companies")
    client.close()

if __name__ == "__main__":
    asyncio.run(migrate())
