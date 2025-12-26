#!/usr/bin/env python3
"""Import new supplier catalogs into MongoDB"""
import os
import sys
import pandas as pd
from pymongo import MongoClient
from pathlib import Path
from datetime import datetime, timezone
import uuid

# Load environment
from dotenv import load_dotenv
load_dotenv(Path('/app/backend/.env'))

mongo_url = os.environ['MONGO_URL']
client = MongoClient(mongo_url)
db = client['test_database']

# Map supplier file names to company IDs
SUPPLIER_MAPPING = {
    'Алиди.xlsx': 'Алиди',
    'Айфрут.xlsx': 'Айфрут', 
    'Восток-Запад.xlsx': 'Восток-Запад',
    'Интегрита.xlsx': 'Интегрита',
    'Нордико.xlsx': 'Нордико',
}

def get_supplier_company_id(supplier_name: str):
    """Get company ID for supplier by name"""
    company = db.companies.find_one({'companyName': supplier_name, 'type': 'supplier'})
    if not company:
        company = db.companies.find_one({'name': supplier_name, 'companyType': 'supplier'})
    
    if company:
        return company['id']
    
    print(f"⚠️  Supplier '{supplier_name}' not found in database!")
    return None

def import_catalog(file_path: str, supplier_name: str):
    """Import a single catalog file"""
    print(f"\n{'='*70}")
    print(f"📂 Импорт: {supplier_name}")
    print(f"{'='*70}")
    
    # Get supplier company ID
    supplier_id = get_supplier_company_id(supplier_name)
    if not supplier_id:
        print(f"❌ Пропуск файла {file_path} - поставщик не найден")
        return 0, 0
    
    print(f"✅ Supplier ID: {supplier_id}")
    
    # Read Excel file
    df = pd.read_excel(file_path)
    
    print(f"📊 Найдено строк в файле: {len(df)}")
    print(f"📊 Колонки: {list(df.columns)}")
    
    products_created = 0
    pricelists_created = 0
    skipped = 0
    
    for idx, row in df.iterrows():
        try:
            product_name = str(row['Название']).strip()
            price = float(row['Цена за единицу'])
            unit = str(row['Единица']).strip()
            article = str(row['Код товара поставщика']).strip() if pd.notna(row['Код товара поставщика']) else ''
            
            # Skip category headers (price = 0)
            if price <= 0 or not product_name or product_name == 'nan':
                skipped += 1
                continue
            
            # Get package quantity and min order
            pack_qty = int(row['Количество в упаковки']) if pd.notna(row['Количество в упаковки']) else 1
            min_qty = int(row['Минимальный заказ']) if pd.notna(row['Минимальный заказ']) else 1
            
            # Create or find product in global catalog
            existing_product = db.products.find_one({
                'name': product_name,
                'unit': unit
            })
            
            if existing_product:
                product_id = existing_product['id']
            else:
                # Create new product
                product_id = str(uuid.uuid4())
                product_doc = {
                    'id': product_id,
                    'name': product_name,
                    'unit': unit,
                    'article': article,
                    'createdAt': datetime.now(timezone.utc).isoformat()
                }
                db.products.insert_one(product_doc)
                products_created += 1
            
            # Create pricelist entry
            pricelist_doc = {
                'id': str(uuid.uuid4()),
                'supplierId': supplier_id,
                'productId': product_id,
                'price': price,
                'packQuantity': pack_qty,
                'minQuantity': min_qty,
                'minOrderAmount': 0,
                'supplierItemCode': article,
                'createdAt': datetime.now(timezone.utc).isoformat(),
                'availability': True,
                'active': True
            }
            db.pricelists.insert_one(pricelist_doc)
            pricelists_created += 1
            
        except Exception as e:
            print(f"⚠️  Ошибка в строке {idx}: {e}")
            skipped += 1
            continue
    
    print(f"\n✅ Результат импорта {supplier_name}:")
    print(f"   Продуктов создано: {products_created}")
    print(f"   Прайс-листов создано: {pricelists_created}")
    print(f"   Пропущено строк: {skipped}")
    
    return products_created, pricelists_created

def main():
    """Import all catalogs"""
    print("🚀 Начинаю импорт 5 новых каталогов...")
    
    catalogs_dir = Path('/app/backend/new_catalogs')
    
    total_products = 0
    total_pricelists = 0
    
    for file_name, supplier_name in SUPPLIER_MAPPING.items():
        file_path = catalogs_dir / file_name
        
        if not file_path.exists():
            print(f"⚠️  Файл {file_name} не найден, пропуск...")
            continue
        
        products, pricelists = import_catalog(str(file_path), supplier_name)
        total_products += products
        total_pricelists += pricelists
    
    print(f"\n{'='*70}")
    print(f"📊 ИТОГОВАЯ СТАТИСТИКА ИМПОРТА")
    print(f"{'='*70}")
    print(f"Всего продуктов создано: {total_products}")
    print(f"Всего прайс-листов создано: {total_pricelists}")
    
    # Verify
    products_count = db.products.count_documents({})
    pricelists_count = db.pricelists.count_documents({})
    
    print(f"\n🔍 Проверка базы данных:")
    print(f"   products: {products_count} записей")
    print(f"   pricelists: {pricelists_count} записей")
    
    print(f"\n✅ Импорт завершен!")

if __name__ == '__main__':
    main()
