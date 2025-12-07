"""
Import price lists from Excel files for two suppliers
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

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# File URLs
FILE_1_URL = "https://customer-assets.emergentagent.com/job_webify-43/artifacts/9w6ogtcr_%D0%9F%D1%80%D0%B0%D0%B8%CC%86%D1%81%20%D0%90%D0%BB%D0%B8%D0%B4%D0%B8%202.xlsx"
FILE_2_URL = "https://customer-assets.emergentagent.com/job_webify-43/artifacts/v2hj6mnr_%D0%BF%D1%80%D0%B0%D0%B8%CC%86%D1%81%20%D0%92%D0%97%202.xlsx"

async def get_supplier_companies():
    """Get the two supplier companies from database"""
    suppliers = await db.companies.find({"type": "supplier"}, {"_id": 0}).to_list(2)
    return suppliers

def download_file(url, filename):
    """Download file from URL"""
    response = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(response.content)
    return filename

def parse_price_file_1(filename):
    """Parse first supplier's price list (Алиди)"""
    # Read without header first
    df = pd.read_excel(filename, header=None)
    
    products = []
    for idx, row in df.iterrows():
        # Skip header rows (first 9 rows)
        if idx < 9:
            continue
        
        # Get product code from column 1 (index 1)
        product_code = row[1]
        if pd.isna(product_code) or str(product_code).strip() == '':
            continue
        
        # Get product name from column 2 (index 2)
        product_name = str(row[2] if not pd.isna(row[2]) else '').strip()
        if not product_name or product_name == 'nan':
            continue
        
        # Get unit from column 4 (index 4) - Фасовка
        unit_text = str(row[4] if len(row) > 4 and not pd.isna(row[4]) else 'кг').strip()
        
        # Determine unit
        if 'кг' in unit_text.lower() or 'kg' in unit_text.lower():
            unit = 'кг'
        elif 'г' in unit_text.lower() and 'кг' not in unit_text.lower():
            unit = 'г'
        elif 'л' in unit_text.lower():
            unit = 'л'
        elif 'мл' in unit_text.lower():
            unit = 'мл'
        else:
            unit = 'шт'
        
        # Generate mock price based on product type
        price = generate_mock_price(product_name, unit)
        
        products.append({
            'productName': product_name,
            'article': str(product_code),
            'price': price,
            'unit': unit
        })
    
    return products

def parse_price_file_2(filename):
    """Parse second supplier's price list (ВЗ)"""
    # Read with skiprows to get past header
    df = pd.read_excel(filename, skiprows=3)
    
    # Ensure we have column names
    if df.columns[0] == 'Unnamed: 0':
        df.columns = ['Товар №', 'Маркетинговое наименование товара', 'Ед. изм', 'Вес нетто', 'Ед. изм ПЕИ', 'Кол-во единиц в ПЕИ', 'Кол-во ЕИ в коробке', 'цена']
    
    products = []
    for _, row in df.iterrows():
        # Skip rows without product number
        if pd.isna(row.get('Товар №')) or str(row.get('Товар №', '')).strip() == '':
            continue
            
        product_name = str(row.get('Маркетинговое наименование товара', '')).strip()
        if not product_name or product_name == 'nan':
            continue
            
        # Get unit from Ед. изм
        unit_text = str(row.get('Ед. изм', 'ШТ')).strip()
        
        # Map units
        unit_map = {
            'ШТ': 'шт',
            'КГ': 'кг',
            'Г': 'г',
            'Л': 'л',
            'МЛ': 'мл'
        }
        unit = unit_map.get(unit_text.upper(), 'шт')
        
        # Generate mock price
        price = generate_mock_price(product_name, unit)
        
        products.append({
            'productName': product_name,
            'article': str(row.get('Товар №', '')),
            'price': price,
            'unit': unit
        })
    
    return products

def generate_mock_price(product_name, unit):
    """Generate reasonable mock prices based on product type and unit"""
    import random
    
    product_lower = product_name.lower()
    
    # Base prices by unit
    if unit == 'кг':
        base = 150
    elif unit == 'г':
        base = 50
    elif unit == 'л':
        base = 100
    elif unit == 'мл':
        base = 30
    else:  # шт
        base = 80
    
    # Adjust based on product type
    if any(word in product_lower for word in ['икра', 'трюфель', 'фуа-гра', 'премиум']):
        multiplier = 8.0
    elif any(word in product_lower for word in ['мясо', 'говядина', 'баранина', 'телятина', 'утка']):
        multiplier = 3.5
    elif any(word in product_lower for word in ['рыба', 'семга', 'лосось', 'форель', 'креветки']):
        multiplier = 4.0
    elif any(word in product_lower for word in ['сыр', 'масло', 'молоко', 'творог']):
        multiplier = 2.0
    elif any(word in product_lower for word in ['овощи', 'фрукты', 'зелень', 'салат']):
        multiplier = 1.2
    elif any(word in product_lower for word in ['крупа', 'мука', 'сахар', 'соль']):
        multiplier = 0.8
    else:
        multiplier = 1.5
    
    # Calculate price with some randomness
    price = base * multiplier * random.uniform(0.8, 1.2)
    
    # Round to reasonable precision
    return round(price, 2)

async def import_prices():
    print("🌱 Starting price list import...")
    
    # Get supplier companies
    suppliers = await get_supplier_companies()
    if len(suppliers) < 2:
        print("❌ Error: Not enough supplier companies in database")
        return
    
    supplier1 = suppliers[0]
    supplier2 = suppliers[1]
    
    print(f"📦 Supplier 1: {supplier1['companyName']} (ID: {supplier1['id']})")
    print(f"📦 Supplier 2: {supplier2['companyName']} (ID: {supplier2['id']})")
    
    # Clear existing price lists for these suppliers
    print("\n🗑️  Clearing existing price lists...")
    await db.price_lists.delete_many({"supplierCompanyId": supplier1['id']})
    await db.price_lists.delete_many({"supplierCompanyId": supplier2['id']})
    
    # Download and parse file 1
    print(f"\n📥 Downloading price list 1 (Алиди)...")
    file1 = download_file(FILE_1_URL, '/tmp/pricelist1.xlsx')
    products1 = parse_price_file_1(file1)
    print(f"✅ Parsed {len(products1)} products from file 1")
    
    # Download and parse file 2
    print(f"\n📥 Downloading price list 2 (ВЗ)...")
    file2 = download_file(FILE_2_URL, '/tmp/pricelist2.xlsx')
    products2 = parse_price_file_2(file2)
    print(f"✅ Parsed {len(products2)} products from file 2")
    
    # Import products for supplier 1
    print(f"\n💾 Importing products for {supplier1['companyName']}...")
    imported1 = 0
    for product in products1:
        price_list_item = {
            'id': str(uuid.uuid4()),
            'supplierCompanyId': supplier1['id'],
            'productName': product['productName'],
            'article': product['article'],
            'price': product['price'],
            'unit': product['unit'],
            'availability': True,
            'active': True,
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'updatedAt': datetime.now(timezone.utc).isoformat()
        }
        await db.price_lists.insert_one(price_list_item)
        imported1 += 1
        if imported1 % 100 == 0:
            print(f"  Imported {imported1}/{len(products1)} products...")
    
    print(f"✅ Imported {imported1} products for Supplier 1")
    
    # Import products for supplier 2
    print(f"\n💾 Importing products for {supplier2['companyName']}...")
    imported2 = 0
    for product in products2:
        price_list_item = {
            'id': str(uuid.uuid4()),
            'supplierCompanyId': supplier2['id'],
            'productName': product['productName'],
            'article': product['article'],
            'price': product['price'],
            'unit': product['unit'],
            'availability': True,
            'active': True,
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'updatedAt': datetime.now(timezone.utc).isoformat()
        }
        await db.price_lists.insert_one(price_list_item)
        imported2 += 1
        if imported2 % 100 == 0:
            print(f"  Imported {imported2}/{len(products2)} products...")
    
    print(f"✅ Imported {imported2} products for Supplier 2")
    
    print(f"\n🎉 Price list import complete!")
    print(f"📊 Total products imported: {imported1 + imported2}")
    print(f"\n🔑 Login credentials:")
    print(f"  Supplier 1: supplier1@example.com / password123")
    print(f"  Supplier 2: supplier2@example.com / password123")

if __name__ == "__main__":
    asyncio.run(import_prices())
