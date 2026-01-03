"""
Backfill script to enrich existing pricelists/products with v12 data

This script:
1. Detects brand_id using brand_aliases from v12
2. Determines product_core_id using seed_dict_rules from v12  
3. Adds offer_status (ACTIVE / HIDDEN_UNCLASSIFIED)
4. Adds price_status (VALID / SUSPECT / INVALID)
5. Updates pricelists collection without reloading price data

IMPORTANT: This does NOT reload pricelists - only enriches existing data.
"""
import os
import re
import sys
from pymongo import MongoClient
from pathlib import Path

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL')
if not mongo_url:
    print("❌ MONGO_URL not found in environment")
    sys.exit(1)

client = MongoClient(mongo_url)
db = client['bestprice']

print("=" * 80)
print("🔄 BACKFILL V12 ENRICHMENT")
print("=" * 80)

# ==================== HELPER FUNCTIONS ====================

def normalize_text(text):
    """Normalize text for matching (lowercase, ё->е, remove special chars)"""
    if not text:
        return ""
    
    text = str(text).lower().strip()
    text = text.replace('ё', 'е')
    
    # Replace punctuation with spaces
    text = text.replace('"', ' ').replace("'", ' ').replace('«', ' ').replace('»', ' ')
    text = text.replace('.', ' ').replace(',', ' ').replace(';', ' ').replace(':', ' ')
    text = text.replace('/', ' ').replace('\\', ' ').replace('-', ' ').replace('_', ' ')
    
    # Remove other special chars
    text = re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)
    
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def detect_brand_id(product_name, aliases_cache):
    """Detect brand_id from product name using brand_aliases"""
    if not product_name:
        return None
    
    name_norm = normalize_text(product_name)
    name_words = set(name_norm.split())
    
    # Sort aliases by length (longest first) for better matching
    sorted_aliases = sorted(aliases_cache.items(), key=lambda x: len(x[0]), reverse=True)
    
    for alias_norm, brand_id in sorted_aliases:
        # For short aliases (< 4 chars), require exact word match
        if len(alias_norm) < 4:
            if alias_norm in name_words:
                return brand_id
        else:
            # For longer aliases, check substring match at word boundary
            if alias_norm in name_norm:
                # Check it's not part of another word
                pattern = r'(^|\s)' + re.escape(alias_norm) + r'($|\s)'
                if re.search(pattern, name_norm) or alias_norm in name_words:
                    return brand_id
    
    return None


def extract_product_core_tokens(product_name, seed_rules_cache):
    """Extract product core tokens from product name using seed_dict_rules
    
    Returns: list of canonical tokens that identify the product category
    """
    if not product_name:
        return []
    
    name_norm = normalize_text(product_name)
    name_words = name_norm.split()
    
    core_tokens = []
    
    # Match seed rules (raw -> canonical)
    for raw_term, canonical in seed_rules_cache.items():
        raw_norm = normalize_text(raw_term)
        
        # Check if raw term appears in product name
        if raw_norm in name_norm or raw_norm in name_words:
            if canonical and canonical not in core_tokens:
                core_tokens.append(canonical)
    
    return core_tokens


def determine_product_core_id(product_name, seed_rules_cache):
    """Determine product_core_id from product name
    
    Uses seed_dict_rules to identify the product category.
    Returns a normalized identifier like 'кетчуп', 'лосось', 'креветки', etc.
    """
    core_tokens = extract_product_core_tokens(product_name, seed_rules_cache)
    
    if not core_tokens:
        return None
    
    # Use the first (most important) token as product_core_id
    # In a more sophisticated system, this could be a combination
    return core_tokens[0]


# ==================== LOAD CACHES FROM V12 ====================

print("\n📚 Loading v12 data into memory...")

# Load brand aliases into cache
print("   Loading brand_aliases...")
aliases_cursor = db.brand_aliases.find({}, {'_id': 0, 'alias_norm': 1, 'brand_id': 1})
aliases_cache = {doc['alias_norm']: doc['brand_id'] for doc in aliases_cursor if doc.get('alias_norm')}
print(f"   ✅ Loaded {len(aliases_cache)} aliases")

# Load seed_dict_rules into cache (raw -> canonical mapping)
print("   Loading seed_dict_rules...")
seed_cursor = db.seed_dict_rules.find(
    {'action': {'$nin': ['удалить', 'skip']}},  # Only keep useful rules
    {'_id': 0, 'raw': 1, 'canonical': 1}
)
seed_rules_cache = {}
for doc in seed_cursor:
    raw = doc.get('raw', '')
    canonical = doc.get('canonical', '')
    if raw and canonical and canonical.lower() != 'nan':
        seed_rules_cache[raw] = canonical
print(f"   ✅ Loaded {len(seed_rules_cache)} seed rules")

# ==================== BACKFILL PRICELISTS ====================

print("\n🔧 Enriching pricelists...")

# Get all pricelists
pricelists = list(db.pricelists.find({}, {'_id': 0}))
total_count = len(pricelists)
print(f"   Found {total_count} pricelist items to process")

# Statistics
stats = {
    'total': total_count,
    'brand_detected': 0,
    'product_core_detected': 0,
    'active': 0,
    'hidden_unclassified': 0
}

updated_items = []

for i, pl in enumerate(pricelists):
    # Get product name
    product_id = pl.get('productId')
    if not product_id:
        continue
    
    product = db.products.find_one({'id': product_id}, {'_id': 0})
    if not product:
        continue
    
    product_name = product.get('name', '')
    
    # Detect brand_id
    brand_id = detect_brand_id(product_name, aliases_cache)
    if brand_id:
        stats['brand_detected'] += 1
    
    # Determine product_core_id
    product_core_id = determine_product_core_id(product_name, seed_rules_cache)
    if product_core_id:
        stats['product_core_detected'] += 1
    
    # Determine offer_status
    if product_core_id:
        offer_status = 'ACTIVE'
        stats['active'] += 1
    else:
        offer_status = 'HIDDEN_UNCLASSIFIED'
        stats['hidden_unclassified'] += 1
    
    # Determine price_status (simple for now - can be enhanced)
    price = pl.get('price', 0)
    if price > 0:
        price_status = 'VALID'
    else:
        price_status = 'INVALID'
    
    # Prepare update
    update_doc = {
        'brand_id': brand_id,
        'product_core_id': product_core_id,
        'offer_status': offer_status,
        'price_status': price_status,
        'name_raw': product_name  # Store for easy access
    }
    
    updated_items.append({
        'filter': {'id': pl['id']},
        'update': {'$set': update_doc}
    })
    
    # Progress indicator
    if (i + 1) % 500 == 0:
        print(f"   Progress: {i + 1}/{total_count} ({(i+1)/total_count*100:.1f}%)")

# Bulk update
if updated_items:
    print(f"\n   Performing bulk update...")
    from pymongo import UpdateOne
    bulk_operations = [UpdateOne(item['filter'], item['update']) for item in updated_items]
    result = db.pricelists.bulk_write(bulk_operations)
    print(f"   ✅ Updated {result.modified_count} pricelist items")

# ==================== SUMMARY ====================

print("\n" + "=" * 80)
print("✅ BACKFILL COMPLETED")
print("=" * 80)
print(f"   Total items processed: {stats['total']}")
print(f"   Brand detected: {stats['brand_detected']} ({stats['brand_detected']/stats['total']*100:.1f}%)")
print(f"   Product core detected: {stats['product_core_detected']} ({stats['product_core_detected']/stats['total']*100:.1f}%)")
print(f"   ACTIVE offers: {stats['active']} ({stats['active']/stats['total']*100:.1f}%)")
print(f"   HIDDEN_UNCLASSIFIED: {stats['hidden_unclassified']} ({stats['hidden_unclassified']/stats['total']*100:.1f}%)")
print("=" * 80)

# Verify sample
print("\n🔍 Sample verification (first 5 items with brand_id):")
samples = db.pricelists.find({'brand_id': {'$ne': None}}, {'_id': 0}).limit(5)
for s in samples:
    print(f"   {s.get('name_raw', '')[:50]}")
    print(f"      brand_id: {s.get('brand_id')}, product_core_id: {s.get('product_core_id')}, status: {s.get('offer_status')}")

print("\n🎉 Done!")
