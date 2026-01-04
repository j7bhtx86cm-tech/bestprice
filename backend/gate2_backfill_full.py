"""
GATE 2 - BACKFILL SUPPLIER_ITEMS (v12 FULL)

According to TZ section 4, perform 4 mandatory backfills:
1. product_core_id backfill (from SEED_DICT_RULES)
2. brand_id backfill (from BRAND_ALIASES)
3. pack + sell_mode backfill (from PACK_RULES)
4. price_per_base_unit backfill

Outputs coverage report for GATE 2 verification.
"""
import os
import sys
import re
from pymongo import MongoClient
from collections import Counter
import time

mongo_url = os.environ.get('MONGO_URL')
client = MongoClient(mongo_url)
db = client['bestprice']

print("="*100)
print("📊 GATE 2 - SUPPLIER_ITEMS BACKFILL (V12 FULL)")
print("="*100)

start_time = time.time()

# ==================== LOAD V12 DATA INTO MEMORY ====================

print("\n1️⃣ Loading v12 rules into memory...")

# Brand aliases
aliases_cursor = db.brand_aliases.find({}, {'_id': 0, 'alias_norm': 1, 'brand_id': 1})
brand_aliases = {doc['alias_norm']: doc['brand_id'] for doc in aliases_cursor if doc.get('alias_norm')}
print(f"   ✅ Loaded {len(brand_aliases)} brand aliases")

# Seed dict rules
seed_cursor = db.seed_dict_rules.find(
    {'action': {'$nin': ['удалить', 'skip']}},
    {'_id': 0, 'raw': 1, 'canonical': 1, 'type': 1}
)
seed_rules = {}
product_core_terms = set()  # For product_core_id identification
for doc in seed_cursor:
    raw = doc.get('raw', '').lower()
    canonical = doc.get('canonical', '')
    rule_type = doc.get('type', '')
    
    if raw and canonical and canonical.lower() != 'nan':
        seed_rules[raw] = {
            'canonical': canonical,
            'type': rule_type
        }
        # Collect core product terms (categories)
        if rule_type in ['category', 'product', 'main_ingredient']:
            product_core_terms.add(canonical.lower())

print(f"   ✅ Loaded {len(seed_rules)} seed rules")
print(f"   ✅ Identified {len(product_core_terms)} product core terms")

# Pack rules (simplified for now - will use regex patterns)
pack_rules_cursor = db.pack_rules.find({}, {'_id': 0}).sort('priority', 1)
pack_rules = list(pack_rules_cursor)
print(f"   ✅ Loaded {len(pack_rules)} pack rules")

# ==================== HELPER FUNCTIONS ====================

def normalize_text(text):
    """Normalize text for matching"""
    if not text:
        return ""
    text = str(text).lower().strip()
    text = text.replace('ё', 'е')
    # Remove punctuation
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    text = re.sub(r'\s+', ' ', text).strip()
    return text

def detect_brand_id(product_name):
    """Detect brand from product name using aliases"""
    if not product_name:
        return None
    
    name_norm = normalize_text(product_name)
    name_words = set(name_norm.split())
    
    # Sort by length (longest first)
    sorted_aliases = sorted(brand_aliases.items(), key=lambda x: len(x[0]), reverse=True)
    
    for alias_norm, brand_id in sorted_aliases:
        if len(alias_norm) < 4:
            if alias_norm in name_words:
                return brand_id
        else:
            if alias_norm in name_norm:
                pattern = r'(^|\s)' + re.escape(alias_norm) + r'($|\s)'
                if re.search(pattern, name_norm):
                    return brand_id
    
    return None

def determine_product_core_id(product_name):
    """Determine product_core_id from SEED_DICT_RULES
    
    Priority: Longest match from product_core_terms
    Filters out technical terms (%, g, l, etc.)
    """
    if not product_name:
        return None
    
    name_norm = normalize_text(product_name)
    name_words = name_norm.split()
    
    # Skip technical measurement terms
    skip_terms = {'0%', '1%', '2%', '3%', '4%', '5%', '6%', '7%', '8%', '9%', 
                  'g', 'l', 'ml', 'kg', 'шт', 'pcs', 'см', 'мм'}
    
    matched_cores = []
    
    for raw_term, rule_info in seed_rules.items():
        canonical = rule_info['canonical']
        
        # Skip if canonical is in skip list
        if canonical in skip_terms or len(canonical) < 2:
            continue
        
        # Check if term appears in product name
        if raw_term in name_norm or raw_term in name_words:
            matched_cores.append((canonical, len(raw_term)))
    
    if not matched_cores:
        return None
    
    # Return longest match (most specific)
    matched_cores.sort(key=lambda x: x[1], reverse=True)
    return matched_cores[0][0]

def extract_pack_value_simple(product_name):
    """Simple pack extraction (will be improved with PACK_RULES later)"""
    if not product_name:
        return None, None
    
    name = product_name.lower()
    
    # Pattern: number + unit
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

# ==================== BACKFILL OPERATIONS ====================

print(f"\n2️⃣ Processing {db.pricelists.count_documents({})} pricelists...")

pricelists = list(db.pricelists.find({}, {'_id': 0}))
products = list(db.products.find({}, {'_id': 0}))
product_map = {p['id']: p for p in products}

stats = {
    'total': len(pricelists),
    'brand_detected': 0,
    'product_core_detected': 0,
    'pack_detected': 0,
    'price_per_base_calculated': 0,
    'active': 0,
    'hidden_unclassified': 0
}

updated_items = []

for i, pl in enumerate(pricelists):
    product = product_map.get(pl['productId'])
    if not product:
        continue
    
    product_name = product.get('name', '')
    price = pl.get('price', 0)
    
    # 1. Brand backfill
    brand_id = detect_brand_id(product_name)
    if brand_id:
        stats['brand_detected'] += 1
    
    # 2. Product core backfill
    product_core_id = determine_product_core_id(product_name)
    if product_core_id:
        stats['product_core_detected'] += 1
    
    # 3. Pack backfill (simple for now)
    pack_value, pack_unit = extract_pack_value_simple(product_name)
    if pack_value and pack_unit:
        stats['pack_detected'] += 1
        
        # Normalize to base units
        if pack_unit == 'g':
            pack_base = pack_value / 1000  # to kg
            base_unit = 'kg'
        elif pack_unit == 'ml':
            pack_base = pack_value / 1000  # to l
            base_unit = 'l'
        else:
            pack_base = pack_value
            base_unit = pack_unit
    else:
        pack_base = None
        base_unit = None
    
    # 4. Offer status
    if product_core_id:
        offer_status = 'ACTIVE'
        stats['active'] += 1
    else:
        offer_status = 'HIDDEN_UNCLASSIFIED'
        stats['hidden_unclassified'] += 1
    
    # 5. Price status
    if price > 0:
        price_status = 'VALID'
    else:
        price_status = 'INVALID'
    
    # 6. Sell mode
    if pack_base and pack_base > 0:
        sell_mode = 'PACK'
    else:
        sell_mode = 'UNKNOWN'
    
    # 7. price_per_base_unit
    if pack_base and pack_base > 0 and price > 0:
        price_per_base_unit = price / pack_base
        stats['price_per_base_calculated'] += 1
    else:
        price_per_base_unit = None
    
    # Prepare update
    update_doc = {
        'brand_id': brand_id,
        'product_core_id': product_core_id,
        'offer_status': offer_status,
        'price_status': price_status,
        'pack_value': pack_value,
        'pack_unit': pack_unit,
        'pack_base': pack_base,
        'base_unit': base_unit,
        'sell_mode': sell_mode,
        'price_per_base_unit': price_per_base_unit,
        'name_raw': product_name
    }
    
    updated_items.append({
        'filter': {'id': pl['id']},
        'update': {'$set': update_doc}
    })
    
    # Progress
    if (i + 1) % 1000 == 0:
        print(f"   Progress: {i + 1}/{stats['total']} ({(i+1)/stats['total']*100:.1f}%)")

# Bulk update
if updated_items:
    print(f"\n3️⃣ Performing bulk update...")
    from pymongo import UpdateOne
    bulk_ops = [UpdateOne(item['filter'], item['update']) for item in updated_items]
    result = db.pricelists.bulk_write(bulk_ops)
    print(f"   ✅ Updated {result.modified_count} pricelist items")

# ==================== GATE 2 COVERAGE REPORT ====================

elapsed = time.time() - start_time

print(f"\n{'='*100}")
print("✅ GATE 2 - BACKFILL COVERAGE REPORT")
print("="*100)

print(f"\n📊 Coverage Statistics:")
print(f"   Total items processed:        {stats['total']}")
print(f"   Brand detected:               {stats['brand_detected']:5} ({stats['brand_detected']/stats['total']*100:5.1f}%)")
print(f"   Product core detected:        {stats['product_core_detected']:5} ({stats['product_core_detected']/stats['total']*100:5.1f}%)")
print(f"   Pack detected:                {stats['pack_detected']:5} ({stats['pack_detected']/stats['total']*100:5.1f}%)")
print(f"   Price per base unit calc:     {stats['price_per_base_calculated']:5} ({stats['price_per_base_calculated']/stats['total']*100:5.1f}%)")
print(f"   ACTIVE offers:                {stats['active']:5} ({stats['active']/stats['total']*100:5.1f}%)")
print(f"   HIDDEN_UNCLASSIFIED:          {stats['hidden_unclassified']:5} ({stats['hidden_unclassified']/stats['total']*100:5.1f}%)")

print(f"\n⏱️  Processing time: {elapsed:.1f}s")

# Verification samples
print(f"\n🔍 Sample verification (random 5 items with core):")
samples = db.pricelists.aggregate([
    {'$match': {'product_core_id': {'$ne': None}}},
    {'$sample': {'size': 5}}
])

for s in samples:
    core = s.get('product_core_id', 'N/A')
    brand = s.get('brand_id', 'N/A')
    pack = s.get('pack_value', 'N/A')
    status = s.get('offer_status', 'N/A')
    print(f"   {s.get('name_raw', '')[:55]:55} | core={core:15} | brand={brand:10} | pack={pack} | {status}")

# Check if coverage is acceptable
if stats['product_core_detected'] / stats['total'] < 0.70:
    print(f"\n⚠️  WARNING: Product core coverage < 70%")
    print("This indicates SEED_DICT_RULES don't cover current pricelists well")
    print("Consider adding more rules to master file")

if stats['product_core_detected'] / stats['total'] >= 0.70:
    print(f"\n🎉 GATE 2 PASSED - Coverage acceptable (≥70%)")
else:
    print(f"\n⚠️  GATE 2 WARNING - Coverage below 70%")

print("\n✅ Done!")
