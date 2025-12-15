import pandas as pd
import requests
from io import BytesIO
from pymongo import MongoClient
import os
from datetime import datetime, timezone
from uuid import uuid4
import bcrypt

# MongoDB connection - USE THE CORRECT DATABASE FROM .env
MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
client = MongoClient(MONGO_URL)
db = client[DB_NAME]

print(f"Using database: {DB_NAME}")

# Catalogue URLs
catalogues = {
    'Айфрут': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/bjvh1y8b_%D0%90%D0%B8%CC%86%D1%84%D1%80%D1%83%D1%82-2.xlsx',
    'Алиди': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/coufww7q_%D0%90%D0%BB%D0%B8%D0%B4%D0%B8-3.xlsx',
    'Восток-Запад': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/2442oi0r_%D0%92%D0%BE%D1%81%D1%82%D0%BE%D0%BA-%D0%97%D0%B0%D0%BF%D0%B0%D0%B4.xlsx',
    'Интегрита': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/rq6d8ihy_%D0%98%D0%BD%D1%82%D0%B5%D0%B3%D1%80%D0%B8%D1%82%D0%B0-3.xlsx',
    'Нордико': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/van2n8wi_%D0%9D%D0%BE%D1%80%D0%B4%D0%B8%D0%BA%D0%BE.xlsx',
    'ПраймФудс': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/vtuc5uf2_%D0%9F%D1%80%D0%B0%D0%B8%CC%86%D0%BC%D0%A4%D1%83%D0%B4%D1%81-3.xlsx',
    'РБД': 'https://customer-assets.emergentagent.com/job_foodsupply-hub-4/artifacts/dpo9ci7q_%D0%A0%D0%91%D0%94.xlsx'
}

print("\n" + "=" * 80)
print("🔄 STARTING CATALOGUE IMPORT TO", DB_NAME)
print("=" * 80)

# Step 1: Clear existing products and pricelists
print("\n📦 Step 1: Clearing existing products and pricelists...")
products_deleted = db.products.delete_many({})
pricelists_deleted = db.pricelists.delete_many({})
print(f"   ✅ Deleted {products_deleted.deleted_count} products")
print(f"   ✅ Deleted {pricelists_deleted.deleted_count} pricelist items")

# Step 2: Check existing suppliers
print("\n👥 Step 2: Checking supplier accounts...")
existing_suppliers = {}
for supplier in db.companies.find({"companyType": "supplier"}, {"_id": 0}):
    existing_suppliers[supplier['name']] = supplier
    print(f"   ✓ Found existing supplier: {supplier['name']}")

# Step 3: Process each catalogue
print("\n📊 Step 3: Processing catalogues...")
total_products_added = 0
total_pricelist_items_added = 0

for supplier_name, url in catalogues.items():
    print(f"\n   📁 {supplier_name}")
    
    try:
        # Download and read Excel
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        df = pd.read_excel(BytesIO(response.content))
        
        # Clean data
        df = df.dropna(subset=['Item_Name'])
        df = df.fillna('')
        
        # Get or create supplier
        if supplier_name in existing_suppliers:
            supplier_company = existing_suppliers[supplier_name]
            print(f"      Using existing supplier account")
        else:
            # Create new supplier account
            supplier_id = str(uuid4())
            supplier_email = f"{supplier_name.lower().replace(' ', '').replace('-', '')}@bestprice.ru"
            
            # Hash password
            hashed_pw = bcrypt.hashpw("password123".encode('utf-8'), bcrypt.gensalt())
            
            # Create user account
            user_doc = {
                "id": str(uuid4()),
                "email": supplier_email,
                "passwordHash": hashed_pw.decode('utf-8'),
                "role": "supplier",
                "companyId": supplier_id,
                "createdAt": datetime.now(timezone.utc).isoformat()
            }
            db.users.insert_one(user_doc)
            
            # Create company
            supplier_company = {
                "id": supplier_id,
                "name": supplier_name,
                "companyType": "supplier",
                "createdAt": datetime.now(timezone.utc).isoformat()
            }
            db.companies.insert_one(supplier_company)
            
            existing_suppliers[supplier_name] = supplier_company
            print(f"      ✅ Created new supplier account: {supplier_email}")
        
        supplier_id = supplier_company['id']
        
        # Process products
        products_batch = []
        pricelist_batch = []
        
        for idx, row in df.iterrows():
            product_id = str(uuid4())
            
            # Create product
            product = {
                "id": product_id,
                "name": str(row['Item_Name']).strip(),
                "unit": str(row['Unit']).strip() if row['Unit'] else 'pcs',
                "suppliers": [supplier_id],
                "createdAt": datetime.now(timezone.utc).isoformat()
            }
            products_batch.append(product)
            
            # Create pricelist entry
            try:
                price = float(row['Price_per_Unit']) if row['Price_per_Unit'] else 0.0
                pack_qty = int(float(row['Pack_Quantity'])) if row['Pack_Quantity'] else 1
                min_packs = int(float(row['Minimum_Order_Packs'])) if row['Minimum_Order_Packs'] else 1
            except:
                price = 0.0
                pack_qty = 1
                min_packs = 1
            
            pricelist = {
                "id": str(uuid4()),
                "supplierId": supplier_id,
                "productId": product_id,
                "price": price,
                "packQuantity": pack_qty,
                "minQuantity": min_packs,
                "minOrderAmount": 0.0,
                "supplierItemCode": str(row['Supplier_Item_Code']).strip() if row['Supplier_Item_Code'] else '',
                "createdAt": datetime.now(timezone.utc).isoformat()
            }
            pricelist_batch.append(pricelist)
        
        # Insert in batches
        if products_batch:
            db.products.insert_many(products_batch)
            total_products_added += len(products_batch)
            print(f"      ✅ Added {len(products_batch)} products")
        
        if pricelist_batch:
            db.pricelists.insert_many(pricelist_batch)
            total_pricelist_items_added += len(pricelist_batch)
            print(f"      ✅ Added {len(pricelist_batch)} pricelist items")
            
    except Exception as e:
        print(f"      ❌ Error: {str(e)}")

# Summary
print("\n" + "=" * 80)
print("✅ IMPORT COMPLETE")
print("=" * 80)
print(f"Database: {DB_NAME}")
print(f"Total suppliers: {len(catalogues)}")
print(f"Total products added: {total_products_added}")
print(f"Total pricelist items added: {total_pricelist_items_added}")
print("\n📋 Supplier Summary:")
for supplier_name in catalogues.keys():
    if supplier_name in existing_suppliers:
        supplier_id = existing_suppliers[supplier_name]['id']
        product_count = db.products.count_documents({"suppliers": supplier_id})
        pricelist_count = db.pricelists.count_documents({"supplierId": supplier_id})
        print(f"   • {supplier_name}: {product_count} products, {pricelist_count} prices")
print("=" * 80)
