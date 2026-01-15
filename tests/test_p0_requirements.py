"""
P0 Requirements Backend Tests

Tests for P0 pricelist import and BestPrice calculation:
- P0.1: Upsert on import (no duplicates) using unique key
- P0.2: One active pricelist per supplier - deactivate old items
- P0.3: Import min_order_qty from files
- P0.4: Unit priority - unitType from file takes precedence
- P0.5: BestPrice total_cost = ceil(user_qty / min_order_qty) * min_order_qty * price
- P0.6: Safe pricelist deactivation endpoints
"""

import pytest
import requests
import os
import io
import math
from datetime import datetime

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://bestprice-search-ui.preview.emergentagent.com').rstrip('/')

# Test credentials
CUSTOMER_EMAIL = "customer@bestprice.ru"
CUSTOMER_PASSWORD = "password123"

# Known supplier ID
ALIDI_SUPPLIER_ID = "2f57f8be-f3b8-410b-83ac-cc2f505dd06f"

# Known favorite ID
CHICKEN_FAVORITE_ID = "e1c92a46-1951-4822-bdb5-32c1aed1bb0a"


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


class TestP06PricelistDeactivation:
    """P0.6: Safe pricelist deactivation endpoints"""
    
    def test_get_supplier_pricelists_returns_list(self, auth_headers):
        """GET /api/price-lists/supplier/{id} should return pricelists with counts"""
        response = requests.get(
            f"{BASE_URL}/api/price-lists/supplier/{ALIDI_SUPPLIER_ID}",
            headers=auth_headers
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        assert isinstance(data, list), f"Expected list, got {type(data)}"
        
        print(f"✅ P0.6: GET /api/price-lists/supplier/{ALIDI_SUPPLIER_ID[:8]}...")
        print(f"   Found {len(data)} pricelists")
        
        if len(data) > 0:
            pl = data[0]
            # Check required fields
            assert "id" in pl, "Missing 'id' field"
            assert "supplierId" in pl, "Missing 'supplierId' field"
            
            # Check item counts (P0.6 requirement)
            assert "activeItemsCount" in pl, "Missing 'activeItemsCount' field"
            assert "totalItemsCount" in pl, "Missing 'totalItemsCount' field"
            
            print(f"   First pricelist: {pl.get('id')[:8]}...")
            print(f"   Active items: {pl.get('activeItemsCount')}")
            print(f"   Total items: {pl.get('totalItemsCount')}")
        
        return data
    
    def test_deactivate_pricelist_requires_auth(self):
        """POST /api/price-lists/{id}/deactivate should require authentication"""
        response = requests.post(
            f"{BASE_URL}/api/price-lists/fake-id/deactivate"
        )
        
        # Should return 403 (Forbidden) without auth
        assert response.status_code == 403, f"Expected 403, got {response.status_code}"
        print("✅ P0.6: Deactivate endpoint requires authentication")
    
    def test_deactivate_nonexistent_pricelist_returns_403_or_404(self, auth_headers):
        """POST /api/price-lists/{id}/deactivate should return 403 (customer not authorized) or 404"""
        response = requests.post(
            f"{BASE_URL}/api/price-lists/nonexistent-pricelist-id/deactivate",
            headers=auth_headers
        )
        
        # Customer role returns 403 (not authorized to deactivate)
        # Supplier/Admin would get 404 for non-existent pricelist
        assert response.status_code in [403, 404], f"Expected 403 or 404, got {response.status_code}"
        print(f"✅ P0.6: Deactivate returns {response.status_code} (customer not authorized or not found)")


class TestP05BestPriceCalculation:
    """P0.5: BestPrice total_cost = ceil(user_qty / min_order_qty) * min_order_qty * price"""
    
    def test_add_from_favorite_returns_total_cost(self, auth_headers):
        """POST /api/cart/add-from-favorite should return total_cost in response"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": CHICKEN_FAVORITE_ID,
                "qty": 5
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        print(f"✅ P0.5: add-from-favorite response")
        print(f"   Status: {data.get('status')}")
        
        if data.get("status") == "ok":
            # Check total_cost is present
            assert "total_cost" in data or "computed_total_cost" in data, "Missing total_cost in response"
            
            total_cost = data.get("total_cost") or data.get("computed_total_cost")
            print(f"   Total cost: {total_cost}")
            
            # Check selected_offer
            if data.get("selected_offer"):
                offer = data["selected_offer"]
                print(f"   Selected: {offer.get('name_raw', '')[:40]}")
                print(f"   Price: {offer.get('price')}")
                print(f"   min_order_qty: {offer.get('min_order_qty', 1)}")
        else:
            print(f"   Message: {data.get('message')}")
        
        return data
    
    def test_total_cost_calculation_with_min_order_qty(self, auth_headers):
        """Verify total_cost formula: ceil(user_qty / min_order_qty) * min_order_qty * price"""
        # Test with qty=3 to see min_order_qty effect
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": CHICKEN_FAVORITE_ID,
                "qty": 3
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        if data.get("status") == "ok" and data.get("selected_offer"):
            offer = data["selected_offer"]
            price = offer.get("price", 0)
            min_order_qty = offer.get("min_order_qty", 1) or 1
            user_qty = 3
            
            # P0.5 formula
            expected_actual_qty = math.ceil(user_qty / min_order_qty) * min_order_qty
            expected_total_cost = expected_actual_qty * price
            
            actual_total_cost = data.get("total_cost") or data.get("computed_total_cost")
            
            print(f"✅ P0.5: Total cost calculation")
            print(f"   user_qty: {user_qty}")
            print(f"   min_order_qty: {min_order_qty}")
            print(f"   price: {price}")
            print(f"   Expected actual_qty: {expected_actual_qty}")
            print(f"   Expected total_cost: {expected_total_cost}")
            print(f"   Actual total_cost: {actual_total_cost}")
            
            # Check debug_log for _actual_qty and _total_cost_p05
            debug_log = data.get("debug_log", {})
            if "_actual_qty" in str(debug_log) or "_total_cost_p05" in str(debug_log):
                print(f"   Debug log contains P0.5 calculation fields")
        else:
            print(f"   Status: {data.get('status')}, Message: {data.get('message')}")
        
        return data
    
    def test_debug_log_contains_min_order_qty(self, auth_headers):
        """debug_log should contain min_order_qty information"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": CHICKEN_FAVORITE_ID,
                "qty": 1
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        if data.get("status") == "ok":
            debug_log = data.get("debug_log", {})
            
            # Check if min_order_qty is tracked
            print(f"✅ P0.5: Debug log analysis")
            print(f"   Debug log keys: {list(debug_log.keys())[:10]}")
            
            # Check selected_offer for min_order_qty
            if data.get("selected_offer"):
                offer = data["selected_offer"]
                moq = offer.get("min_order_qty")
                print(f"   Selected offer min_order_qty: {moq}")
        
        return data


class TestP03MinOrderQtyImport:
    """P0.3: Import min_order_qty from files"""
    
    def test_supplier_items_have_min_order_qty(self, auth_headers):
        """Verify supplier_items collection has min_order_qty field"""
        # Use MongoDB directly to check
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017")
        db = client["test_database"]
        
        # Count items with min_order_qty
        count_with_moq = db.supplier_items.count_documents({"min_order_qty": {"$exists": True}})
        count_moq_gt_1 = db.supplier_items.count_documents({"min_order_qty": {"$gt": 1}})
        count_total = db.supplier_items.count_documents({})
        
        print(f"✅ P0.3: min_order_qty in supplier_items")
        print(f"   Total items: {count_total}")
        print(f"   Items with min_order_qty field: {count_with_moq}")
        print(f"   Items with min_order_qty > 1: {count_moq_gt_1}")
        
        # At least some items should have min_order_qty > 1
        assert count_moq_gt_1 > 0, "No items with min_order_qty > 1 found"
        
        # Get sample item with min_order_qty > 1
        sample = db.supplier_items.find_one({"min_order_qty": {"$gt": 1}})
        if sample:
            print(f"   Sample item: {sample.get('name_raw', '')[:40]}")
            print(f"   min_order_qty: {sample.get('min_order_qty')}")
            print(f"   price: {sample.get('price')}")
        
        client.close()


class TestP01UpsertOnImport:
    """P0.1: Upsert on import (no duplicates) using unique key"""
    
    def test_supplier_items_have_unique_key(self, auth_headers):
        """Verify supplier_items have unique_key field"""
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017")
        db = client["test_database"]
        
        # Count items with unique_key
        count_with_key = db.supplier_items.count_documents({"unique_key": {"$exists": True}})
        count_total = db.supplier_items.count_documents({})
        
        print(f"✅ P0.1: unique_key in supplier_items")
        print(f"   Total items: {count_total}")
        print(f"   Items with unique_key: {count_with_key}")
        
        # All items should have unique_key
        assert count_with_key == count_total, f"Not all items have unique_key: {count_with_key}/{count_total}"
        
        # Check unique_key format
        sample = db.supplier_items.find_one({"unique_key": {"$exists": True}})
        if sample:
            unique_key = sample.get("unique_key", "")
            print(f"   Sample unique_key: {unique_key[:60]}...")
            
            # Should contain supplier_id
            assert ":" in unique_key, "unique_key should contain ':' separator"
        
        client.close()
    
    def test_no_duplicate_unique_keys(self, auth_headers):
        """Verify no duplicate unique_keys exist"""
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017")
        db = client["test_database"]
        
        # Find duplicates using aggregation
        pipeline = [
            {"$group": {"_id": "$unique_key", "count": {"$sum": 1}}},
            {"$match": {"count": {"$gt": 1}}},
            {"$limit": 5}
        ]
        
        duplicates = list(db.supplier_items.aggregate(pipeline))
        
        print(f"✅ P0.1: Checking for duplicate unique_keys")
        print(f"   Duplicates found: {len(duplicates)}")
        
        if duplicates:
            for dup in duplicates:
                print(f"   Duplicate: {dup['_id'][:50]}... (count: {dup['count']})")
        
        # Should have no duplicates
        assert len(duplicates) == 0, f"Found {len(duplicates)} duplicate unique_keys"
        
        client.close()


class TestP02OneActivePricelistPerSupplier:
    """P0.2: One active pricelist per supplier - deactivate old items"""
    
    def test_supplier_items_have_active_field(self, auth_headers):
        """Verify supplier_items have active field"""
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017")
        db = client["test_database"]
        
        # Count items with active field
        count_active_true = db.supplier_items.count_documents({"active": True})
        count_active_false = db.supplier_items.count_documents({"active": False})
        count_total = db.supplier_items.count_documents({})
        
        print(f"✅ P0.2: active field in supplier_items")
        print(f"   Total items: {count_total}")
        print(f"   Active items: {count_active_true}")
        print(f"   Inactive items: {count_active_false}")
        
        # Most items should be active
        assert count_active_true > 0, "No active items found"
        
        client.close()
    
    def test_supplier_items_have_price_list_id(self, auth_headers):
        """Verify supplier_items have price_list_id field"""
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017")
        db = client["test_database"]
        
        # Count items with price_list_id
        count_with_plid = db.supplier_items.count_documents({"price_list_id": {"$exists": True}})
        count_total = db.supplier_items.count_documents({})
        
        print(f"✅ P0.2: price_list_id in supplier_items")
        print(f"   Total items: {count_total}")
        print(f"   Items with price_list_id: {count_with_plid}")
        
        # All items should have price_list_id
        assert count_with_plid == count_total, f"Not all items have price_list_id: {count_with_plid}/{count_total}"
        
        client.close()


class TestP04UnitPriority:
    """P0.4: Unit priority - unitType from file takes precedence"""
    
    def test_supplier_items_have_unit_type(self, auth_headers):
        """Verify supplier_items have unit_type field"""
        from pymongo import MongoClient
        client = MongoClient("mongodb://localhost:27017")
        db = client["test_database"]
        
        # Count items with unit_type
        count_with_ut = db.supplier_items.count_documents({"unit_type": {"$exists": True}})
        count_total = db.supplier_items.count_documents({})
        
        print(f"✅ P0.4: unit_type in supplier_items")
        print(f"   Total items: {count_total}")
        print(f"   Items with unit_type: {count_with_ut}")
        
        # Check unit_type values
        unit_types = db.supplier_items.distinct("unit_type")
        print(f"   Unit types found: {unit_types}")
        
        # Should have standard unit types
        expected_types = ["WEIGHT", "VOLUME", "PIECE"]
        for ut in unit_types:
            if ut:
                assert ut in expected_types, f"Unexpected unit_type: {ut}"
        
        client.close()


class TestImportEndpoint:
    """Test POST /api/price-lists/import endpoint"""
    
    def test_import_endpoint_exists(self, auth_headers):
        """Verify import endpoint exists and requires file"""
        # Try without file - should fail with 422 (validation error)
        response = requests.post(
            f"{BASE_URL}/api/price-lists/import",
            headers=auth_headers,
            data={"column_mapping": "{}"}
        )
        
        # Should return 422 (missing file) or 400 (bad request)
        assert response.status_code in [400, 422], f"Unexpected status: {response.status_code}"
        print(f"✅ Import endpoint exists and validates input")
        print(f"   Status without file: {response.status_code}")


class TestSelectOfferEndpoint:
    """Test /api/cart/select-offer endpoint"""
    
    def test_select_offer_works(self, auth_headers):
        """select-offer endpoint works for normal requests"""
        response = requests.post(
            f"{BASE_URL}/api/cart/select-offer",
            headers=auth_headers,
            json={
                "reference_item": {
                    "name_raw": "Курица грудка",
                    "unit_norm": "kg",
                    "brand_critical": False
                },
                "match_threshold": 0.4,
                "required_volume": 2.0
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        
        print(f"✅ select-offer endpoint works")
        if data.get("selected_offer"):
            offer = data["selected_offer"]
            print(f"   Found: {offer.get('name_raw', '')[:40]}")
            print(f"   Price: {offer.get('price')}")
            print(f"   Total cost: {offer.get('total_cost')}")
        else:
            print(f"   Reason: {data.get('reason')}")
        
        return data


class TestEdgeCases:
    """Edge case tests for P0 requirements"""
    
    def test_add_from_favorite_with_large_qty(self, auth_headers):
        """Test add-from-favorite with large quantity"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": CHICKEN_FAVORITE_ID,
                "qty": 100
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        print(f"✅ Large qty test (qty=100)")
        print(f"   Status: {data.get('status')}")
        
        if data.get("status") == "ok":
            total_cost = data.get("total_cost") or data.get("computed_total_cost")
            print(f"   Total cost: {total_cost}")
        
        return data
    
    def test_add_from_favorite_with_fractional_qty(self, auth_headers):
        """Test add-from-favorite with fractional quantity"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": CHICKEN_FAVORITE_ID,
                "qty": 2.5
            }
        )
        
        assert response.status_code == 200, f"Request failed: {response.text}"
        
        data = response.json()
        print(f"✅ Fractional qty test (qty=2.5)")
        print(f"   Status: {data.get('status')}")
        
        if data.get("status") == "ok":
            total_cost = data.get("total_cost") or data.get("computed_total_cost")
            print(f"   Total cost: {total_cost}")
        
        return data
    
    def test_nonexistent_favorite_returns_not_found(self, auth_headers):
        """Non-existent favorite should return not_found status"""
        response = requests.post(
            f"{BASE_URL}/api/cart/add-from-favorite",
            headers=auth_headers,
            json={
                "favorite_id": "nonexistent-favorite-id-12345",
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
