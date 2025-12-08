"""
Import price lists from 5 new suppliers - all prices in rubles
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

# File URLs and supplier names
SUPPLIERS = [
    {
        'name': 'Алиди',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/sr01y2nb_%D0%90%D0%BB%D0%B8%D0%B4%D0%B8.xlsx',
        'email': 'alidi@example.com'
    },
    {
        'name': 'ВЗ',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/4wmwfkrq_%D0%92%D0%97%20.xlsx',
        'email': 'vz@example.com'
    },
    {
        'name': 'Мореодор',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/x2ycd95g_%D0%9C%D0%BE%D1%80%D0%B5%D0%BE%D0%B4%D0%BE%D1%80%20.xlsx',
        'email': 'moreodor@example.com'
    },
    {
        'name': 'РомановАНИП',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/mbva3mr2_%D0%A0%D0%BE%D0%BC%D0%B0%D0%BD%D0%BE%D0%B2%D0%90%D0%9D%D0%98%D0%9F.xlsx',
        'email': 'romanov@example.com'
    },
    {
        'name': 'NORDICO',
        'url': 'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/fxirzkqr_NORDICO.xlsx',
        'email': 'nordico@example.com'
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
    """Smart parser for Excel files - finds headers automatically"""
    print(f"📊 Parsing {filename}...")
    
    try:
        df = pd.read_excel(filename, header=None)
        
        products = []
        header_row = -1
        name_col = None
        price_col = None
        unit_col = None
        article_col = None
        
        # Find header row
        for idx, row in df.iterrows():
            if idx > 20:  # Don't search beyond row 20
                break
            
            row_str = ' '.join([str(x).lower() for x in row if pd.notna(x)])
            
            # Look for common header patterns
            if any(keyword in row_str for keyword in ['наименование', 'название', 'товар', 'продукт', 'name', 'product']):
                header_row = idx
                
                for col_idx, cell in enumerate(row):
                    if pd.isna(cell):
                        continue
                    cell_str = str(cell).lower()
                    
                    if ('наименование' in cell_str or 'название' in cell_str or 
                        'товар' in cell_str or 'продукт' in cell_str or 'name' in cell_str):
                        name_col = col_idx
                    elif 'цена' in cell_str or 'price' in cell_str or 'стоимость' in cell_str:
                        price_col = col_idx
                    elif ('ед.' in cell_str or 'unit' in cell_str or 'единица' in cell_str or 
                          'фасовка' in cell_str or 'упаковка' in cell_str):
                        unit_col = col_idx
                    elif 'артикул' in cell_str or 'код' in cell_str or 'article' in cell_str or 'арт.' in cell_str:
                        article_col = col_idx
                
                if name_col is not None and price_col is not None:
                    print(f"✅ Found header at row {idx}")
                    print(f"   Columns - Name: {name_col}, Price: {price_col}, Unit: {unit_col}, Article: {article_col}")
                    break
        
        # If no header found, use first 4 columns as name, article, unit, price
        if header_row == -1:
            print("⚠️  No header found, using default column mapping")
            header_row = 0
            name_col = 0
            article_col = 1
            unit_col = 2
            price_col = 3
        
        # Parse data rows
        for idx, row in df.iterrows():
            if idx <= header_row:
                continue
            
            # Get product name
            product_name = row[name_col] if name_col is not None and name_col < len(row) else None
            if pd.isna(product_name) or str(product_name).strip() == '':
                continue
            
            # Get price
            price_value = row[price_col] if price_col is not None and price_col < len(row) else None
            if pd.isna(price_value):
                continue
            
            try:
                price = float(price_value)
                if price <= 0:
                    continue
            except:
                continue
            
            # Get unit
            unit = 'шт'
            if unit_col is not None and unit_col < len(row):
                unit_value = row[unit_col]
                if not pd.isna(unit_value):
                    unit = str(unit_value).strip()
            
            # Get article
            article = str(idx)
            if article_col is not None and article_col < len(row):
                article_value = row[article_col]
                if not pd.isna(article_value):
                    article = str(article_value).strip()
            
            products.append({
                'productName': str(product_name).strip(),
                'price': price,
                'unit': unit,
                'article': article
            })
        
        print(f"✅ Parsed {len(products)} products from {supplier_name}")
        return products
        
    except Exception as e:
        print(f"❌ Error parsing {filename}: {str(e)}")
        import traceback
        traceback.print_exc()
        return []

async def create_or_get_supplier(supplier_info):
    """Create supplier company and user if they don't exist"""
    # Check if user exists
    user = await db.users.find_one({"email": supplier_info['email']}, {"_id": 0})
    
    if not user:
        # Create user
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
        print(f"  ✅ Created user for {supplier_info['name']}")
    else:
        user_id = user['id']
        print(f"  ℹ️  User already exists for {supplier_info['name']}")
    
    # Check if company exists
    company = await db.companies.find_one({"userId": user_id}, {"_id": 0})
    
    if not company:
        # Create company
        company_id = str(uuid.uuid4())
        company_doc = {
            'id': company_id,
            'type': 'supplier',
            'userId': user_id,
            'inn': f"{7700000000 + hash(supplier_info['name']) % 1000000}",
            'ogrn': f"{1027700000000 + hash(supplier_info['name']) % 1000000}",
            'companyName': supplier_info['name'],
            'legalAddress': f"г. Москва, ул. {supplier_info['name']}, д. 1",
            'actualAddress': f"г. Москва, ул. {supplier_info['name']}, д. 1",
            'phone': '+7 (999) 123-45-67',
            'email': supplier_info['email'],
            'contactPersonName': 'Иван Иванов',
            'contactPersonPosition': 'Менеджер',
            'contactPersonPhone': '+7 (999) 123-45-67',
            'deliveryAddresses': [],
            'contractAccepted': True,
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'updatedAt': datetime.now(timezone.utc).isoformat()
        }
        await db.companies.insert_one(company_doc)
        print(f"  ✅ Created company: {supplier_info['name']}")
        return company_id
    else:
        print(f"  ℹ️  Company already exists: {supplier_info['name']}")
        return company['id']

async def import_all_suppliers():
    """Import price lists for all 5 suppliers"""
    print("🌱 Starting import of all supplier price lists...")
    print(f"📦 Total suppliers to import: {len(SUPPLIERS)}\n")
    
    # Clear existing price lists
    print("🗑️  Clearing existing price lists...")
    await db.price_lists.delete_many({})
    
    total_products = 0
    
    for supplier_info in SUPPLIERS:
        print(f"\n{'='*60}")
        print(f"📦 Processing: {supplier_info['name']}")
        print(f"{'='*60}")
        
        # Create or get supplier company
        company_id = await create_or_get_supplier(supplier_info)
        
        # Download and parse file
        filename = f"/tmp/{supplier_info['name']}.xlsx"
        download_file(supplier_info['url'], filename)
        
        products = parse_excel_smart(filename, supplier_info['name'])
        
        if not products:
            print(f"⚠️  No products found for {supplier_info['name']}, skipping...")
            continue
        
        # Import products
        print(f"💾 Importing {len(products)} products for {supplier_info['name']}...")
        
        for i, product in enumerate(products):
            price_list = {
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
            }
            await db.price_lists.insert_one(price_list)
            
            if (i + 1) % 100 == 0:
                print(f"  Imported {i + 1}/{len(products)} products...")
        
        print(f"✅ Imported {len(products)} products for {supplier_info['name']}")
        total_products += len(products)
    
    print(f"\n{'='*60}")
    print(f"🎉 Import complete!")
    print(f"📊 Total products imported: {total_products}")
    print(f"📦 Total suppliers: {len(SUPPLIERS)}")
    print(f"{'='*60}")
    
    # Show supplier list
    suppliers = await db.companies.find({"type": "supplier"}, {"_id": 0, "companyName": 1, "email": 1}).to_list(10)
    print(f"\n📋 Suppliers in database:")
    for s in suppliers:
        count = await db.price_lists.count_documents({"supplierCompanyId": s.get('id', '')})
        print(f"  - {s['companyName']}: {count} products (login: {s['email']} / password123)")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(import_all_suppliers())
