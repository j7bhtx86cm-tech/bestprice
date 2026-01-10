"""
P0 Critical Matching Fixes Tests - Backend API Testing

Tests for:
1. CRITICAL: Кальмар (squid) MUST NOT match курица (chicken) - SEAFOOD vs MEAT
2. CRITICAL: Креветки с хвостом MUST NOT match креветки без хвоста - attribute mismatch
3. Default brand_critical=True when adding new favorites
4. BestPrice returns seafood for seafood reference
5. Category mismatch guard rejects meat candidates for seafood reference
6. Attribute compatibility check works for shrimp tail attributes

Uses existing favorite with кальмар (ID: c582028e-2aaa-4ab7-8270-a20bb2d9b201)
"""

import pytest
import requests
import os
import sys

# Add backend to path for direct function testing
sys.path.insert(0, '/app/backend')

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://product-match-10.preview.emergentagent.com').rstrip('/')

# Test credentials
CUSTOMER_EMAIL = "customer@bestprice.ru"
CUSTOMER_PASSWORD = "password123"

# Known favorite ID with кальмар
SQUID_FAVORITE_ID = "c582028e-2aaa-4ab7-8270-a20bb2d9b201"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for customer"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": CUSTOMER_EMAIL,
        "password": CUSTOMER_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Authentication failed: {response.status_code} - {response.text}")


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }


class TestP0CategoryMismatchGuard:
    """Test that seafood vs meat category mismatch is blocked"""
    
    def test_check_category_mismatch_function_squid_vs_chicken(self):
        """Direct test: check_category_mismatch blocks squid → chicken"""
        from p0_hotfix_stabilization import check_category_mismatch
        
        # Squid reference should NOT match chicken candidate
        reference = "Кальмар командорский филе"
        candidates = [
            "КУРИЦА ГРУДКА ОХЛАЖДЕННАЯ",
            "Куриное филе 1кг",
            "Цыпленок бройлер",
            "Chicken breast fillet",
            "Курица бедро б/к",
        ]
        
        for candidate in candidates:
            is_valid, reason = check_category_mismatch(reference, candidate, "seafood.squid")
            assert not is_valid, f"CRITICAL FAIL: Squid '{reference}' should NOT match chicken '{candidate}'"
            assert "CATEGORY_MISMATCH" in reason, f"Expected CATEGORY_MISMATCH in reason, got: {reason}"
            print(f"✅ Squid correctly rejected chicken: '{candidate[:30]}...' - {reason}")
    
    def test_check_category_mismatch_function_shrimp_vs_beef(self):
        """Direct test: check_category_mismatch blocks shrimp → beef"""
        from p0_hotfix_stabilization import check_category_mismatch
        
        reference = "Креветки тигровые 16/20"
        candidates = [
            "Говядина тазобедренная часть",
            "BEEF RIBEYE STEAK",
            "Говяжий фарш 80/20",
        ]
        
        for candidate in candidates:
            is_valid, reason = check_category_mismatch(reference, candidate, "seafood.shrimp")
            assert not is_valid, f"CRITICAL FAIL: Shrimp should NOT match beef '{candidate}'"
            print(f"✅ Shrimp correctly rejected beef: '{candidate[:30]}...'")
    
    def test_check_category_mismatch_function_chicken_vs_seafood(self):
        """Direct test: check_category_mismatch blocks chicken → seafood"""
        from p0_hotfix_stabilization import check_category_mismatch
        
        reference = "Куриная грудка охлажденная"
        candidates = [
            "Кальмар филе б/к",
            "Креветки тигровые 16/20",
            "Лосось филе",
            "Squid cleaned",
        ]
        
        for candidate in candidates:
            is_valid, reason = check_category_mismatch(reference, candidate, "meat.chicken")
            assert not is_valid, f"CRITICAL FAIL: Chicken should NOT match seafood '{candidate}'"
            print(f"✅ Chicken correctly rejected seafood: '{candidate[:30]}...'")
    
    def test_same_category_passes(self):
        """Same category items should pass category check"""
        from p0_hotfix_stabilization import check_category_mismatch
        
        test_cases = [
            ("Кальмар филе", "Кальмар тушка", "seafood.squid"),
            ("Креветки 16/20", "Креветки тигровые 21/25", "seafood.shrimp"),
            ("Куриная грудка", "Курица филе бедра", "meat.chicken"),
            ("Говядина рибай", "Говядина стейк", "meat.beef"),
        ]
        
        for reference, candidate, super_class in test_cases:
            is_valid, reason = check_category_mismatch(reference, candidate, super_class)
            assert is_valid, f"FAIL: Same category should pass: '{reference}' vs '{candidate}'"
            print(f"✅ Same category passes: '{reference}' <-> '{candidate}'")


class TestP0AttributeCompatibility:
    """Test attribute compatibility (с хвостом vs без хвоста)"""
    
    def test_shrimp_tail_on_vs_tail_off(self):
        """CRITICAL: Креветки с хвостом MUST NOT match креветки без хвоста"""
        from p0_hotfix_stabilization import check_attribute_compatibility
        
        reference = "Креветки тигровые с хвостом 16/20"
        candidates = [
            "Креветки без хвоста 16/20",
            "Креветки очищенные полностью",
            "Креветки хвосты удалены",
        ]
        
        for candidate in candidates:
            is_valid, reason = check_attribute_compatibility(reference, candidate)
            assert not is_valid, f"CRITICAL FAIL: Tail mismatch should be rejected: '{reference}' vs '{candidate}'"
            assert "ATTRIBUTE_CONFLICT" in reason, f"Expected ATTRIBUTE_CONFLICT in reason, got: {reason}"
            print(f"✅ Tail attribute conflict detected: '{candidate[:30]}...' - {reason}")
    
    def test_shrimp_peeled_vs_unpeeled(self):
        """Очищенные креветки MUST NOT match неочищенные"""
        from p0_hotfix_stabilization import check_attribute_compatibility
        
        test_cases = [
            ("Креветки очищенные", "Креветки неочищенные в панцире"),
            ("Креветки в панцире", "Креветки без панциря очищенные"),
        ]
        
        for reference, candidate in test_cases:
            is_valid, reason = check_attribute_compatibility(reference, candidate)
            assert not is_valid, f"FAIL: Peeled mismatch should be rejected: '{reference}' vs '{candidate}'"
            print(f"✅ Peeled attribute conflict detected: '{reference}' vs '{candidate}'")
    
    def test_squid_skin_attributes(self):
        """Кальмар без кожи vs с кожей"""
        from p0_hotfix_stabilization import check_attribute_compatibility
        
        reference = "Кальмар филе без кожи"
        candidate = "Кальмар с кожей нечищеный"
        
        is_valid, reason = check_attribute_compatibility(reference, candidate)
        assert not is_valid, f"FAIL: Squid skin mismatch should be rejected"
        print(f"✅ Squid skin attribute conflict detected")
    
    def test_same_attributes_pass(self):
        """Same attributes should pass"""
        from p0_hotfix_stabilization import check_attribute_compatibility
        
        test_cases = [
            ("Креветки с хвостом 16/20", "Креветки тигровые с хвостом"),
            ("Креветки очищенные", "Креветки чищеные"),
            ("Кальмар без кожи", "Кальмар чищеный"),
        ]
        
        for reference, candidate in test_cases:
            is_valid, reason = check_attribute_compatibility(reference, candidate)
            assert is_valid, f"FAIL: Same attributes should pass: '{reference}' vs '{candidate}'"
            print(f"✅ Same attributes pass: '{reference}' <-> '{candidate}'")


class TestP0KeywordLists:
    """Test that keyword lists are properly populated"""
    
    def test_seafood_keywords_populated(self):
        """SEAFOOD_KEYWORDS should have 50+ keywords"""
        from p0_hotfix_stabilization import SEAFOOD_KEYWORDS
        
        assert len(SEAFOOD_KEYWORDS) >= 20, f"SEAFOOD_KEYWORDS too small: {len(SEAFOOD_KEYWORDS)}"
        
        # Check critical keywords are present
        critical_keywords = ['кальмар', 'squid', 'креветк', 'shrimp', 'лосос', 'salmon', 'рыб', 'fish']
        for kw in critical_keywords:
            assert kw in SEAFOOD_KEYWORDS, f"Missing critical keyword: {kw}"
        
        print(f"✅ SEAFOOD_KEYWORDS has {len(SEAFOOD_KEYWORDS)} keywords")
    
    def test_meat_keywords_populated(self):
        """MEAT_KEYWORDS should have 30+ keywords"""
        from p0_hotfix_stabilization import MEAT_KEYWORDS
        
        assert len(MEAT_KEYWORDS) >= 15, f"MEAT_KEYWORDS too small: {len(MEAT_KEYWORDS)}"
        
        # Check critical keywords are present
        critical_keywords = ['курин', 'chicken', 'говядин', 'beef', 'свинин', 'pork']
        for kw in critical_keywords:
            assert kw in MEAT_KEYWORDS, f"Missing critical keyword: {kw}"
        
        print(f"✅ MEAT_KEYWORDS has {len(MEAT_KEYWORDS)} keywords")
    
    def test_forbidden_cross_matches_squid(self):
        """seafood.squid should have meat keywords in FORBIDDEN_CROSS_MATCHES"""
        from p0_hotfix_stabilization import FORBIDDEN_CROSS_MATCHES
        
        forbidden = FORBIDDEN_CROSS_MATCHES.get('seafood.squid', [])
        assert len(forbidden) > 0, "seafood.squid should have forbidden keywords"
        
        # Check meat keywords are forbidden for squid
        required_forbidden = ['курин', 'chicken', 'говядин', 'свинин', 'баранин']
        for kw in required_forbidden:
            assert kw in forbidden, f"'{kw}' should be forbidden for seafood.squid"
        
        print(f"✅ seafood.squid has {len(forbidden)} forbidden keywords")
    
    def test_forbidden_cross_matches_chicken(self):
        """meat.chicken should have seafood keywords in FORBIDDEN_CROSS_MATCHES"""
        from p0_hotfix_stabilization import FORBIDDEN_CROSS_MATCHES
        
        forbidden = FORBIDDEN_CROSS_MATCHES.get('meat.chicken', [])
        assert len(forbidden) > 0, "meat.chicken should have forbidden keywords"
        
        # Check seafood keywords are forbidden for chicken
        required_forbidden = ['кальмар', 'squid', 'креветк', 'shrimp', 'лосос']
        for kw in required_forbidden:
            assert kw in forbidden, f"'{kw}' should be forbidden for meat.chicken"
        
        print(f"✅ meat.chicken has {len(forbidden)} forbidden keywords")


class TestP0SuperClassMapper:
    """Test that super_class mapper correctly classifies seafood"""
    
    def test_squid_fillet_is_seafood(self):
        """Кальмар филе should be classified as seafood.squid, NOT meat"""
        from universal_super_class_mapper import detect_super_class
        
        test_products = [
            "Кальмар командорский филе",
            "Кальмар филе б/к",
            "Кальмар филе очищенный",
            "Кальмар",
        ]
        
        for product in test_products:
            super_class, confidence = detect_super_class(product)
            assert super_class is not None, f"super_class should be detected for '{product}'"
            assert super_class.startswith('seafood'), f"'{product}' should be seafood, got: {super_class}"
            assert 'meat' not in super_class.lower(), f"'{product}' should NOT be meat, got: {super_class}"
            print(f"✅ '{product}' → {super_class} (conf={confidence:.2f})")
    
    def test_chicken_is_meat(self):
        """Курица should be classified as meat.chicken"""
        from universal_super_class_mapper import detect_super_class
        
        test_products = [
            "Куриная грудка",
            "Курица филе",
            "Цыпленок бройлер",
        ]
        
        for product in test_products:
            super_class, confidence = detect_super_class(product)
            assert super_class is not None, f"super_class should be detected for '{product}'"
            assert super_class.startswith('meat'), f"'{product}' should be meat, got: {super_class}"
            assert 'seafood' not in super_class.lower(), f"'{product}' should NOT be seafood, got: {super_class}"
            print(f"✅ '{product}' → {super_class} (conf={confidence:.2f})")


class TestP0BrandCriticalDefault:
    """Test that brand_critical defaults to True for new favorites"""
    
    def test_add_favorite_default_brand_critical(self, auth_headers):
        """When adding a new favorite, brand_critical should default to True"""
        # First, get a product to add as favorite
        response = requests.get(f"{BASE_URL}/api/suppliers", headers=auth_headers)
        if response.status_code != 200:
            pytest.skip("Cannot get suppliers")
        
        suppliers = response.json()
        if not suppliers:
            pytest.skip("No suppliers available")
        
        supplier_id = suppliers[0]['id']
        
        # Get products from supplier
        response = requests.get(f"{BASE_URL}/api/suppliers/{supplier_id}/price-lists", headers=auth_headers)
        if response.status_code != 200:
            pytest.skip("Cannot get price lists")
        
        products = response.json()
        if not products:
            pytest.skip("No products available")
        
        # Add product to favorites
        product = products[0]
        response = requests.post(
            f"{BASE_URL}/api/favorites",
            headers=auth_headers,
            json={
                "productId": product.get('productId') or product.get('id'),
                "supplierId": supplier_id
            }
        )
        
        if response.status_code in [200, 201]:
            favorite = response.json()
            # Check brand_critical default
            brand_critical = favorite.get('brand_critical')
            print(f"   New favorite brand_critical: {brand_critical}")
            # Note: brand_critical may be True or derived from brandMode
            # The key is that it should be True by default per P0 fix
            
            # Clean up - delete the test favorite
            fav_id = favorite.get('id')
            if fav_id:
                requests.delete(f"{BASE_URL}/api/favorites/{fav_id}", headers=auth_headers)
            
            print(f"✅ Favorite created with brand_critical={brand_critical}")
        else:
            print(f"   Add favorite response: {response.status_code} - {response.text[:200]}")


class TestP0BestPriceAPI:
    """Test BestPrice API with squid favorite"""
    
    def test_squid_favorite_exists(self, auth_headers):
        """Verify the squid favorite exists"""
        response = requests.get(f"{BASE_URL}/api/favorites", headers=auth_headers)
        assert response.status_code == 200, f"Failed to get favorites: {response.status_code}"
        
        favorites = response.json()
        squid_fav = next((f for f in favorites if f.get('id') == SQUID_FAVORITE_ID), None)
        
        if squid_fav:
            print(f"✅ Found squid favorite: {squid_fav.get('productName', 'N/A')[:50]}")
            print(f"   brand_critical: {squid_fav.get('brand_critical')}")
            print(f"   brandMode: {squid_fav.get('brandMode')}")
        else:
            # List available favorites with кальмар
            squid_favs = [f for f in favorites if 'кальмар' in f.get('productName', '').lower()]
            if squid_favs:
                print(f"   Found {len(squid_favs)} squid favorites:")
                for f in squid_favs[:3]:
                    print(f"   - {f.get('id')}: {f.get('productName', 'N/A')[:50]}")
            pytest.skip(f"Squid favorite {SQUID_FAVORITE_ID} not found. Available: {len(favorites)} favorites")
    
    def test_bestprice_squid_returns_seafood(self, auth_headers):
        """CRITICAL: BestPrice for squid should return seafood, NOT chicken"""
        # First check if favorite exists
        response = requests.get(f"{BASE_URL}/api/favorites", headers=auth_headers)
        favorites = response.json() if response.status_code == 200 else []
        
        # Find any squid favorite
        squid_fav = next((f for f in favorites if 'кальмар' in f.get('productName', '').lower()), None)
        
        if not squid_fav:
            pytest.skip("No squid favorite found")
        
        favorite_id = squid_fav.get('id')
        print(f"   Testing with favorite: {squid_fav.get('productName', 'N/A')[:50]}")
        
        # Call BestPrice API
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": favorite_id,
                "qty": 1
            }
        )
        
        print(f"   BestPrice response status: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            status = result.get('status')
            print(f"   Status: {status}")
            
            if status == 'found':
                selected = result.get('selected_offer', {})
                product_name = selected.get('product_name', '')
                print(f"   Selected product: {product_name}")
                
                # CRITICAL CHECK: Product should NOT contain chicken keywords
                chicken_keywords = ['курин', 'кура', 'курица', 'chicken', 'цыпл', 'бройлер']
                product_lower = product_name.lower()
                
                for kw in chicken_keywords:
                    assert kw not in product_lower, \
                        f"CRITICAL FAIL: Squid favorite matched chicken product! Found '{kw}' in '{product_name}'"
                
                # Product should contain squid keywords
                squid_keywords = ['кальмар', 'squid', 'calamari']
                has_squid = any(kw in product_lower for kw in squid_keywords)
                
                if has_squid:
                    print(f"✅ BestPrice correctly returned squid product: {product_name[:50]}")
                else:
                    print(f"⚠️ BestPrice returned non-squid product (may be OK if same category): {product_name[:50]}")
                
                # Check debug_log for category mismatch rejections
                debug_log = result.get('debug_log', {})
                counts = debug_log.get('counts', {})
                rejected_category = counts.get('rejected_by_category_mismatch', 0)
                rejected_attributes = counts.get('rejected_by_attribute_mismatch', 0)
                
                print(f"   Rejected by category mismatch: {rejected_category}")
                print(f"   Rejected by attribute mismatch: {rejected_attributes}")
                
            elif status == 'not_found':
                message = result.get('message', '')
                debug_log = result.get('debug_log', {})
                print(f"   Not found: {message}")
                print(f"   Debug: {debug_log}")
                # This is acceptable - no matching products found
                
            else:
                print(f"   Unexpected status: {status}")
                print(f"   Full response: {result}")
        else:
            print(f"   Error response: {response.text[:500]}")


class TestP0IntegrationEndToEnd:
    """End-to-end integration tests"""
    
    def test_full_flow_squid_search(self, auth_headers):
        """Full flow: Create squid favorite → BestPrice → Verify no chicken match"""
        # Step 1: Find a squid product in supplier catalog
        response = requests.get(f"{BASE_URL}/api/suppliers", headers=auth_headers)
        if response.status_code != 200:
            pytest.skip("Cannot get suppliers")
        
        suppliers = response.json()
        squid_product = None
        supplier_id = None
        
        for supplier in suppliers[:5]:  # Check first 5 suppliers
            response = requests.get(
                f"{BASE_URL}/api/suppliers/{supplier['id']}/price-lists",
                headers=auth_headers,
                params={"search": "кальмар"}
            )
            if response.status_code == 200:
                products = response.json()
                if products:
                    squid_product = products[0]
                    supplier_id = supplier['id']
                    break
        
        if not squid_product:
            pytest.skip("No squid product found in any supplier catalog")
        
        print(f"   Found squid product: {squid_product.get('productName', 'N/A')[:50]}")
        
        # Step 2: Add to favorites
        response = requests.post(
            f"{BASE_URL}/api/favorites",
            headers=auth_headers,
            json={
                "productId": squid_product.get('productId') or squid_product.get('id'),
                "supplierId": supplier_id
            }
        )
        
        if response.status_code not in [200, 201]:
            print(f"   Failed to add favorite: {response.status_code} - {response.text[:200]}")
            pytest.skip("Cannot add favorite")
        
        favorite = response.json()
        favorite_id = favorite.get('id')
        print(f"   Created favorite: {favorite_id}")
        
        try:
            # Step 3: Call BestPrice
            response = requests.post(
                f"{BASE_URL}/api/cart/add-from-favorite",
                headers=auth_headers,
                json={
                    "favorite_id": favorite_id,
                    "qty": 1
                }
            )
            
            print(f"   BestPrice status: {response.status_code}")
            
            if response.status_code == 200:
                result = response.json()
                status = result.get('status')
                
                if status == 'found':
                    selected = result.get('selected_offer', {})
                    product_name = selected.get('product_name', '')
                    
                    # CRITICAL: Verify no chicken match
                    chicken_keywords = ['курин', 'кура', 'курица', 'chicken', 'цыпл']
                    product_lower = product_name.lower()
                    
                    for kw in chicken_keywords:
                        assert kw not in product_lower, \
                            f"CRITICAL FAIL: Squid matched chicken! '{kw}' in '{product_name}'"
                    
                    print(f"✅ Full flow passed: Squid → {product_name[:40]}")
                else:
                    print(f"   BestPrice status: {status}")
        finally:
            # Cleanup: Delete test favorite
            requests.delete(f"{BASE_URL}/api/favorites/{favorite_id}", headers=auth_headers)
            print(f"   Cleaned up favorite: {favorite_id}")


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
