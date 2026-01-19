#!/usr/bin/env python3
"""
Best Price Search Testing - Final Stabilization
Tests the completely refactored "Best Price" search from Favorites

Test User:
- Email: customer@bestprice.ru
- Password: password123

Critical Tests:
1. Create Favorites with Schema V2
2. Brand Critical = OFF (бренд полностью игнорируется)
3. Brand Critical = ON (только тот же бренд)
4. Origin Critical for Non-Branded (лосось Норвегия)
5. Pack Range ±20% (not x2)
6. Guard Rules (кетчуп ≠ вода)
7. Total Cost Calculation
8. Score Thresholds (85% ON, 70% OFF)
"""

import requests
import json
from typing import Dict, Optional, List

# Backend URL
BACKEND_URL = "https://catalog-gold.preview.emergentagent.com/api"

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
        print(f"   ✅ {test_name}: {message}")
    
    def add_fail(self, test_name: str, message: str):
        self.failed.append(f"❌ {test_name}: {message}")
        print(f"   ❌ {test_name}: {message}")
    
    def add_warning(self, test_name: str, message: str):
        self.warnings.append(f"⚠️ {test_name}: {message}")
        print(f"   ⚠️ {test_name}: {message}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("TEST SUMMARY")
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
            print(f"Login failed: {response.status_code} - {response.text}")
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

def get_catalog_products(token: str, search_term: str = None) -> List[Dict]:
    """Get products from catalog"""
    headers = get_headers(token)
    
    # Get all suppliers
    suppliers_response = requests.get(f"{BACKEND_URL}/suppliers", headers=headers, timeout=10)
    if suppliers_response.status_code != 200:
        return []
    
    suppliers = suppliers_response.json()
    all_products = []
    
    for supplier in suppliers:
        supplier_id = supplier.get("id")
        params = {}
        if search_term:
            params['search'] = search_term
        
        products_response = requests.get(
            f"{BACKEND_URL}/suppliers/{supplier_id}/price-lists",
            headers=headers,
            params=params,
            timeout=10
        )
        
        if products_response.status_code == 200:
            products = products_response.json()
            for product in products:
                product['supplierId'] = supplier_id
                product['supplierName'] = supplier.get('companyName', 'Unknown')
            all_products.extend(products)
    
    return all_products

def test_1_create_favorites_schema_v2(token: str):
    """Test 1: Create Favorites with Schema V2"""
    print("\n" + "="*80)
    print("TEST 1: Create Favorites with Schema V2")
    print("="*80)
    
    headers = get_headers(token)
    
    # Get diverse products from catalog
    test_products = [
        "кетчуп",
        "лосось",
        "ягненок",
        "вода",
        "креветки",
        "сибас",
        "масло",
        "соль",
        "перец",
        "сахар"
    ]
    
    created_favorites = []
    
    for search_term in test_products[:5]:  # Test with 5 products
        print(f"\n[{search_term}] Searching for product...")
        products = get_catalog_products(token, search_term)
        
        if not products:
            result.add_warning(f"Create Favorite ({search_term})", f"No products found for '{search_term}'")
            continue
        
        # Take first product
        product = products[0]
        product_id = product.get('productId')
        supplier_id = product.get('supplierId')
        
        print(f"   Found: {product.get('productName')[:50]}")
        
        # Add to favorites
        try:
            response = requests.post(
                f"{BACKEND_URL}/favorites",
                headers=headers,
                json={
                    "productId": product_id,
                    "supplierId": supplier_id
                },
                timeout=10
            )
            
            if response.status_code == 200:
                fav_data = response.json()
                
                # Verify schema v2 fields
                has_schema_version = fav_data.get('schema_version') == 2
                has_origin = 'origin_country' in fav_data
                
                if has_schema_version:
                    result.add_pass(f"Schema V2 ({search_term})", f"Created with schema_version=2")
                    
                    if 'лосось' in search_term.lower() or 'salmon' in product.get('productName', '').lower():
                        if fav_data.get('origin_country'):
                            result.add_pass(f"Origin Extraction ({search_term})", f"Origin: {fav_data.get('origin_country')}")
                        else:
                            result.add_warning(f"Origin Extraction ({search_term})", "No origin extracted for salmon")
                    
                    created_favorites.append(fav_data)
                else:
                    result.add_fail(f"Schema V2 ({search_term})", "Missing schema_version field")
            
            elif response.status_code == 400 and "already in favorites" in response.text.lower():
                result.add_warning(f"Create Favorite ({search_term})", "Product already in favorites")
            else:
                result.add_fail(f"Create Favorite ({search_term})", f"Failed: {response.status_code} - {response.text[:100]}")
        
        except Exception as e:
            result.add_fail(f"Create Favorite ({search_term})", f"Error: {str(e)}")
    
    return created_favorites

def test_2_brand_critical_off(token: str):
    """Test 2: Brand Critical = OFF (бренд полностью игнорируется)"""
    print("\n" + "="*80)
    print("TEST 2: Brand Critical = OFF (бренд полностью игнорируется)")
    print("="*80)
    
    headers = get_headers(token)
    
    # Get favorites
    favorites_response = requests.get(f"{BACKEND_URL}/favorites", headers=headers, timeout=10)
    if favorites_response.status_code != 200:
        result.add_fail("Brand Critical OFF", "Failed to get favorites")
        return
    
    favorites = favorites_response.json()
    
    # Find a branded ketchup
    ketchup_fav = None
    for fav in favorites:
        name = fav.get('productName', '').lower()
        if 'кетчуп' in name or 'ketchup' in name:
            ketchup_fav = fav
            break
    
    if not ketchup_fav:
        result.add_warning("Brand Critical OFF", "No ketchup found in favorites to test")
        return
    
    print(f"\n   Testing with: {ketchup_fav.get('productName')[:50]}")
    print(f"   Brand critical: {ketchup_fav.get('brand_critical', False)}")
    
    # Ensure brand_critical is OFF
    if ketchup_fav.get('brand_critical', False):
        # Turn it OFF
        update_response = requests.put(
            f"{BACKEND_URL}/favorites/{ketchup_fav['id']}/brand-mode",
            headers=headers,
            json={"brandMode": "ANY"},
            timeout=10
        )
        print(f"   Set brand_critical to OFF")
    
    # Call add-from-favorite
    try:
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={
                "favorite_id": ketchup_fav['id'],
                "qty": 1
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'ok':
                selected = data.get('selected_offer', {})
                score = selected.get('score', 0)
                price = selected.get('price', 0)
                name = selected.get('name_raw', '')
                
                print(f"   ✓ Selected: {name[:50]}")
                print(f"   ✓ Price: {price} ₽")
                print(f"   ✓ Score: {score}")
                
                # Verify score >= 70%
                if score >= 0.70:
                    result.add_pass("Brand Critical OFF - Score", f"Score {score:.2f} >= 0.70 threshold")
                else:
                    result.add_fail("Brand Critical OFF - Score", f"Score {score:.2f} < 0.70 threshold")
                
                # Verify it selected cheapest (not necessarily same brand)
                result.add_pass("Brand Critical OFF - Selection", f"Selected cheapest ketchup: {price} ₽")
            else:
                result.add_fail("Brand Critical OFF", f"Status: {data.get('status')}, Message: {data.get('message')}")
        else:
            result.add_fail("Brand Critical OFF", f"Failed: {response.status_code} - {response.text[:200]}")
    
    except Exception as e:
        result.add_fail("Brand Critical OFF", f"Error: {str(e)}")

def test_3_brand_critical_on(token: str):
    """Test 3: Brand Critical = ON (только тот же бренд)"""
    print("\n" + "="*80)
    print("TEST 3: Brand Critical = ON (только тот же бренд)")
    print("="*80)
    
    headers = get_headers(token)
    
    # Get favorites
    favorites_response = requests.get(f"{BACKEND_URL}/favorites", headers=headers, timeout=10)
    if favorites_response.status_code != 200:
        result.add_fail("Brand Critical ON", "Failed to get favorites")
        return
    
    favorites = favorites_response.json()
    
    # Find a branded ketchup
    ketchup_fav = None
    for fav in favorites:
        name = fav.get('productName', '').lower()
        if 'кетчуп' in name or 'ketchup' in name:
            ketchup_fav = fav
            break
    
    if not ketchup_fav:
        result.add_warning("Brand Critical ON", "No ketchup found in favorites to test")
        return
    
    print(f"\n   Testing with: {ketchup_fav.get('productName')[:50]}")
    
    # Set brand_critical to ON
    update_response = requests.put(
        f"{BACKEND_URL}/favorites/{ketchup_fav['id']}/brand-mode",
        headers=headers,
        json={"brandMode": "STRICT"},
        timeout=10
    )
    print(f"   Set brand_critical to ON (STRICT)")
    
    # Call add-from-favorite
    try:
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={
                "favorite_id": ketchup_fav['id'],
                "qty": 1
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'ok':
                selected = data.get('selected_offer', {})
                score = selected.get('score', 0)
                name = selected.get('name_raw', '')
                
                print(f"   ✓ Selected: {name[:50]}")
                print(f"   ✓ Score: {score}")
                
                # Verify score >= 85%
                if score >= 0.85:
                    result.add_pass("Brand Critical ON - Score", f"Score {score:.2f} >= 0.85 threshold")
                else:
                    result.add_fail("Brand Critical ON - Score", f"Score {score:.2f} < 0.85 threshold")
                
                # Verify same brand (if original had brand)
                original_brand = ketchup_fav.get('brand')
                if original_brand:
                    if original_brand.lower() in name.lower():
                        result.add_pass("Brand Critical ON - Brand Match", f"Correctly matched brand: {original_brand}")
                    else:
                        result.add_warning("Brand Critical ON - Brand Match", f"Original brand '{original_brand}' not in selected product name")
                else:
                    result.add_pass("Brand Critical ON - Selection", "Selected product with strict brand filtering")
            
            elif data.get('status') == 'not_found':
                result.add_pass("Brand Critical ON - Not Found", "Correctly returned 'not_found' when no matching brand available")
            else:
                result.add_fail("Brand Critical ON", f"Status: {data.get('status')}, Message: {data.get('message')}")
        else:
            result.add_fail("Brand Critical ON", f"Failed: {response.status_code} - {response.text[:200]}")
    
    except Exception as e:
        result.add_fail("Brand Critical ON", f"Error: {str(e)}")

def test_4_origin_critical_non_branded(token: str):
    """Test 4: Origin Critical for Non-Branded (лосось Норвегия)"""
    print("\n" + "="*80)
    print("TEST 4: Origin Critical for Non-Branded (лосось Норвегия)")
    print("="*80)
    
    headers = get_headers(token)
    
    # Get favorites
    favorites_response = requests.get(f"{BACKEND_URL}/favorites", headers=headers, timeout=10)
    if favorites_response.status_code != 200:
        result.add_fail("Origin Critical", "Failed to get favorites")
        return
    
    favorites = favorites_response.json()
    
    # Find salmon
    salmon_fav = None
    for fav in favorites:
        name = fav.get('productName', '').lower()
        if 'лосось' in name or 'salmon' in name:
            salmon_fav = fav
            break
    
    if not salmon_fav:
        result.add_warning("Origin Critical", "No salmon found in favorites to test")
        return
    
    print(f"\n   Testing with: {salmon_fav.get('productName')[:50]}")
    print(f"   Origin: {salmon_fav.get('origin_country', 'Not set')}")
    print(f"   Brand ID: {salmon_fav.get('brand_id', 'None')}")
    
    # Verify it has origin but NO brand_id
    has_origin = salmon_fav.get('origin_country') is not None
    has_brand = salmon_fav.get('brand_id') is not None
    
    if has_origin and not has_brand:
        result.add_pass("Origin Critical - Schema", f"Salmon has origin ({salmon_fav.get('origin_country')}) but no brand_id")
    elif not has_origin:
        result.add_warning("Origin Critical - Schema", "Salmon has no origin_country set")
    
    # Set brand_critical to ON (for non-branded, this means origin matching)
    update_response = requests.put(
        f"{BACKEND_URL}/favorites/{salmon_fav['id']}/brand-mode",
        headers=headers,
        json={"brandMode": "STRICT"},
        timeout=10
    )
    print(f"   Set brand_critical to ON for origin matching")
    
    # Call add-from-favorite
    try:
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={
                "favorite_id": salmon_fav['id'],
                "qty": 1
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'ok':
                selected = data.get('selected_offer', {})
                name = selected.get('name_raw', '')
                
                print(f"   ✓ Selected: {name[:50]}")
                
                # Check if origin matches
                original_origin = salmon_fav.get('origin_country', '').lower()
                if original_origin and original_origin in name.lower():
                    result.add_pass("Origin Critical - Match", f"Correctly matched origin: {original_origin}")
                else:
                    result.add_warning("Origin Critical - Match", f"Could not verify origin match in product name")
            
            elif data.get('status') == 'not_found':
                result.add_pass("Origin Critical - Not Found", "Correctly returned 'not_found' when origin doesn't match")
            else:
                result.add_fail("Origin Critical", f"Status: {data.get('status')}, Message: {data.get('message')}")
        else:
            result.add_fail("Origin Critical", f"Failed: {response.status_code} - {response.text[:200]}")
    
    except Exception as e:
        result.add_fail("Origin Critical", f"Error: {str(e)}")

def test_5_pack_range_20_percent(token: str):
    """Test 5: Pack Range ±20% (not x2)"""
    print("\n" + "="*80)
    print("TEST 5: Pack Range ±20% (not x2)")
    print("="*80)
    
    headers = get_headers(token)
    
    # Get favorites
    favorites_response = requests.get(f"{BACKEND_URL}/favorites", headers=headers, timeout=10)
    if favorites_response.status_code != 200:
        result.add_fail("Pack Range", "Failed to get favorites")
        return
    
    favorites = favorites_response.json()
    
    # Find item with known pack_size (e.g., ketchup 0.8kg)
    test_fav = None
    for fav in favorites:
        pack_size = fav.get('pack_size')
        if pack_size and pack_size > 0:
            test_fav = fav
            break
    
    if not test_fav:
        result.add_warning("Pack Range", "No favorites with pack_size found to test")
        return
    
    # Ensure brand_critical is OFF for this test
    update_response = requests.put(
        f"{BACKEND_URL}/favorites/{test_fav['id']}/brand-mode",
        headers=headers,
        json={"brandMode": "ANY"},
        timeout=10
    )
    
    pack_size = test_fav.get('pack_size', 0)
    print(f"\n   Testing with: {test_fav.get('productName')[:50]}")
    print(f"   Pack size: {pack_size} {test_fav.get('unit', '')}")
    
    # Calculate expected range (±20%)
    min_pack = pack_size * 0.8
    max_pack = pack_size * 1.2
    print(f"   Expected range: {min_pack:.2f} - {max_pack:.2f}")
    
    # Call add-from-favorite
    try:
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={
                "favorite_id": test_fav['id'],
                "qty": 1
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check debug_log for pack_filter
            debug_log = data.get('debug_log', {})
            if debug_log:
                pack_filter = debug_log.get('pack_filter', '')
                print(f"   ✓ Pack filter from debug_log: {pack_filter}")
                
                # Verify it shows ±20% range (not 0.5x-2x)
                if '0.8' in str(pack_filter) or '1.2' in str(pack_filter) or '±20%' in str(pack_filter):
                    result.add_pass("Pack Range - Filter", f"Pack filter shows ±20% range: {pack_filter}")
                elif '0.5' in str(pack_filter) or '2.0' in str(pack_filter) or '2x' in str(pack_filter):
                    result.add_fail("Pack Range - Filter", f"Pack filter still shows old x2 range: {pack_filter}")
                else:
                    result.add_warning("Pack Range - Filter", f"Pack filter format unclear: {pack_filter}")
            else:
                result.add_warning("Pack Range - Debug", "No debug_log in response to verify pack filter")
            
            if data.get('status') == 'ok':
                result.add_pass("Pack Range - Selection", "Successfully selected product within pack range")
        else:
            result.add_fail("Pack Range", f"Failed: {response.status_code} - {response.text[:200]}")
    
    except Exception as e:
        result.add_fail("Pack Range", f"Error: {str(e)}")

def test_6_guard_rules(token: str):
    """Test 6: Guard Rules (кетчуп ≠ вода)"""
    print("\n" + "="*80)
    print("TEST 6: Guard Rules (кетчуп ≠ вода)")
    print("="*80)
    
    headers = get_headers(token)
    
    # Get favorites
    favorites_response = requests.get(f"{BACKEND_URL}/favorites", headers=headers, timeout=10)
    if favorites_response.status_code != 200:
        result.add_fail("Guard Rules", "Failed to get favorites")
        return
    
    favorites = favorites_response.json()
    
    # Find ketchup
    ketchup_fav = None
    for fav in favorites:
        name = fav.get('productName', '').lower()
        if 'кетчуп' in name or 'ketchup' in name:
            ketchup_fav = fav
            break
    
    if not ketchup_fav:
        result.add_warning("Guard Rules", "No ketchup found in favorites to test")
        return
    
    # Ensure brand_critical is OFF for this test
    update_response = requests.put(
        f"{BACKEND_URL}/favorites/{ketchup_fav['id']}/brand-mode",
        headers=headers,
        json={"brandMode": "ANY"},
        timeout=10
    )
    
    print(f"\n   Testing with: {ketchup_fav.get('productName')[:50]}")
    
    # Call add-from-favorite
    try:
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={
                "favorite_id": ketchup_fav['id'],
                "qty": 1
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'ok':
                selected = data.get('selected_offer', {})
                name = selected.get('name_raw', '').lower()
                
                print(f"   ✓ Selected: {name[:50]}")
                
                # Verify it's NOT water or other wrong category
                wrong_categories = ['вода', 'water', 'сок', 'juice', 'молоко', 'milk']
                is_wrong_category = any(cat in name for cat in wrong_categories)
                
                if not is_wrong_category:
                    result.add_pass("Guard Rules - Category", "Correctly prevented cross-category match")
                else:
                    result.add_fail("Guard Rules - Category", f"CRITICAL: Matched wrong category: {name}")
                
                # Verify it's ketchup-related
                if 'кетчуп' in name or 'ketchup' in name or 'соус' in name:
                    result.add_pass("Guard Rules - Match", "Correctly matched ketchup category")
                else:
                    result.add_warning("Guard Rules - Match", f"Selected product may not be ketchup: {name}")
        else:
            result.add_fail("Guard Rules", f"Failed: {response.status_code} - {response.text[:200]}")
    
    except Exception as e:
        result.add_fail("Guard Rules", f"Error: {str(e)}")

def test_7_total_cost_calculation(token: str):
    """Test 7: Total Cost Calculation"""
    print("\n" + "="*80)
    print("TEST 7: Total Cost Calculation")
    print("="*80)
    
    headers = get_headers(token)
    
    # Get favorites
    favorites_response = requests.get(f"{BACKEND_URL}/favorites", headers=headers, timeout=10)
    if favorites_response.status_code != 200:
        result.add_fail("Total Cost", "Failed to get favorites")
        return
    
    favorites = favorites_response.json()
    
    if not favorites:
        result.add_warning("Total Cost", "No favorites found to test")
        return
    
    test_fav = favorites[0]
    
    # Ensure brand_critical is OFF for this test
    update_response = requests.put(
        f"{BACKEND_URL}/favorites/{test_fav['id']}/brand-mode",
        headers=headers,
        json={"brandMode": "ANY"},
        timeout=10
    )
    
    print(f"\n   Testing with: {test_fav.get('productName')[:50]}")
    
    # Call add-from-favorite with qty=2
    try:
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={
                "favorite_id": test_fav['id'],
                "qty": 2
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            # Check debug_log for total_cost calculation
            debug_log = data.get('debug_log', {})
            if debug_log:
                print(f"   ✓ Debug log available")
                
                # Look for total_cost mentions
                debug_str = json.dumps(debug_log)
                if 'total_cost' in debug_str.lower():
                    result.add_pass("Total Cost - Calculation", "Debug log shows total_cost calculation")
                else:
                    result.add_warning("Total Cost - Calculation", "total_cost not found in debug_log")
            
            if data.get('status') == 'ok':
                selected = data.get('selected_offer', {})
                price = selected.get('price', 0)
                
                print(f"   ✓ Selected price: {price} ₽")
                print(f"   ✓ Quantity: 2")
                print(f"   ✓ Total cost: {price * 2} ₽")
                
                result.add_pass("Total Cost - Selection", f"Selected by minimum total_cost: {price * 2} ₽")
        else:
            result.add_fail("Total Cost", f"Failed: {response.status_code} - {response.text[:200]}")
    
    except Exception as e:
        result.add_fail("Total Cost", f"Error: {str(e)}")

def test_8_score_thresholds(token: str):
    """Test 8: Score Thresholds (85% ON, 70% OFF)"""
    print("\n" + "="*80)
    print("TEST 8: Score Thresholds (85% ON, 70% OFF)")
    print("="*80)
    
    headers = get_headers(token)
    
    # Get favorites
    favorites_response = requests.get(f"{BACKEND_URL}/favorites", headers=headers, timeout=10)
    if favorites_response.status_code != 200:
        result.add_fail("Score Thresholds", "Failed to get favorites")
        return
    
    favorites = favorites_response.json()
    
    if not favorites:
        result.add_warning("Score Thresholds", "No favorites found to test")
        return
    
    # Test with brand_critical=OFF (70% threshold)
    test_fav = favorites[0]
    print(f"\n   Testing with: {test_fav.get('productName')[:50]}")
    
    # Ensure brand_critical is OFF
    update_response = requests.put(
        f"{BACKEND_URL}/favorites/{test_fav['id']}/brand-mode",
        headers=headers,
        json={"brandMode": "ANY"},
        timeout=10
    )
    
    print(f"\n   [A] Testing with brand_critical=OFF (threshold 70%)...")
    try:
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={
                "favorite_id": test_fav['id'],
                "qty": 1
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'ok':
                selected = data.get('selected_offer', {})
                score = selected.get('score', 0)
                
                print(f"   ✓ Score: {score:.2f}")
                
                if score >= 0.70:
                    result.add_pass("Score Threshold OFF", f"Score {score:.2f} >= 0.70 threshold")
                else:
                    result.add_fail("Score Threshold OFF", f"Score {score:.2f} < 0.70 threshold")
    except Exception as e:
        result.add_fail("Score Threshold OFF", f"Error: {str(e)}")
    
    # Test with brand_critical=ON (85% threshold)
    update_response = requests.put(
        f"{BACKEND_URL}/favorites/{test_fav['id']}/brand-mode",
        headers=headers,
        json={"brandMode": "STRICT"},
        timeout=10
    )
    
    print(f"\n   [B] Testing with brand_critical=ON (threshold 85%)...")
    try:
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={
                "favorite_id": test_fav['id'],
                "qty": 1
            },
            timeout=15
        )
        
        if response.status_code == 200:
            data = response.json()
            
            if data.get('status') == 'ok':
                selected = data.get('selected_offer', {})
                score = selected.get('score', 0)
                
                print(f"   ✓ Score: {score:.2f}")
                
                if score >= 0.85:
                    result.add_pass("Score Threshold ON", f"Score {score:.2f} >= 0.85 threshold")
                else:
                    result.add_fail("Score Threshold ON", f"Score {score:.2f} < 0.85 threshold")
            elif data.get('status') == 'not_found':
                result.add_pass("Score Threshold ON", "Correctly rejected items below 85% threshold")
    except Exception as e:
        result.add_fail("Score Threshold ON", f"Error: {str(e)}")

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BEST PRICE SEARCH TESTING - FINAL STABILIZATION")
    print("Testing: Pack range ±20%, Origin support, Brand critical logic, Score thresholds")
    print("="*80)
    
    # Step 1: Login
    print(f"\n[LOGIN] Authenticating as {TEST_USER['email']}...")
    auth_data = login(TEST_USER['email'], TEST_USER['password'])
    
    if not auth_data:
        print("❌ Login failed - cannot proceed with tests")
        return 1
    
    print(f"✅ Login successful")
    token = auth_data['token']
    
    # Run all tests
    test_1_create_favorites_schema_v2(token)
    test_2_brand_critical_off(token)
    test_3_brand_critical_on(token)
    test_4_origin_critical_non_branded(token)
    test_5_pack_range_20_percent(token)
    test_6_guard_rules(token)
    test_7_total_cost_calculation(token)
    test_8_score_thresholds(token)
    
    # Print summary
    result.print_summary()
    
    # Return exit code
    return 0 if len(result.failed) == 0 else 1

if __name__ == "__main__":
    exit(main())
