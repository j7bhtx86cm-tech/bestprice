"""
Iteration 10 Tests - Favorites Clear & Offer Modal Features

Testing:
1. POST /api/v12/favorites/clear - Clear all favorites endpoint
2. GET /api/v12/item/{item_id}/alternatives - Get alternative offers
3. Guard logic in OfferSelectModal - should not crash if sourceItem=null
4. Add to cart from modal with quantity
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://data-clean-1.preview.emergentagent.com')
TEST_USER_ID = "0b3f0b09-d8ba-4ff9-9d2a-519e1c34067e"


class TestFavoritesClearEndpoint:
    """Test POST /api/v12/favorites/clear endpoint"""
    
    def test_favorites_clear_endpoint_exists(self):
        """Test that the clear favorites endpoint exists and accepts POST"""
        response = requests.post(
            f"{BASE_URL}/api/v12/favorites/clear",
            params={"user_id": TEST_USER_ID}
        )
        # Should return 200 OK (not 404 or 405)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_favorites_clear_returns_counts(self):
        """Test that clear returns deleted_count and remaining_count"""
        response = requests.post(
            f"{BASE_URL}/api/v12/favorites/clear",
            params={"user_id": TEST_USER_ID}
        )
        assert response.status_code == 200
        
        data = response.json()
        # Verify response structure
        assert "deleted_count" in data, "Response should contain deleted_count"
        assert "remaining_count" in data, "Response should contain remaining_count"
        assert "status" in data, "Response should contain status"
        
        # Verify types
        assert isinstance(data["deleted_count"], int), "deleted_count should be int"
        assert isinstance(data["remaining_count"], int), "remaining_count should be int"
        assert data["status"] == "ok", f"Status should be 'ok', got {data['status']}"
    
    def test_favorites_clear_actually_clears(self):
        """Test that clear actually removes all favorites"""
        # First, add some favorites
        # Get a catalog item to add
        catalog_response = requests.get(
            f"{BASE_URL}/api/v12/catalog",
            params={"limit": 3}
        )
        assert catalog_response.status_code == 200
        items = catalog_response.json().get("items", [])
        
        if items:
            # Add items to favorites
            for item in items[:2]:
                requests.post(
                    f"{BASE_URL}/api/v12/favorites",
                    params={"user_id": TEST_USER_ID, "reference_id": item["id"]}
                )
        
        # Now clear all
        clear_response = requests.post(
            f"{BASE_URL}/api/v12/favorites/clear",
            params={"user_id": TEST_USER_ID}
        )
        assert clear_response.status_code == 200
        data = clear_response.json()
        
        # remaining_count should be 0
        assert data["remaining_count"] == 0, f"remaining_count should be 0 after clear, got {data['remaining_count']}"
        
        # Verify by fetching favorites
        favorites_response = requests.get(
            f"{BASE_URL}/api/v12/favorites",
            params={"user_id": TEST_USER_ID, "limit": 100}
        )
        assert favorites_response.status_code == 200
        favorites = favorites_response.json().get("items", [])
        assert len(favorites) == 0, f"Favorites should be empty after clear, got {len(favorites)} items"


class TestAlternativesEndpoint:
    """Test GET /api/v12/item/{item_id}/alternatives endpoint"""
    
    @pytest.fixture
    def sample_item_id(self):
        """Get a sample item ID from catalog"""
        response = requests.get(
            f"{BASE_URL}/api/v12/catalog",
            params={"limit": 1}
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        if items:
            return items[0]["id"]
        pytest.skip("No items in catalog")
    
    def test_alternatives_endpoint_exists(self, sample_item_id):
        """Test that alternatives endpoint exists"""
        response = requests.get(
            f"{BASE_URL}/api/v12/item/{sample_item_id}/alternatives"
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
    
    def test_alternatives_returns_source(self, sample_item_id):
        """Test that alternatives returns source item info"""
        response = requests.get(
            f"{BASE_URL}/api/v12/item/{sample_item_id}/alternatives"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "source" in data, "Response should contain source"
        
        source = data["source"]
        if source:  # source can be None if item not found
            assert "id" in source, "Source should have id"
            assert "name" in source, "Source should have name"
            assert "price" in source, "Source should have price"
    
    def test_alternatives_returns_alternatives_list(self, sample_item_id):
        """Test that alternatives returns alternatives list"""
        response = requests.get(
            f"{BASE_URL}/api/v12/item/{sample_item_id}/alternatives"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "alternatives" in data, "Response should contain alternatives"
        assert "total" in data, "Response should contain total"
        
        assert isinstance(data["alternatives"], list), "alternatives should be a list"
        assert isinstance(data["total"], int), "total should be int"
    
    def test_alternatives_structure(self, sample_item_id):
        """Test structure of alternative items"""
        response = requests.get(
            f"{BASE_URL}/api/v12/item/{sample_item_id}/alternatives"
        )
        assert response.status_code == 200
        
        data = response.json()
        alternatives = data.get("alternatives", [])
        
        if alternatives:
            alt = alternatives[0]
            # Check required fields
            assert "id" in alt, "Alternative should have id"
            assert "name" in alt, "Alternative should have name"
            assert "price" in alt, "Alternative should have price"
            assert "supplier_name" in alt, "Alternative should have supplier_name"
    
    def test_alternatives_nonexistent_item(self):
        """Test alternatives for non-existent item returns empty"""
        response = requests.get(
            f"{BASE_URL}/api/v12/item/nonexistent-item-id-12345/alternatives"
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("source") is None, "Source should be None for non-existent item"
        assert data.get("alternatives") == [], "Alternatives should be empty for non-existent item"
        assert data.get("total") == 0, "Total should be 0 for non-existent item"


class TestAddToCartFromModal:
    """Test adding items to cart with quantity (from modal)"""
    
    @pytest.fixture
    def sample_item_id(self):
        """Get a sample item ID from catalog"""
        response = requests.get(
            f"{BASE_URL}/api/v12/catalog",
            params={"limit": 1}
        )
        assert response.status_code == 200
        items = response.json().get("items", [])
        if items:
            return items[0]["id"]
        pytest.skip("No items in catalog")
    
    def test_add_to_cart_with_qty(self, sample_item_id):
        """Test adding item to cart with specific quantity"""
        # Clear cart first
        requests.delete(
            f"{BASE_URL}/api/v12/cart",
            params={"user_id": TEST_USER_ID}
        )
        requests.delete(
            f"{BASE_URL}/api/v12/cart/intents",
            params={"user_id": TEST_USER_ID}
        )
        
        # Add with qty=5
        response = requests.post(
            f"{BASE_URL}/api/v12/cart/intent",
            json={
                "supplier_item_id": sample_item_id,
                "qty": 5,
                "user_id": TEST_USER_ID
            }
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("status") == "ok", f"Status should be 'ok', got {data.get('status')}"
        
        # Verify intent was created with correct qty
        intents_response = requests.get(
            f"{BASE_URL}/api/v12/cart/intents",
            params={"user_id": TEST_USER_ID}
        )
        assert intents_response.status_code == 200
        
        intents = intents_response.json().get("intents", [])
        assert len(intents) > 0, "Should have at least one intent"
        
        # Find our intent
        our_intent = next((i for i in intents if i.get("supplier_item_id") == sample_item_id), None)
        assert our_intent is not None, "Should find our intent"
        assert our_intent.get("qty") == 5, f"Qty should be 5, got {our_intent.get('qty')}"
    
    def test_add_alternative_to_cart(self, sample_item_id):
        """Test adding an alternative offer to cart"""
        # Get alternatives
        alt_response = requests.get(
            f"{BASE_URL}/api/v12/item/{sample_item_id}/alternatives"
        )
        assert alt_response.status_code == 200
        
        alternatives = alt_response.json().get("alternatives", [])
        
        if not alternatives:
            pytest.skip("No alternatives available for this item")
        
        alt_id = alternatives[0]["id"]
        
        # Clear cart
        requests.delete(
            f"{BASE_URL}/api/v12/cart/intents",
            params={"user_id": TEST_USER_ID}
        )
        
        # Add alternative with qty=3
        response = requests.post(
            f"{BASE_URL}/api/v12/cart/intent",
            json={
                "supplier_item_id": alt_id,
                "qty": 3,
                "user_id": TEST_USER_ID
            }
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "ok"


class TestFavoritesWorkflow:
    """Test complete favorites workflow including clear"""
    
    def test_add_favorites_then_clear(self):
        """Test adding favorites and then clearing all"""
        # Get catalog items
        catalog_response = requests.get(
            f"{BASE_URL}/api/v12/catalog",
            params={"limit": 5}
        )
        assert catalog_response.status_code == 200
        items = catalog_response.json().get("items", [])
        
        if len(items) < 2:
            pytest.skip("Not enough items in catalog")
        
        # Clear existing favorites first
        requests.post(
            f"{BASE_URL}/api/v12/favorites/clear",
            params={"user_id": TEST_USER_ID}
        )
        
        # Add 3 items to favorites
        added_count = 0
        for item in items[:3]:
            response = requests.post(
                f"{BASE_URL}/api/v12/favorites",
                params={"user_id": TEST_USER_ID, "reference_id": item["id"]}
            )
            if response.status_code == 200:
                added_count += 1
        
        # Verify favorites were added
        favorites_response = requests.get(
            f"{BASE_URL}/api/v12/favorites",
            params={"user_id": TEST_USER_ID, "limit": 100}
        )
        assert favorites_response.status_code == 200
        favorites_before = favorites_response.json().get("items", [])
        assert len(favorites_before) >= added_count, f"Should have at least {added_count} favorites"
        
        # Clear all
        clear_response = requests.post(
            f"{BASE_URL}/api/v12/favorites/clear",
            params={"user_id": TEST_USER_ID}
        )
        assert clear_response.status_code == 200
        
        clear_data = clear_response.json()
        assert clear_data["deleted_count"] >= added_count, f"Should delete at least {added_count} items"
        assert clear_data["remaining_count"] == 0, "Should have 0 remaining"
        
        # Verify empty
        favorites_after = requests.get(
            f"{BASE_URL}/api/v12/favorites",
            params={"user_id": TEST_USER_ID, "limit": 100}
        )
        assert favorites_after.status_code == 200
        assert len(favorites_after.json().get("items", [])) == 0, "Favorites should be empty"


class TestCatalogEndpoints:
    """Test catalog endpoints are working"""
    
    def test_catalog_returns_items(self):
        """Test catalog returns items"""
        response = requests.get(
            f"{BASE_URL}/api/v12/catalog",
            params={"limit": 10}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "items" in data
        assert "total" in data
        assert len(data["items"]) > 0, "Catalog should have items"
    
    def test_catalog_item_has_required_fields(self):
        """Test catalog items have required fields for modal"""
        response = requests.get(
            f"{BASE_URL}/api/v12/catalog",
            params={"limit": 1}
        )
        assert response.status_code == 200
        
        items = response.json().get("items", [])
        if items:
            item = items[0]
            assert "id" in item, "Item should have id"
            assert "price" in item or "best_price" in item, "Item should have price"
            assert "name_raw" in item or "name" in item, "Item should have name"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
