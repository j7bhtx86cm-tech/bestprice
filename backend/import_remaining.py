"""
Import РомановАНИП and NORDICO files with custom parsing
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

def download_file(url, filename):
    """Download file from URL"""
    print(f"📥 Downloading {filename}...")
    response = requests.get(url)
    with open(filename, 'wb') as f:
        f.write(response.content)
    return filename

def parse_romanov_file(filename):
    """Parse РомановАНИП file - custom format"""
    print(f"📊 Parsing РомановАНИП...")
    
    try:
        # Read all sheets
        xl_file = pd.ExcelFile(filename)
        print(f"  Found {len(xl_file.sheet_names)} sheets: {xl_file.sheet_names}")
        
        all_products = []
        
        for sheet_name in xl_file.sheet_names:
            df = pd.read_excel(filename, sheet_name=sheet_name, header=None)
            print(f"\n  Processing sheet: {sheet_name} ({len(df)} rows)")
            
            # Try to find data pattern: article, name, price
            for idx, row in df.iterrows():
                # Look for rows with at least 3 non-empty cells
                non_empty = [cell for cell in row if pd.notna(cell) and str(cell).strip() != '']
                
                if len(non_empty) >= 3:
                    # Try to identify: first number = article, last number = price, middle = name
                    try:
                        article = str(non_empty[0]).strip()
                        price = None
                        name = None
                        
                        # Look for price (last numeric value)
                        for i in range(len(non_empty) - 1, -1, -1):
                            try:
                                price_val = float(non_empty[i])
                                if price_val > 0 and price_val < 100000:
                                    price = price_val
                                    # Everything between article and price is the name
                                    name = ' '.join([str(x) for x in non_empty[1:i]])
                                    break
                            except:
                                continue
                        
                        if price and name and name.strip():
                            all_products.append({
                                'productName': name.strip(),
                                'price': price,
                                'article': article,
                                'unit': 'шт'
                            })
                    except:
                        continue
        
        print(f"✅ Parsed {len(all_products)} products from РомановАНИП")
        return all_products
        
    except Exception as e:
        print(f"❌ Error parsing РомановАНИП: {str(e)}")
        return []

def parse_nordico_file(filename):
    """Parse NORDICO file - custom format"""
    print(f"📊 Parsing NORDICO...")
    
    try:
        xl_file = pd.ExcelFile(filename)
        print(f"  Found {len(xl_file.sheet_names)} sheets: {xl_file.sheet_names}")
        
        all_products = []
        
        for sheet_name in xl_file.sheet_names:
            df = pd.read_excel(filename, sheet_name=sheet_name, header=None)
            print(f"\n  Processing sheet: {sheet_name} ({len(df)} rows)")
            
            # Similar parsing logic
            for idx, row in df.iterrows():
                non_empty = [cell for cell in row if pd.notna(cell) and str(cell).strip() != '']
                
                if len(non_empty) >= 3:
                    try:
                        article = str(non_empty[0]).strip()
                        price = None
                        name = None
                        
                        for i in range(len(non_empty) - 1, -1, -1):
                            try:
                                price_val = float(non_empty[i])
                                if price_val > 0 and price_val < 100000:
                                    price = price_val
                                    name = ' '.join([str(x) for x in non_empty[1:i]])
                                    break
                            except:
                                continue
                        
                        if price and name and name.strip():
                            all_products.append({
                                'productName': name.strip(),
                                'price': price,
                                'article': article,
                                'unit': 'шт'
                            })
                    except:
                        continue
        
        print(f"✅ Parsed {len(all_products)} products from NORDICO")
        return all_products
        
    except Exception as e:
        print(f"❌ Error parsing NORDICO: {str(e)}")
        return []

async def import_remaining_suppliers():
    """Import the remaining 2 suppliers"""
    print("🌱 Importing remaining suppliers: РомановАНИП and NORDICO\n")
    
    # Get supplier companies
    romanov = await db.companies.find_one({"companyName": "РомановАНИП"}, {"_id": 0})
    nordico = await db.companies.find_one({"companyName": "NORDICO"}, {"_id": 0})
    
    if not romanov or not nordico:
        print("❌ Supplier companies not found. Run import_new_catalogs.py first.")
        return
    
    total_imported = 0
    
    # Import РомановАНИП
    print("=" * 60)
    print("📦 Importing РомановАНИП")
    print("=" * 60)
    
    file1 = download_file(
        'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/mbva3mr2_%D0%A0%D0%BE%D0%BC%D0%B0%D0%BD%D0%BE%D0%B2%D0%90%D0%9D%D0%98%D0%9F.xlsx',
        '/tmp/romanov.xlsx'
    )
    products1 = parse_romanov_file(file1)
    
    if products1:
        print(f"💾 Importing {len(products1)} products...")
        for i, product in enumerate(products1):
            await db.price_lists.insert_one({
                'id': str(uuid.uuid4()),
                'supplierCompanyId': romanov['id'],
                'productName': product['productName'],
                'article': product['article'],
                'price': product['price'],
                'unit': product['unit'],
                'availability': True,
                'active': True,
                'createdAt': datetime.now(timezone.utc).isoformat(),
                'updatedAt': datetime.now(timezone.utc).isoformat()
            })
            
            if (i + 1) % 100 == 0:
                print(f"  Imported {i + 1}/{len(products1)} products...")
        
        print(f"✅ Imported {len(products1)} products for РомановАНИП")
        total_imported += len(products1)
    
    # Import NORDICO
    print("\n" + "=" * 60)
    print("📦 Importing NORDICO")
    print("=" * 60)
    
    file2 = download_file(
        'https://customer-assets.emergentagent.com/job_resto-supplier/artifacts/fxirzkqr_NORDICO.xlsx',
        '/tmp/nordico.xlsx'
    )
    products2 = parse_nordico_file(file2)
    
    if products2:
        print(f"💾 Importing {len(products2)} products...")
        for i, product in enumerate(products2):
            await db.price_lists.insert_one({
                'id': str(uuid.uuid4()),
                'supplierCompanyId': nordico['id'],
                'productName': product['productName'],
                'article': product['article'],
                'price': product['price'],
                'unit': product['unit'],
                'availability': True,
                'active': True,
                'createdAt': datetime.now(timezone.utc).isoformat(),
                'updatedAt': datetime.now(timezone.utc).isoformat()
            })
            
            if (i + 1) % 100 == 0:
                print(f"  Imported {i + 1}/{len(products2)} products...")
        
        print(f"✅ Imported {len(products2)} products for NORDICO")
        total_imported += len(products2)
    
    print("\n" + "=" * 60)
    print(f"🎉 Import complete! Total new products: {total_imported}")
    print("=" * 60)
    
    # Show final counts
    all_suppliers = await db.companies.find({"type": "supplier"}, {"_id": 0, "companyName": 1}).to_list(10)
    print(f"\n📋 All Suppliers:")
    grand_total = 0
    for s in all_suppliers:
        count = await db.price_lists.count_documents({"supplierCompanyId": s.get('id', '')})
        print(f"  - {s['companyName']}: {count} products")
        grand_total += count
    
    print(f"\n📊 Grand Total: {grand_total} products across {len(all_suppliers)} suppliers")
    
    client.close()

if __name__ == "__main__":
    asyncio.run(import_remaining_suppliers())
