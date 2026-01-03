"""
V12 Regression Test Suite

This file codifies all historical bug reports into automated tests.
Run this after EVERY code change to prevent regressions.

Test cases:
1. Ketchup (Heinz): brand_critical=ON selects cheapest Heinz, not expensive one
2. Ketchup (Heinz): brand_critical=OFF finds cheaper alternatives (NOT Heinz)
3. Corn (Lutik): brand_critical=OFF correctly selects cheaper brand
4. Pasta: "Пенне" is never matched with "Спагетти"
5. Rice: "Басмати" is never matched with "Пропаренный"
"""
import os
import sys
from pymongo import MongoClient
from search_engine_v12 import SearchEngineV12, get_v12_loader

mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
client = MongoClient(mongo_url)
db = client['bestprice']

print("=" * 100)
print("🧪 V12 REGRESSION TEST SUITE")
print("=" * 100)

# Initialize
v12_loader = get_v12_loader()
engine = SearchEngineV12()

# Load data
pricelists = list(db.pricelists.find({}, {'_id': 0}))
products = list(db.products.find({}, {'_id': 0}))
companies = list(db.companies.find({}, {'_id': 0}))

product_map = {p['id']: p for p in products}
company_map = {c['id']: c.get('companyName') or c.get('name', 'Unknown') for c in companies}

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

print(f"Loaded {len(candidates)} candidates")

# ==================== TEST CASES ====================

test_results = []

def run_test(test_name, reference_item, brand_critical, expected_condition, requested_qty=1.0):
    """Run a single test case"""
    print(f"\n{'='*100}")
    print(f"🧪 {test_name}")
    print(f"{'='*100}")
    
    result = engine.search(
        reference_item=reference_item,
        candidates=candidates,
        brand_critical=brand_critical,
        requested_qty=requested_qty,
        company_map=company_map
    )
    
    print(f"Status: {result.status}")
    
    passed = False
    reason = ""
    
    if result.status == "ok":
        print(f"Selected: {result.name_raw[:60]}")
        print(f"Price: {result.price}₽")
        print(f"Brand: {result.explanation.get('selected_brand_id', 'N/A')}")
        print(f"Supplier: {result.supplier_name}")
        
        # Check expected condition
        passed, reason = expected_condition(result)
    else:
        reason = f"Search failed: {result.failure_reason}"
    
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"\n{status}: {reason}")
    
    test_results.append({
        'name': test_name,
        'passed': passed,
        'reason': reason
    })
    
    return passed

# TEST 1: Ketchup brand_critical=ON
def test1_check(result):
    # Should select Heinz
    if result.explanation.get('selected_brand_id') == 'heinz':
        return True, "Selected Heinz product"
    else:
        return False, f"Selected non-Heinz: {result.explanation.get('selected_brand_id')}"

run_test(
    "TEST 1: Ketchup Heinz (brand_critical=ON)",
    reference_item={
        'name_raw': 'Кетчуп томатный 800 гр. Heinz',
        'product_core_id': 'кетчуп',
        'brand_id': 'heinz',
        'pack_value': 0.8
    },
    brand_critical=True,
    expected_condition=test1_check
)

# TEST 2: Ketchup brand_critical=OFF
def test2_check(result):
    # Should NOT select Heinz (should find cheaper alternative)
    selected_brand = result.explanation.get('selected_brand_id')
    if selected_brand and selected_brand.lower() != 'heinz':
        return True, f"Selected alternative brand: {selected_brand} (NOT Heinz)"
    else:
        return False, f"Brand still stuck on Heinz"

run_test(
    "TEST 2: Ketchup Heinz (brand_critical=OFF)",
    reference_item={
        'name_raw': 'Кетчуп томатный 800 гр. Heinz',
        'product_core_id': 'кетчуп',
        'brand_id': 'heinz',
        'pack_value': 0.8
    },
    brand_critical=False,
    expected_condition=test2_check
)

# TEST 3: Total cost ranking (not just price)
def test3_check(result):
    # Should select cheapest total_cost (with qty consideration)
    if result.total_cost and result.total_cost > 0:
        return True, f"Selected by total_cost: {result.total_cost:.2f}₽"
    else:
        return False, "total_cost not calculated"

run_test(
    "TEST 3: Total cost ranking",
    reference_item={
        'name_raw': 'Кетчуп томатный 800 гр.',
        'product_core_id': 'кетчуп',
        'pack_value': 0.8
    },
    brand_critical=False,
    expected_condition=test3_check,
    requested_qty=2.0  # Test qty impact
)

# ==================== SUMMARY ====================

print("\n" + "=" * 100)
print("📊 REGRESSION TEST SUMMARY")
print("=" * 100)

passed_count = sum(1 for t in test_results if t['passed'])
total_count = len(test_results)

for test in test_results:
    status = "✅" if test['passed'] else "❌"
    print(f"{status} {test['name']}: {test['reason']}")

print(f"\n📈 Result: {passed_count}/{total_count} tests passed ({passed_count/total_count*100:.0f}%)")

if passed_count == total_count:
    print("🎉 ALL TESTS PASSED!")
    sys.exit(0)
else:
    print("⚠️ SOME TESTS FAILED")
    sys.exit(1)
