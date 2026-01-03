"""
Load BESTPRICE_IDEAL_MASTER_PATCH_v12.xlsx into MongoDB

This script loads the v12 master file into MongoDB collections:
- brands (from BRANDS_MASTER sheet)
- brand_aliases (from BRAND_ALIASES sheet)
- seed_dict_rules (from SEED_DICT_RULES sheet)

This is the single source of truth for all brand, alias, and product classification logic.
"""
import pandas as pd
from pymongo import MongoClient
import os
from pathlib import Path
import sys

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL')
if not mongo_url:
    print("❌ MONGO_URL not found in environment")
    sys.exit(1)

client = MongoClient(mongo_url)
db = client['bestprice']

# File path
v12_file = Path(__file__).parent / 'BESTPRICE_IDEAL_MASTER_PATCH_v12.xlsx'

if not v12_file.exists():
    print(f"❌ File not found: {v12_file}")
    sys.exit(1)

print(f"📋 Loading v12 master file: {v12_file}")
print(f"=" * 80)

# ==================== LOAD BRANDS_MASTER ====================
print("\n1️⃣ Loading BRANDS_MASTER...")
df_brands = pd.read_excel(v12_file, sheet_name='BRANDS_MASTER')
print(f"   Found {len(df_brands)} brands")

# Drop existing collection
db.brands.drop()
print("   Dropped existing 'brands' collection")

# Insert brands
brands_docs = []
for _, row in df_brands.iterrows():
    brand_id = str(row.get('brand_id', '')).strip().lower()
    if not brand_id or brand_id == 'nan':
        continue
    
    brand_ru = str(row['brand_ru']) if pd.notna(row.get('brand_ru')) else None
    brand_en = str(row['brand_en']) if pd.notna(row.get('brand_en')) else None
    
    # Parse default_strict
    default_strict_raw = row.get('default_strict', 0)
    default_strict = bool(default_strict_raw) if pd.notna(default_strict_raw) else False
    
    brands_docs.append({
        'brand_id': brand_id,
        'brand_ru': brand_ru,
        'brand_en': brand_en,
        'category': str(row.get('category', 'unknown')) if pd.notna(row.get('category')) else 'unknown',
        'default_strict': default_strict,
        'notes': str(row.get('notes', '')) if pd.notna(row.get('notes')) else ''
    })

if brands_docs:
    db.brands.insert_many(brands_docs)
    print(f"   ✅ Inserted {len(brands_docs)} brands into 'brands' collection")

    # Create index
    db.brands.create_index('brand_id', unique=True)
    print("   ✅ Created index on brand_id")
else:
    print("   ⚠️ No brands to insert")

# ==================== LOAD BRAND_ALIASES ====================
print("\n2️⃣ Loading BRAND_ALIASES...")
df_aliases = pd.read_excel(v12_file, sheet_name='BRAND_ALIASES')
print(f"   Found {len(df_aliases)} aliases")

# Drop existing collection
db.brand_aliases.drop()
print("   Dropped existing 'brand_aliases' collection")

# Insert aliases
alias_docs = []
for _, row in df_aliases.iterrows():
    alias = str(row.get('alias', '')) if pd.notna(row.get('alias')) else ''
    alias_norm = str(row.get('alias_norm', '')) if pd.notna(row.get('alias_norm')) else ''
    target_brand_id = str(row.get('brand_id', '')).strip().lower() if pd.notna(row.get('brand_id')) else ''
    
    if not alias and not alias_norm:
        continue
    if not target_brand_id:
        continue
    
    alias_docs.append({
        'alias': alias,
        'alias_norm': alias_norm.strip().lower() if alias_norm else '',
        'brand_id': target_brand_id,
        'source': str(row.get('source', '')) if pd.notna(row.get('source')) else '',
        'comment': str(row.get('comment', '')) if pd.notna(row.get('comment')) else ''
    })

if alias_docs:
    db.brand_aliases.insert_many(alias_docs)
    print(f"   ✅ Inserted {len(alias_docs)} aliases into 'brand_aliases' collection")
    
    # Create indexes
    db.brand_aliases.create_index('alias_norm')
    db.brand_aliases.create_index('brand_id')
    print("   ✅ Created indexes on alias_norm and brand_id")
else:
    print("   ⚠️ No aliases to insert")

# ==================== LOAD SEED_DICT_RULES ====================
print("\n3️⃣ Loading SEED_DICT_RULES...")
df_seed = pd.read_excel(v12_file, sheet_name='SEED_DICT_RULES')
print(f"   Found {len(df_seed)} rules")

# Drop existing collection
db.seed_dict_rules.drop()
print("   Dropped existing 'seed_dict_rules' collection")

# Insert rules
seed_docs = []
for _, row in df_seed.iterrows():
    dict_id = int(row['DICT_ID']) if pd.notna(row.get('DICT_ID')) else None
    raw = str(row.get('RAW', '')) if pd.notna(row.get('RAW')) else ''
    
    if not raw or not dict_id:
        continue
    
    seed_docs.append({
        'dict_id': dict_id,
        'raw': raw,
        'description': str(row.get('РАСШИФРОВКА', '')) if pd.notna(row.get('РАСШИФРОВКА')) else '',
        'canonical': str(row.get('CANONICAL', '')) if pd.notna(row.get('CANONICAL')) else '',
        'type': str(row.get('ТИП', '')) if pd.notna(row.get('ТИП')) else '',
        'action': str(row.get('ДЕЙСТВИЕ', '')) if pd.notna(row.get('ДЕЙСТВИЕ')) else '',
        'example': str(row.get('ПРИМЕР', '')) if pd.notna(row.get('ПРИМЕР')) else '',
        'comment': str(row.get('КОММЕНТАРИЙ', '')) if pd.notna(row.get('КОММЕНТАРИЙ')) else '',
        'section': str(row.get('РАЗДЕЛ', '')) if pd.notna(row.get('РАЗДЕЛ')) else ''
    })

if seed_docs:
    db.seed_dict_rules.insert_many(seed_docs)
    print(f"   ✅ Inserted {len(seed_docs)} rules into 'seed_dict_rules' collection")
    
    # Create index
    db.seed_dict_rules.create_index('dict_id')
    db.seed_dict_rules.create_index('raw')
    print("   ✅ Created indexes on dict_id and raw")
else:
    print("   ⚠️ No rules to insert")

# ==================== SUMMARY ====================
print("\n" + "=" * 80)
print("✅ V12 MASTER FILE LOADED SUCCESSFULLY")
print(f"   Brands: {len(brands_docs)}")
print(f"   Aliases: {len(alias_docs)}")
print(f"   Seed Rules: {len(seed_docs)}")
print("=" * 80)

# Verify collections
print("\n📊 Verification:")
print(f"   db.brands count: {db.brands.count_documents({})}")
print(f"   db.brand_aliases count: {db.brand_aliases.count_documents({})}")
print(f"   db.seed_dict_rules count: {db.seed_dict_rules.count_documents({})}")

print("\n🎉 Done!")
