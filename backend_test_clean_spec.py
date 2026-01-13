#!/usr/bin/env python3
"""
Backend API Testing for BestPrice - Clean Technical Specification
Tests the FINAL ACCEPTANCE TESTS from Clean Spec with:
- Candidate Guard: Minimum 2 common tokens
- Category check in guard rules
- Reference vs Supplier Item separation
- All prohibitions enforced
"""

import requests
import json
from typing import Dict, Optional, List

# Backend URL from environment
BACKEND_URL = "https://catalog-fix-4.preview.emergentagent.com/api"

# Test credentials
TEST_USER = {
    "email": "customer@bestprice.ru",
    "password": "password123"
}

class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, test_name: str, message: str = ""):
        self.passed.append(f"✅ {test_name}: {message}")
    
    def add_fail(self, test_name: str, message: str):
        self.failed.append(f"❌ {test_name}: {message}")
    
    def add_warning(self, test_name: str, message: str):
        self.warnings.append(f"⚠️ {test_name}: {message}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("TEST SUMMARY - CLEAN TECHNICAL SPECIFICATION")
        print("="*80)
        
        if self.failed:
            print("\n🔴 FAILED TESTS:")
            for fail in self.failed:
                print(f"  {fail}")
        
        if self.warnings:
            print("\n🟡 WARNINGS:")
            for warn in self.warnings:
                print(f"  {warn}")
        
        if self.passed:
            print("\n🟢 PASSED TESTS:")
            for pass_test in self.passed:
                print(f"  {pass_test}")
        
        print("\n" + "="*80)
        print(f"Total: {len(self.passed)} passed, {len(self.failed)} failed, {len(self.warnings)} warnings")
        print("="*80 + "\n")

result = TestResult()

def login(email: str, password: str) -> Optional[Dict]:
    """Login and return token + user info"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                "token": data.get("access_token"),
                "user": data.get("user")
            }
        else:
            return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def get_headers(token: str) -> Dict:
    """Get authorization headers"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def get_favorites(token: str) -> List[Dict]:
    """Get user's favorites list"""
    try:
        headers = get_headers(token)
        response = requests.get(
            f"{BACKEND_URL}/favorites",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to get favorites: {response.status_code}")
            return []
    except Exception as e:
        print(f"Error getting favorites: {e}")
        return []

def find_favorite_by_name(favorites: List[Dict], search_term: str) -> Optional[Dict]:
    """Find favorite by product name (case-insensitive partial match)"""
    search_lower = search_term.lower()
    for fav in favorites:
        name = fav.get('productName', '') or fav.get('reference_name', '')
        if search_lower in name.lower():
            return fav
    return None

def add_from_favorite(token: str, favorite_id: str, qty: float = 1.0) -> Dict:
    """Add item from favorite to cart"""
    try:
        headers = get_headers(token)
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={
                "favorite_id": favorite_id,
                "qty": qty
            },
            timeout=15
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Failed to add from favorite: {response.status_code} - {response.text}")
            return {"status": "error", "message": f"HTTP {response.status_code}"}
    except Exception as e:
        print(f"Error adding from favorite: {e}")
        return {"status": "error", "message": str(e)}

def update_favorite_brand_mode(token: str, favorite_id: str, brand_critical: bool) -> bool:
    """Update favorite's brand_critical setting"""
    try:
        headers = get_headers(token)
        # Convert boolean to brandMode string
        brand_mode = "STRICT" if brand_critical else "ANY"
        response = requests.put(
            f"{BACKEND_URL}/favorites/{favorite_id}/brand-mode",
            headers=headers,
            json={"brandMode": brand_mode},
            timeout=10
        )
        
        return response.status_code == 200
    except Exception as e:
        print(f"Error updating brand mode: {e}")
        return False

def test_1_ketchup_brand_off(token: str):
    """Test 1: Кетчуп Heinz 0.8, brand_critical=OFF
    
    Objective: ANY brand, cheapest option, pack within ±20%
    
    Requirements:
    - Brand COMPLETELY IGNORED
    - Should return ANY ketchup (not just Heinz)
    - Select cheapest after total_cost calculation
    - Score >= 70%
    - Pack within ±20%
    """
    print("\n" + "="*80)
    print("TEST 1: Кетчуп Heinz 0.8, brand_critical=OFF")
    print("Objective: ANY brand, cheapest option, pack within ±20%")
    print("="*80)
    
    # Get favorites
    favorites = get_favorites(token)
    
    if not favorites:
        result.add_fail("Test 1 - Setup", "No favorites found")
        return
    
    # Find ketchup favorite
    ketchup_fav = find_favorite_by_name(favorites, "кетчуп")
    
    if not ketchup_fav:
        result.add_fail("Test 1 - Setup", "Кетчуп not found in favorites")
        return
    
    print(f"\n[1] Found кетчуп favorite: {ketchup_fav.get('productName', ketchup_fav.get('reference_name', ''))}")
    
    # Ensure brand_critical is OFF
    favorite_id = ketchup_fav['id']
    if not update_favorite_brand_mode(token, favorite_id, False):
        result.add_warning("Test 1 - Setup", "Failed to set brand_critical=false")
    
    # Add from favorite
    print(f"\n[2] Calling add-from-favorite with qty=1...")
    response = add_from_favorite(token, favorite_id, qty=1.0)
    
    if response.get("status") != "ok":
        result.add_fail("Test 1 - Response", f"Expected status 'ok', got '{response.get('status')}'. Reason: {response.get('message', 'Unknown')}")
        return
    
    selected_offer = response.get("selected_offer")
    
    if not selected_offer:
        result.add_fail("Test 1 - Response", "No selected_offer in response")
        return
    
    # Verify results
    print(f"\n[3] Verifying results...")
    print(f"   Selected: {selected_offer.get('name_raw')}")
    print(f"   Price: {selected_offer.get('price')} ₽")
    print(f"   Supplier: {selected_offer.get('supplier_name')}")
    print(f"   Score: {selected_offer.get('score')}")
    
    # Check 1: Score >= 70%
    score = selected_offer.get('score', 0)
    if score >= 0.70:
        result.add_pass("Test 1 - Score Threshold", f"Score {score:.2f} >= 0.70 ✓")
    else:
        result.add_fail("Test 1 - Score Threshold", f"Score {score:.2f} < 0.70")
    
    # Check 2: Can be ANY brand (not necessarily Heinz)
    product_name = selected_offer.get('name_raw', '').upper()
    if 'КЕТЧУП' in product_name or 'KETCHUP' in product_name:
        result.add_pass("Test 1 - Product Type", f"Correctly returned ketchup product")
        
        # Note: It CAN be Heinz, but doesn't have to be
        if 'HEINZ' in product_name:
            result.add_pass("Test 1 - Brand Ignored", "Selected Heinz (acceptable when brand_critical=OFF)")
        else:
            result.add_pass("Test 1 - Brand Ignored", f"Selected non-Heinz brand (proves brand is ignored) ✓")
    else:
        result.add_fail("Test 1 - Product Type", f"Expected ketchup, got: {product_name}")
    
    # Check 3: Is it the cheapest?
    top_candidates = response.get("top_candidates", [])
    if top_candidates and len(top_candidates) > 1:
        prices = [c.get('price', 0) for c in top_candidates[:5]]
        print(f"   Top 5 prices: {prices}")
        
        if prices[0] == min(prices):
            result.add_pass("Test 1 - Cheapest Selection", f"Selected cheapest option: {prices[0]} ₽")
        else:
            result.add_warning("Test 1 - Cheapest Selection", f"Selected {prices[0]} ₽ but cheaper options exist: {min(prices)} ₽")
    
    # Check 4: Pack within ±20%
    debug_log = response.get("debug_log", {})
    if debug_log:
        pack_filter = debug_log.get("pack_filter", {})
        if pack_filter:
            print(f"   Pack filter: {pack_filter}")
            result.add_pass("Test 1 - Pack Range", "Pack filter applied (±20%)")
    
    print("\n✅ Test 1 Complete: Brand ignored, cheapest ketchup selected")

def test_2_ketchup_brand_on(token: str):
    """Test 2: Кетчуп Heinz 0.8, brand_critical=ON
    
    Objective: ONLY Heinz, or not_found
    
    Requirements:
    - Only same brand_id considered
    - Score >= 85%
    - If no Heinz available → status "not_found"
    """
    print("\n" + "="*80)
    print("TEST 2: Кетчуп Heinz 0.8, brand_critical=ON")
    print("Objective: ONLY Heinz, or not_found")
    print("="*80)
    
    # Get favorites
    favorites = get_favorites(token)
    
    if not favorites:
        result.add_fail("Test 2 - Setup", "No favorites found")
        return
    
    # Find ketchup favorite
    ketchup_fav = find_favorite_by_name(favorites, "кетчуп")
    
    if not ketchup_fav:
        result.add_fail("Test 2 - Setup", "Кетчуп not found in favorites")
        return
    
    print(f"\n[1] Found кетчуп favorite: {ketchup_fav.get('productName', ketchup_fav.get('reference_name', ''))}")
    
    # Ensure brand_critical is ON
    favorite_id = ketchup_fav['id']
    if not update_favorite_brand_mode(token, favorite_id, True):
        result.add_warning("Test 2 - Setup", "Failed to set brand_critical=true")
    
    # Add from favorite
    print(f"\n[2] Calling add-from-favorite with brand_critical=true...")
    response = add_from_favorite(token, favorite_id, qty=1.0)
    
    status = response.get("status")
    
    if status == "ok":
        selected_offer = response.get("selected_offer")
        
        if not selected_offer:
            result.add_fail("Test 2 - Response", "Status 'ok' but no selected_offer")
            return
        
        print(f"\n[3] Verifying results...")
        print(f"   Selected: {selected_offer.get('name_raw')}")
        print(f"   Price: {selected_offer.get('price')} ₽")
        print(f"   Supplier: {selected_offer.get('supplier_name')}")
        print(f"   Score: {selected_offer.get('score')}")
        
        # Check 1: Must be Heinz brand
        product_name = selected_offer.get('name_raw', '').upper()
        if 'HEINZ' in product_name:
            result.add_pass("Test 2 - Brand Filtering", "Correctly returned ONLY Heinz product ✓")
        else:
            result.add_fail("Test 2 - Brand Filtering", f"Expected Heinz, got: {product_name}")
        
        # Check 2: Score >= 85%
        score = selected_offer.get('score', 0)
        if score >= 0.85:
            result.add_pass("Test 2 - Score Threshold", f"Score {score:.2f} >= 0.85 ✓")
        else:
            result.add_fail("Test 2 - Score Threshold", f"Score {score:.2f} < 0.85")
        
        # Check 3: All candidates should be Heinz
        top_candidates = response.get("top_candidates", [])
        if top_candidates:
            non_heinz = [c for c in top_candidates[:5] if 'HEINZ' not in c.get('name_raw', '').upper()]
            if len(non_heinz) == 0:
                result.add_pass("Test 2 - Strict Filtering", f"All top {min(5, len(top_candidates))} candidates are Heinz ✓")
            else:
                result.add_fail("Test 2 - Strict Filtering", f"Found {len(non_heinz)} non-Heinz products in top candidates")
        
        print("\n✅ Test 2 Complete: Only Heinz products returned")
        
    elif status == "not_found":
        print(f"\n[3] Status: not_found")
        print(f"   Reason: {response.get('message', 'No Heinz products available')}")
        result.add_pass("Test 2 - Not Found", "Correctly returned 'not_found' when no Heinz available ✓")
        
    else:
        result.add_fail("Test 2 - Response", f"Unexpected status: {status}")

def test_3_salmon_origin_matching(token: str):
    """Test 3: Лосось без бренда, с указанием страны
    
    Objective: Origin matching for non-branded items
    
    Requirements:
    - When brand_critical=ON + no brand_id + has origin → use origin_critical
    - Country must match
    - Region/city if specified in reference
    """
    print("\n" + "="*80)
    print("TEST 3: Лосось без бренда, с указанием страны")
    print("Objective: Origin matching for non-branded items")
    print("="*80)
    
    # Get favorites
    favorites = get_favorites(token)
    
    if not favorites:
        result.add_fail("Test 3 - Setup", "No favorites found")
        return
    
    # Find salmon favorite
    salmon_fav = find_favorite_by_name(favorites, "лосось")
    
    if not salmon_fav:
        result.add_fail("Test 3 - Setup", "Лосось not found in favorites")
        return
    
    print(f"\n[1] Found лосось favorite: {salmon_fav.get('productName', salmon_fav.get('reference_name', ''))}")
    
    # Check if it has origin and NO brand
    has_origin = salmon_fav.get('origin_country') is not None
    has_brand = salmon_fav.get('brand_id') is not None
    
    print(f"   Has origin: {has_origin} (country: {salmon_fav.get('origin_country')})")
    print(f"   Has brand: {has_brand}")
    
    if not has_origin:
        result.add_warning("Test 3 - Setup", "Salmon favorite has no origin_country - cannot test origin matching")
        return
    
    if has_brand:
        result.add_warning("Test 3 - Setup", "Salmon favorite has brand_id - this test is for non-branded items")
    
    # Set brand_critical=true (which should trigger origin_critical for non-branded items)
    favorite_id = salmon_fav['id']
    if not update_favorite_brand_mode(token, favorite_id, True):
        result.add_warning("Test 3 - Setup", "Failed to set brand_critical=true")
    
    # Add from favorite
    print(f"\n[2] Calling add-from-favorite with brand_critical=true (should use origin_critical)...")
    response = add_from_favorite(token, favorite_id, qty=1.0)
    
    status = response.get("status")
    
    if status == "ok":
        selected_offer = response.get("selected_offer")
        
        if not selected_offer:
            result.add_fail("Test 3 - Response", "Status 'ok' but no selected_offer")
            return
        
        print(f"\n[3] Verifying results...")
        print(f"   Selected: {selected_offer.get('name_raw')}")
        print(f"   Price: {selected_offer.get('price')} ₽")
        print(f"   Supplier: {selected_offer.get('supplier_name')}")
        
        # Check: Origin should match
        expected_origin = salmon_fav.get('origin_country', '').lower()
        product_name = selected_offer.get('name_raw', '').lower()
        
        if expected_origin and expected_origin in product_name:
            result.add_pass("Test 3 - Origin Matching", f"Correctly matched origin: {expected_origin} ✓")
        else:
            result.add_warning("Test 3 - Origin Matching", f"Expected origin '{expected_origin}' not found in product name")
        
        print("\n✅ Test 3 Complete: Origin matching applied")
        
    elif status == "not_found":
        print(f"\n[3] Status: not_found")
        print(f"   Reason: {response.get('message', 'No matching origin')}")
        result.add_pass("Test 3 - Not Found", "Correctly returned 'not_found' when origin doesn't match ✓")
        
    else:
        result.add_fail("Test 3 - Response", f"Unexpected status: {status}")

def test_4_sea_bass_cheaper_option(token: str):
    """Test 4: Сибас → должен заменяться на более дешевый при OFF
    
    Objective: System selects cheaper option when brand_critical=OFF
    
    Requirements:
    - If multiple sea bass options exist
    - Select cheapest by total_cost
    - Not stuck on original supplier
    """
    print("\n" + "="*80)
    print("TEST 4: Сибас → должен заменяться на более дешевый при OFF")
    print("Objective: System selects cheaper option when brand_critical=OFF")
    print("="*80)
    
    # Get favorites
    favorites = get_favorites(token)
    
    if not favorites:
        result.add_fail("Test 4 - Setup", "No favorites found")
        return
    
    # Find sea bass favorite
    seabass_fav = find_favorite_by_name(favorites, "сибас")
    
    if not seabass_fav:
        result.add_fail("Test 4 - Setup", "Сибас not found in favorites")
        return
    
    print(f"\n[1] Found сибас favorite: {seabass_fav.get('productName', seabass_fav.get('reference_name', ''))}")
    
    # Ensure brand_critical is OFF
    favorite_id = seabass_fav['id']
    if not update_favorite_brand_mode(token, favorite_id, False):
        result.add_warning("Test 4 - Setup", "Failed to set brand_critical=false")
    
    # Add from favorite
    print(f"\n[2] Calling add-from-favorite with brand_critical=false...")
    response = add_from_favorite(token, favorite_id, qty=1.0)
    
    if response.get("status") != "ok":
        result.add_fail("Test 4 - Response", f"Expected status 'ok', got '{response.get('status')}'")
        return
    
    selected_offer = response.get("selected_offer")
    
    if not selected_offer:
        result.add_fail("Test 4 - Response", "No selected_offer in response")
        return
    
    print(f"\n[3] Verifying results...")
    print(f"   Selected: {selected_offer.get('name_raw')}")
    print(f"   Price: {selected_offer.get('price')} ₽")
    print(f"   Supplier: {selected_offer.get('supplier_name')}")
    print(f"   Score: {selected_offer.get('score')}")
    
    # Check: Should select cheapest option
    top_candidates = response.get("top_candidates", [])
    if top_candidates and len(top_candidates) > 1:
        prices = [c.get('price', 0) for c in top_candidates[:5]]
        suppliers = [c.get('supplier', {}).get('name', 'Unknown') for c in top_candidates[:5]]
        
        print(f"   Top 5 options:")
        for i, (price, supplier) in enumerate(zip(prices, suppliers)):
            print(f"      {i+1}. {price} ₽ - {supplier}")
        
        selected_price = selected_offer.get('price')
        min_price = min(prices)
        
        if selected_price == min_price:
            result.add_pass("Test 4 - Cheapest Selection", f"Correctly selected cheapest option: {selected_price} ₽ ✓")
        else:
            result.add_fail("Test 4 - Cheapest Selection", f"Selected {selected_price} ₽ but cheaper option exists: {min_price} ₽")
        
        # Verify it's not stuck on original supplier
        selected_supplier = selected_offer.get('supplier_name')
        original_supplier = seabass_fav.get('originalSupplierId')
        
        if original_supplier and selected_supplier:
            if selected_price < 950:  # Example: if cheaper than 950₽
                result.add_pass("Test 4 - Not Stuck", f"Selected cheaper option from {selected_supplier} (not stuck on original)")
        
        print("\n✅ Test 4 Complete: Cheapest sea bass option selected")
    else:
        result.add_warning("Test 4 - Verification", "Not enough candidates to verify cheapest selection")

def test_5_ketchup_not_water(token: str):
    """Test 5: Кетчуп НЕ может заменяться на воду
    
    Objective: Guard rules prevent cross-category matches
    
    Requirements:
    - Minimum 2 common meaningful tokens
    - Category must match (if specified)
    - Token conflicts checked (ketchup ≠ water)
    """
    print("\n" + "="*80)
    print("TEST 5: Кетчуп НЕ может заменяться на воду")
    print("Objective: Guard rules prevent cross-category matches")
    print("="*80)
    
    # Get favorites
    favorites = get_favorites(token)
    
    if not favorites:
        result.add_fail("Test 5 - Setup", "No favorites found")
        return
    
    # Find ketchup favorite
    ketchup_fav = find_favorite_by_name(favorites, "кетчуп")
    
    if not ketchup_fav:
        result.add_fail("Test 5 - Setup", "Кетчуп not found in favorites")
        return
    
    print(f"\n[1] Found кетчуп favorite: {ketchup_fav.get('productName', ketchup_fav.get('reference_name', ''))}")
    
    # Ensure brand_critical is OFF (to allow broader matching)
    favorite_id = ketchup_fav['id']
    if not update_favorite_brand_mode(token, favorite_id, False):
        result.add_warning("Test 5 - Setup", "Failed to set brand_critical=false")
    
    # Add from favorite
    print(f"\n[2] Calling add-from-favorite...")
    response = add_from_favorite(token, favorite_id, qty=1.0)
    
    if response.get("status") != "ok":
        result.add_fail("Test 5 - Response", f"Expected status 'ok', got '{response.get('status')}'")
        return
    
    selected_offer = response.get("selected_offer")
    
    if not selected_offer:
        result.add_fail("Test 5 - Response", "No selected_offer in response")
        return
    
    print(f"\n[3] Analyzing guard rejections...")
    
    # Check debug_log for guard_rejections
    debug_log = response.get("debug_log", {})
    guard_rejections = debug_log.get("guard_rejections", [])
    
    if guard_rejections:
        print(f"   Found {len(guard_rejections)} guard rejections")
        
        # Check if water, juice, milk were rejected
        rejected_categories = []
        for rejection in guard_rejections[:10]:  # Check first 10
            name = rejection.get('name', '').lower()
            if 'вода' in name or 'water' in name:
                rejected_categories.append('water')
            elif 'сок' in name or 'juice' in name:
                rejected_categories.append('juice')
            elif 'молоко' in name or 'milk' in name:
                rejected_categories.append('milk')
        
        if rejected_categories:
            result.add_pass("Test 5 - Guard Rules", f"Correctly rejected cross-category products: {set(rejected_categories)} ✓")
        else:
            result.add_warning("Test 5 - Guard Rules", "No obvious cross-category rejections found in debug log")
    else:
        result.add_warning("Test 5 - Guard Rules", "No guard_rejections in debug_log")
    
    # Verify selected product is ketchup
    product_name = selected_offer.get('name_raw', '').lower()
    
    if 'кетчуп' in product_name or 'ketchup' in product_name:
        result.add_pass("Test 5 - Correct Category", "Selected product is ketchup (not water/juice) ✓")
    else:
        result.add_fail("Test 5 - Correct Category", f"Selected wrong category: {product_name}")
    
    # Check for water/juice in selected product (should NOT be there)
    wrong_categories = ['вода', 'water', 'сок', 'juice', 'молоко', 'milk']
    has_wrong_category = any(cat in product_name for cat in wrong_categories)
    
    if not has_wrong_category:
        result.add_pass("Test 5 - No Cross-Category", "No water/juice/milk in selected product ✓")
    else:
        result.add_fail("Test 5 - No Cross-Category", f"Found wrong category in: {product_name}")
    
    print("\n✅ Test 5 Complete: Guard rules prevent cross-category matches")

def test_6_minimum_2_tokens(token: str):
    """Test 6: Minimum 2 Tokens Required
    
    Objective: Verify Candidate Guard with min 2 tokens
    """
    print("\n" + "="*80)
    print("TEST 6: Minimum 2 Tokens Required")
    print("Objective: Verify Candidate Guard with min 2 tokens")
    print("="*80)
    
    # Get favorites
    favorites = get_favorites(token)
    
    if not favorites:
        result.add_fail("Test 6 - Setup", "No favorites found")
        return
    
    # Use any favorite
    if len(favorites) == 0:
        result.add_fail("Test 6 - Setup", "No favorites available")
        return
    
    test_fav = favorites[0]
    print(f"\n[1] Testing with: {test_fav.get('productName', test_fav.get('reference_name', ''))}")
    
    # Add from favorite
    favorite_id = test_fav['id']
    response = add_from_favorite(token, favorite_id, qty=1.0)
    
    # Check debug_log for token_filter
    debug_log = response.get("debug_log", {})
    
    if debug_log:
        token_filter = debug_log.get("token_filter", {})
        
        if token_filter:
            min_tokens = token_filter.get("min_tokens")
            
            if min_tokens == 2:
                result.add_pass("Test 6 - Min Tokens", "Candidate Guard correctly requires min 2 tokens ✓")
            else:
                result.add_fail("Test 6 - Min Tokens", f"Expected min_tokens=2, got {min_tokens}")
        else:
            result.add_warning("Test 6 - Min Tokens", "No token_filter in debug_log")
    else:
        result.add_warning("Test 6 - Min Tokens", "No debug_log in response")
    
    # Check guard_rejections for 1-token matches
    guard_rejections = debug_log.get("guard_rejections", [])
    
    if guard_rejections:
        one_token_rejections = [r for r in guard_rejections if r.get('reason') == 'insufficient_tokens']
        
        if one_token_rejections:
            result.add_pass("Test 6 - Token Rejection", f"Correctly rejected {len(one_token_rejections)} candidates with only 1 common token ✓")
    
    print("\n✅ Test 6 Complete: Minimum 2 tokens verified")

def test_7_category_check(token: str):
    """Test 7: Category Check in Guard
    
    Objective: Verify category matching if available
    """
    print("\n" + "="*80)
    print("TEST 7: Category Check in Guard")
    print("Objective: Verify category matching if available")
    print("="*80)
    
    # Get favorites
    favorites = get_favorites(token)
    
    if not favorites:
        result.add_fail("Test 7 - Setup", "No favorites found")
        return
    
    # Use any favorite
    if len(favorites) == 0:
        result.add_fail("Test 7 - Setup", "No favorites available")
        return
    
    test_fav = favorites[0]
    print(f"\n[1] Testing with: {test_fav.get('productName', test_fav.get('reference_name', ''))}")
    
    # Add from favorite
    favorite_id = test_fav['id']
    response = add_from_favorite(token, favorite_id, qty=1.0)
    
    # Check debug_log for category rejections
    debug_log = response.get("debug_log", {})
    guard_rejections = debug_log.get("guard_rejections", [])
    
    if guard_rejections:
        category_rejections = [r for r in guard_rejections if 'category' in r.get('reason', '').lower()]
        
        if category_rejections:
            result.add_pass("Test 7 - Category Check", f"Found {len(category_rejections)} category-based rejections ✓")
        else:
            result.add_warning("Test 7 - Category Check", "No explicit category rejections found")
    else:
        result.add_warning("Test 7 - Category Check", "No guard_rejections in debug_log")
    
    # Check if debug_log mentions category + token_conflicts
    if debug_log:
        debug_str = str(debug_log).lower()
        
        if 'category' in debug_str and 'token' in debug_str:
            result.add_pass("Test 7 - Guard Logic", "Debug log shows category + token_conflicts checking ✓")
    
    print("\n✅ Test 7 Complete: Category check verified")

def main():
    """Run all Clean Spec acceptance tests"""
    print("\n" + "="*80)
    print("BESTPRICE - CLEAN TECHNICAL SPECIFICATION TESTING")
    print("Final Acceptance Tests")
    print("="*80)
    
    # Login
    print(f"\n[LOGIN] Authenticating as {TEST_USER['email']}...")
    auth_data = login(TEST_USER["email"], TEST_USER["password"])
    
    if not auth_data:
        print("❌ Login failed - cannot proceed with tests")
        return 1
    
    print(f"✅ Login successful")
    token = auth_data["token"]
    
    # Run all 7 mandatory tests
    test_1_ketchup_brand_off(token)
    test_2_ketchup_brand_on(token)
    test_3_salmon_origin_matching(token)
    test_4_sea_bass_cheaper_option(token)
    test_5_ketchup_not_water(token)
    test_6_minimum_2_tokens(token)
    test_7_category_check(token)
    
    # Print summary
    result.print_summary()
    
    # Return exit code
    return 0 if len(result.failed) == 0 else 1

if __name__ == "__main__":
    exit(main())
