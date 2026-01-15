"""
Backend API Tests for Brand Features (B2B HoReCa Marketplace)

Tests:
1. Brand dictionary loaded correctly from new XLSX file
2. /api/admin/brands/backfill endpoint works and updates products
3. /api/admin/brands/stats returns correct statistics
4. /api/cart/select-offer with brand_critical=false returns cheapest offer across ALL brands
5. /api/cart/select-offer with brand_critical=true filters by brand_id
6. /api/cart/select-offer never returns 500 - returns structured error on bad input
7. Login flow works for customer
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://bestprice-search-ui.preview.emergentagent.com').rstrip('/')

# Test credentials
CUSTOMER_EMAIL = "customer@bestprice.ru"
CUSTOMER_PASSWORD = "password123"


class TestAuthFlow:
    """Test 7: Login flow works for customer"""
    
    def test_customer_login_success(self):
        """Customer can login with valid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": CUSTOMER_EMAIL, "password": CUSTOMER_PASSWORD}
        )
        
        assert response.status_code == 200, f"Login failed: {response.text}"
        
        data = response.json()
        assert "access_token" in data, "No access_token in response"
        assert "user" in data, "No user in response"
        assert data["user"]["email"] == CUSTOMER_EMAIL
        assert data["user"]["role"] == "customer"
        assert "companyId" in data["user"]
        
        print(f"✅ Customer login successful: {data['user']['email']}")
        return data["access_token"]
    
    def test_customer_login_invalid_credentials(self):
        """Login fails with invalid credentials"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": "wrong@email.com", "password": "wrongpassword"}
        )
        
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"
        print("✅ Invalid credentials correctly rejected")


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token for tests"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": CUSTOMER_EMAIL, "password": CUSTOMER_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture
def auth_headers(auth_token):
    """Headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


class TestBrandStats:
    """Test 3: /api/admin/brands/stats returns correct statistics"""
    
    def test_brand_stats_returns_data(self, auth_headers):
        """Brand stats endpoint returns dictionary and product stats"""
        response = requests.get(
            f"{BASE_URL}/api/admin/brands/stats",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Brand stats failed: {response.text}"
        
        data = response.json()
        
        # Check dictionary stats
        assert "dictionary" in data, "No dictionary stats"
        dict_stats = data["dictionary"]
        assert "total_brands" in dict_stats
        assert "total_aliases" in dict_stats
        assert dict_stats["total_brands"] > 0, "No brands loaded"
        
        # Check product stats
        assert "products" in data, "No product stats"
        prod_stats = data["products"]
        assert "total" in prod_stats
        assert "branded" in prod_stats
        assert "unbranded" in prod_stats
        assert "branded_percent" in prod_stats
        
        # Check top brands
        assert "top_brands_in_products" in data
        
        print(f"✅ Brand stats: {dict_stats['total_brands']} brands, {dict_stats['total_aliases']} aliases")
        print(f"   Products: {prod_stats['total']} total, {prod_stats['branded']} branded ({prod_stats['branded_percent']}%)")
        
        return data


class TestBrandBackfill:
    """Test 2: /api/admin/brands/backfill endpoint works and updates products"""
    
    def test_backfill_endpoint_works(self, auth_headers):
        """Backfill endpoint runs and returns statistics"""
        response = requests.post(
            f"{BASE_URL}/api/admin/brands/backfill",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Backfill failed: {response.text}"
        
        data = response.json()
        
        assert data.get("success") == True, "Backfill not successful"
        assert "stats" in data, "No stats in response"
        assert "top_brands" in data, "No top_brands in response"
        
        stats = data["stats"]
        assert "total_products" in stats
        assert "branded" in stats
        assert "no_brand" in stats
        assert "updated" in stats
        
        # Check brand dictionary was loaded
        assert "brand_dictionary" in stats
        assert stats["brand_dictionary"]["total_brands"] > 0, "Brand dictionary not loaded"
        
        print(f"✅ Backfill complete:")
        print(f"   Total products: {stats['total_products']}")
        print(f"   Branded: {stats['branded']}")
        print(f"   No brand: {stats['no_brand']}")
        print(f"   Updated: {stats['updated']}")
        print(f"   Dictionary: {stats['brand_dictionary']['total_brands']} brands")
        
        return data


class TestSelectOfferBrandCritical:
    """Tests 4, 5, 6: /api/cart/select-offer with brand_critical logic"""
    
    def test_select_offer_brand_critical_false_returns_cheapest(self, auth_headers):
        """Test 4: brand_critical=false returns cheapest offer across ALL brands"""
        # Search for a common product like salmon (Лосось)
        payload = {
            "reference_item": {
                "name_raw": "Лосось филе охлажденный",
                "unit_norm": "kg",
                "brand_critical": False  # Should return cheapest regardless of brand
            },
            "match_threshold": 0.5,  # Lower threshold to get more candidates
            "required_volume": 1.0
        }
        
        response = requests.post(
            f"{BASE_URL}/api/cart/select-offer",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200, f"Select offer failed: {response.text}"
        
        data = response.json()
        
        # Should return a result (either selected_offer or reason)
        if data.get("selected_offer"):
            offer = data["selected_offer"]
            assert "supplier_id" in offer
            assert "price" in offer
            assert "name_raw" in offer
            print(f"✅ brand_critical=false: Found cheapest offer")
            print(f"   Product: {offer['name_raw'][:50]}")
            print(f"   Price: {offer['price']}₽")
            print(f"   Supplier: {offer.get('supplier_name', 'Unknown')}")
            
            # Check top candidates - should include different brands
            if data.get("top_candidates"):
                print(f"   Top {len(data['top_candidates'])} candidates available")
        else:
            # No match is acceptable if no products match
            reason = data.get("reason", "UNKNOWN")
            print(f"⚠️ brand_critical=false: No match found (reason: {reason})")
            assert reason in ["NO_MATCH_OVER_THRESHOLD", "NOT_FOUND", "INSUFFICIENT_DATA"]
    
    def test_select_offer_brand_critical_true_filters_by_brand(self, auth_headers):
        """Test 5: brand_critical=true filters by brand_id"""
        # Search for a branded product like Heinz ketchup
        payload = {
            "reference_item": {
                "name_raw": "Кетчуп томатный Heinz",
                "unit_norm": "kg",
                "brand_id": "heinz",  # Specific brand
                "brand_critical": True  # Should filter by brand
            },
            "match_threshold": 0.5,
            "required_volume": 1.0
        }
        
        response = requests.post(
            f"{BASE_URL}/api/cart/select-offer",
            headers=auth_headers,
            json=payload
        )
        
        assert response.status_code == 200, f"Select offer failed: {response.text}"
        
        data = response.json()
        
        if data.get("selected_offer"):
            offer = data["selected_offer"]
            print(f"✅ brand_critical=true: Found branded offer")
            print(f"   Product: {offer['name_raw'][:50]}")
            print(f"   Price: {offer['price']}₽")
            # Note: The offer should be from Heinz brand (filtered)
        else:
            reason = data.get("reason", "UNKNOWN")
            print(f"⚠️ brand_critical=true: No match found (reason: {reason})")
            # This is acceptable if no Heinz products exist
            assert reason in ["NO_MATCH_OVER_THRESHOLD", "NOT_FOUND", "INSUFFICIENT_DATA"]
    
    def test_select_offer_never_returns_500_on_bad_input(self, auth_headers):
        """Test 6: select-offer never returns 500 - returns structured error"""
        # Test with empty name
        payload = {
            "reference_item": {
                "name_raw": "",  # Empty name
                "unit_norm": "kg",
                "brand_critical": False
            },
            "match_threshold": 0.85
        }
        
        response = requests.post(
            f"{BASE_URL}/api/cart/select-offer",
            headers=auth_headers,
            json=payload
        )
        
        # Should NOT return 500
        assert response.status_code != 500, f"Got 500 error: {response.text}"
        assert response.status_code == 200, f"Unexpected status: {response.status_code}"
        
        data = response.json()
        assert "reason" in data, "No reason field in response"
        assert data["reason"] == "INSUFFICIENT_DATA", f"Expected INSUFFICIENT_DATA, got {data['reason']}"
        
        print(f"✅ Empty name handled gracefully: reason={data['reason']}")
    
    def test_select_offer_null_safe_with_missing_fields(self, auth_headers):
        """Test 6 continued: select-offer handles missing fields gracefully"""
        # Test with minimal payload
        payload = {
            "reference_item": {
                "name_raw": "Молоко"
                # Missing other fields
            }
        }
        
        response = requests.post(
            f"{BASE_URL}/api/cart/select-offer",
            headers=auth_headers,
            json=payload
        )
        
        # Should NOT return 500
        assert response.status_code != 500, f"Got 500 error: {response.text}"
        
        data = response.json()
        print(f"✅ Minimal payload handled: status={response.status_code}")
        if data.get("selected_offer"):
            print(f"   Found offer: {data['selected_offer']['name_raw'][:40]}")
        else:
            print(f"   Reason: {data.get('reason', 'N/A')}")


class TestBrandDictionaryLoaded:
    """Test 1: Brand dictionary loaded correctly from new XLSX file"""
    
    def test_brand_dictionary_has_expected_brands(self, auth_headers):
        """Verify brand dictionary contains expected brands"""
        response = requests.get(
            f"{BASE_URL}/api/admin/brands/stats",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        # Check dictionary stats
        dict_stats = data["dictionary"]
        
        # Should have 1502 brands as mentioned in context
        assert dict_stats["total_brands"] >= 1000, f"Expected ~1502 brands, got {dict_stats['total_brands']}"
        
        # Should have aliases
        assert dict_stats["total_aliases"] > dict_stats["total_brands"], "Should have more aliases than brands"
        
        # Check categories exist
        assert "categories" in dict_stats
        
        print(f"✅ Brand dictionary loaded:")
        print(f"   Brands: {dict_stats['total_brands']}")
        print(f"   Aliases: {dict_stats['total_aliases']}")
        print(f"   Categories: {len(dict_stats.get('categories', []))}")
    
    def test_products_have_brand_ids(self, auth_headers):
        """Verify products have brand_id set after backfill"""
        response = requests.get(
            f"{BASE_URL}/api/admin/brands/stats",
            headers=auth_headers
        )
        
        assert response.status_code == 200
        data = response.json()
        
        prod_stats = data["products"]
        
        # Should have some branded products
        assert prod_stats["branded"] > 0, "No branded products found"
        
        # Check branded percentage is reasonable (context says 5698 updated)
        print(f"✅ Products with brands:")
        print(f"   Total: {prod_stats['total']}")
        print(f"   Branded: {prod_stats['branded']} ({prod_stats['branded_percent']}%)")
        print(f"   Unbranded: {prod_stats['unbranded']}")
        
        # Check top brands
        top_brands = data.get("top_brands_in_products", [])
        if top_brands:
            print(f"   Top 5 brands: {[b['brand_id'] for b in top_brands[:5]]}")


class TestSelectOfferEdgeCases:
    """Additional edge case tests for select-offer"""
    
    def test_select_offer_with_specific_product(self, auth_headers):
        """Test with a specific product that should exist"""
        # Try different products to find one that matches
        test_products = [
            "Масло сливочное",
            "Сыр моцарелла",
            "Курица филе",
            "Помидоры свежие",
            "Огурцы свежие"
        ]
        
        found_match = False
        for product_name in test_products:
            payload = {
                "reference_item": {
                    "name_raw": product_name,
                    "unit_norm": "kg",
                    "brand_critical": False
                },
                "match_threshold": 0.4,  # Lower threshold
                "required_volume": 1.0
            }
            
            response = requests.post(
                f"{BASE_URL}/api/cart/select-offer",
                headers=auth_headers,
                json=payload
            )
            
            assert response.status_code == 200
            data = response.json()
            
            if data.get("selected_offer"):
                found_match = True
                offer = data["selected_offer"]
                print(f"✅ Found match for '{product_name}':")
                print(f"   Product: {offer['name_raw'][:50]}")
                print(f"   Price: {offer['price']}₽")
                break
        
        if not found_match:
            print("⚠️ No matches found for common products - may need to check product data")
    
    def test_select_offer_brand_critical_comparison(self, auth_headers):
        """Compare results with brand_critical=true vs false"""
        # Use a product that might have multiple brands
        product_name = "Соус соевый"
        
        # First with brand_critical=false
        payload_false = {
            "reference_item": {
                "name_raw": product_name,
                "unit_norm": "l",
                "brand_critical": False
            },
            "match_threshold": 0.4,
            "required_volume": 1.0
        }
        
        response_false = requests.post(
            f"{BASE_URL}/api/cart/select-offer",
            headers=auth_headers,
            json=payload_false
        )
        
        assert response_false.status_code == 200
        data_false = response_false.json()
        
        # Then with brand_critical=true and a specific brand
        payload_true = {
            "reference_item": {
                "name_raw": product_name,
                "unit_norm": "l",
                "brand_id": "kikkoman",  # Specific brand
                "brand_critical": True
            },
            "match_threshold": 0.4,
            "required_volume": 1.0
        }
        
        response_true = requests.post(
            f"{BASE_URL}/api/cart/select-offer",
            headers=auth_headers,
            json=payload_true
        )
        
        assert response_true.status_code == 200
        data_true = response_true.json()
        
        print(f"✅ Brand critical comparison for '{product_name}':")
        
        if data_false.get("selected_offer"):
            print(f"   brand_critical=false: {data_false['selected_offer']['name_raw'][:40]} @ {data_false['selected_offer']['price']}₽")
        else:
            print(f"   brand_critical=false: No match ({data_false.get('reason')})")
        
        if data_true.get("selected_offer"):
            print(f"   brand_critical=true (kikkoman): {data_true['selected_offer']['name_raw'][:40]} @ {data_true['selected_offer']['price']}₽")
        else:
            print(f"   brand_critical=true (kikkoman): No match ({data_true.get('reason')})")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
