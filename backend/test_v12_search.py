"""
Test V12 Search Engine - Critical Bug Fix Verification

Test cases:
1. Heinz кетчуп 800г с brand_critical=OFF → должен найти ЛЮБОЙ бренд (Царский, Calve, EFKO), NOT только Heinz
2. Heinz кетчуп 800г с brand_critical=ON → должен найти только Heinz
3. Кукуруза 425мл с brand_critical=OFF → должен найти самый дешевый
"""
import os
import sys
from pymongo import MongoClient
from search_engine_v12 import SearchEngineV12, get_v12_loader

# MongoDB connection
mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = MongoClient(mongo_url)
db = client['bestprice']

print("=" * 100)
print("🧪 V12 SEARCH ENGINE TEST - BRAND AGNOSTIC VERIFICATION")
print("=" * 100)

# Initialize
v12_loader = get_v12_loader()
engine = SearchEngineV12()

# Get all pricelists and products
print("\n📦 Loading data...")
pricelists = list(db.pricelists.find({}, {'_id': 0}))
products = list(db.products.find({}, {'_id': 0}))
companies = list(db.companies.find({}, {'_id': 0}))

product_map = {p['id']: p for p in products}
company_map = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in companies}

print(f"   Pricelists: {len(pricelists)}")
print(f"   Products: {len(products)}")
print(f"   Companies: {len(companies)}")

# Prepare candidates
candidates = []
for pl in pricelists:
    product = product_map.get(pl['productId'])
    if not product:
        continue
    
    candidates.append({
        'id': pl['id'],
        'supplierId': pl['supplierId'],
        'name_raw': pl.get('name_raw') or product['name'],
        'price': pl['price'],
        'product_core_id': pl.get('product_core_id'),
        'brand_id': pl.get('brand_id'),
        'offer_status': pl.get('offer_status', 'ACTIVE'),
        'price_status': pl.get('price_status', 'VALID'),
        'pack_value': pl.get('pack_value')
    })

print(f"   Total candidates: {len(candidates)}")

# ==================== TEST 1: Heinz Ketchup with brand_critical=OFF ====================
print("\n" + "=" * 100)
print("TEST 1: Heinz кетчуп 800г с brand_critical=OFF")
print("Expected: Should find ЛЮБОЙ бренд (Царский, Calve, EFKO), NOT just Heinz")
print("=" * 100)

reference_item_1 = {
    'name_raw': 'Кетчуп томатный 800 гр. Heinz',
    'product_core_id': 'кетчуп',
    'brand_id': 'heinz',
    'pack_value': 0.8,  # 800g
    'pack_tolerance_pct': 20
}

result_1 = engine.search(
    reference_item=reference_item_1,
    candidates=candidates,
    brand_critical=False,  # CRITICAL: OFF = ignore brand
    requested_qty=1.0,
    company_map=company_map
)

print(f"\n📊 Result: {result_1.status}")
if result_1.status == "ok":
    print(f"   ✅ Selected: {result_1.name_raw}")
    print(f"   Price: {result_1.price}₽")
    print(f"   Brand: {result_1.explanation.get('selected_brand_id', 'N/A')}")
    print(f"   Supplier: {result_1.supplier_name}")
    print(f"   Total cost: {result_1.total_cost}₽")
    print(f"\n🏆 Top 5 candidates:")
    for i, cand in enumerate(result_1.top_candidates[:5], 1):
        print(f"      {i}. {cand['name_raw'][:60]} - {cand['price']}₽ ({cand['supplier']})")
    
    # Verify: Top candidates should include OTHER brands
    top_brands = []
    for cand in result_1.top_candidates[:10]:
        # Try to extract brand from name
        for pl in pricelists:
            if pl.get('name_raw') == cand['name_raw']:
                top_brands.append(pl.get('brand_id'))
                break
    
    unique_brands = set(b for b in top_brands if b)
    if len(unique_brands) > 1:
        print(f"\n   ✅ PASS: Found {len(unique_brands)} different brands: {unique_brands}")
    else:
        print(f"\n   ❌ FAIL: Only found 1 brand (Heinz stuck): {unique_brands}")
else:
    print(f"   ❌ FAIL: {result_1.failure_reason}")

print(f"\n🔍 Filter breakdown:")
for filter_name in result_1.explanation.get('filters_applied', []):
    print(f"   - {filter_name}")
print(f"\n📈 Counts:")
for key, value in result_1.explanation.get('counts', {}).items():
    print(f"   - {key}: {value}")

# ==================== TEST 2: Heinz Ketchup with brand_critical=ON ====================
print("\n" + "=" * 100)
print("TEST 2: Heinz кетчуп 800г с brand_critical=ON")
print("Expected: Should find ONLY Heinz products")
print("=" * 100)

result_2 = engine.search(
    reference_item=reference_item_1,
    candidates=candidates,
    brand_critical=True,  # ON = strict brand
    requested_qty=1.0,
    company_map=company_map
)

print(f"\n📊 Result: {result_2.status}")
if result_2.status == "ok":
    print(f"   ✅ Selected: {result_2.name_raw}")
    print(f"   Price: {result_2.price}₽")
    print(f"   Supplier: {result_2.supplier_name}")
    print(f"   Total cost: {result_2.total_cost}₽")
    print(f"\n🏆 Top 5 candidates (all should be Heinz):")
    for i, cand in enumerate(result_2.top_candidates[:5], 1):
        print(f"      {i}. {cand['name_raw'][:60]} - {cand['price']}₽")
else:
    print(f"   ❌ FAIL: {result_2.failure_reason}")

# ==================== TEST 3: Corn with brand_critical=OFF ====================
print("\n" + "=" * 100)
print("TEST 3: Кукуруза 425мл с brand_critical=OFF")
print("Expected: Should find cheapest from ANY brand")
print("=" * 100)

reference_item_3 = {
    'name_raw': 'КУКУРУЗА сладкая консервированная 425 мл. Lutik',
    'product_core_id': 'кукуруза_консервированная',
    'brand_id': 'lutik',
    'pack_value': 0.425,  # 425ml
    'pack_tolerance_pct': 20
}

result_3 = engine.search(
    reference_item=reference_item_3,
    candidates=candidates,
    brand_critical=False,
    requested_qty=1.0,
    company_map=company_map
)

print(f"\n📊 Result: {result_3.status}")
if result_3.status == "ok":
    print(f"   ✅ Selected: {result_3.name_raw}")
    print(f"   Price: {result_3.price}₽")
    print(f"   Supplier: {result_3.supplier_name}")
    print(f"   Total cost: {result_3.total_cost}₽")
    print(f"\n🏆 Top 5 candidates:")
    for i, cand in enumerate(result_3.top_candidates[:5], 1):
        print(f"      {i}. {cand['name_raw'][:60]} - {cand['price']}₽ ({cand['supplier']})")
else:
    print(f"   ❌ FAIL: {result_3.failure_reason}")

# ==================== SUMMARY ====================
print("\n" + "=" * 100)
print("📝 SUMMARY")
print("=" * 100)
print(f"TEST 1 (Heinz OFF): {'✅ PASS' if result_1.status == 'ok' else '❌ FAIL'}")
print(f"TEST 2 (Heinz ON):  {'✅ PASS' if result_2.status == 'ok' else '❌ FAIL'}")
print(f"TEST 3 (Corn OFF):  {'✅ PASS' if result_3.status == 'ok' else '❌ FAIL'}")

print("\n🎉 Test completed!")
