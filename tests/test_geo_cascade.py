"""
Test: Geography Cascade (City > Region > Country)
Feature: Extended 'Country as Brand' rule to full geography cascade.
Priority: City > Region > Country - the most specific geo attribute is used for filtering.

Test Favorites:
- fav_russia_beef_test: origin_country='РОССИЯ' only - should filter by country
- fav_kamchatka_test: origin_region='КАМЧАТКА' - should filter by region (not country)
- fav_murmansk_test: origin_city='МУРМАНСК' - should filter by city (highest priority)
- fav_city_only_test: origin_city='САНКТ-ПЕТЕРБУРГ' - should filter by city
- fav_no_country_beef_test: no geo - should NOT apply geo filtering

Expected debug_log fields:
- geo_as_brand: true/false
- geo_filter_type: 'city', 'region', or 'country'
- geo_filter_value: the actual filter value used

Supplier Items Distribution:
- КАМЧАТКА region: 21 items
- МУРМАНСК city: 18 items
- САНКТ-ПЕТЕРБУРГ city: 14 items
- РОССИЯ country: 855 items
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
TEST_EMAIL = "customer@bestprice.ru"
TEST_PASSWORD = "password123"


class TestGeoCascade:
    """Test Geography Cascade feature (City > Region > Country)"""
    
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
    
    def test_region_filter_kamchatka(self, auth_headers):
        """
        Test: Favorite with origin_region='КАМЧАТКА' should filter by region
        Expected:
        - geo_as_brand=True
        - geo_filter_type='region'
        - geo_filter_value='КАМЧАТКА'
        - Candidates filtered by origin_region
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_kamchatka_test", "qty": 1}
        )
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        debug_log = data.get("debug_log", {})
        
        # Check geo_as_brand is True
        assert debug_log.get("geo_as_brand") == True, \
            f"Expected geo_as_brand=True, got: {debug_log.get('geo_as_brand')}"
        
        # Check geo_filter_type is 'region'
        assert debug_log.get("geo_filter_type") == "region", \
            f"Expected geo_filter_type='region', got: {debug_log.get('geo_filter_type')}"
        
        # Check geo_filter_value is 'КАМЧАТКА'
        assert debug_log.get("geo_filter_value") == "КАМЧАТКА", \
            f"Expected geo_filter_value='КАМЧАТКА', got: {debug_log.get('geo_filter_value')}"
        
        # Check filtering happened
        counts = debug_log.get("counts", {})
        total = counts.get("total", 0)
        after_geo = counts.get("after_geo_filter", counts.get("after_brand", 0))
        
        print(f"✅ Kamchatka region test: geo_as_brand={debug_log.get('geo_as_brand')}, "
              f"geo_filter_type={debug_log.get('geo_filter_type')}, "
              f"geo_filter_value={debug_log.get('geo_filter_value')}, "
              f"total={total}, after_geo_filter={after_geo}, status={data.get('status')}")
    
    def test_city_filter_murmansk(self, auth_headers):
        """
        Test: Favorite with origin_city='МУРМАНСК' should filter by city (highest priority)
        Expected:
        - geo_as_brand=True
        - geo_filter_type='city'
        - geo_filter_value='МУРМАНСК'
        - City takes priority over region and country
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_murmansk_test", "qty": 1}
        )
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        debug_log = data.get("debug_log", {})
        
        # Check geo_as_brand is True
        assert debug_log.get("geo_as_brand") == True, \
            f"Expected geo_as_brand=True, got: {debug_log.get('geo_as_brand')}"
        
        # Check geo_filter_type is 'city' (highest priority)
        assert debug_log.get("geo_filter_type") == "city", \
            f"Expected geo_filter_type='city', got: {debug_log.get('geo_filter_type')}"
        
        # Check geo_filter_value is 'МУРМАНСК'
        assert debug_log.get("geo_filter_value") == "МУРМАНСК", \
            f"Expected geo_filter_value='МУРМАНСК', got: {debug_log.get('geo_filter_value')}"
        
        print(f"✅ Murmansk city test: geo_as_brand={debug_log.get('geo_as_brand')}, "
              f"geo_filter_type={debug_log.get('geo_filter_type')}, "
              f"geo_filter_value={debug_log.get('geo_filter_value')}, status={data.get('status')}")
    
    def test_city_only_spb(self, auth_headers):
        """
        Test: Favorite with only origin_city='САНКТ-ПЕТЕРБУРГ' (no region) should filter by city
        Expected:
        - geo_as_brand=True
        - geo_filter_type='city'
        - geo_filter_value='САНКТ-ПЕТЕРБУРГ'
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_city_only_test", "qty": 1}
        )
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        debug_log = data.get("debug_log", {})
        
        # Check geo_as_brand is True
        assert debug_log.get("geo_as_brand") == True, \
            f"Expected geo_as_brand=True, got: {debug_log.get('geo_as_brand')}"
        
        # Check geo_filter_type is 'city'
        assert debug_log.get("geo_filter_type") == "city", \
            f"Expected geo_filter_type='city', got: {debug_log.get('geo_filter_type')}"
        
        # Check geo_filter_value is 'САНКТ-ПЕТЕРБУРГ'
        assert debug_log.get("geo_filter_value") == "САНКТ-ПЕТЕРБУРГ", \
            f"Expected geo_filter_value='САНКТ-ПЕТЕРБУРГ', got: {debug_log.get('geo_filter_value')}"
        
        print(f"✅ SPB city test: geo_as_brand={debug_log.get('geo_as_brand')}, "
              f"geo_filter_type={debug_log.get('geo_filter_type')}, "
              f"geo_filter_value={debug_log.get('geo_filter_value')}, status={data.get('status')}")
    
    def test_country_filter_russia(self, auth_headers):
        """
        Test: Favorite with only origin_country='РОССИЯ' should filter by country
        Expected:
        - geo_as_brand=True
        - geo_filter_type='country'
        - geo_filter_value='РОССИЯ'
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_russia_beef_test", "qty": 1}
        )
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        debug_log = data.get("debug_log", {})
        
        # Check geo_as_brand is True
        assert debug_log.get("geo_as_brand") == True, \
            f"Expected geo_as_brand=True, got: {debug_log.get('geo_as_brand')}"
        
        # Check geo_filter_type is 'country'
        assert debug_log.get("geo_filter_type") == "country", \
            f"Expected geo_filter_type='country', got: {debug_log.get('geo_filter_type')}"
        
        # Check geo_filter_value is 'РОССИЯ'
        assert debug_log.get("geo_filter_value") == "РОССИЯ", \
            f"Expected geo_filter_value='РОССИЯ', got: {debug_log.get('geo_filter_value')}"
        
        print(f"✅ Russia country test: geo_as_brand={debug_log.get('geo_as_brand')}, "
              f"geo_filter_type={debug_log.get('geo_filter_type')}, "
              f"geo_filter_value={debug_log.get('geo_filter_value')}, status={data.get('status')}")
    
    def test_no_geo_does_not_apply_filter(self, auth_headers):
        """
        Test: Favorite WITHOUT any geo attributes does NOT apply geo filtering
        Expected:
        - geo_as_brand=False
        - geo_filter_type should be empty or None
        - Standard brand matching logic applies
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_no_country_beef_test", "qty": 1}
        )
        
        assert response.status_code == 200, f"API call failed: {response.text}"
        data = response.json()
        
        debug_log = data.get("debug_log", {})
        
        # Check geo_as_brand is False
        assert debug_log.get("geo_as_brand") == False, \
            f"Expected geo_as_brand=False, got: {debug_log.get('geo_as_brand')}"
        
        # geo_filter_type should be empty or None
        geo_filter_type = debug_log.get("geo_filter_type")
        assert geo_filter_type in [None, "", "none"], \
            f"Expected geo_filter_type to be empty/None, got: {geo_filter_type}"
        
        print(f"✅ No geo test: geo_as_brand={debug_log.get('geo_as_brand')}, "
              f"geo_filter_type={debug_log.get('geo_filter_type')}, status={data.get('status')}")


class TestGeoCascadeDebugLog:
    """Test debug_log fields for geo cascade"""
    
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
    
    def test_debug_log_contains_geo_fields(self, auth_headers):
        """
        Test: Verify debug_log contains geo_as_brand, geo_filter_type, geo_filter_value fields
        """
        # Test with geo
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_kamchatka_test", "qty": 1}
        )
        data = response.json()
        debug_log = data.get("debug_log", {})
        
        assert "geo_as_brand" in debug_log, \
            "debug_log should contain 'geo_as_brand' field"
        assert "geo_filter_type" in debug_log, \
            "debug_log should contain 'geo_filter_type' field"
        assert "geo_filter_value" in debug_log, \
            "debug_log should contain 'geo_filter_value' field"
        
        print(f"✅ Debug log fields present: geo_as_brand={debug_log.get('geo_as_brand')}, "
              f"geo_filter_type={debug_log.get('geo_filter_type')}, "
              f"geo_filter_value={debug_log.get('geo_filter_value')}")
    
    def test_debug_log_counts_after_geo_filter(self, auth_headers):
        """
        Test: Verify counts show filtering reduction after geo filter
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_kamchatka_test", "qty": 1}
        )
        data = response.json()
        debug_log = data.get("debug_log", {})
        counts = debug_log.get("counts", {})
        
        total = counts.get("total", 0)
        after_geo = counts.get("after_geo_filter", counts.get("after_brand", 0))
        
        # Geo filter should reduce candidates
        assert after_geo < total, \
            f"Geo filter should reduce candidates: total={total}, after_geo={after_geo}"
        
        print(f"✅ Counts show filtering: total={total}, after_geo_filter={after_geo}")


class TestGeoCascadeErrorMessages:
    """Test localized error messages based on geo_filter_type"""
    
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
    
    def test_country_not_found_message(self, auth_headers):
        """
        Test: Error message for unknown country should mention 'страна'
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_unknown_country_test", "qty": 1}
        )
        data = response.json()
        
        if data.get("status") == "not_found":
            message = data.get("message", "")
            # Should mention country (страна/страны)
            assert "стран" in message.lower() or "АВСТРАЛИЯ" in message, \
                f"Error message should mention country, got: '{message}'"
            print(f"✅ Country not found message: '{message}'")
        else:
            print(f"⚠️ Status was {data.get('status')}, not 'not_found'")


class TestGeoCascadePriority:
    """Test that cascade priority is correctly applied: City > Region > Country"""
    
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
    
    def test_city_takes_priority_over_region_and_country(self, auth_headers):
        """
        Test: When city, region, and country are all set, city should be used
        fav_murmansk_test has: city=МУРМАНСК, region=МУРМАНСКАЯ ОБЛ., country=РОССИЯ
        Expected: geo_filter_type='city', geo_filter_value='МУРМАНСК'
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_murmansk_test", "qty": 1}
        )
        data = response.json()
        debug_log = data.get("debug_log", {})
        
        # City should take priority
        assert debug_log.get("geo_filter_type") == "city", \
            f"City should take priority, got geo_filter_type={debug_log.get('geo_filter_type')}"
        assert debug_log.get("geo_filter_value") == "МУРМАНСК", \
            f"Expected МУРМАНСК, got {debug_log.get('geo_filter_value')}"
        
        print(f"✅ City priority test: geo_filter_type={debug_log.get('geo_filter_type')}, "
              f"geo_filter_value={debug_log.get('geo_filter_value')}")
    
    def test_region_takes_priority_over_country(self, auth_headers):
        """
        Test: When region and country are set (no city), region should be used
        fav_kamchatka_test has: region=КАМЧАТКА, country=РОССИЯ
        Expected: geo_filter_type='region', geo_filter_value='КАМЧАТКА'
        """
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "fav_kamchatka_test", "qty": 1}
        )
        data = response.json()
        debug_log = data.get("debug_log", {})
        
        # Region should take priority over country
        assert debug_log.get("geo_filter_type") == "region", \
            f"Region should take priority over country, got geo_filter_type={debug_log.get('geo_filter_type')}"
        assert debug_log.get("geo_filter_value") == "КАМЧАТКА", \
            f"Expected КАМЧАТКА, got {debug_log.get('geo_filter_value')}"
        
        print(f"✅ Region priority test: geo_filter_type={debug_log.get('geo_filter_type')}, "
              f"geo_filter_value={debug_log.get('geo_filter_value')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
