#!/usr/bin/env python3
"""
Backend API Testing for BestPrice - Photo Scenarios + Regressions
Tests 5 photo scenarios + 3 regression tests for best price matching

Test User: customer@bestprice.ru / password123

Critical Fixes Applied:
- Fix #1: Volume/Weight Normalization (unit=шт with pack_value)
- Fix #2: Pack Range Relaxed (±20% → ±50%)
- Fix #3: Preserve Candidate Unit
- Fix #4: Pasta Shape Guards
- Fix #5: Threshold 60% (brand_critical=OFF)
"""

import requests
import json
from typing import Dict, Optional, List

# Backend URL from environment
BACKEND_URL = "https://smartbuy-39.preview.emergentagent.com/api"

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

def create_favorite(token: str, product_name: str, unit: str, brand_critical: bool = False) -> Optional[str]:
    """Create a favorite and return its ID"""
    headers = get_headers(token)
    
    try:
        # First, search for the product in catalog
        suppliers_response = requests.get(f"{BACKEND_URL}/suppliers", headers=headers, timeout=10)
        
        if suppliers_response.status_code != 200:
            print(f"   ⚠️ Failed to get suppliers: {suppliers_response.status_code}")
            return None
        
        suppliers = suppliers_response.json()
        
        # Search for product across all suppliers
        for supplier in suppliers:
            supplier_id = supplier.get("id")
            products_response = requests.get(
                f"{BACKEND_URL}/suppliers/{supplier_id}/price-lists",
                headers=headers,
                timeout=10
            )
            
            if products_response.status_code == 200:
                products = products_response.json()
                
                # Find matching product
                for product in products:
                    product_name_lower = product.get("productName", "").lower()
                    search_terms = product_name.lower().split()
                    
                    # Check if all search terms are in product name
                    if all(term in product_name_lower for term in search_terms):
                        # Found matching product, create favorite
                        favorite_data = {
                            "productId": product.get("productId"),
                            "supplierId": supplier_id,
                            "reference_name": product.get("productName"),
                            "unit_norm": unit,
                            "brand_critical": brand_critical
                        }
                        
                        fav_response = requests.post(
                            f"{BACKEND_URL}/favorites",
                            headers=headers,
                            json=favorite_data,
                            timeout=10
                        )
                        
                        if fav_response.status_code == 200:
                            fav_data = fav_response.json()
                            return fav_data.get("id")
                        else:
                            print(f"   ⚠️ Failed to create favorite: {fav_response.status_code} - {fav_response.text}")
                            return None
        
        print(f"   ⚠️ Product not found in catalog: {product_name}")
        return None
    
    except Exception as e:
        print(f"   ⚠️ Error creating favorite: {str(e)}")
        return None

def test_from_favorite(token: str, favorite_id: str, qty: float = 1.0) -> Optional[Dict]:
    """Test adding from favorite to cart"""
    headers = get_headers(token)
    
    try:
        response = requests.post(
            f"{BACKEND_URL}/cart/add-from-favorite",
            headers=headers,
            json={"favorite_id": favorite_id, "qty": qty},
            timeout=15
        )
        
        if response.status_code == 200:
            return response.json()
        else:
            print(f"   ⚠️ Failed to add from favorite: {response.status_code} - {response.text}")
            return None
    
    except Exception as e:
        print(f"   ⚠️ Error testing favorite: {str(e)}")
        return None

def test_photo_1_kimchi_volume_normalization():
    """Test 1: Kimchi 1.5л vs 1.8л - Volume Normalization
    
    Expected: Find 1.8л if cheaper per liter
    Verify: Calculates 410/1.5 vs другие/их_объем
    """
    print("\n" + "="*80)
    print("TEST 1: Kimchi 1.5л vs 1.8л - Volume Normalization")
    print("Expected: Find 1.8л if cheaper per liter (410₽/1.5л = 273₽/л)")
    print("="*80)
    
    # Login
    auth_data = login(TEST_USER["email"], TEST_USER["password"])
    if not auth_data:
        result.add_fail("Test 1 Login", "Login failed")
        return
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Create favorite for Kimchi Tamaki 1.5л
    print("\n[1] Creating favorite: Kimchi Tamaki 1.5л (410₽)...")
    favorite_id = create_favorite(token, "Kimchi Tamaki", "л", brand_critical=False)
    
    if not favorite_id:
        result.add_fail("Test 1: Kimchi", "Failed to create favorite")
        return
    
    print(f"   ✓ Created favorite ID: {favorite_id}")
    
    # Test adding from favorite
    print("\n[2] Testing best price search...")
    response_data = test_from_favorite(token, favorite_id, qty=1.0)
    
    if not response_data:
        result.add_fail("Test 1: Kimchi", "Failed to get response")
        return
    
    if response_data.get("status") == "ok" and response_data.get("selected_offer"):
        offer = response_data["selected_offer"]
        price = offer.get("price")
        name = offer.get("name_raw", "")
        volume = offer.get("pack_size", 0)
        price_per_liter = price / volume if volume > 0 else 0
        
        print(f"   ✓ Selected: {name}")
        print(f"   ✓ Price: {price} ₽")
        print(f"   ✓ Volume: {volume} л")
        print(f"   ✓ Price per liter: {price_per_liter:.2f} ₽/л")
        
        # Check if volume normalization is working
        if volume > 1.5:  # Found larger volume
            result.add_pass("Test 1: Kimchi Volume", f"✅ Found larger volume: {volume}л at {price_per_liter:.2f}₽/л")
        else:
            result.add_warning("Test 1: Kimchi Volume", f"⚠️ Selected same volume: {volume}л")
        
        # Verify price per liter calculation
        expected_price_per_liter = 410 / 1.5  # 273.33₽/л
        if price_per_liter < expected_price_per_liter:
            result.add_pass("Test 1: Kimchi Price", f"✅ Found cheaper per liter: {price_per_liter:.2f}₽/л < {expected_price_per_liter:.2f}₽/л")
        else:
            result.add_warning("Test 1: Kimchi Price", f"⚠️ Not cheaper per liter: {price_per_liter:.2f}₽/л >= {expected_price_per_liter:.2f}₽/л")
    else:
        status = response_data.get("status", "unknown")
        message = response_data.get("message", "No message")
        result.add_fail("Test 1: Kimchi", f"No offer selected. Status: {status}, Message: {message}")

def test_photo_2_olive_oil_pack_range():
    """Test 2: Olive Oil 250ml - Pack Range ±50%
    
    Expected: Find all 250ml variants
    Verify: Pack filter accepts 250ml candidates
    """
    print("\n" + "="*80)
    print("TEST 2: Olive Oil 250ml - Pack Range ±50%")
    print("Expected: Find all 250ml variants (125ml - 375ml range)")
    print("="*80)
    
    # Login
    auth_data = login(TEST_USER["email"], TEST_USER["password"])
    if not auth_data:
        result.add_fail("Test 2 Login", "Login failed")
        return
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Create favorite for Olive Oil 250ml
    print("\n[1] Creating favorite: Olive Oil 250ml...")
    favorite_id = create_favorite(token, "масло оливковое", "мл", brand_critical=False)
    
    if not favorite_id:
        result.add_fail("Test 2: Olive Oil", "Failed to create favorite")
        return
    
    print(f"   ✓ Created favorite ID: {favorite_id}")
    
    # Test adding from favorite
    print("\n[2] Testing pack range filter...")
    response_data = test_from_favorite(token, favorite_id, qty=1.0)
    
    if not response_data:
        result.add_fail("Test 2: Olive Oil", "Failed to get response")
        return
    
    if response_data.get("status") == "ok" and response_data.get("selected_offer"):
        offer = response_data["selected_offer"]
        price = offer.get("price")
        name = offer.get("name_raw", "")
        pack_size = offer.get("pack_size", 0)
        
        print(f"   ✓ Selected: {name}")
        print(f"   ✓ Price: {price} ₽")
        print(f"   ✓ Pack size: {pack_size} мл")
        
        # Check if pack range is working (±50% of 250ml = 125ml - 375ml)
        if 125 <= pack_size <= 375:
            result.add_pass("Test 2: Olive Oil Pack", f"✅ Pack size within ±50% range: {pack_size}мл (125-375мл)")
        else:
            result.add_fail("Test 2: Olive Oil Pack", f"❌ Pack size outside ±50% range: {pack_size}мл (expected 125-375мл)")
        
        # Check top candidates
        if "top_candidates" in response_data:
            candidates = response_data["top_candidates"]
            print(f"   ✓ Top candidates: {len(candidates)}")
            
            # Check if all candidates are within pack range
            out_of_range = 0
            for candidate in candidates[:5]:
                cand_pack = candidate.get("pack_size", 0)
                if cand_pack < 125 or cand_pack > 375:
                    out_of_range += 1
            
            if out_of_range == 0:
                result.add_pass("Test 2: Pack Filter", f"✅ All top candidates within ±50% range")
            else:
                result.add_fail("Test 2: Pack Filter", f"❌ {out_of_range} candidates outside ±50% range")
    else:
        status = response_data.get("status", "unknown")
        message = response_data.get("message", "No message")
        result.add_fail("Test 2: Olive Oil", f"No offer selected. Status: {status}, Message: {message}")

def test_photo_3_honey_pack_range_1kg():
    """Test 3: Honey 700g - Pack Range Allows 1kg
    
    Expected: Find 1kg honey at 237₽ (cheaper per kg)
    Verify: 1kg passes pack filter (700g * 1.5 = 1050g > 1000g)
    """
    print("\n" + "="*80)
    print("TEST 3: Honey 700g - Pack Range Allows 1kg")
    print("Expected: Find 1kg honey (cheaper per kg than 700g at 249₽)")
    print("="*80)
    
    # Login
    auth_data = login(TEST_USER["email"], TEST_USER["password"])
    if not auth_data:
        result.add_fail("Test 3 Login", "Login failed")
        return
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Create favorite for Smart Chef мед 700г
    print("\n[1] Creating favorite: Smart Chef мед 700г (249₽)...")
    favorite_id = create_favorite(token, "мед Smart Chef", "г", brand_critical=False)
    
    if not favorite_id:
        result.add_fail("Test 3: Honey", "Failed to create favorite")
        return
    
    print(f"   ✓ Created favorite ID: {favorite_id}")
    
    # Test adding from favorite
    print("\n[2] Testing pack range allows 1kg...")
    response_data = test_from_favorite(token, favorite_id, qty=1.0)
    
    if not response_data:
        result.add_fail("Test 3: Honey", "Failed to get response")
        return
    
    if response_data.get("status") == "ok" and response_data.get("selected_offer"):
        offer = response_data["selected_offer"]
        price = offer.get("price")
        name = offer.get("name_raw", "")
        pack_size = offer.get("pack_size", 0)
        price_per_kg = (price / pack_size) * 1000 if pack_size > 0 else 0
        
        print(f"   ✓ Selected: {name}")
        print(f"   ✓ Price: {price} ₽")
        print(f"   ✓ Pack size: {pack_size} г")
        print(f"   ✓ Price per kg: {price_per_kg:.2f} ₽/кг")
        
        # Check if 1kg is allowed (700g * 1.5 = 1050g > 1000g)
        if pack_size >= 1000:
            result.add_pass("Test 3: Honey Pack", f"✅ Found 1kg honey: {pack_size}г (pack range allows it)")
        else:
            result.add_warning("Test 3: Honey Pack", f"⚠️ Selected smaller pack: {pack_size}г (expected 1kg)")
        
        # Check if cheaper per kg
        expected_price_per_kg = (249 / 700) * 1000  # 355.71₽/кг
        if price_per_kg < expected_price_per_kg:
            result.add_pass("Test 3: Honey Price", f"✅ Found cheaper per kg: {price_per_kg:.2f}₽/кг < {expected_price_per_kg:.2f}₽/кг")
        else:
            result.add_warning("Test 3: Honey Price", f"⚠️ Not cheaper per kg: {price_per_kg:.2f}₽/кг >= {expected_price_per_kg:.2f}₽/кг")
    else:
        status = response_data.get("status", "unknown")
        message = response_data.get("message", "No message")
        result.add_fail("Test 3: Honey", f"No offer selected. Status: {status}, Message: {message}")

def test_photo_4_flour_missing_pricelists():
    """Test 4: Мука предпортовая 10кг - Graceful Handling
    
    Expected: "Товар недоступен у поставщиков" (not crash)
    Verify: Null-safe error message
    """
    print("\n" + "="*80)
    print("TEST 4: Мука предпортовая 10кг - Graceful Handling")
    print("Expected: Graceful error message (not crash)")
    print("="*80)
    
    # Login
    auth_data = login(TEST_USER["email"], TEST_USER["password"])
    if not auth_data:
        result.add_fail("Test 4 Login", "Login failed")
        return
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Try to create favorite for Мука предпортовая
    print("\n[1] Creating favorite: Мука предпортовая 10кг...")
    favorite_id = create_favorite(token, "мука предпортовая", "кг", brand_critical=False)
    
    if not favorite_id:
        result.add_pass("Test 4: Flour Missing", "✅ Product not found in catalog (expected)")
        return
    
    print(f"   ✓ Created favorite ID: {favorite_id}")
    
    # Test adding from favorite
    print("\n[2] Testing graceful error handling...")
    response_data = test_from_favorite(token, favorite_id, qty=1.0)
    
    if not response_data:
        result.add_fail("Test 4: Flour", "Failed to get response (should return graceful error)")
        return
    
    status = response_data.get("status", "unknown")
    message = response_data.get("message", "")
    
    print(f"   ✓ Status: {status}")
    print(f"   ✓ Message: {message}")
    
    # Check for graceful error handling
    if status == "not_found" or "недоступен" in message.lower() or "not found" in message.lower():
        result.add_pass("Test 4: Flour Graceful", f"✅ Graceful error message: {message}")
    elif status == "ok":
        result.add_warning("Test 4: Flour Graceful", f"⚠️ Found product (unexpected): {message}")
    else:
        result.add_fail("Test 4: Flour Graceful", f"❌ Unexpected status: {status}, message: {message}")

def test_photo_5_pasta_shape_guards():
    """Test 5: Pasta пенне vs спагетти - Shape Guards
    
    Expected: Guard prevents спагетти match
    Verify: check_guard_conflict returns True
    """
    print("\n" + "="*80)
    print("TEST 5: Pasta пенне vs спагетти - Shape Guards")
    print("Expected: Пенне should NOT match спагетти")
    print("="*80)
    
    # Login
    auth_data = login(TEST_USER["email"], TEST_USER["password"])
    if not auth_data:
        result.add_fail("Test 5 Login", "Login failed")
        return
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Create favorite for Pasta пенне
    print("\n[1] Creating favorite: Pasta пенне...")
    favorite_id = create_favorite(token, "паста пенне", "г", brand_critical=False)
    
    if not favorite_id:
        result.add_fail("Test 5: Pasta", "Failed to create favorite")
        return
    
    print(f"   ✓ Created favorite ID: {favorite_id}")
    
    # Test adding from favorite
    print("\n[2] Testing pasta shape guards...")
    response_data = test_from_favorite(token, favorite_id, qty=1.0)
    
    if not response_data:
        result.add_fail("Test 5: Pasta", "Failed to get response")
        return
    
    if response_data.get("status") == "ok" and response_data.get("selected_offer"):
        offer = response_data["selected_offer"]
        name = offer.get("name_raw", "").lower()
        
        print(f"   ✓ Selected: {offer.get('name_raw', '')}")
        print(f"   ✓ Price: {offer.get('price')} ₽")
        
        # Check if спагетти is in the name (should NOT be)
        if "спагетти" in name or "spaghetti" in name:
            result.add_fail("Test 5: Pasta Guards", f"❌ Matched спагетти (guard failed): {offer.get('name_raw', '')}")
        elif "пенне" in name or "penne" in name:
            result.add_pass("Test 5: Pasta Guards", f"✅ Correctly matched пенне (guard working)")
        else:
            result.add_warning("Test 5: Pasta Guards", f"⚠️ Matched other pasta type: {offer.get('name_raw', '')}")
        
        # Check top candidates for спагетти
        if "top_candidates" in response_data:
            candidates = response_data["top_candidates"]
            spaghetti_count = 0
            for candidate in candidates[:10]:
                cand_name = candidate.get("name_raw", "").lower()
                if "спагетти" in cand_name or "spaghetti" in cand_name:
                    spaghetti_count += 1
            
            if spaghetti_count == 0:
                result.add_pass("Test 5: Pasta Filter", f"✅ No спагетти in top candidates (guard working)")
            else:
                result.add_fail("Test 5: Pasta Filter", f"❌ Found {spaghetti_count} спагетти in top candidates (guard failed)")
    else:
        status = response_data.get("status", "unknown")
        message = response_data.get("message", "No message")
        result.add_fail("Test 5: Pasta", f"No offer selected. Status: {status}, Message: {message}")

def test_regression_6_heinz_brand_off():
    """Test 6: Heinz 800g (OFF) - Brand Exclusion
    
    Expected: 83₽ Царский (not Heinz 185₽)
    Verify: Brand token exclusion works
    """
    print("\n" + "="*80)
    print("TEST 6 (REGRESSION): Heinz 800g (brand_critical=OFF)")
    print("Expected: Find Царский 83₽ (NOT Heinz 185₽)")
    print("="*80)
    
    # Login
    auth_data = login(TEST_USER["email"], TEST_USER["password"])
    if not auth_data:
        result.add_fail("Test 6 Login", "Login failed")
        return
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Create favorite for Heinz кетчуп 800г with brand_critical=OFF
    print("\n[1] Creating favorite: Heinz кетчуп 800г (brand_critical=OFF)...")
    favorite_id = create_favorite(token, "Heinz кетчуп 800", "г", brand_critical=False)
    
    if not favorite_id:
        result.add_fail("Test 6: Heinz OFF", "Failed to create favorite")
        return
    
    print(f"   ✓ Created favorite ID: {favorite_id}")
    
    # Test adding from favorite
    print("\n[2] Testing brand exclusion...")
    response_data = test_from_favorite(token, favorite_id, qty=1.0)
    
    if not response_data:
        result.add_fail("Test 6: Heinz OFF", "Failed to get response")
        return
    
    if response_data.get("status") == "ok" and response_data.get("selected_offer"):
        offer = response_data["selected_offer"]
        price = offer.get("price")
        name = offer.get("name_raw", "").lower()
        
        print(f"   ✓ Selected: {offer.get('name_raw', '')}")
        print(f"   ✓ Price: {price} ₽")
        
        # Check if Царский is selected (cheaper)
        if "царский" in name:
            result.add_pass("Test 6: Heinz OFF Brand", f"✅ Found Царский (brand exclusion working)")
        elif "heinz" in name:
            result.add_fail("Test 6: Heinz OFF Brand", f"❌ Selected Heinz (brand exclusion failed)")
        else:
            result.add_warning("Test 6: Heinz OFF Brand", f"⚠️ Selected other brand: {offer.get('name_raw', '')}")
        
        # Check price
        if price < 100:
            result.add_pass("Test 6: Heinz OFF Price", f"✅ Found cheap option: {price}₽ (expected ~83₽)")
        elif price > 180:
            result.add_fail("Test 6: Heinz OFF Price", f"❌ Selected expensive option: {price}₽ (expected ~83₽)")
        else:
            result.add_warning("Test 6: Heinz OFF Price", f"⚠️ Price: {price}₽ (expected ~83₽)")
    else:
        status = response_data.get("status", "unknown")
        message = response_data.get("message", "No message")
        result.add_fail("Test 6: Heinz OFF", f"No offer selected. Status: {status}, Message: {message}")

def test_regression_7_mirin_threshold():
    """Test 7: Мирин Duncan (OFF) - Threshold 60%
    
    Expected: 1941₽ Duncan (not 2253₽ ДУНКАН)
    Verify: Threshold 60% allows
    """
    print("\n" + "="*80)
    print("TEST 7 (REGRESSION): Мирин Duncan (brand_critical=OFF)")
    print("Expected: Find Duncan 1941₽ (NOT ДУНКАН 2253₽)")
    print("="*80)
    
    # Login
    auth_data = login(TEST_USER["email"], TEST_USER["password"])
    if not auth_data:
        result.add_fail("Test 7 Login", "Login failed")
        return
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Create favorite for Мирин Duncan
    print("\n[1] Creating favorite: Мирин Duncan (brand_critical=OFF)...")
    favorite_id = create_favorite(token, "мирин Duncan", "мл", brand_critical=False)
    
    if not favorite_id:
        result.add_fail("Test 7: Mirin", "Failed to create favorite")
        return
    
    print(f"   ✓ Created favorite ID: {favorite_id}")
    
    # Test adding from favorite
    print("\n[2] Testing threshold 60%...")
    response_data = test_from_favorite(token, favorite_id, qty=1.0)
    
    if not response_data:
        result.add_fail("Test 7: Mirin", "Failed to get response")
        return
    
    if response_data.get("status") == "ok" and response_data.get("selected_offer"):
        offer = response_data["selected_offer"]
        price = offer.get("price")
        name = offer.get("name_raw", "")
        score = offer.get("score", 0)
        
        print(f"   ✓ Selected: {name}")
        print(f"   ✓ Price: {price} ₽")
        print(f"   ✓ Score: {score}")
        
        # Check if Duncan is selected (cheaper)
        if "duncan" in name.lower():
            result.add_pass("Test 7: Mirin Brand", f"✅ Found Duncan (threshold 60% working)")
        else:
            result.add_warning("Test 7: Mirin Brand", f"⚠️ Selected other brand: {name}")
        
        # Check price
        if 1900 <= price <= 2000:
            result.add_pass("Test 7: Mirin Price", f"✅ Found Duncan price: {price}₽ (expected ~1941₽)")
        elif price > 2200:
            result.add_fail("Test 7: Mirin Price", f"❌ Selected expensive option: {price}₽ (expected ~1941₽)")
        else:
            result.add_warning("Test 7: Mirin Price", f"⚠️ Price: {price}₽ (expected ~1941₽)")
        
        # Check score threshold
        if score >= 0.60:
            result.add_pass("Test 7: Mirin Threshold", f"✅ Score {score} >= 0.60 (threshold working)")
        else:
            result.add_fail("Test 7: Mirin Threshold", f"❌ Score {score} < 0.60 (threshold too high)")
    else:
        status = response_data.get("status", "unknown")
        message = response_data.get("message", "No message")
        result.add_fail("Test 7: Mirin", f"No offer selected. Status: {status}, Message: {message}")

def test_regression_8_noodles_vs_flour():
    """Test 8: Лапша vs Мука - Guard Rules
    
    Expected: Guard prevents мука match
    Verify: Лапша ≠ мука conflict detected
    """
    print("\n" + "="*80)
    print("TEST 8 (REGRESSION): Лапша vs Мука - Guard Rules")
    print("Expected: Лапша should NOT match мука")
    print("="*80)
    
    # Login
    auth_data = login(TEST_USER["email"], TEST_USER["password"])
    if not auth_data:
        result.add_fail("Test 8 Login", "Login failed")
        return
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Create favorite for Лапша
    print("\n[1] Creating favorite: Лапша...")
    favorite_id = create_favorite(token, "лапша", "г", brand_critical=False)
    
    if not favorite_id:
        result.add_fail("Test 8: Noodles", "Failed to create favorite")
        return
    
    print(f"   ✓ Created favorite ID: {favorite_id}")
    
    # Test adding from favorite
    print("\n[2] Testing guard rules...")
    response_data = test_from_favorite(token, favorite_id, qty=1.0)
    
    if not response_data:
        result.add_fail("Test 8: Noodles", "Failed to get response")
        return
    
    if response_data.get("status") == "ok" and response_data.get("selected_offer"):
        offer = response_data["selected_offer"]
        name = offer.get("name_raw", "").lower()
        
        print(f"   ✓ Selected: {offer.get('name_raw', '')}")
        print(f"   ✓ Price: {offer.get('price')} ₽")
        
        # Check if мука is in the name (should NOT be)
        if "мука" in name or "flour" in name:
            result.add_fail("Test 8: Noodles Guards", f"❌ Matched мука (guard failed): {offer.get('name_raw', '')}")
        elif "лапша" in name or "noodle" in name:
            result.add_pass("Test 8: Noodles Guards", f"✅ Correctly matched лапша (guard working)")
        else:
            result.add_warning("Test 8: Noodles Guards", f"⚠️ Matched other product: {offer.get('name_raw', '')}")
        
        # Check top candidates for мука
        if "top_candidates" in response_data:
            candidates = response_data["top_candidates"]
            flour_count = 0
            for candidate in candidates[:10]:
                cand_name = candidate.get("name_raw", "").lower()
                if "мука" in cand_name or "flour" in cand_name:
                    flour_count += 1
            
            if flour_count == 0:
                result.add_pass("Test 8: Noodles Filter", f"✅ No мука in top candidates (guard working)")
            else:
                result.add_fail("Test 8: Noodles Filter", f"❌ Found {flour_count} мука in top candidates (guard failed)")
    else:
        status = response_data.get("status", "unknown")
        message = response_data.get("message", "No message")
        result.add_fail("Test 8: Noodles", f"No offer selected. Status: {status}, Message: {message}")

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BACKEND API TESTING - PHOTO SCENARIOS + REGRESSIONS")
    print("Testing 5 photo scenarios + 3 regression tests")
    print("="*80)
    
    # Photo Scenarios
    test_photo_1_kimchi_volume_normalization()
    test_photo_2_olive_oil_pack_range()
    test_photo_3_honey_pack_range_1kg()
    test_photo_4_flour_missing_pricelists()
    test_photo_5_pasta_shape_guards()
    
    # Regression Tests
    test_regression_6_heinz_brand_off()
    test_regression_7_mirin_threshold()
    test_regression_8_noodles_vs_flour()
    
    # Print summary
    result.print_summary()

if __name__ == "__main__":
    main()
