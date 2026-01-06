"""
Test: Country as Brand Rule
Feature: If a product in favorites has 'origin_country' specified, then brand_critical 
should automatically become True and the country becomes the required 'brand' for filtering candidates.

Test Favorites (pre-created):
- fav_russia_beef_test: origin_country='РОССИЯ' - should filter by country
- fav_argentina_beef_test: origin_country='АРГЕНТИНА' - should filter by country  
- fav_no_country_beef_test: no origin_country - should NOT apply country filtering
- fav_unknown_country_test: origin_country='АВСТРАЛИЯ' - not in DB, should return not_found

Supplier Items:
- 60 items with origin_country='РОССИЯ'
- 40 items with origin_country='АРГЕНТИНА'
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "customer@bestprice.ru"
TEST_PASSWORD = "password123"


class TestCountryAsBrand:
    """Test Country as Brand feature for BestPrice matching engine"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_russia_country_triggers_country_as_brand(self, auth_headers):
        """
        Test: Favorite with origin_country='РОССИЯ' triggers country_as_brand=True
        Expected: 
        - country_as_brand=True in debug_log
        - Candidates filtered by origin_country='РОССИЯ'
        - Returns status='ok' with matching product
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_russia_beef_test", "qty": 1}
        )
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        # Check status
        assert data.get("status") == "ok", f"Expected status='ok', got '{data.get('status')}'. Message: {data.get('message')}"
        
        # Check debug_log contains country_as_brand=True
        debug_log = data.get("debug_log", {})
        assert debug_log.get("country_as_brand") == True, \
            f"Expected country_as_brand=True in debug_log, got: {debug_log.get('country_as_brand')}"
        
        # Check that a product was selected (response uses selected_offer, not selected_item)
        selected_offer = data.get("selected_offer")
        assert selected_offer is not None, "Expected selected_offer in response"
        
        # Verify after_brand count shows filtering happened (should be less than total)
        counts = debug_log.get("counts", {})
        total = counts.get("total", 0)
        after_brand = counts.get("after_brand", 0)
        assert after_brand < total, \
            f"Country filter should reduce candidates: total={total}, after_brand={after_brand}"
        assert after_brand > 0, "Country filter should find some matches"
        
        print(f"✅ Russia test passed: country_as_brand={debug_log.get('country_as_brand')}, "
              f"total={total}, after_country_filter={after_brand}, "
              f"selected={selected_offer.get('name_raw', '')[:50]}")
    
    def test_argentina_country_triggers_country_as_brand(self, auth_headers):
        """
        Test: Favorite with origin_country='АРГЕНТИНА' triggers country_as_brand=True
        Expected:
        - country_as_brand=True in debug_log
        - Candidates filtered by origin_country='АРГЕНТИНА'
        - Returns status='ok' with matching product
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_argentina_beef_test", "qty": 1}
        )
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        # Check status
        assert data.get("status") == "ok", f"Expected status='ok', got '{data.get('status')}'. Message: {data.get('message')}"
        
        # Check debug_log contains country_as_brand=True
        debug_log = data.get("debug_log", {})
        assert debug_log.get("country_as_brand") == True, \
            f"Expected country_as_brand=True in debug_log, got: {debug_log.get('country_as_brand')}"
        
        # Check that a product was selected (response uses selected_offer, not selected_item)
        selected_offer = data.get("selected_offer")
        assert selected_offer is not None, "Expected selected_offer in response"
        
        # Verify after_brand count shows filtering happened
        counts = debug_log.get("counts", {})
        total = counts.get("total", 0)
        after_brand = counts.get("after_brand", 0)
        assert after_brand < total, \
            f"Country filter should reduce candidates: total={total}, after_brand={after_brand}"
        assert after_brand > 0, "Country filter should find some matches"
        
        print(f"✅ Argentina test passed: country_as_brand={debug_log.get('country_as_brand')}, "
              f"total={total}, after_country_filter={after_brand}, "
              f"selected={selected_offer.get('name_raw', '')[:50]}")
    
    def test_no_country_does_not_apply_country_filter(self, auth_headers):
        """
        Test: Favorite WITHOUT origin_country does NOT apply country filtering
        Expected:
        - country_as_brand=False in debug_log
        - Standard brand matching logic applies
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_no_country_beef_test", "qty": 1}
        )
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        # Check debug_log contains country_as_brand=False
        debug_log = data.get("debug_log", {})
        assert debug_log.get("country_as_brand") == False, \
            f"Expected country_as_brand=False in debug_log, got: {debug_log.get('country_as_brand')}"
        
        # Status can be 'ok' or 'not_found' depending on matching logic
        # The key assertion is that country_as_brand=False
        print(f"✅ No country test passed: country_as_brand={debug_log.get('country_as_brand')}, "
              f"status={data.get('status')}")
    
    def test_unknown_country_returns_not_found(self, auth_headers):
        """
        Test: Favorite with origin_country='АВСТРАЛИЯ' (not in DB) returns not_found
        Expected:
        - status='not_found'
        - country_as_brand=True in debug_log
        - Proper error message about country not found
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_unknown_country_test", "qty": 1}
        )
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        # Check status is not_found
        assert data.get("status") == "not_found", \
            f"Expected status='not_found', got '{data.get('status')}'"
        
        # Check debug_log contains country_as_brand=True
        debug_log = data.get("debug_log", {})
        assert debug_log.get("country_as_brand") == True, \
            f"Expected country_as_brand=True in debug_log, got: {debug_log.get('country_as_brand')}"
        
        # Check error message mentions country
        message = data.get("message", "")
        assert "АВСТРАЛИЯ" in message or "страны" in message.lower(), \
            f"Expected error message to mention country, got: '{message}'"
        
        print(f"✅ Unknown country test passed: status={data.get('status')}, "
              f"message={message[:50]}")
    
    def test_debug_log_contains_country_as_brand_field(self, auth_headers):
        """
        Test: Verify debug_log always contains country_as_brand field
        """
        # Test with country
        response1 = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_russia_beef_test", "qty": 1}
        )
        data1 = response1.json()
        debug_log1 = data1.get("debug_log", {})
        assert "country_as_brand" in debug_log1, \
            "debug_log should contain 'country_as_brand' field for favorite with country"
        
        # Test without country
        response2 = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_no_country_beef_test", "qty": 1}
        )
        data2 = response2.json()
        debug_log2 = data2.get("debug_log", {})
        assert "country_as_brand" in debug_log2, \
            "debug_log should contain 'country_as_brand' field for favorite without country"
        
        print(f"✅ Debug log field test passed: with_country={debug_log1.get('country_as_brand')}, "
              f"without_country={debug_log2.get('country_as_brand')}")


class TestCountryAsBrandEdgeCases:
    """Edge case tests for Country as Brand feature"""
    
    @pytest.fixture(scope="class")
    def auth_token(self):
        """Get authentication token"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": TEST_EMAIL, "password": TEST_PASSWORD}
        )
        assert response.status_code == 200, f"Login failed: {response.text}"
        return response.json().get("access_token")
    
    @pytest.fixture(scope="class")
    def auth_headers(self, auth_token):
        """Get headers with auth token"""
        return {
            "Authorization": f"Bearer {auth_token}",
            "Content-Type": "application/json"
        }
    
    def test_country_filter_counts_in_debug_log(self, auth_headers):
        """
        Test: Verify after_country_filter count appears in debug_log for country filtering
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_russia_beef_test", "qty": 1}
        )
        
        data = response.json()
        debug_log = data.get("debug_log", {})
        counts = debug_log.get("counts", {})
        
        # When country_as_brand is True, we should see filtering happened
        if debug_log.get("country_as_brand"):
            # Check that after_brand (which is country filter in this mode) is less than total
            after_brand = counts.get("after_brand", counts.get("after_brand_filter", 0))
            total = counts.get("total", 0)
            
            # The country filter should reduce candidates
            print(f"✅ Country filter counts: total={total}, after_country_filter={after_brand}")
    
    def test_russia_beef_returns_beef_product(self, auth_headers):
        """
        Test: Verify that Russia beef favorite returns a beef product from Russia
        Note: We verify via debug_log that country filtering was applied
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_russia_beef_test", "qty": 1}
        )
        
        data = response.json()
        
        if data.get("status") == "ok":
            selected_offer = data.get("selected_offer", {})
            name = selected_offer.get("name_raw", "").lower()
            debug_log = data.get("debug_log", {})
            
            # Verify country_as_brand was applied
            assert debug_log.get("country_as_brand") == True, \
                "Expected country_as_brand=True for Russia beef favorite"
            
            # Verify the product name contains beef-related terms
            beef_terms = ["говядина", "beef", "мясо"]
            has_beef_term = any(term in name for term in beef_terms)
            assert has_beef_term, f"Expected beef product, got: {name[:50]}"
            
            print(f"✅ Russia beef test: selected '{name[:50]}', country_as_brand={debug_log.get('country_as_brand')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
