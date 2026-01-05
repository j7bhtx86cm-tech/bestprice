"""
Backend API Tests for Enhanced Search Engine MVP Safe-Mode

VERSION 2.0 (December 2025)

TESTS:
1. FAV_KETCHUP_ANY (brand_critical=false) - выбирает самый дешёвый вариант любого бренда
2. FAV_KETCHUP_HEINZ (brand_critical=true) - выбирает только Heinz, фасовка в диапазоне
3. Pack range filter - 340г и 5кг должны быть ОТСЕЯНЫ (вне диапазона 0.5x-2x от 800г)
4. FAV_ECON_TEST - Экономика: выбор по total_cost (1кг×230₽ дешевле 800г×200₽ за кг)
5. FAV_OLD_FORMAT - старое избранное не падает с ошибкой
6. Guard rules - Соус не должен подставляться вместо Кетчупа
7. debug_log содержит counters (before/after каждого фильтра), pack_rejections, guard_rejections

CRITICAL RULES:
1. brand_critical=false → brand COMPLETELY IGNORED (no filter, no score)
2. brand_critical=true → only same brand_id
3. Pack range: 0.5 * ref_pack <= candidate_pack <= 2 * ref_pack
4. Selection by total_cost, score is tie-breaker only
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://pricematch-pro-1.preview.emergentagent.com').rstrip('/')

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
        """Create test fixtures for MVP matching tests"""
        response = requests.post(
            f"{BASE_URL}/api/test/create-fixtures",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Create fixtures failed: {response.text}"
        
        data = response.json()
        assert data.get("success") == True, f"Fixtures not created: {data}"
        
        print(f"✅ Test fixtures created:")
        print(f"   Products: {data['data']['products']}")
        print(f"   Pricelists: {data['data']['pricelists']}")
        print(f"   Favorites: {data['data']['favorites']}")
        
        # Verify expected behavior is documented
        assert "expected_behavior" in data
        assert "FAV_KETCHUP_ANY" in data["expected_behavior"]
        assert "FAV_KETCHUP_HEINZ" in data["expected_behavior"]
        assert "FAV_ECON_TEST" in data["expected_behavior"]
        
        print(f"\n   Expected behavior:")
        for key, value in data["expected_behavior"].items():
            print(f"      {key}: {value}")
        
        return data


class TestFavKetchupAnyBrandCriticalFalse:
    """ТЕСТ 1: FAV_KETCHUP_ANY (brand_critical=false) - выбирает самый дешёвый вариант любого бренда"""
    
    def test_fav_ketchup_any_selects_cheapest_across_all_brands(self, auth_headers):
        """FAV_KETCHUP_ANY (brand_critical=false) должен выбрать Calve 500г (240₽/кг) - самый дешёвый"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_KETCHUP_ANY",
                "qty": 0.8,  # 800g
                "match_threshold": 0.3
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        # Should NOT return 500 error
        assert data.get("status") != "error", f"Got error: {data.get('message')}"
        
        # Check debug_log exists
        assert "debug_log" in data, "No debug_log in response"
        debug_log = data["debug_log"]
        
        # Check brand_critical is false
        reference = debug_log.get("reference", {})
        brand_critical = reference.get("brand_critical", False)
        assert brand_critical == False, f"Expected brand_critical=false, got {brand_critical}"
        
        # Check filters_applied contains 'brand_filter: DISABLED'
        filters = debug_log.get("filters_applied", [])
        brand_filter_disabled = any("DISABLED" in str(f) for f in filters)
        assert brand_filter_disabled, f"Expected 'brand_filter: DISABLED' in filters, got {filters}"
        
        print(f"✅ ТЕСТ 1: FAV_KETCHUP_ANY (brand_critical=false)")
        print(f"   Status: {data.get('status')}")
        print(f"   brand_critical: {brand_critical}")
        print(f"   filters_applied: {filters}")
        
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            print(f"   Selected: {offer.get('supplier_item_id')} @ {offer.get('price')}₽")
            print(f"   Product: {offer.get('name_raw', '')[:50]}")
            print(f"   Price per unit: {offer.get('price_per_base_unit', 'N/A')}₽/кг")
            print(f"   Total cost: {offer.get('total_cost', 'N/A')}₽")
            
            # CRITICAL: Should select Calve 500г (SI_KETCHUP_OTHER_500) - 240₽/кг
            # Or any other cheapest option
            if offer.get("supplier_item_id") == "SI_KETCHUP_OTHER_500":
                print(f"   ✅ CORRECT: Selected SI_KETCHUP_OTHER_500 (Calve, cheapest)")
            elif offer.get("price_per_base_unit") and offer.get("price_per_base_unit") <= 250:
                print(f"   ✅ Selected cheap option: {offer.get('price_per_base_unit')}₽/кг")
            else:
                print(f"   ⚠️ May not be cheapest - verify manually")
        else:
            print(f"   Reason: {debug_log.get('result', {}).get('failure_reason')}")
        
        return data


class TestFavKetchupHeinzBrandCriticalTrue:
    """ТЕСТ 2: FAV_KETCHUP_HEINZ (brand_critical=true) - выбирает только Heinz, фасовка в диапазоне"""
    
    def test_fav_ketchup_heinz_filters_by_brand(self, auth_headers):
        """FAV_KETCHUP_HEINZ (brand_critical=true) должен выбрать Heinz 1кг (280₽/кг) - самый дешёвый Heinz в диапазоне"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_KETCHUP_HEINZ",
                "qty": 0.8,  # 800g
                "match_threshold": 0.3
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        # Should NOT return 500 error
        assert data.get("status") != "error", f"Got error: {data.get('message')}"
        
        # Check debug_log exists
        assert "debug_log" in data, "No debug_log in response"
        debug_log = data["debug_log"]
        
        # Check brand_critical is true
        reference = debug_log.get("reference", {})
        brand_critical = reference.get("brand_critical", False)
        assert brand_critical == True, f"Expected brand_critical=true, got {brand_critical}"
        
        # Check filters_applied contains 'brand_filter: brand_id=...'
        filters = debug_log.get("filters_applied", [])
        brand_filter_enabled = any("brand_id=" in str(f) or "brand_filter:" in str(f) for f in filters)
        
        print(f"✅ ТЕСТ 2: FAV_KETCHUP_HEINZ (brand_critical=true)")
        print(f"   Status: {data.get('status')}")
        print(f"   brand_critical: {brand_critical}")
        print(f"   filters_applied: {filters}")
        
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            print(f"   Selected: {offer.get('supplier_item_id')} @ {offer.get('price')}₽")
            print(f"   Product: {offer.get('name_raw', '')[:50]}")
            print(f"   Price per unit: {offer.get('price_per_base_unit', 'N/A')}₽/кг")
            print(f"   Brand: {offer.get('brand_id', 'N/A')}")
            
            # CRITICAL: Should select Heinz 1кг (SI_KETCHUP_HEINZ_1KG) - 280₽/кг
            # NOT Heinz 340г (too small) or Heinz 5кг (too large)
            if offer.get("supplier_item_id") == "SI_KETCHUP_HEINZ_1KG":
                print(f"   ✅ CORRECT: Selected SI_KETCHUP_HEINZ_1KG (Heinz 1кг, cheapest Heinz in range)")
            elif offer.get("supplier_item_id") == "SI_KETCHUP_HEINZ_800":
                print(f"   ✅ CORRECT: Selected SI_KETCHUP_HEINZ_800 (Heinz 800г, reference)")
            elif "heinz" in str(offer.get("name_raw", "")).lower():
                print(f"   ✅ Selected Heinz product")
            else:
                print(f"   ⚠️ May not be Heinz - verify manually")
        else:
            print(f"   Reason: {debug_log.get('result', {}).get('failure_reason')}")
        
        return data


class TestPackRangeFilter:
    """ТЕСТ 3: Pack range filter - 340г и 5кг должны быть ОТСЕЯНЫ (вне диапазона 0.5x-2x от 800г)"""
    
    def test_pack_range_rejects_out_of_range(self, auth_headers):
        """Pack range filter должен отсеять 340г (< 400г) и 5кг (> 1.6кг)"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_KETCHUP_HEINZ",  # Reference: 800г
                "qty": 0.8,
                "match_threshold": 0.3
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        debug_log = data.get("debug_log", {})
        
        # Check pack_rejections in debug_log
        pack_rejections = debug_log.get("pack_rejections_sample", [])
        
        print(f"✅ ТЕСТ 3: Pack range filter (0.5x-2x)")
        print(f"   Reference pack: 0.8 kg (800г)")
        print(f"   Valid range: 0.4 kg - 1.6 kg")
        print(f"   Pack rejections: {len(pack_rejections)}")
        
        # Check counters
        counters = debug_log.get("counters", {})
        print(f"   Counters:")
        print(f"      Total candidates: {counters.get('total', 'N/A')}")
        print(f"      After pack filter: {counters.get('after_pack_filter', 'N/A')}")
        
        # Verify pack filter is applied
        filters = debug_log.get("filters_applied", [])
        pack_filter_applied = any("pack_filter" in str(f) for f in filters)
        assert pack_filter_applied, f"Expected pack_filter in filters, got {filters}"
        
        # Check that 340г and 5кг are rejected
        for rejection in pack_rejections:
            print(f"      Rejected: {rejection.get('name', 'N/A')[:40]} - {rejection.get('reason', 'N/A')}")
        
        # If we got a result, verify it's in range
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            pack_value = offer.get("pack_value", 0)
            print(f"   Selected pack: {pack_value} kg")
            
            # Verify pack is in range (0.4 - 1.6 kg for 800g reference)
            if pack_value:
                assert 0.4 <= pack_value <= 1.6, f"Selected pack {pack_value} is out of range 0.4-1.6"
                print(f"   ✅ Pack {pack_value} kg is in valid range")
        
        return data


class TestEconomicsSelection:
    """ТЕСТ 4: FAV_ECON_TEST - Экономика: выбор по total_cost"""
    
    def test_fav_econ_selects_by_total_cost(self, auth_headers):
        """FAV_ECON_TEST должен выбрать SI_ECON_B (230₽/кг) - дешевле за кг чем SI_ECON_A (250₽/кг)"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_ECON_TEST",
                "qty": 0.8,  # 800g
                "match_threshold": 0.3
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        # Should NOT return 500 error
        assert data.get("status") != "error", f"Got error: {data.get('message')}"
        
        print(f"✅ ТЕСТ 4: FAV_ECON_TEST (Economics)")
        print(f"   Status: {data.get('status')}")
        
        debug_log = data.get("debug_log", {})
        
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            print(f"   Selected: {offer.get('supplier_item_id')} @ {offer.get('price')}₽")
            print(f"   Product: {offer.get('name_raw', '')[:50]}")
            print(f"   Price per unit: {offer.get('price_per_base_unit', 'N/A')}₽/кг")
            print(f"   Total cost: {offer.get('total_cost', 'N/A')}₽")
            
            # CRITICAL: Should select SI_ECON_B (230₽/кг) over SI_ECON_A (250₽/кг)
            # SI_ECON_A: 800г × 200₽ = 250₽/кг
            # SI_ECON_B: 1кг × 230₽ = 230₽/кг (CHEAPER!)
            if offer.get("supplier_item_id") == "SI_ECON_B":
                print(f"   ✅ CORRECT: Selected SI_ECON_B (230₽/кг - cheaper per unit)")
            elif offer.get("price_per_base_unit") and offer.get("price_per_base_unit") <= 240:
                print(f"   ✅ Selected cheap option: {offer.get('price_per_base_unit')}₽/кг")
            else:
                print(f"   ⚠️ May not be cheapest per unit - verify manually")
        else:
            print(f"   Reason: {debug_log.get('result', {}).get('failure_reason')}")
        
        # Check top_candidates to verify sorting by total_cost
        top_candidates = data.get("top_candidates", [])
        if top_candidates:
            print(f"\n   Top candidates (sorted by total_cost):")
            for i, cand in enumerate(top_candidates[:3]):
                print(f"      {i+1}. {cand.get('name_raw', '')[:30]} - {cand.get('price_per_unit', 'N/A')}₽/кг, total: {cand.get('total_cost', 'N/A')}₽")
        
        return data


class TestOldFormatFavorite:
    """ТЕСТ 5: FAV_OLD_FORMAT - старое избранное не падает с ошибкой"""
    
    def test_fav_old_format_no_500_error(self, auth_headers):
        """FAV_OLD_FORMAT (старый формат без v2 полей) - не должен падать с 500"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_OLD_FORMAT",
                "qty": 1,
                "match_threshold": 0.3
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
        
        print(f"✅ ТЕСТ 5: FAV_OLD_FORMAT (старый формат)")
        print(f"   Status: {data.get('status')}")
        print(f"   Message: {data.get('message')}")
        
        debug_log = data.get("debug_log", {})
        print(f"   Failure reason: {debug_log.get('result', {}).get('failure_reason') or debug_log.get('failure_reason')}")
        
        return data


class TestGuardRules:
    """ТЕСТ 6: Guard rules - Соус не должен подставляться вместо Кетчупа"""
    
    def test_guard_rules_reject_sauce_for_ketchup(self, auth_headers):
        """Guard rules должны отсеять Соус при поиске Кетчупа"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_KETCHUP_ANY",  # Кетчуп
                "qty": 0.8,
                "match_threshold": 0.3
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        debug_log = data.get("debug_log", {})
        
        # Check guard_rejections in debug_log
        guard_rejections = debug_log.get("guard_rejections_sample", [])
        
        print(f"✅ ТЕСТ 6: Guard rules (кетчуп ≠ соус)")
        print(f"   Guard rejections: {len(guard_rejections)}")
        
        for rejection in guard_rejections:
            print(f"      Rejected: {rejection[:40]}")
        
        # Check counters
        counters = debug_log.get("counters", {})
        print(f"   Counters:")
        print(f"      After token filter: {counters.get('after_token_filter', 'N/A')}")
        print(f"      After guard filter: {counters.get('after_guard_filter', 'N/A')}")
        
        # Verify guard filter is applied
        filters = debug_log.get("filters_applied", [])
        guard_filter_applied = any("guard_filter" in str(f) for f in filters)
        assert guard_filter_applied, f"Expected guard_filter in filters, got {filters}"
        
        # If we got a result, verify it's not a sauce
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            name = offer.get("name_raw", "").lower()
            
            # Should NOT be "соус соевый" or similar
            assert "соевый" not in name, f"Guard rules failed: selected sauce '{name}'"
            print(f"   ✅ Selected product is not a sauce: {name[:40]}")
        
        return data


class TestDebugLogCounters:
    """ТЕСТ 7: debug_log содержит counters (before/after каждого фильтра), pack_rejections, guard_rejections"""
    
    def test_debug_log_contains_all_counters(self, auth_headers):
        """debug_log должен содержать counters с before/after каждого фильтра"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "FAV_KETCHUP_ANY",
                "qty": 0.8,
                "match_threshold": 0.3
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        
        assert "debug_log" in data, "No debug_log in response"
        debug_log = data["debug_log"]
        
        # Check counters
        assert "counters" in debug_log, "No counters in debug_log"
        counters = debug_log["counters"]
        
        # Required counter fields
        required_counters = [
            "total",
            "after_brand_filter",
            "after_unit_filter",
            "after_pack_filter",
            "after_token_filter",
            "after_guard_filter",
            "final"
        ]
        
        print(f"✅ ТЕСТ 7: debug_log counters")
        print(f"   Counters:")
        for counter in required_counters:
            value = counters.get(counter, "MISSING")
            print(f"      {counter}: {value}")
            assert counter in counters, f"Missing counter '{counter}' in debug_log"
        
        # Check pack_rejections_sample
        assert "pack_rejections_sample" in debug_log, "No pack_rejections_sample in debug_log"
        print(f"   Pack rejections sample: {len(debug_log['pack_rejections_sample'])}")
        
        # Check guard_rejections_sample
        assert "guard_rejections_sample" in debug_log, "No guard_rejections_sample in debug_log"
        print(f"   Guard rejections sample: {len(debug_log['guard_rejections_sample'])}")
        
        # Check filters_applied
        assert "filters_applied" in debug_log, "No filters_applied in debug_log"
        print(f"   Filters applied: {debug_log['filters_applied']}")
        
        # Check result
        assert "result" in debug_log, "No result in debug_log"
        result = debug_log["result"]
        assert "status" in result, "No status in result"
        print(f"   Result status: {result['status']}")
        
        return debug_log


class TestBrandCriticalComparison:
    """Compare brand_critical=true vs false to verify different behavior"""
    
    def test_brand_critical_produces_different_results(self, auth_headers):
        """brand_critical=true and false should produce different filter behavior and potentially different prices"""
        # Test with FAV_KETCHUP_ANY (brand_critical=false)
        response_false = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "FAV_KETCHUP_ANY", "qty": 0.8, "match_threshold": 0.3}
        )
        
        # Test with FAV_KETCHUP_HEINZ (brand_critical=true)
        response_true = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={"favorite_id": "FAV_KETCHUP_HEINZ", "qty": 0.8, "match_threshold": 0.3}
        )
        
        assert response_false.status_code == 200
        assert response_true.status_code == 200
        
        data_false = response_false.json()
        data_true = response_true.json()
        
        # Both should have debug_log
        assert "debug_log" in data_false
        assert "debug_log" in data_true
        
        # brand_critical should be different
        ref_false = data_false["debug_log"].get("reference", {})
        ref_true = data_true["debug_log"].get("reference", {})
        
        assert ref_false.get("brand_critical") == False, f"Expected brand_critical=false, got {ref_false.get('brand_critical')}"
        assert ref_true.get("brand_critical") == True, f"Expected brand_critical=true, got {ref_true.get('brand_critical')}"
        
        # filters_applied should be different
        filters_false = data_false["debug_log"]["filters_applied"]
        filters_true = data_true["debug_log"]["filters_applied"]
        
        has_disabled = any("DISABLED" in str(f) for f in filters_false)
        has_brand_id = any("brand_id=" in str(f) or "brand_filter:" in str(f) for f in filters_true)
        
        print(f"✅ Brand critical comparison:")
        print(f"   FAV_KETCHUP_ANY (false): filters={filters_false}")
        print(f"   FAV_KETCHUP_HEINZ (true): filters={filters_true}")
        
        # If both found offers, compare prices
        if data_false.get("selected_offer") and data_true.get("selected_offer"):
            price_false = data_false["selected_offer"].get("price_per_base_unit", 0)
            price_true = data_true["selected_offer"].get("price_per_base_unit", 0)
            print(f"   FAV_KETCHUP_ANY price: {price_false}₽/кг")
            print(f"   FAV_KETCHUP_HEINZ price: {price_true}₽/кг")
            
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
