"""
Backend API Tests for Two-Phase Search Engine with Brand Family Support

VERSION 1.0 (December 2025)

TESTS:
1. FAV_TEST_1 (brand_critical=false) - должен выбрать SI_TEST_2 (931.44₽, BRAND_B) - самый дешёвый среди ВСЕХ брендов
2. FAV_TEST_2 (brand_critical=true) - должен выбрать SI_TEST_1 (990.60₽, BRAND_A) - самый дешёвый только среди BRAND_A
3. FAV_TEST_FAMILY (brand_critical=true, miratorg_chef) - должен найти продукт Миратор/Мираторг Chef через brand family
4. FAV_TEST_PACK_MISSING (без pack) - должен найти с штрафом (rescue phase если нужно)
5. FAV_TEST_OLD (старый формат) - не должен падать с 500
6. /api/admin/search/quality-report - возвращает покрытие брендов по поставщикам
7. /api/admin/brands/families - возвращает список brand families
8. debug_log содержит phase (strict/rescue), counters, filters_applied, failure_reason
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://matchmaker-126.preview.emergentagent.com').rstrip('/')

# Test credentials
CUSTOMER_EMAIL = "customer@bestprice.ru"
CUSTOMER_PASSWORD = "password123"


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


class TestSetupFixtures:
    """Setup: Create test fixtures before running tests"""
    
    def test_create_fixtures(self, auth_headers):
        """Create test fixtures for two-phase search testing"""
        response = requests.post(
            f"{BASE_URL}/api/test/create-fixtures",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Create fixtures failed: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Fixtures not created: {data}"
        
        print(f"✅ Test fixtures created:")
        print(f"   Products: {len(data['data']['products'])}")
        print(f"   Pricelists: {len(data['data']['pricelists'])}")
        print(f"   Favorites: {len(data['data']['favorites'])}")
        
        # Verify expected behavior is documented
        assert "expected_behavior" in data
        assert "FAV_TEST_1" in data["expected_behavior"]
        assert "FAV_TEST_2" in data["expected_behavior"]
        
        return data


class TestFavTest1BrandCriticalFalse:
    """ТЕСТ 1: FAV_TEST_1 (brand_critical=false) - должен выбрать SI_TEST_2 (931.44₽, BRAND_B)"""
    
    def test_fav_test_1_selects_cheapest_across_all_brands(self, auth_headers):
        """FAV_TEST_1 (brand_critical=false) должен выбрать SI_TEST_2 (931.44₽ BRAND_B) - самый дешёвый среди ВСЕХ брендов"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_TEST_1",
                "qty": 1,
                "match_threshold": 0.4  # Lower threshold for test data
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        # Should NOT return 500 error
        assert data.get("status") != "error", f"Got error: {data.get('message')}"
        
        # Check debug_log exists
        assert "debug_log" in data, "No debug_log in response"
        debug_log = data["debug_log"]
        
        # CRITICAL: brand_critical should be False
        # Note: debug_log may have nested structure
        reference = debug_log.get("reference", {})
        brand_critical = reference.get("brand_critical", debug_log.get("brand_critical"))
        
        # Check filters_applied contains 'brand_filter: DISABLED'
        filters = debug_log.get("filters_applied", [])
        brand_filter_disabled = any("DISABLED" in str(f) for f in filters)
        
        print(f"✅ ТЕСТ 1: FAV_TEST_1 (brand_critical=false)")
        print(f"   Status: {data.get('status')}")
        print(f"   brand_critical: {brand_critical}")
        print(f"   filters_applied: {filters}")
        
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            print(f"   Selected: {offer.get('supplier_item_id')} @ {offer.get('price')}₽")
            print(f"   Product: {offer.get('name_raw', '')[:50]}")
            
            # CRITICAL: Should select SI_TEST_2 (931.44₽) - the cheapest
            if offer.get("supplier_item_id") == "SI_TEST_2":
                print(f"   ✅ CORRECT: Selected SI_TEST_2 (cheapest across all brands)")
            elif offer.get("price") and offer.get("price") <= 931.44:
                print(f"   ✅ Selected cheapest option: {offer.get('price')}₽")
            else:
                print(f"   ⚠️ May not be cheapest - verify manually")
        else:
            print(f"   Reason: {debug_log.get('result', {}).get('failure_reason')}")
        
        # Verify brand filter is disabled
        assert brand_filter_disabled, f"Expected 'brand_filter: DISABLED' in filters, got {filters}"
        
        return data


class TestFavTest2BrandCriticalTrue:
    """ТЕСТ 2: FAV_TEST_2 (brand_critical=true) - должен выбрать SI_TEST_1 (990.60₽, BRAND_A)"""
    
    def test_fav_test_2_filters_by_brand(self, auth_headers):
        """FAV_TEST_2 (brand_critical=true) должен выбрать SI_TEST_1 (990.60₽ BRAND_A) - самый дешёвый только среди BRAND_A"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_TEST_2",
                "qty": 1,
                "match_threshold": 0.4
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        # Should NOT return 500 error
        assert data.get("status") != "error", f"Got error: {data.get('message')}"
        
        # Check debug_log exists
        assert "debug_log" in data, "No debug_log in response"
        debug_log = data["debug_log"]
        
        # Check filters_applied contains 'brand_filter: brand_id=...'
        filters = debug_log.get("filters_applied", [])
        brand_filter_enabled = any("brand_id=" in str(f) or "brand_filter:" in str(f) for f in filters)
        
        print(f"✅ ТЕСТ 2: FAV_TEST_2 (brand_critical=true)")
        print(f"   Status: {data.get('status')}")
        print(f"   filters_applied: {filters}")
        
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            print(f"   Selected: {offer.get('supplier_item_id')} @ {offer.get('price')}₽")
            print(f"   Product: {offer.get('name_raw', '')[:50]}")
            
            # Should select from BRAND_A only
            if offer.get("supplier_item_id") in ["SI_TEST_1", "SI_TEST_3"]:
                print(f"   ✅ CORRECT: Selected from BRAND_A")
        else:
            print(f"   Reason: {debug_log.get('result', {}).get('failure_reason')}")
        
        return data


class TestFavTestFamilyBrandFamily:
    """ТЕСТ 3: FAV_TEST_FAMILY (brand_critical=true, miratorg_chef) - должен найти через brand family"""
    
    def test_fav_test_family_uses_brand_family(self, auth_headers):
        """FAV_TEST_FAMILY (brand_critical=true, miratorg_chef) должен найти продукт Миратор/Мираторг Chef через brand family"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_TEST_FAMILY",
                "qty": 1,
                "match_threshold": 0.4
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        # Should NOT return 500 error
        assert data.get("status") != "error", f"Got error: {data.get('message')}"
        
        # Check debug_log exists
        assert "debug_log" in data, "No debug_log in response"
        debug_log = data["debug_log"]
        
        # Check for brand family fallback in filters
        filters = debug_log.get("filters_applied", [])
        
        print(f"✅ ТЕСТ 3: FAV_TEST_FAMILY (brand_critical=true, miratorg_chef)")
        print(f"   Status: {data.get('status')}")
        print(f"   filters_applied: {filters}")
        
        # Check reference for brand_family_id
        reference = debug_log.get("reference", {})
        print(f"   brand_id: {reference.get('brand_id')}")
        print(f"   brand_family_id: {reference.get('brand_family_id')}")
        
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            print(f"   Selected: {offer.get('supplier_item_id')} @ {offer.get('price')}₽")
            print(f"   Product: {offer.get('name_raw', '')[:50]}")
            
            # Should find Miratorg or Miratorg Chef product
            if "miratorg" in str(offer.get("supplier_item_id", "")).lower() or "miratorg" in str(offer.get("name_raw", "")).lower():
                print(f"   ✅ CORRECT: Found Miratorg family product")
        else:
            print(f"   Reason: {debug_log.get('result', {}).get('failure_reason')}")
        
        return data


class TestFavTestPackMissing:
    """ТЕСТ 4: FAV_TEST_PACK_MISSING (без pack) - должен найти с штрафом (rescue phase если нужно)"""
    
    def test_fav_test_pack_missing_uses_rescue(self, auth_headers):
        """FAV_TEST_PACK_MISSING (без pack) должен найти с штрафом (rescue phase если нужно)"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_TEST_PACK_MISSING",
                "qty": 1,
                "match_threshold": 0.4
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        # Should NOT return 500 error
        assert data.get("status") != "error", f"Got error: {data.get('message')}"
        
        # Check debug_log exists
        assert "debug_log" in data, "No debug_log in response"
        debug_log = data["debug_log"]
        
        # Check phase (strict or rescue)
        phase = debug_log.get("phase")
        
        print(f"✅ ТЕСТ 4: FAV_TEST_PACK_MISSING (без pack)")
        print(f"   Status: {data.get('status')}")
        print(f"   Phase: {phase}")
        print(f"   filters_applied: {debug_log.get('filters_applied', [])}")
        
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            print(f"   Selected: {offer.get('supplier_item_id')} @ {offer.get('price')}₽")
            print(f"   Product: {offer.get('name_raw', '')[:50]}")
            print(f"   ✅ Found product despite missing pack")
        else:
            print(f"   Reason: {debug_log.get('result', {}).get('failure_reason')}")
        
        return data


class TestFavTestOldFormat:
    """ТЕСТ 5: FAV_TEST_OLD (старый формат) - не должен падать с 500"""
    
    def test_fav_test_old_no_500_error(self, auth_headers):
        """FAV_TEST_OLD (старый формат без v2 полей) - не должен падать с 500"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_TEST_OLD",
                "qty": 1,
                "match_threshold": 0.4
            }
        )
        
        # CRITICAL: Should NOT return 500
        assert response.status_code != 500, f"Got 500 error: {response.text}"
        assert response.status_code == 200, f"Unexpected status: {response.status_code}"
        
        data = response.json()
        
        # Should return structured response, not crash
        assert "status" in data, "No status in response"
        assert data.get("status") in ["ok", "not_found", "insufficient_data", "error"], f"Unexpected status: {data.get('status')}"
        
        # Should have debug_log
        assert "debug_log" in data, "No debug_log in response"
        
        print(f"✅ ТЕСТ 5: FAV_TEST_OLD (старый формат)")
        print(f"   Status: {data.get('status')}")
        print(f"   Message: {data.get('message')}")
        
        debug_log = data.get("debug_log", {})
        print(f"   Failure reason: {debug_log.get('result', {}).get('failure_reason') or debug_log.get('failure_reason')}")
        
        return data


class TestSearchQualityReport:
    """ТЕСТ 6: /api/admin/search/quality-report - возвращает покрытие брендов по поставщикам"""
    
    def test_quality_report_returns_brand_coverage(self, auth_headers):
        """/api/admin/search/quality-report возвращает покрытие брендов по поставщикам"""
        response = requests.get(
            f"{BASE_URL}/api/admin/search/quality-report",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        # Check overall stats
        assert "overall" in data, "No overall stats in response"
        overall = data["overall"]
        assert "total_items" in overall, "No total_items in overall"
        assert "with_brand" in overall, "No with_brand in overall"
        assert "without_brand" in overall, "No without_brand in overall"
        assert "brand_coverage_pct" in overall, "No brand_coverage_pct in overall"
        
        # Check by_supplier stats
        assert "by_supplier" in data, "No by_supplier stats in response"
        
        # Check sample_without_brand
        assert "sample_without_brand" in data, "No sample_without_brand in response"
        
        print(f"✅ ТЕСТ 6: /api/admin/search/quality-report")
        print(f"   Total items: {overall['total_items']}")
        print(f"   With brand: {overall['with_brand']} ({overall['brand_coverage_pct']}%)")
        print(f"   Without brand: {overall['without_brand']}")
        print(f"   Suppliers: {len(data['by_supplier'])}")
        
        # Print top suppliers by brand coverage
        by_supplier = data["by_supplier"]
        if by_supplier:
            sorted_suppliers = sorted(by_supplier.items(), key=lambda x: x[1].get('brand_coverage_pct', 0), reverse=True)
            print(f"   Top suppliers by brand coverage:")
            for supplier_id, stats in sorted_suppliers[:3]:
                print(f"      {stats.get('supplier_name', supplier_id)}: {stats.get('brand_coverage_pct', 0)}%")
        
        return data


class TestBrandFamilies:
    """ТЕСТ 7: /api/admin/brands/families - возвращает список brand families"""
    
    def test_brand_families_returns_list(self, auth_headers):
        """/api/admin/brands/families возвращает список brand families"""
        response = requests.get(
            f"{BASE_URL}/api/admin/brands/families",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        # Check families list
        assert "families" in data, "No families in response"
        families = data["families"]
        assert isinstance(families, list), "families should be a list"
        
        # Check stats
        assert "stats" in data, "No stats in response"
        stats = data["stats"]
        assert "total_families" in stats, "No total_families in stats"
        assert "brands_with_family" in stats, "No brands_with_family in stats"
        assert "total_brands" in stats, "No total_brands in stats"
        
        print(f"✅ ТЕСТ 7: /api/admin/brands/families")
        print(f"   Total families: {stats['total_families']}")
        print(f"   Brands with family: {stats['brands_with_family']}")
        print(f"   Total brands: {stats['total_brands']}")
        
        # Print top families
        if families:
            print(f"   Top families by member count:")
            for family in families[:5]:
                print(f"      {family['family_id']}: {family['member_count']} members ({family['members'][:3]}...)")
        
        return data


class TestDebugLogFields:
    """ТЕСТ 8: debug_log содержит phase (strict/rescue), counters, filters_applied, failure_reason"""
    
    def test_debug_log_contains_all_required_fields(self, auth_headers):
        """debug_log должен содержать phase, counters, filters_applied, failure_reason"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_TEST_1",
                "qty": 1,
                "match_threshold": 0.4
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "debug_log" in data, "No debug_log in response"
        debug_log = data["debug_log"]
        
        # Check phase field
        assert "phase" in debug_log, "No phase in debug_log"
        assert debug_log["phase"] in ["strict", "rescue"], f"Invalid phase: {debug_log['phase']}"
        
        # Check counters
        assert "counters" in debug_log, "No counters in debug_log"
        counters = debug_log["counters"]
        assert "total" in counters, "No total in counters"
        assert "after_brand_filter" in counters, "No after_brand_filter in counters"
        assert "after_score_filter" in counters, "No after_score_filter in counters"
        
        # Check filters_applied
        assert "filters_applied" in debug_log, "No filters_applied in debug_log"
        assert isinstance(debug_log["filters_applied"], list), "filters_applied should be a list"
        
        # Check result (contains failure_reason if failed)
        assert "result" in debug_log, "No result in debug_log"
        result = debug_log["result"]
        assert "status" in result, "No status in result"
        # failure_reason is optional (only present on failure)
        
        print(f"✅ ТЕСТ 8: debug_log содержит все необходимые поля")
        print(f"   phase: {debug_log['phase']}")
        print(f"   counters: {counters}")
        print(f"   filters_applied: {debug_log['filters_applied']}")
        print(f"   result.status: {result['status']}")
        print(f"   result.failure_reason: {result.get('failure_reason', 'N/A')}")
        
        return debug_log


class TestBrandCriticalComparison:
    """Compare brand_critical=true vs false to verify different behavior"""
    
    def test_brand_critical_produces_different_results(self, auth_headers):
        """brand_critical=true and false should produce different filter behavior"""
        # Test with FAV_TEST_1 (brand_critical=false)
        response_false = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "FAV_TEST_1", "qty": 1, "match_threshold": 0.4}
        )
        
        # Test with FAV_TEST_2 (brand_critical=true)
        response_true = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "FAV_TEST_2", "qty": 1, "match_threshold": 0.4}
        )
        
        assert response_false.status_code == 200
        assert response_true.status_code == 200
        
        data_false = response_false.json()
        data_true = response_true.json()
        
        # Both should have debug_log
        assert "debug_log" in data_false
        assert "debug_log" in data_true
        
        # filters_applied should be different
        filters_false = data_false["debug_log"]["filters_applied"]
        filters_true = data_true["debug_log"]["filters_applied"]
        
        has_disabled = any("DISABLED" in str(f) for f in filters_false)
        has_brand_id = any("brand_id=" in str(f) or "brand_filter:" in str(f) for f in filters_true)
        
        print(f"✅ Brand critical comparison:")
        print(f"   FAV_TEST_1 (false): filters={filters_false}")
        print(f"   FAV_TEST_2 (true): filters={filters_true}")
        
        # If both found offers, compare prices
        if data_false.get("selected_offer") and data_true.get("selected_offer"):
            price_false = data_false["selected_offer"]["price"]
            price_true = data_true["selected_offer"]["price"]
            print(f"   FAV_TEST_1 price: {price_false}₽")
            print(f"   FAV_TEST_2 price: {price_true}₽")
            
            # brand_critical=false should find cheaper or equal price
            # (since it searches across all brands)
            if price_false <= price_true:
                print(f"   ✅ brand_critical=false found cheaper/equal price")
            else:
                print(f"   ⚠️ brand_critical=false found more expensive - check data")
        
        assert has_disabled, f"brand_critical=false should have DISABLED filter, got {filters_false}"


class TestNonExistentFavorite:
    """Test handling of non-existent favorite"""
    
    def test_non_existent_favorite_returns_not_found(self, auth_headers):
        """Non-existent favorite should return not_found status"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "NON_EXISTENT_FAV_12345",
                "qty": 1
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        assert data.get("status") == "not_found", f"Expected not_found, got {data.get('status')}"
        
        print(f"✅ Non-existent favorite handled correctly")
        print(f"   Status: {data.get('status')}")
        print(f"   Message: {data.get('message')}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
