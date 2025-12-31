"""
Run Acceptance Tests for Advanced Product Matcher
Based on AT-1 to AT-5 from specification
"""
import requests
import os

API_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://itemfinder-35.preview.emergentagent.com')
API = f"{API_URL}/api"

print("=" * 80)
print("RUNNING ACCEPTANCE TESTS")
print("=" * 80)

def test_search(query, strict_pack=None, strict_brand=False, brand=None, test_name=""):
    print(f"\n{test_name}")
    print("-" * 70)
    print(f"Query: {query}")
    if strict_pack is not None:
        print(f"Strict Pack: {strict_pack}")
    if strict_brand:
        print(f"Strict Brand: {brand}")
    
    response = requests.post(
        f"{API}/search/similar",
        json={
            "query_text": query,
            "strict_pack": strict_pack,
            "strict_brand": strict_brand,
            "brand": brand,
            "top_n": 10
        }
    )
    
    if response.status_code == 200:
        data = response.json()
        print(f"\\n\u2705 Formula: {data['formula_used']}")
        print(f"Matches: {data['matches_found']}")
        
        if data['results']:
            print(f"\\nTop 3 results:")
            for i, r in enumerate(data['results'][:3], 1):
                print(f"  {i}. {r['raw_name'][:50]}")
                print(f"     Score: {r['score']:.1f} | Price: {r['price']} \u20bd")
                if r.get('caliber'):
                    print(f"     Caliber: {r['caliber']}")
                if r.get('pack_weight_kg'):
                    print(f"     Pack: {r['pack_weight_kg']} kg")
                if r.get('pack_volume_l'):
                    print(f"     Pack: {r['pack_volume_l']} l")
        return data
    else:
        print(f"\u274c Error: {response.status_code}")
        print(response.text)
        return None

# AT-1: Shrimp caliber
print("\\n")
result1 = test_search(
    "\u041a\u0440\u0435\u0432\u0435\u0442\u043a\u0430 31/40 1 \u043a\u0433",
    test_name="AT-1: Shrimp Caliber (31/40 only, no 26/30 or 16/20)"
)

# AT-2: Coconut milk volume (strict pack for drinks)
result2 = test_search(
    "\u041a\u043e\u043a\u043e\u0441\u043e\u0432\u043e\u0435 \u043c\u043e\u043b\u043e\u043a\u043e 1 \u043b",
    test_name="AT-2: Coconut Milk Volume (0.95-1.10l pass, strict pack)"
)

# AT-3: Butter fat (82% only, no milk/drink)
result3 = test_search(
    "\u041c\u0430\u0441\u043b\u043e \u0441\u043b\u0438\u0432\u043e\u0447\u043d\u043e\u0435 82% 0.45 \u043a\u0433",
    test_name="AT-3: Butter 82% Fat (dairy only, no drinks)"
)

# AT-4: Ketchup brand strict
result4 = test_search(
    "\u041a\u0435\u0442\u0447\u0443\u043f Heinz",
    strict_brand=True,
    brand="Heinz",
    test_name="AT-4: Ketchup Heinz (strict brand, exclude non-Heinz)"
)

# AT-5: Pack tolerance
result5 = test_search(
    "\u041c\u043e\u043b\u043e\u043a\u043e 0.8 \u043b",
    test_name="AT-5: Milk 0.8l (0.75-0.88l allowed with tolerance)"
)

print("\\n" + "=" * 80)
print("ACCEPTANCE TESTS COMPLETE")
print("=" * 80)

# Summary
tests = [result1, result2, result3, result4, result5]
passed = sum(1 for t in tests if t and t.get('matches_found', 0) > 0)
print(f"\\nResults: {passed}/5 tests returned matches")
print("\\nManual verification needed to confirm:")
print("  - Caliber mismatches excluded (AT-1)")
print("  - Pack tolerance working (AT-2, AT-5)")
print("  - Super-class filtering (AT-3)")
print("  - Brand strict mode (AT-4)")
print("=" * 80)
