"""
ПОЛНОЕ ИСПРАВЛЕНИЕ: Favorites → Add to Cart

Проблема: no_candidates_after_product_guard
Причина: Mismatch между product_core_id в favorites и supplier_items

Решение:
1. Полная переустановка master v12 (v2)
2. Улучшенный backfill с ПРИОРИТЕТНОЙ логикой product_core_id
3. Детальное логирование на каждом этапе
"""
import os
import sys
import re
import pandas as pd
from pymongo import MongoClient, UpdateOne
from collections import Counter
import time

mongo_url = os.environ.get('MONGO_URL')
client = MongoClient(mongo_url)
db = client['bestprice']

v12_file = '/app/backend/BESTPRICE_MASTER_v12_FULL_v2.xlsx'

print("="*100)
print("🔧 ПОЛНОЕ ИСПРАВЛЕНИЕ: Favorites → Add to Cart")
print("="*100)

# ==================== STEP 1: DELETE OLD COLLECTIONS ====================
print("\n1️⃣ Удаление старых коллекций...")

old_collections = ['brands', 'brand_aliases', 'seed_dict_rules', 'pack_rules', 
                   'bestprice_spec', 'favorites_schema_v12']

for col in old_collections:
    if col in db.list_collection_names():
        count = db[col].count_documents({})
        db[col].drop()
        print(f"   ✅ Удалено '{col}' ({count} документов)")

print(f"\n   Прайсы: {db.pricelists.count_documents({})} (сохранены)")

# ==================== STEP 2: IMPORT NEW V12 ====================
print("\n2️⃣ Импорт нового master v12...")

# BRANDS_MASTER
df_brands = pd.read_excel(v12_file, sheet_name='BRANDS_MASTER')
brands_docs = []
for _, row in df_brands.iterrows():
    brand_id = str(row.get('brand_id', '')).strip().lower()
    if brand_id and brand_id != 'nan':
        brands_docs.append({
            'brand_id': brand_id,
            'brand_ru': str(row['brand_ru']) if pd.notna(row.get('brand_ru')) else None,
            'brand_en': str(row['brand_en']) if pd.notna(row.get('brand_en')) else None,
            'category': str(row.get('category', '')) if pd.notna(row.get('category')) else '',
            'default_strict': bool(row.get('default_strict', 0)) if pd.notna(row.get('default_strict')) else False
        })

if brands_docs:
    db.brands.insert_many(brands_docs)
    db.brands.create_index('brand_id', unique=True)
    print(f"   ✅ BRANDS: {len(brands_docs)}")

# BRAND_ALIASES
df_aliases = pd.read_excel(v12_file, sheet_name='BRAND_ALIASES')
alias_docs = []
for _, row in df_aliases.iterrows():
    alias_norm = str(row.get('alias_norm', '')).strip().lower() if pd.notna(row.get('alias_norm')) else ''
    brand_id = str(row.get('brand_id', '')).strip().lower() if pd.notna(row.get('brand_id')) else ''
    if alias_norm and brand_id:
        alias_docs.append({
            'alias_norm': alias_norm,
            'brand_id': brand_id,
            'source': str(row.get('source', '')) if pd.notna(row.get('source')) else ''
        })

if alias_docs:
    db.brand_aliases.insert_many(alias_docs)
    db.brand_aliases.create_index('alias_norm')
    print(f"   ✅ ALIASES: {len(alias_docs)}")

# SEED_DICT_RULES
df_seed = pd.read_excel(v12_file, sheet_name='SEED_DICT_RULES')
seed_docs = []
for _, row in df_seed.iterrows():
    raw = str(row.get('RAW', '')) if pd.notna(row.get('RAW')) else ''
    canonical = str(row.get('CANONICAL', '')) if pd.notna(row.get('CANONICAL')) else ''
    if raw and canonical and canonical.lower() != 'nan':
        seed_docs.append({
            'raw': raw,
            'canonical': canonical,
            'type': str(row.get('ТИП', '')) if pd.notna(row.get('ТИП')) else '',
            'action': str(row.get('ДЕЙСТВИЕ', '')) if pd.notna(row.get('ДЕЙСТВИЕ')) else '',
            'priority': 100  # Default
        })

if seed_docs:
    db.seed_dict_rules.insert_many(seed_docs)
    db.seed_dict_rules.create_index('raw')
    db.seed_dict_rules.create_index('canonical')
    print(f"   ✅ SEED RULES: {len(seed_docs)}")

print("\n✅ Импорт завершён")

# ==================== STEP 3: IMPROVED BACKFILL ====================
print("\n3️⃣ УЛУЧШЕННЫЙ BACKFILL с приоритетной логикой...")

# Load into memory
aliases = {doc['alias_norm']: doc['brand_id'] for doc in db.brand_aliases.find({}, {'_id': 0})}
seed_rules = list(db.seed_dict_rules.find({'action': {'$nin': ['удалить', 'skip']}}, {'_id': 0}))

print(f"   Загружено: {len(aliases)} aliases, {len(seed_rules)} rules")

# Build priority-based seed lookup
seed_by_priority = {}
for rule in seed_rules:
    raw = rule.get('raw', '').lower()
    canonical = rule.get('canonical', '')
    rule_type = rule.get('type', '')
    
    # PRIORITY: category > product > main_ingredient > ingredient > attribute
    if rule_type == 'category':
        priority = 1
    elif rule_type == 'product':
        priority = 2
    elif rule_type == 'main_ingredient':
        priority = 3
    elif rule_type == 'ingredient':
        priority = 4
    else:
        priority = 5
    
    if raw and canonical and len(canonical) >= 3:
        seed_by_priority[raw] = {'canonical': canonical, 'priority': priority, 'length': len(raw)}

print(f"   Создан priority index: {len(seed_by_priority)} terms")

def normalize(text):
    if not text:
        return ""
    text = str(text).lower().strip().replace('ё', 'е')
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()

def detect_brand(name):
    if not name:
        return None
    name_norm = normalize(name)
    name_words = set(name_norm.split())
    sorted_aliases = sorted(aliases.items(), key=lambda x: len(x[0]), reverse=True)
    for alias_norm, brand_id in sorted_aliases:
        if len(alias_norm) < 4:
            if alias_norm in name_words:
                return brand_id
        else:
            if alias_norm in name_norm:
                return brand_id
    return None

def determine_product_core(name):
    """УЛУЧШЕННАЯ логика с приоритетами"""
    if not name:
        return None
    
    name_norm = normalize(name)
    name_words = name_norm.split()
    
    # Skip technical terms
    skip = {'0%', '1%', '2%', '3%', '4%', '5%', 'g', 'kg', 'l', 'ml', 'шт', 'pcs'}
    
    matches = []
    
    for raw, info in seed_by_priority.items():
        canonical = info['canonical']
        
        # Skip if in skip list
        if canonical in skip:
            continue
        
        # Check if term appears
        if raw in name_norm or raw in name_words:
            matches.append({
                'canonical': canonical,
                'priority': info['priority'],
                'length': info['length']
            })
    
    if not matches:
        return None
    
    # Sort by: priority ASC (lower=better), then length DESC (longer=better)
    matches.sort(key=lambda x: (x['priority'], -x['length']))
    
    return matches[0]['canonical']

def extract_pack(name):
    if not name:
        return None, None
    name = name.lower()
    patterns = [
        (r'(\d+[\.,]?\d*)\s*кг', 'kg'),
        (r'(\d+[\.,]?\d*)\s*г', 'g'),
        (r'(\d+[\.,]?\d*)\s*л', 'l'),
        (r'(\d+[\.,]?\d*)\s*мл', 'ml'),
        (r'(\d+[\.,]?\d*)\s*шт', 'pcs'),
    ]
    for pattern, unit in patterns:
        match = re.search(pattern, name)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                return value, unit
            except:
                continue
    return None, None

# Process all pricelists
pricelists = list(db.pricelists.find({}, {'_id': 0}))
products = {p['id']: p for p in db.products.find({}, {'_id': 0})}

print(f"\n   Обработка {len(pricelists)} товаров...")

stats = {'total': len(pricelists), 'brand': 0, 'core': 0, 'pack': 0, 'active': 0}
updates = []

for i, pl in enumerate(pricelists):
    product = products.get(pl['productId'])
    if not product:
        continue
    
    name = product.get('name', '')
    price = pl.get('price', 0)
    
    # Backfill
    brand_id = detect_brand(name)
    product_core_id = determine_product_core(name)
    pack_value, pack_unit = extract_pack(name)
    
    if brand_id:
        stats['brand'] += 1
    if product_core_id:
        stats['core'] += 1
    if pack_value:
        stats['pack'] += 1
    
    # Calculate pack_base
    if pack_value and pack_unit:
        if pack_unit == 'g':
            pack_base = pack_value / 1000
            base_unit = 'kg'
        elif pack_unit == 'ml':
            pack_base = pack_value / 1000
            base_unit = 'l'
        else:
            pack_base = pack_value
            base_unit = pack_unit
    else:
        pack_base = None
        base_unit = None
    
    # Offer status
    if product_core_id:
        offer_status = 'ACTIVE'
        stats['active'] += 1
    else:
        offer_status = 'HIDDEN_UNCLASSIFIED'
    
    # Price per base unit
    if pack_base and pack_base > 0 and price > 0:
        price_per_base_unit = price / pack_base
    else:
        price_per_base_unit = None
    
    updates.append(UpdateOne(
        {'id': pl['id']},
        {'$set': {
            'brand_id': brand_id,
            'product_core_id': product_core_id,
            'offer_status': offer_status,
            'price_status': 'VALID' if price > 0 else 'INVALID',
            'pack_value': pack_value,
            'pack_unit': pack_unit,
            'pack_base': pack_base,
            'base_unit': base_unit,
            'price_per_base_unit': price_per_base_unit,
            'name_raw': name
        }}
    ))
    
    if (i + 1) % 1000 == 0:
        print(f"   Progress: {i + 1}/{len(pricelists)}")

if updates:
    result = db.pricelists.bulk_write(updates)
    print(f"\n   ✅ Обновлено: {result.modified_count}")

print(f"\n📊 Coverage:")
print(f"   Brand:        {stats['brand']:4} ({stats['brand']/stats['total']*100:5.1f}%)")
print(f"   Core:         {stats['core']:4} ({stats['core']/stats['total']*100:5.1f}%)")
print(f"   Pack:         {stats['pack']:4} ({stats['pack']/stats['total']*100:5.1f}%)")
print(f"   ACTIVE:       {stats['active']:4} ({stats['active']/stats['total']*100:5.1f}%)")

# ==================== VERIFICATION ====================
print("\n4️⃣ Проверка: поиск 'кетчуп'...")

ketchup_items = list(db.pricelists.find(
    {'name_raw': {'$regex': 'кетчуп', '$options': 'i'}},
    {'_id': 0, 'name_raw': 1, 'product_core_id': 1, 'brand_id': 1, 'price': 1}
).limit(5))

for item in ketchup_items:
    name = item.get('name_raw', '')[:50]
    core = item.get('product_core_id', 'NONE')
    brand = item.get('brand_id', 'NONE')
    price = item.get('price', 0)
    print(f"   {name:50} | core={core:15} | brand={brand:10} | {price}₽")

print("\n✅ ГОТОВО! Теперь тестируем search engine...")
