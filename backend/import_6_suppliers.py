"""
Import complete catalog with 6 suppliers from multi-tab Excel file
Each tab = one supplier
Columns: Supplier, Code, Product Name, Unit, Min Qty, Price per unit, Min order amount
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from pathlib import Path
import uuid
from datetime import datetime, timezone
import pandas as pd
import requests
import bcrypt

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

FILE_URL = 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/b1378429_%D0%92%D0%A1%D0%95%20%D0%B2%D0%BA%D0%BB%D0%B0%D0%B4%D0%BA%D0%B8.xlsx'

# Supplier email mapping
SUPPLIER_EMAILS = {
    'Алиди': 'alidi@bestprice.ru',
    'Интегрита': 'integrita@bestprice.ru',
    'Ромакс': 'romax@bestprice.ru',
    'Прайфуд': 'primefood@bestprice.ru',
    'Vici': 'vici@bestprice.ru',
    'В-З': 'vz@bestprice.ru'
}

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

async def create_or_get_supplier(supplier_name):
    """Create supplier if doesn't exist"""
    company = await db.companies.find_one({"companyName": supplier_name}, {"_id": 0})
    
    if company:
        return company['id']
    
    # Create user
    email = SUPPLIER_EMAILS.get(supplier_name, f"{supplier_name.lower()}@bestprice.ru")
    user = await db.users.find_one({"email": email}, {"_id": 0})
    
    if not user:
        user_id = str(uuid.uuid4())
        await db.users.insert_one({
            'id': user_id,
            'email': email,
            'passwordHash': hash_password('password123'),
            'role': 'supplier',
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'updatedAt': datetime.now(timezone.utc).isoformat()
        })
    else:
        user_id = user['id']
    
    # Create company
    company_id = str(uuid.uuid4())
    await db.companies.insert_one({
        'id': company_id,
        'type': 'supplier',
        'userId': user_id,
        'inn': f"{7700000000 + abs(hash(supplier_name)) % 1000000}",
        'ogrn': f"{1027700000000 + abs(hash(supplier_name)) % 1000000}",
        'companyName': supplier_name,
        'legalAddress': f"г. Москва, {supplier_name}",
        'actualAddress': f"г. Москва, {supplier_name}",
        'phone': '+7 (495) 000-00-00',
        'email': email,
        'contractAccepted': True,
        'createdAt': datetime.now(timezone.utc).isoformat(),
        'updatedAt': datetime.now(timezone.utc).isoformat()
    })
    
    print(f"  ✅ Created supplier: {supplier_name}")
    return company_id

async def import_new_catalog():
    print("🔄 IMPORTING NEW 6-SUPPLIER CATALOG")
    print("=" * 70)
    
    # Download file
    print("\n📥 Downloading file...")
    r = requests.get(FILE_URL)
    filename = '/tmp/all_suppliers.xlsx'
    with open(filename, 'wb') as f:
        f.write(r.content)
    
    # Clear all existing suppliers and products
    print("\n🗑️  Clearing existing data...")
    await db.price_lists.delete_many({})
    old_suppliers = await db.companies.find({"type": "supplier"}, {"_id": 0}).to_list(100)
    for supplier in old_suppliers:
        await db.users.delete_many({"id": supplier['userId']})
        await db.companies.delete_one({"id": supplier['id']})
    print(f"   Cleared {len(old_suppliers)} old suppliers")
    
    # Read Excel file
    xl = pd.ExcelFile(filename)
    print(f"\n📋 Found {len(xl.sheet_names)} sheets: {', '.join(xl.sheet_names)}")
    
    total_products = 0
    
    # Process each sheet (supplier)
    for sheet_name in xl.sheet_names:
        print(f"\n{'='*70}")
        print(f"📦 Processing: {sheet_name}")
        print(f"{'='*70}")
        
        # Read sheet
        df = pd.read_excel(filename, sheet_name=sheet_name, header=None)
        
        # Find header row (row with "Наименование продукта")
        header_row = 1  # Usually at row 1
        
        # Column indices (based on structure analysis)
        # Column 0: Supplier name
        # Column 1: Product code
        # Column 2: Product name
        # Column 3: Unit (metrics)
        # Column 4: Minimum quantity
        # Column 5: Price per unit
        # Column 6: Minimum order amount
        
        # Get or create supplier
        company_id = await create_or_get_supplier(sheet_name)
        
        products = []
        
        # Parse data rows
        for idx in range(header_row + 1, len(df)):
            row = df.iloc[idx]
            
            # Skip empty rows
            if pd.isna(row[2]) or str(row[2]).strip() == '':
                continue
            
            try:
                product_code = str(row[1]).strip() if pd.notna(row[1]) else str(idx)
                product_name = str(row[2]).strip()
                unit = str(row[3]).strip() if pd.notna(row[3]) else 'шт'
                min_qty = int(row[4]) if pd.notna(row[4]) and row[4] != '' else 1
                price = float(row[5]) if pd.notna(row[5]) else None
                
                if not price or price <= 0:
                    continue
                
                products.append({
                    'productName': product_name[:200],
                    'article': product_code,
                    'price': price,
                    'unit': unit,
                    'minQuantity': min_qty
                })
                
            except Exception as e:
                continue
        
        # Import products
        if products:
            print(f"💾 Importing {len(products)} products...")
            
            for i, product in enumerate(products):
                await db.price_lists.insert_one({
                    'id': str(uuid.uuid4()),
                    'supplierCompanyId': company_id,
                    'productName': product['productName'],
                    'article': product['article'],
                    'price': product['price'],
                    'unit': product['unit'],
                    'minQuantity': product['minQuantity'],
                    'availability': True,
                    'active': True,
                    'createdAt': datetime.now(timezone.utc).isoformat(),
                    'updatedAt': datetime.now(timezone.utc).isoformat()
                })
                
                if (i + 1) % 200 == 0:
                    print(f"  Imported {i + 1}/{len(products)}...")
            
            print(f"✅ Imported {len(products)} products for {sheet_name}")
            total_products += len(products)
        else:
            print(f"⚠️  No products found for {sheet_name}")
    
    print(f"\n{'='*70}")
    print(f"🎉 IMPORT COMPLETE")
    print(f"📊 Total: {total_products} products")
    print(f"{'='*70}")
    
    # Verify
    print(f"\n📋 Final verification:")
    suppliers = await db.companies.find({"type": "supplier"}, {"_id": 0, "companyName": 1, "id": 1}).to_list(20)
    grand_total = 0
    
    for s in suppliers:
        count = await db.price_lists.count_documents({"supplierCompanyId": s['id']})
        status = "✅" if count > 50 else ("⚠️" if count > 0 else "❌")
        print(f"  {status} {s['companyName']}: {count} products")
        grand_total += count
    
    print(f"\n📊 GRAND TOTAL: {grand_total} products across {len(suppliers)} suppliers")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(import_new_catalog())
