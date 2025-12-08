"""
Import price lists from user-provided Excel files
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
FILE_ALIDI_URL = "https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/fuv4jnci_alidi%20price%20.xlsx"
FILE_B3_URL = "https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/umjdg255_b3%20price%20.xlsx"

async def get_supplier_companies():
    """Get the two supplier companies from database"""
    suppliers = await db.companies.find({"type": "supplier"}, {"_id": 0}).to_list(2)
    return suppliers

def download_file(url, filename):
    """Download file from URL"""
    print(f"📥 Downloading {filename}...")
    response = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(response.content)
    return filename

def parse_excel_file(filename):
    """Parse Excel file and extract products"""
    print(f"📊 Parsing {filename}...")
    
    try:
        # Try to read the Excel file
        df = pd.read_excel(filename, header=None)
        
        products = []
        header_found = False
        name_col = None
        price_col = None
        unit_col = None
        article_col = None
        
        # Find header row by looking for common column names
        for idx, row in df.iterrows():
            row_str = ' '.join([str(x).lower() for x in row if pd.notna(x)])
            if any(keyword in row_str for keyword in ['наименование', 'название', 'товар', 'продукт', 'name']):
                # Found potential header row
                for col_idx, cell in enumerate(row):
                    cell_str = str(cell).lower()
                    if 'наименование' in cell_str or 'название' in cell_str or 'name' in cell_str:
                        name_col = col_idx
                    elif 'цена' in cell_str or 'price' in cell_str or 'стоимость' in cell_str:
                        price_col = col_idx
                    elif 'ед.' in cell_str or 'unit' in cell_str or 'единица' in cell_str:
                        unit_col = col_idx
                    elif 'артикул' in cell_str or 'код' in cell_str or 'article' in cell_str:
                        article_col = col_idx
                
                if name_col is not None and price_col is not None:
                    header_found = True
                    print(f"✅ Found header at row {idx}")
                    print(f"   Name column: {name_col}, Price column: {price_col}, Unit column: {unit_col}, Article column: {article_col}")
                    break
        
        if not header_found:
            print("⚠️  No clear header found, using first row as data")
            name_col = 0
            price_col = 1
            article_col = 2
            unit_col = 3
        
        # Parse data rows
        start_row = (idx + 1) if header_found else 0
        
        for idx, row in df.iterrows():
            if idx < start_row:
                continue
            
            # Get product name
            product_name = row[name_col] if name_col is not None else row[0]
            if pd.isna(product_name) or str(product_name).strip() == '':
                continue
            
            # Get price
            price = row[price_col] if price_col is not None else row[1]
            if pd.isna(price):
                continue
            
            try:
                price = float(price)
            except:
                continue
            
            # Get unit
            unit = row[unit_col] if unit_col is not None and unit_col < len(row) else 'шт'
            if pd.isna(unit):
                unit = 'шт'
            unit = str(unit).strip()
            
            # Get article
            article = row[article_col] if article_col is not None and article_col < len(row) else str(idx)
            if pd.isna(article):
                article = str(idx)
            article = str(article).strip()
            
            products.append({
                'productName': str(product_name).strip(),
                'price': price,
                'unit': unit,
                'article': article
            })
        
        print(f"✅ Parsed {len(products)} products from {filename}")
        return products
        
    except Exception as e:
        print(f"❌ Error parsing {filename}: {str(e)}")
        return []

async def import_products():
    """Main import function"""
    print("🌱 Starting price list import from user files...")
    
    # Get suppliers
    suppliers = await get_supplier_companies()
    if len(suppliers) < 2:
        print("❌ Not enough suppliers in database")
        return
    
    print(f"📦 Supplier 1: {suppliers[0]['companyName']} (ID: {suppliers[0]['id']})")
    print(f"📦 Supplier 2: {suppliers[1]['companyName']} (ID: {suppliers[1]['id']})")
    
    # Clear existing price lists
    print("\n🗑️  Clearing existing price lists...")
    await db.price_lists.delete_many({})
    
    # Download and parse files
    file1 = download_file(FILE_ALIDI_URL, '/tmp/alidi_price.xlsx')
    products1 = parse_excel_file(file1)
    
    file2 = download_file(FILE_B3_URL, '/tmp/b3_price.xlsx')
    products2 = parse_excel_file(file2)
    
    # Import products for Supplier 1 (Alidi)
    print(f"\n💾 Importing {len(products1)} products for {suppliers[0]['companyName']}...")
    for i, product in enumerate(products1):
        price_list = {
            'id': str(uuid.uuid4()),
            'supplierCompanyId': suppliers[0]['id'],
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
            print(f"  Imported {i + 1}/{len(products1)} products...")
    
    print(f"✅ Imported {len(products1)} products for Supplier 1")
    
    # Import products for Supplier 2 (B3)
    print(f"\n💾 Importing {len(products2)} products for {suppliers[1]['companyName']}...")
    for i, product in enumerate(products2):
        price_list = {
            'id': str(uuid.uuid4()),
            'supplierCompanyId': suppliers[1]['id'],
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
            print(f"  Imported {i + 1}/{len(products2)} products...")
    
    print(f"✅ Imported {len(products2)} products for Supplier 2")
    
    print(f"\n🎉 Price list import complete!")
    print(f"📊 Total products imported: {len(products1) + len(products2)}")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(import_products())
