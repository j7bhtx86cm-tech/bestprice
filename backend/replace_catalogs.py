"""
Import NEW catalogs - Replace all existing suppliers
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

# NEW Supplier list
SUPPLIERS = [
    {
        'name': 'Алиди',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/m287cc6h_%D0%90%D0%BB%D0%B8%D0%B4%D0%B8%20%281%29.xlsx',
        'email': 'alidi@bestprice.ru'
    },
    {
        'name': 'ВЗ',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/49b50io7_%D0%92%D0%97.xlsx',
        'email': 'vz@bestprice.ru'
    },
    {
        'name': 'ПраймФудс',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/0v37whfj_%D0%9F%D1%80%D0%B0%D0%B8%CC%86%D0%BC%D0%A4%D1%83%D0%B4%D1%81.xlsx',
        'email': 'primefoods@bestprice.ru'
    },
    {
        'name': 'Ромакс',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/dg7tz9ss_%D0%A0%D0%BE%D0%BC%D0%B0%D0%BA%D1%81%20%281%29.xlsx',
        'email': 'romax@bestprice.ru'
    },
    {
        'name': 'VICI',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/fsmj7tfk_VICI%20.xlsx',
        'email': 'vici@bestprice.ru'
    }
]

def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

def download_file(url, filename):
    """Download file from URL"""
    print(f"📥 Downloading {filename}...")
    response = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(response.content)
    return filename

def parse_excel_smart(filename, supplier_name):
    """Smart parser for Excel files"""
    print(f"📊 Parsing {supplier_name}...")
    
    try:
        # Try reading all sheets
        xl_file = pd.ExcelFile(filename)
        all_products = []
        
        for sheet_name in xl_file.sheet_names:
            df = pd.read_excel(filename, sheet_name=sheet_name, header=None)
            
            # Find header row
            header_row = -1
            name_col = None
            price_col = None
            unit_col = None
            article_col = None
            
            for idx, row in df.iterrows():
                if idx > 20:
                    break
                
                row_str = ' '.join([str(x).lower() for x in row if pd.notna(x)])
                
                if any(keyword in row_str for keyword in ['наименование', 'название', 'товар', 'name']):
                    header_row = idx
                    
                    for col_idx, cell in enumerate(row):
                        if pd.isna(cell):
                            continue
                        cell_str = str(cell).lower()
                        
                        if 'наименование' in cell_str or 'название' in cell_str or 'name' in cell_str:
                            name_col = col_idx
                        elif 'цена' in cell_str or 'price' in cell_str:
                            price_col = col_idx
                        elif 'ед.' in cell_str or 'unit' in cell_str or 'единица' in cell_str:
                            unit_col = col_idx
                        elif 'артикул' in cell_str or 'код' in cell_str or 'article' in cell_str:
                            article_col = col_idx
                    
                    if name_col is not None and price_col is not None:
                        break
            
            # If no header, try to parse as raw data (article, name, price pattern)
            if header_row == -1:
                for idx, row in df.iterrows():
                    non_empty = [cell for cell in row if pd.notna(cell) and str(cell).strip() != '']
                    
                    if len(non_empty) >= 2:
                        try:
                            # Try to find price (last numeric value)
                            price = None
                            name = None
                            article = str(idx)
                            
                            for i in range(len(non_empty) - 1, -1, -1):
                                try:
                                    price_val = float(non_empty[i])
                                    if 0 < price_val < 100000:
                                        price = price_val
                                        name = ' '.join([str(x) for x in non_empty[:i]])
                                        if non_empty[0] and str(non_empty[0]).isdigit():
                                            article = str(non_empty[0])
                                        break
                                except:
                                    continue
                            
                            if price and name and name.strip():
                                all_products.append({
                                    'productName': name.strip()[:200],
                                    'price': price,
                                    'article': article,
                                    'unit': 'шт'
                                })
                        except:
                            continue
            else:
                # Parse with header
                for idx, row in df.iterrows():
                    if idx <= header_row:
                        continue
                    
                    product_name = row[name_col] if name_col < len(row) else None
                    if pd.isna(product_name) or str(product_name).strip() == '':
                        continue
                    
                    price_value = row[price_col] if price_col < len(row) else None
                    if pd.isna(price_value):
                        continue
                    
                    try:
                        price = float(price_value)
                        if price <= 0:
                            continue
                    except:
                        continue
                    
                    unit = 'шт'
                    if unit_col is not None and unit_col < len(row):
                        unit_value = row[unit_col]
                        if not pd.isna(unit_value):
                            unit = str(unit_value).strip()
                    
                    article = str(idx)
                    if article_col is not None and article_col < len(row):
                        article_value = row[article_col]
                        if not pd.isna(article_value):
                            article = str(article_value).strip()
                    
                    all_products.append({
                        'productName': str(product_name).strip()[:200],
                        'price': price,
                        'unit': unit,
                        'article': article
                    })
        
        print(f"✅ Parsed {len(all_products)} products from {supplier_name}")
        return all_products
        
    except Exception as e:
        print(f"❌ Error parsing {supplier_name}: {str(e)}")
        return []

async def create_or_update_supplier(supplier_info):
    """Create or update supplier company"""
    # Check if company exists by name
    company = await db.companies.find_one({"companyName": supplier_info['name']}, {"_id": 0})
    
    if company:
        print(f"  ✅ Supplier exists: {supplier_info['name']}")
        return company['id']
    
    # Check if user exists
    user = await db.users.find_one({"email": supplier_info['email']}, {"_id": 0})
    
    if not user:
        user_id = str(uuid.uuid4())
        user_doc = {
            'id': user_id,
            'email': supplier_info['email'],
            'passwordHash': hash_password('password123'),
            'role': 'supplier',
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'updatedAt': datetime.now(timezone.utc).isoformat()
        }
        await db.users.insert_one(user_doc)
    else:
        user_id = user['id']
    
    # Create company
    company_id = str(uuid.uuid4())
    company_doc = {
        'id': company_id,
        'type': 'supplier',
        'userId': user_id,
        'inn': f"{7700000000 + abs(hash(supplier_info['name'])) % 1000000}",
        'ogrn': f"{1027700000000 + abs(hash(supplier_info['name'])) % 1000000}",
        'companyName': supplier_info['name'],
        'legalAddress': f"г. Москва, ул. {supplier_info['name']}, д. 1",
        'actualAddress': f"г. Москва, ул. {supplier_info['name']}, д. 1",
        'phone': '+7 (495) 000-00-00',
        'email': supplier_info['email'],
        'contactPersonName': 'Менеджер',
        'contactPersonPosition': 'Менеджер',
        'contactPersonPhone': '+7 (495) 000-00-00',
        'deliveryAddresses': [],
        'contractAccepted': True,
        'createdAt': datetime.now(timezone.utc).isoformat(),
        'updatedAt': datetime.now(timezone.utc).isoformat()
    }
    await db.companies.insert_one(company_doc)
    print(f"  ✅ Created supplier: {supplier_info['name']}")
    return company_id

async def replace_catalogs():
    """Replace all catalogs with new ones"""
    print("🔄 REPLACING ALL CATALOGS")
    print("=" * 60)
    
    # 1. Clear ALL existing price lists
    print("\n🗑️  Clearing all existing price lists...")
    result = await db.price_lists.delete_many({})
    print(f"   Deleted {result.deleted_count} products")
    
    # 2. Remove old suppliers (keep only customers)
    print("\n🗑️  Removing old suppliers...")
    old_suppliers = await db.companies.find({"type": "supplier"}, {"_id": 0}).to_list(100)
    for supplier in old_suppliers:
        # Delete supplier user
        await db.users.delete_many({"id": supplier['userId']})
        # Delete supplier company
        await db.companies.delete_one({"id": supplier['id']})
        print(f"   Removed: {supplier['companyName']}")
    
    # 3. Import new suppliers
    print("\n" + "=" * 60)
    print("📦 IMPORTING NEW SUPPLIERS")
    print("=" * 60)
    
    total_products = 0
    
    for supplier_info in SUPPLIERS:
        print(f"\n{'='*60}")
        print(f"📦 {supplier_info['name']}")
        print(f"{'='*60}")
        
        # Create supplier
        company_id = await create_or_update_supplier(supplier_info)
        
        # Download and parse
        filename = f"/tmp/{supplier_info['name']}.xlsx"
        download_file(supplier_info['url'], filename)
        products = parse_excel_smart(filename, supplier_info['name'])
        
        if not products:
            print(f"⚠️  No products found, skipping...")
            continue
        
        # Import products
        print(f"💾 Importing {len(products)} products...")
        for i, product in enumerate(products):
            await db.price_lists.insert_one({
                'id': str(uuid.uuid4()),
                'supplierCompanyId': company_id,
                'productName': product['productName'],
                'article': product['article'],
                'price': product['price'],
                'unit': product['unit'],
                'availability': True,
                'active': True,
                'createdAt': datetime.now(timezone.utc).isoformat(),
                'updatedAt': datetime.now(timezone.utc).isoformat()
            })
            
            if (i + 1) % 200 == 0:
                print(f"  Imported {i + 1}/{len(products)}...")
        
        print(f"✅ Imported {len(products)} products")
        total_products += len(products)
    
    print("\n" + "=" * 60)
    print(f"🎉 IMPORT COMPLETE!")
    print(f"📊 Total: {total_products} products")
    print("=" * 60)
    
    # Verify
    print("\n📋 Final supplier list:")
    suppliers = await db.companies.find({"type": "supplier"}, {"_id": 0, "companyName": 1}).to_list(20)
    for s in suppliers:
        count = await db.price_lists.count_documents({"supplierCompanyId": s.get('id', '')})
        print(f"  ✅ {s['companyName']}: {count} products")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(replace_catalogs())
