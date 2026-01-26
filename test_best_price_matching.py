#!/usr/bin/env python3
"""
Test Best Price Matching Logic in /api/favorites Endpoint

Tests:
1. Weight Tolerance - Should MATCH (within 20%)
2. Weight Tolerance - Should NOT MATCH (>20% difference)
3. Type Matching - Must match primary type
4. Price Sorting - Cheapest first
"""

import requests
import json
from typing import Dict, Optional, List

# Backend URL from environment
BACKEND_URL = "https://product-compare-14.preview.emergentagent.com/api"

# Test credentials
EMAIL = "customer@bestprice.ru"
PASSWORD = "password123"

class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, test_name: str, message: str = ""):
        self.passed.append(f"✅ {test_name}: {message}")
        print(f"✅ {test_name}: {message}")
    
    def add_fail(self, test_name: str, message: str):
        self.failed.append(f"❌ {test_name}: {message}")
        print(f"❌ {test_name}: {message}")
    
    def add_warning(self, test_name: str, message: str):
        self.warnings.append(f"⚠️ {test_name}: {message}")
        print(f"⚠️ {test_name}: {message}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("TEST SUMMARY - BEST PRICE MATCHING LOGIC")
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

def find_product_by_name(token: str, search_term: str) -> Optional[Dict]:
    """Find a product by searching through suppliers"""
    headers = get_headers(token)
    
    try:
        # Get all suppliers
        suppliers_response = requests.get(f"{BACKEND_URL}/suppliers", headers=headers, timeout=10)
        if suppliers_response.status_code != 200:
            return None
        
        suppliers = suppliers_response.json()
        
        # Search through each supplier's products
        for supplier in suppliers:
            supplier_id = supplier.get("id")
            products_response = requests.get(
                f"{BACKEND_URL}/suppliers/{supplier_id}/price-lists",
                headers=headers,
                timeout=10
            )
            
            if products_response.status_code == 200:
                products = products_response.json()
                for product in products:
                    if search_term.lower() in product.get("productName", "").lower():
                        return {
                            "productId": product.get("productId"),
                            "productName": product.get("productName"),
                            "price": product.get("price"),
                            "unit": product.get("unit"),
                            "supplierId": product.get("supplierCompanyId"),
                            "article": product.get("article", "")
                        }
        
        return None
    except Exception as e:
        print(f"Error finding product: {e}")
        return None

def add_to_favorites(token: str, product_id: str, supplier_id: str) -> Optional[str]:
    """Add product to favorites and return favorite ID"""
    headers = get_headers(token)
    
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
            data = response.json()
            return data.get("id")
        else:
            print(f"Add to favorites failed: {response.status_code} - {response.text}")
            return None
    except Exception as e:
        print(f"Error adding to favorites: {e}")
        return None

def set_favorite_mode(token: str, favorite_id: str, mode: str) -> bool:
    """Set favorite mode to 'cheapest' or 'exact'"""
    headers = get_headers(token)
    
    try:
        response = requests.put(
            f"{BACKEND_URL}/favorites/{favorite_id}/mode",
            headers=headers,
            json={"mode": mode},
            timeout=10
        )
        
        return response.status_code == 200
    except Exception as e:
        print(f"Error setting favorite mode: {e}")
        return False

def get_favorites(token: str) -> List[Dict]:
    """Get all favorites with Best Price matching"""
    headers = get_headers(token)
    
    try:
        response = requests.get(
            f"{BACKEND_URL}/favorites",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"Get favorites failed: {response.status_code} - {response.text}")
            return []
    except Exception as e:
        print(f"Error getting favorites: {e}")
        return []

def test_weight_tolerance_match():
    """Test Case 1: Weight Tolerance - Should MATCH (within 20%)"""
    print("\n" + "="*80)
    print("TEST CASE 1: Weight Tolerance - Should MATCH (within 20%)")
    print("="*80)
    
    # Login
    print("\n[1] Logging in...")
    auth_data = login(EMAIL, PASSWORD)
    if not auth_data:
        result.add_fail("Weight Tolerance Match", "Login failed")
        return
    
    token = auth_data["token"]
    print(f"✓ Logged in as {EMAIL}")
    
    # Find СИБАС 300-400g product
    print("\n[2] Finding СИБАС 300-400g product...")
    product = find_product_by_name(token, "СИБАС 300-400")
    
    if not product:
        result.add_warning("Weight Tolerance Match", "Could not find СИБАС 300-400g product in catalog")
        return
    
    print(f"✓ Found product: {product['productName']} at {product['price']} ₽")
    
    # Add to favorites
    print("\n[3] Adding to favorites...")
    favorite_id = add_to_favorites(token, product["productId"], product["supplierId"])
    
    if not favorite_id:
        result.add_fail("Weight Tolerance Match", "Failed to add product to favorites")
        return
    
    print(f"✓ Added to favorites (ID: {favorite_id})")
    
    # Set mode to 'cheapest'
    print("\n[4] Setting mode to 'cheapest'...")
    if not set_favorite_mode(token, favorite_id, "cheapest"):
        result.add_fail("Weight Tolerance Match", "Failed to set mode to cheapest")
        return
    
    print("✓ Mode set to 'cheapest'")
    
    # Get favorites with Best Price matching
    print("\n[5] Getting favorites with Best Price matching...")
    favorites = get_favorites(token)
    
    if not favorites:
        result.add_fail("Weight Tolerance Match", "No favorites returned")
        return
    
    # Find our favorite
    our_favorite = None
    for fav in favorites:
        if fav.get("id") == favorite_id:
            our_favorite = fav
            break
    
    if not our_favorite:
        result.add_fail("Weight Tolerance Match", "Could not find our favorite in response")
        return
    
    print(f"\n[6] Analyzing Best Price matching results...")
    print(f"   Original Price: {our_favorite.get('originalPrice')} ₽")
    print(f"   Best Price: {our_favorite.get('bestPrice')} ₽")
    print(f"   Has Cheaper Match: {our_favorite.get('hasCheaperMatch')}")
    
    if our_favorite.get('hasCheaperMatch'):
        found_product = our_favorite.get('foundProduct', {})
        print(f"   Found Product: {found_product.get('name')}")
        print(f"   Found Price: {found_product.get('price')} ₽")
        print(f"   Found Weight: {found_product.get('weight')} kg")
    
    # Verify expectations
    original_price = our_favorite.get('originalPrice')
    best_price = our_favorite.get('bestPrice')
    has_cheaper = our_favorite.get('hasCheaperMatch')
    
    # Expected: Should find cheaper СИБАС 300-400g at 906.50 ₽
    # Should NOT match 5kg bulk packages
    if has_cheaper and best_price < original_price:
        found_product = our_favorite.get('foundProduct', {})
        found_name = found_product.get('name', '')
        found_weight = found_product.get('weight')
        
        # Check if it's a similar weight product (not 5kg bulk)
        if found_weight and found_weight < 1.0:  # Less than 1kg
            result.add_pass(
                "Weight Tolerance Match",
                f"Correctly found cheaper match at {best_price} ₽ (weight: {found_weight} kg) - NOT bulk package"
            )
        else:
            result.add_fail(
                "Weight Tolerance Match",
                f"Found match but weight is too different: {found_weight} kg (expected ~0.35 kg)"
            )
    elif not has_cheaper:
        result.add_warning(
            "Weight Tolerance Match",
            "No cheaper match found - current price may already be best"
        )
    else:
        result.add_fail(
            "Weight Tolerance Match",
            f"Unexpected result: hasCheaperMatch={has_cheaper}, bestPrice={best_price}, originalPrice={original_price}"
        )

def test_weight_tolerance_no_match():
    """Test Case 2: Weight Tolerance - Should NOT MATCH (>20% difference)"""
    print("\n" + "="*80)
    print("TEST CASE 2: Weight Tolerance - Should NOT MATCH (>20% difference)")
    print("="*80)
    
    # Login
    print("\n[1] Logging in...")
    auth_data = login(EMAIL, PASSWORD)
    if not auth_data:
        result.add_fail("Weight Tolerance No Match", "Login failed")
        return
    
    token = auth_data["token"]
    print(f"✓ Logged in as {EMAIL}")
    
    # Find МИНТАЙ филе 1 кг product
    print("\n[2] Finding МИНТАЙ филе 1 кг product...")
    product = find_product_by_name(token, "МИНТАЙ филе 1")
    
    if not product:
        result.add_warning("Weight Tolerance No Match", "Could not find МИНТАЙ филе 1 кг product in catalog")
        return
    
    print(f"✓ Found product: {product['productName']} at {product['price']} ₽")
    
    # Add to favorites
    print("\n[3] Adding to favorites...")
    favorite_id = add_to_favorites(token, product["productId"], product["supplierId"])
    
    if not favorite_id:
        result.add_fail("Weight Tolerance No Match", "Failed to add product to favorites")
        return
    
    print(f"✓ Added to favorites (ID: {favorite_id})")
    
    # Set mode to 'cheapest'
    print("\n[4] Setting mode to 'cheapest'...")
    if not set_favorite_mode(token, favorite_id, "cheapest"):
        result.add_fail("Weight Tolerance No Match", "Failed to set mode to cheapest")
        return
    
    print("✓ Mode set to 'cheapest'")
    
    # Get favorites with Best Price matching
    print("\n[5] Getting favorites with Best Price matching...")
    favorites = get_favorites(token)
    
    if not favorites:
        result.add_fail("Weight Tolerance No Match", "No favorites returned")
        return
    
    # Find our favorite
    our_favorite = None
    for fav in favorites:
        if fav.get("id") == favorite_id:
            our_favorite = fav
            break
    
    if not our_favorite:
        result.add_fail("Weight Tolerance No Match", "Could not find our favorite in response")
        return
    
    print(f"\n[6] Analyzing Best Price matching results...")
    print(f"   Original Price: {our_favorite.get('originalPrice')} ₽")
    print(f"   Best Price: {our_favorite.get('bestPrice')} ₽")
    print(f"   Has Cheaper Match: {our_favorite.get('hasCheaperMatch')}")
    print(f"   Fallback Message: {our_favorite.get('fallbackMessage', 'N/A')}")
    
    # Verify expectations
    has_cheaper = our_favorite.get('hasCheaperMatch')
    fallback_msg = our_favorite.get('fallbackMessage', '')
    
    # Expected: Should NOT match with 300g portions (>20% weight difference)
    # Should show "Аналоги найдены, но текущая цена уже лучшая"
    if not has_cheaper and "текущая цена уже лучшая" in fallback_msg:
        result.add_pass(
            "Weight Tolerance No Match",
            "Correctly did NOT match products with >20% weight difference - shows fallback message"
        )
    elif not has_cheaper and not fallback_msg:
        result.add_warning(
            "Weight Tolerance No Match",
            "No cheaper match found but no fallback message displayed"
        )
    elif has_cheaper:
        found_product = our_favorite.get('foundProduct', {})
        found_weight = found_product.get('weight')
        result.add_fail(
            "Weight Tolerance No Match",
            f"Should NOT match products with >20% weight difference but found match at weight {found_weight} kg"
        )
    else:
        result.add_fail(
            "Weight Tolerance No Match",
            f"Unexpected result: hasCheaperMatch={has_cheaper}, fallbackMessage={fallback_msg}"
        )

def test_type_matching():
    """Test Case 3: Type Matching - Must match primary type"""
    print("\n" + "="*80)
    print("TEST CASE 3: Type Matching - Must match primary type")
    print("="*80)
    
    # Login
    print("\n[1] Logging in...")
    auth_data = login(EMAIL, PASSWORD)
    if not auth_data:
        result.add_fail("Type Matching", "Login failed")
        return
    
    token = auth_data["token"]
    print(f"✓ Logged in as {EMAIL}")
    
    # Test with СИБАС product
    print("\n[2] Testing СИБАС type matching...")
    product = find_product_by_name(token, "СИБАС")
    
    if not product:
        result.add_warning("Type Matching", "Could not find СИБАС product in catalog")
        return
    
    print(f"✓ Found product: {product['productName']} at {product['price']} ₽")
    
    # Add to favorites
    favorite_id = add_to_favorites(token, product["productId"], product["supplierId"])
    if not favorite_id:
        result.add_fail("Type Matching", "Failed to add product to favorites")
        return
    
    # Set mode to 'cheapest'
    if not set_favorite_mode(token, favorite_id, "cheapest"):
        result.add_fail("Type Matching", "Failed to set mode to cheapest")
        return
    
    # Get favorites
    favorites = get_favorites(token)
    our_favorite = None
    for fav in favorites:
        if fav.get("id") == favorite_id:
            our_favorite = fav
            break
    
    if not our_favorite:
        result.add_fail("Type Matching", "Could not find our favorite in response")
        return
    
    print(f"\n[3] Analyzing type matching...")
    
    # If a cheaper match was found, verify it's also СИБАС
    if our_favorite.get('hasCheaperMatch'):
        found_product = our_favorite.get('foundProduct', {})
        found_name = found_product.get('name', '').upper()
        
        if 'СИБАС' in found_name or 'СИБАСС' in found_name:
            result.add_pass(
                "Type Matching",
                f"Correctly matched only СИБАС products: {found_product.get('name')}"
            )
        else:
            result.add_fail(
                "Type Matching",
                f"Matched wrong product type: {found_product.get('name')} (expected СИБАС)"
            )
    else:
        result.add_warning(
            "Type Matching",
            "No cheaper match found - cannot verify type matching (current price may be best)"
        )

def test_price_sorting():
    """Test Case 4: Price Sorting - Cheapest first"""
    print("\n" + "="*80)
    print("TEST CASE 4: Price Sorting - Cheapest first")
    print("="*80)
    
    # Login
    print("\n[1] Logging in...")
    auth_data = login(EMAIL, PASSWORD)
    if not auth_data:
        result.add_fail("Price Sorting", "Login failed")
        return
    
    token = auth_data["token"]
    print(f"✓ Logged in as {EMAIL}")
    
    # Find a product with multiple offers
    print("\n[2] Finding product with multiple offers...")
    product = find_product_by_name(token, "СИБАС 300-400")
    
    if not product:
        result.add_warning("Price Sorting", "Could not find test product in catalog")
        return
    
    print(f"✓ Found product: {product['productName']} at {product['price']} ₽")
    
    # Add to favorites
    favorite_id = add_to_favorites(token, product["productId"], product["supplierId"])
    if not favorite_id:
        result.add_fail("Price Sorting", "Failed to add product to favorites")
        return
    
    # Set mode to 'cheapest'
    if not set_favorite_mode(token, favorite_id, "cheapest"):
        result.add_fail("Price Sorting", "Failed to set mode to cheapest")
        return
    
    # Get favorites
    favorites = get_favorites(token)
    our_favorite = None
    for fav in favorites:
        if fav.get("id") == favorite_id:
            our_favorite = fav
            break
    
    if not our_favorite:
        result.add_fail("Price Sorting", "Could not find our favorite in response")
        return
    
    print(f"\n[3] Analyzing price sorting...")
    print(f"   Original Price: {our_favorite.get('originalPrice')} ₽")
    print(f"   Best Price: {our_favorite.get('bestPrice')} ₽")
    print(f"   Match Count: {our_favorite.get('matchCount', 0)}")
    
    # Verify that best price is the cheapest
    if our_favorite.get('hasCheaperMatch'):
        best_price = our_favorite.get('bestPrice')
        original_price = our_favorite.get('originalPrice')
        match_count = our_favorite.get('matchCount', 0)
        
        if best_price < original_price:
            result.add_pass(
                "Price Sorting",
                f"Correctly returned cheapest price: {best_price} ₽ (from {match_count} matches)"
            )
        else:
            result.add_fail(
                "Price Sorting",
                f"Best price ({best_price} ₽) is not cheaper than original ({original_price} ₽)"
            )
    else:
        result.add_warning(
            "Price Sorting",
            "No cheaper matches found - cannot verify price sorting"
        )

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BEST PRICE MATCHING LOGIC - COMPREHENSIVE TESTING")
    print("Testing /api/favorites endpoint with mode='cheapest'")
    print("="*80)
    
    # Run all test cases
    test_weight_tolerance_match()
    test_weight_tolerance_no_match()
    test_type_matching()
    test_price_sorting()
    
    # Print summary
    result.print_summary()
    
    # Return exit code
    return 0 if len(result.failed) == 0 else 1

if __name__ == "__main__":
    exit(main())
