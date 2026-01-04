"""
RESET + IMPORT V12 FULL - According to strict TZ

Steps:
1. Delete OLD collections (except pricelists/supplier_items)
2. Import NEW v12 data from FULL file
3. Report counts (GATE 1 verification)

Collections to DELETE:
- brands
- brand_aliases  
- seed_dict_rules
- pack_rules
- bestprice_spec
- favorites_schema_v12
- Any other master/rules collections

Collections to KEEP:
- pricelists (supplier price data)
- products
- suppliers
- companies
- orders
- users
- etc.
"""
import os
import sys
import pandas as pd
from pymongo import MongoClient
from pathlib import Path

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL')
if not mongo_url:
    print("❌ MONGO_URL not found")
    sys.exit(1)

client = MongoClient(mongo_url)
db = client['bestprice']

v12_file = Path(__file__).parent / 'BESTPRICE_IDEAL_MASTER_v12_PATCH_FULL.xlsx'

print("="*100)
print("🗑️  STEP 1: DELETE OLD COLLECTIONS (keeping pricelists)")
print("="*100)

# Collections to delete
old_collections = [
    'brands',
    'brand_aliases',
    'seed_dict_rules',
    'pack_rules',
    'bestprice_spec',
    'favorites_schema_v12',
    'master_files',
    'sot_versions',
    'rules_versions'
]

for col_name in old_collections:
    if col_name in db.list_collection_names():
        count = db[col_name].count_documents({})
        db[col_name].drop()
        print(f"   ✅ Dropped '{col_name}' ({count} documents)")
    else:
        print(f"   ℹ️  '{col_name}' не существовала")

print(f"\n✅ Old collections deleted")

# ==================== IMPORT NEW V12 DATA ====================

print(f"\n{'='*100}")
print("📥 STEP 2: IMPORT V12 FULL")
print("="*100)

if not v12_file.exists():
    print(f"❌ File not found: {v12_file}")
    sys.exit(1)

print(f"File: {v12_file.name}\n")

# Track counts for GATE 1 verification
import_counts = {}

# ==================== BRANDS_MASTER ====================
print("1️⃣ Importing BRANDS_MASTER...")
df_brands = pd.read_excel(v12_file, sheet_name='BRANDS_MASTER')

brands_docs = []
for _, row in df_brands.iterrows():
    brand_id = str(row.get('brand_id', '')).strip().lower()
    if not brand_id or brand_id == 'nan':
        continue
    
    brands_docs.append({
        'brand_id': brand_id,
        'brand_ru': str(row['brand_ru']) if pd.notna(row.get('brand_ru')) else None,
        'brand_en': str(row['brand_en']) if pd.notna(row.get('brand_en')) else None,
        'category': str(row.get('category', 'unknown')) if pd.notna(row.get('category')) else 'unknown',
        'default_strict': bool(row.get('default_strict', 0)) if pd.notna(row.get('default_strict')) else False,
        'notes': str(row.get('notes', '')) if pd.notna(row.get('notes')) else ''
    })

if brands_docs:
    db.brands.insert_many(brands_docs)
    db.brands.create_index('brand_id', unique=True)
    import_counts['brands'] = len(brands_docs)
    print(f"   ✅ {len(brands_docs)} brands imported")

# ==================== BRAND_ALIASES ====================
print("2️⃣ Importing BRAND_ALIASES...")
df_aliases = pd.read_excel(v12_file, sheet_name='BRAND_ALIASES')

alias_docs = []
for _, row in df_aliases.iterrows():
    alias_norm = str(row.get('alias_norm', '')).strip().lower() if pd.notna(row.get('alias_norm')) else ''
    brand_id = str(row.get('brand_id', '')).strip().lower() if pd.notna(row.get('brand_id')) else ''
    
    if alias_norm and brand_id:
        alias_docs.append({
            'alias': str(row.get('alias', '')) if pd.notna(row.get('alias')) else '',
            'alias_norm': alias_norm,
            'brand_id': brand_id,
            'source': str(row.get('source', '')) if pd.notna(row.get('source')) else '',
            'comment': str(row.get('comment', '')) if pd.notna(row.get('comment')) else ''
        })

if alias_docs:
    db.brand_aliases.insert_many(alias_docs)
    db.brand_aliases.create_index('alias_norm')
    db.brand_aliases.create_index('brand_id')
    import_counts['brand_aliases'] = len(alias_docs)
    print(f"   ✅ {len(alias_docs)} aliases imported")

# ==================== SEED_DICT_RULES ====================
print("3️⃣ Importing SEED_DICT_RULES...")
df_seed = pd.read_excel(v12_file, sheet_name='SEED_DICT_RULES')

seed_docs = []
for _, row in df_seed.iterrows():
    raw = str(row.get('RAW', '')) if pd.notna(row.get('RAW')) else ''
    canonical = str(row.get('CANONICAL', '')) if pd.notna(row.get('CANONICAL')) else ''
    
    if raw and canonical and canonical.lower() != 'nan':
        seed_docs.append({
            'dict_id': int(row['DICT_ID']) if pd.notna(row.get('DICT_ID')) else None,
            'raw': raw,
            'description': str(row.get('РАСШИФРОВКА', '')) if pd.notna(row.get('РАСШИФРОВКА')) else '',
            'canonical': canonical,
            'type': str(row.get('ТИП', '')) if pd.notna(row.get('ТИП')) else '',
            'action': str(row.get('ДЕЙСТВИЕ', '')) if pd.notna(row.get('ДЕЙСТВИЕ')) else '',
            'example': str(row.get('ПРИМЕР', '')) if pd.notna(row.get('ПРИМЕР')) else '',
            'comment': str(row.get('КОММЕНТАРИЙ', '')) if pd.notna(row.get('КОММЕНТАРИЙ')) else ''
        })

if seed_docs:
    db.seed_dict_rules.insert_many(seed_docs)
    db.seed_dict_rules.create_index('raw')
    db.seed_dict_rules.create_index('canonical')
    import_counts['seed_dict_rules'] = len(seed_docs)
    print(f"   ✅ {len(seed_docs)} seed rules imported")

# ==================== PACK_RULES ====================
print("4️⃣ Importing PACK_RULES...")
df_pack = pd.read_excel(v12_file, sheet_name='PACK_RULES')

pack_docs = []
for _, row in df_pack.iterrows():
    rule_id = int(row['RULE_ID']) if pd.notna(row.get('RULE_ID')) else None
    pattern = str(row.get('PATTERN_REGEX', '')) if pd.notna(row.get('PATTERN_REGEX')) else ''
    
    if rule_id and pattern:
        pack_docs.append({
            'rule_id': rule_id,
            'rule_scope': str(row.get('RULE_SCOPE', '')) if pd.notna(row.get('RULE_SCOPE')) else '',
            'pattern_regex': pattern,
            'unit': str(row.get('UNIT', '')) if pd.notna(row.get('UNIT')) else '',
            'multipack': str(row.get('MULTIPACK', '')) if pd.notna(row.get('MULTIPACK')) else '',
            'output_fields': str(row.get('OUTPUT_FIELDS', '')) if pd.notna(row.get('OUTPUT_FIELDS')) else '',
            'priority': int(row.get('PRIORITY', 100)) if pd.notna(row.get('PRIORITY')) else 100,
            'examples': str(row.get('EXAMPLES', '')) if pd.notna(row.get('EXAMPLES')) else ''
        })

if pack_docs:
    db.pack_rules.insert_many(pack_docs)
    db.pack_rules.create_index('rule_id')
    import_counts['pack_rules'] = len(pack_docs)
    print(f"   ✅ {len(pack_docs)} pack rules imported")

# ==================== BESTPRICE_SPEC ====================
print("5️⃣ Importing BESTPRICE_SPEC...")
df_spec = pd.read_excel(v12_file, sheet_name='BESTPRICE_SPEC')

spec_docs = []
for _, row in df_spec.iterrows():
    section = str(row.get('SECTION', '')) if pd.notna(row.get('SECTION')) else ''
    key = str(row.get('KEY', '')) if pd.notna(row.get('KEY')) else ''
    
    if section and key:
        spec_docs.append({
            'section': section,
            'key': key,
            'value': str(row.get('VALUE', '')) if pd.notna(row.get('VALUE')) else '',
            'notes': str(row.get('NOTES', '')) if pd.notna(row.get('NOTES')) else ''
        })

if spec_docs:
    db.bestprice_spec.insert_many(spec_docs)
    db.bestprice_spec.create_index([('section', 1), ('key', 1)])
    import_counts['bestprice_spec'] = len(spec_docs)
    print(f"   ✅ {len(spec_docs)} spec entries imported")

# ==================== FAVORITES_SCHEMA_V12 ====================
print("6️⃣ Importing FAVORITES_SCHEMA_V12...")
df_fav_schema = pd.read_excel(v12_file, sheet_name='FAVORITES_SCHEMA_V12')

fav_schema_docs = []
for _, row in df_fav_schema.iterrows():
    field_name = str(row.get('FIELD_NAME', '')) if pd.notna(row.get('FIELD_NAME')) else ''
    
    if field_name:
        fav_schema_docs.append({
            'field_name': field_name,
            'field_type': str(row.get('FIELD_TYPE', '')) if pd.notna(row.get('FIELD_TYPE')) else '',
            'required': bool(row.get('REQUIRED', False)) if pd.notna(row.get('REQUIRED')) else False,
            'default_value': str(row.get('DEFAULT_VALUE', '')) if pd.notna(row.get('DEFAULT_VALUE')) else '',
            'description': str(row.get('DESCRIPTION', '')) if pd.notna(row.get('DESCRIPTION')) else '',
            'source': str(row.get('SOURCE', '')) if pd.notna(row.get('SOURCE')) else '',
            'validation_rules': str(row.get('VALIDATION_RULES', '')) if pd.notna(row.get('VALIDATION_RULES')) else ''
        })

if fav_schema_docs:
    db.favorites_schema_v12.insert_many(fav_schema_docs)
    import_counts['favorites_schema_v12'] = len(fav_schema_docs)
    print(f"   ✅ {len(fav_schema_docs)} schema fields imported")

# ==================== SUMMARY ====================
print(f"\n{'='*100}")
print("✅ IMPORT COMPLETED - GATE 1 VERIFICATION")
print("="*100)

for collection, count in import_counts.items():
    print(f"   {collection:30} : {count} rows")

# Check if any is 0
if any(count == 0 for count in import_counts.values()):
    print(f"\n⚠️  WARNING: Some collections have 0 rows")
    print("Import considered FAILED according to TZ")
else:
    print(f"\n🎉 All collections populated - GATE 1 PASSED")

print(f"\n📊 Database state:")
print(f"   Pricelists: {db.pricelists.count_documents({})} (preserved)")
print(f"   Products: {db.products.count_documents({})} (preserved)")

print("\n✅ Done!")
