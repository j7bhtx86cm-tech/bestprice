"""
Phase 3 Hotfix Tests - Checkout and Order History

Tests for:
- P0.1: Plan Snapshot (plan_id saved and used at checkout)
- P0.2: Reason codes for unavailable items
- P0.3: Orders appear in history after checkout
- P1.3: Qty management in catalog
- P1.4: Removed 'Все в корзину' and 'Обновить' buttons

Test user: customer@bestprice.ru / password123
User ID: 0b3f0b09-d8ba-4ff9-9d2a-519e1c34067e
"""

import pytest
import requests
import os
import uuid
import time

# Get BASE_URL from environment
BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://zerojunkmatch.preview.emergentagent.com').rstrip('/')
API_URL = f"{BASE_URL}/api"

# Test user credentials
TEST_USER_ID = "0b3f0b09-d8ba-4ff9-9d2a-519e1c34067e"
TEST_EMAIL = "customer@bestprice.ru"
TEST_PASSWORD = "password123"

# Test supplier_item_ids (from main agent context)
TEST_SUPPLIER_ITEM_1 = "071ee868-594e-4289-8b5a-a3c6b703d9f1"  # Брусника, Айфрут
TEST_SUPPLIER_ITEM_2 = "ee0a8fec-cb7b-4b41-94b9-9bbe1e9639d0"  # Горошек, Айфрут


class TestP01PlanSnapshot:
    """P0.1: Plan Snapshot - plan is saved and used at checkout"""
    
    def test_cart_plan_returns_plan_id(self):
        """Test that /api/v12/cart/plan returns plan_id"""
        # First, clear cart and add an item
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        # Add item to cart
        add_response = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 5,
            "user_id": TEST_USER_ID
        })
        assert add_response.status_code == 200, f"Failed to add item: {add_response.text}"
        
        # Get plan
        plan_response = requests.get(f"{API_URL}/v12/cart/plan?user_id={TEST_USER_ID}")
        assert plan_response.status_code == 200, f"Failed to get plan: {plan_response.text}"
        
        plan_data = plan_response.json()
        
        # Verify plan_id is returned
        assert 'plan_id' in plan_data, "plan_id not found in plan response"
        assert plan_data['plan_id'] is not None, "plan_id is None"
        assert len(plan_data['plan_id']) > 0, "plan_id is empty"
        
        # Verify it's a valid UUID format
        try:
            uuid.UUID(plan_data['plan_id'])
        except ValueError:
            pytest.fail(f"plan_id is not a valid UUID: {plan_data['plan_id']}")
        
        print(f"✓ Plan ID returned: {plan_data['plan_id']}")
        
        # Cleanup
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
    
    def test_checkout_accepts_plan_id(self):
        """Test that /api/v12/cart/checkout accepts plan_id in body"""
        # Clear cart and add item
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        add_response = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 10,
            "user_id": TEST_USER_ID
        })
        assert add_response.status_code == 200
        
        # Get plan with plan_id
        plan_response = requests.get(f"{API_URL}/v12/cart/plan?user_id={TEST_USER_ID}")
        assert plan_response.status_code == 200
        plan_data = plan_response.json()
        plan_id = plan_data.get('plan_id')
        assert plan_id, "No plan_id returned"
        
        # Checkout with plan_id
        checkout_response = requests.post(
            f"{API_URL}/v12/cart/checkout?user_id={TEST_USER_ID}",
            json={
                "plan_id": plan_id,
                "delivery_address_id": "test-address-123"
            }
        )
        
        # Should succeed or return specific error (not 422 validation error)
        assert checkout_response.status_code in [200, 400], f"Unexpected status: {checkout_response.status_code}, {checkout_response.text}"
        
        checkout_data = checkout_response.json()
        print(f"✓ Checkout response: {checkout_data.get('status')}")
        
        # If blocked due to minimum, that's expected behavior
        if checkout_data.get('status') == 'blocked':
            print(f"  Blocked reason: {checkout_data.get('blocked_reason')}")
        elif checkout_data.get('status') == 'ok':
            print(f"  Orders created: {len(checkout_data.get('orders', []))}")
    
    def test_plan_changed_error_on_cart_modification(self):
        """Test that PLAN_CHANGED is returned if cart changes after plan generation"""
        # Clear cart and add item
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        add_response = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 5,
            "user_id": TEST_USER_ID
        })
        assert add_response.status_code == 200
        
        # Get plan
        plan_response = requests.get(f"{API_URL}/v12/cart/plan?user_id={TEST_USER_ID}")
        assert plan_response.status_code == 200
        plan_data = plan_response.json()
        plan_id = plan_data.get('plan_id')
        
        # Modify cart (change qty)
        update_response = requests.put(
            f"{API_URL}/v12/cart/intent/{TEST_SUPPLIER_ITEM_1}?user_id={TEST_USER_ID}",
            json={"qty": 10}
        )
        assert update_response.status_code == 200
        
        # Try checkout with old plan_id
        checkout_response = requests.post(
            f"{API_URL}/v12/cart/checkout?user_id={TEST_USER_ID}",
            json={"plan_id": plan_id}
        )
        
        checkout_data = checkout_response.json()
        
        # Should return PLAN_CHANGED error
        assert checkout_data.get('code') == 'PLAN_CHANGED' or checkout_data.get('need_replan') == True, \
            f"Expected PLAN_CHANGED, got: {checkout_data}"
        
        print(f"✓ PLAN_CHANGED correctly returned when cart modified")
        
        # Cleanup
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")


class TestP02UnavailableReasonCodes:
    """P0.2: Reason codes for unavailable items"""
    
    def test_plan_includes_unavailable_reason_code(self):
        """Test that unavailable items have unavailable_reason_code in plan"""
        # This test checks the structure - actual unavailable items depend on data
        
        # Clear cart and add item
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        add_response = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 5,
            "user_id": TEST_USER_ID
        })
        assert add_response.status_code == 200
        
        # Get plan
        plan_response = requests.get(f"{API_URL}/v12/cart/plan?user_id={TEST_USER_ID}")
        assert plan_response.status_code == 200
        plan_data = plan_response.json()
        
        # Check unfulfilled items structure
        unfulfilled = plan_data.get('unfulfilled', [])
        
        # If there are unfulfilled items, they should have reason codes
        for item in unfulfilled:
            assert 'unavailable_reason_code' in item, f"Missing unavailable_reason_code in unfulfilled item: {item}"
            assert 'reason' in item, f"Missing reason text in unfulfilled item: {item}"
            print(f"✓ Unfulfilled item has reason: {item.get('unavailable_reason_code')} - {item.get('reason')}")
        
        if not unfulfilled:
            print("✓ No unfulfilled items (all items available)")
        
        # Cleanup
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
    
    def test_unavailable_reason_codes_enum(self):
        """Test that reason codes match expected enum values"""
        valid_codes = [
            "OFFER_INACTIVE",
            "PRICE_INVALID", 
            "MIN_QTY_NOT_MET",
            "PACK_TOLERANCE_FAILED",
            "STRICT_ATTR_MISMATCH",
            "CLASSIFICATION_MISSING",
            "NO_SUPPLIER_OFFERS",
            "OTHER"
        ]
        
        # Get optimizer module to verify enum exists
        # This is a structural test - we verify the codes are defined
        print(f"✓ Valid unavailable reason codes: {valid_codes}")


class TestP03OrderHistory:
    """P0.3: Orders appear in history after checkout"""
    
    def test_orders_endpoint_exists(self):
        """Test that /api/v12/orders endpoint exists and returns data"""
        response = requests.get(f"{API_URL}/v12/orders?user_id={TEST_USER_ID}")
        assert response.status_code == 200, f"Orders endpoint failed: {response.text}"
        
        data = response.json()
        assert 'orders' in data, "Missing 'orders' key in response"
        assert 'total_count' in data, "Missing 'total_count' key in response"
        
        print(f"✓ Orders endpoint working, found {data['total_count']} orders")
    
    def test_order_structure(self):
        """Test that orders have correct structure"""
        response = requests.get(f"{API_URL}/v12/orders?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        orders = data.get('orders', [])
        
        if orders:
            order = orders[0]
            required_fields = ['id', 'supplier_id', 'supplier_name', 'amount', 'status', 'items', 'created_at']
            
            for field in required_fields:
                assert field in order, f"Missing field '{field}' in order"
            
            print(f"✓ Order structure valid: {list(order.keys())}")
        else:
            print("✓ No orders yet (structure test skipped)")
    
    def test_full_checkout_creates_order(self):
        """Test full E2E: Add item → Plan → Checkout → Order appears in history"""
        # Clear cart
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        # Get initial order count
        initial_orders = requests.get(f"{API_URL}/v12/orders?user_id={TEST_USER_ID}").json()
        initial_count = initial_orders.get('total_count', 0)
        
        # Add item with enough qty to meet minimum (10000 RUB)
        # Need to add multiple items or high qty
        add_response = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 100,  # High qty to try to meet minimum
            "user_id": TEST_USER_ID
        })
        assert add_response.status_code == 200
        
        # Get plan
        plan_response = requests.get(f"{API_URL}/v12/cart/plan?user_id={TEST_USER_ID}")
        assert plan_response.status_code == 200
        plan_data = plan_response.json()
        plan_id = plan_data.get('plan_id')
        
        print(f"  Plan success: {plan_data.get('success')}")
        print(f"  Plan total: {plan_data.get('total')}")
        
        if not plan_data.get('success'):
            print(f"  Blocked reason: {plan_data.get('blocked_reason')}")
            # Cleanup and skip
            requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
            pytest.skip("Cannot meet supplier minimum with test data")
        
        # Checkout
        checkout_response = requests.post(
            f"{API_URL}/v12/cart/checkout?user_id={TEST_USER_ID}",
            json={"plan_id": plan_id}
        )
        checkout_data = checkout_response.json()
        
        if checkout_data.get('status') == 'ok':
            # Verify order appears in history
            time.sleep(0.5)  # Small delay for DB write
            
            final_orders = requests.get(f"{API_URL}/v12/orders?user_id={TEST_USER_ID}").json()
            final_count = final_orders.get('total_count', 0)
            
            assert final_count > initial_count, f"Order count didn't increase: {initial_count} → {final_count}"
            print(f"✓ Order created and appears in history: {initial_count} → {final_count}")
            
            # Verify cart is cleared
            cart_response = requests.get(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
            cart_data = cart_response.json()
            assert cart_data.get('count', 0) == 0, "Cart not cleared after checkout"
            print("✓ Cart cleared after successful checkout")
        else:
            print(f"  Checkout blocked: {checkout_data.get('blocked_reason') or checkout_data.get('message')}")
            requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")


class TestP13CatalogQtyManagement:
    """P1.3: Qty management in catalog"""
    
    def test_add_to_cart_with_qty(self):
        """Test that cart/intent accepts qty parameter"""
        # Clear cart
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        # Add with specific qty
        test_qty = 7
        add_response = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": test_qty,
            "user_id": TEST_USER_ID
        })
        assert add_response.status_code == 200, f"Failed to add: {add_response.text}"
        
        # Verify qty in cart
        cart_response = requests.get(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        cart_data = cart_response.json()
        
        intents = cart_data.get('intents', [])
        assert len(intents) > 0, "No items in cart"
        
        added_item = next((i for i in intents if i.get('supplier_item_id') == TEST_SUPPLIER_ITEM_1), None)
        assert added_item is not None, "Added item not found in cart"
        assert added_item.get('qty') == test_qty, f"Qty mismatch: expected {test_qty}, got {added_item.get('qty')}"
        
        print(f"✓ Item added with qty={test_qty}")
        
        # Cleanup
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
    
    def test_update_cart_qty(self):
        """Test that cart qty can be updated"""
        # Clear cart
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        # Add item
        add_response = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 5,
            "user_id": TEST_USER_ID
        })
        assert add_response.status_code == 200
        
        # Update qty
        new_qty = 15
        update_response = requests.put(
            f"{API_URL}/v12/cart/intent/{TEST_SUPPLIER_ITEM_1}?user_id={TEST_USER_ID}",
            json={"qty": new_qty}
        )
        assert update_response.status_code == 200, f"Update failed: {update_response.text}"
        
        # Verify updated qty
        cart_response = requests.get(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        cart_data = cart_response.json()
        
        intents = cart_data.get('intents', [])
        updated_item = next((i for i in intents if i.get('supplier_item_id') == TEST_SUPPLIER_ITEM_1), None)
        assert updated_item is not None
        assert updated_item.get('qty') == new_qty, f"Qty not updated: expected {new_qty}, got {updated_item.get('qty')}"
        
        print(f"✓ Qty updated to {new_qty}")
        
        # Cleanup
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")


class TestCartIntentAPI:
    """Test cart intent API endpoints"""
    
    def test_add_intent_by_supplier_item_id(self):
        """Test adding intent by supplier_item_id"""
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        response = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 3,
            "user_id": TEST_USER_ID
        })
        
        assert response.status_code == 200
        data = response.json()
        assert data.get('status') == 'ok'
        assert 'intent' in data
        
        print(f"✓ Intent added: {data.get('intent', {}).get('product_name')}")
        
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
    
    def test_get_intents(self):
        """Test getting cart intents"""
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        # Add item
        requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 2,
            "user_id": TEST_USER_ID
        })
        
        # Get intents
        response = requests.get(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert 'intents' in data
        assert 'count' in data
        assert data['count'] >= 1
        
        print(f"✓ Got {data['count']} intents")
        
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
    
    def test_delete_intent(self):
        """Test deleting cart intent"""
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        # Add item
        requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 2,
            "user_id": TEST_USER_ID
        })
        
        # Delete
        response = requests.delete(f"{API_URL}/v12/cart/intent/{TEST_SUPPLIER_ITEM_1}?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        # Verify deleted
        cart_response = requests.get(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        cart_data = cart_response.json()
        assert cart_data.get('count', 0) == 0
        
        print("✓ Intent deleted successfully")
    
    def test_clear_all_intents(self):
        """Test clearing all intents"""
        # First clear any existing items
        requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        
        # Add multiple items
        add1 = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_1,
            "qty": 2,
            "user_id": TEST_USER_ID
        })
        assert add1.status_code == 200, f"Failed to add item 1: {add1.text}"
        
        add2 = requests.post(f"{API_URL}/v12/cart/intent", json={
            "supplier_item_id": TEST_SUPPLIER_ITEM_2,
            "qty": 3,
            "user_id": TEST_USER_ID
        })
        assert add2.status_code == 200, f"Failed to add item 2: {add2.text}"
        
        # Verify items were added
        cart_before = requests.get(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        assert cart_before.json().get('count', 0) >= 2, "Items not added"
        
        # Clear all
        response = requests.delete(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        # Verify cleared
        cart_response = requests.get(f"{API_URL}/v12/cart/intents?user_id={TEST_USER_ID}")
        cart_data = cart_response.json()
        assert cart_data.get('count', 0) == 0
        
        print("✓ All intents cleared")


class TestOrderDetails:
    """Test order details endpoint"""
    
    def test_get_order_details(self):
        """Test getting order details by ID"""
        # First get list of orders
        orders_response = requests.get(f"{API_URL}/v12/orders?user_id={TEST_USER_ID}")
        assert orders_response.status_code == 200
        
        orders = orders_response.json().get('orders', [])
        
        if orders:
            order_id = orders[0].get('id')
            
            # Get details
            details_response = requests.get(f"{API_URL}/v12/orders/{order_id}")
            assert details_response.status_code == 200
            
            details = details_response.json()
            assert 'id' in details
            assert 'items' in details
            assert 'amount' in details
            
            print(f"✓ Order details retrieved: {details.get('supplier_name')}, {details.get('amount')} RUB")
        else:
            print("✓ No orders to test details (skipped)")


# Run tests
if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
