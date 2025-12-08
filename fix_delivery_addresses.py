#!/usr/bin/env python3
"""Fix delivery addresses that are still in string format"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent / 'backend'
load_dotenv(ROOT_DIR / '.env')

async def fix_delivery_addresses():
    # Connect to MongoDB
    mongo_url = os.environ['MONGO_URL']
    client = AsyncIOMotorClient(mongo_url)
    db = client[os.environ['DB_NAME']]
    
    print("Checking for companies with string-format delivery addresses...")
    
    # Find all companies
    companies = await db.companies.find({}).to_list(length=None)
    
    fixed_count = 0
    for company in companies:
        if 'deliveryAddresses' in company and company['deliveryAddresses']:
            needs_fix = False
            fixed_addresses = []
            
            for addr in company['deliveryAddresses']:
                if isinstance(addr, str):
                    # Convert string to object format
                    fixed_addresses.append({
                        'address': addr,
                        'phone': '',
                        'additionalPhone': None
                    })
                    needs_fix = True
                    print(f"Found string address in company {company.get('companyName', company['id'])}: {addr}")
                elif isinstance(addr, dict):
                    # Already in correct format
                    fixed_addresses.append(addr)
                else:
                    print(f"Unknown address format: {type(addr)} - {addr}")
            
            if needs_fix:
                # Update the company
                result = await db.companies.update_one(
                    {'id': company['id']},
                    {'$set': {'deliveryAddresses': fixed_addresses}}
                )
                if result.modified_count > 0:
                    fixed_count += 1
                    print(f"✅ Fixed delivery addresses for company: {company.get('companyName', company['id'])}")
    
    print(f"\n✅ Migration complete! Fixed {fixed_count} companies")
    client.close()

if __name__ == '__main__':
    asyncio.run(fix_delivery_addresses())
