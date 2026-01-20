"""
Iteration 11 Tests - Optimizer Price, Classification, Lemma Index, UI Price Indicator

Tests:
1. Optimizer - икра лососевая за 5724₽ должна находить замену за ту же цену, не за 213₽
2. API plan - должен возвращать original_price для каждого item
3. Поиск по lemma_tokens - проверить что индекс создан и работает
4. Классификатор - икра лососевая должна быть seafood.caviar, не seafood.salmon
"""

import pytest
import requests
import os
from pymongo import MongoClient

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://optimizer-pro.preview.emergentagent.com').rstrip('/')

# Test credentials
TEST_EMAIL = "customer@bestprice.ru"
TEST_PASSWORD = "password123"
TEST_USER_ID = "0b3f0b09-d8ba-4ff9-9d2a-519e1c34067e"


@pytest.fixture(scope="module")
def auth_token():
    """Get authentication token"""
    response = requests.post(f"{BASE_URL}/api/auth/login", json={
        "email": TEST_EMAIL,
        "password": TEST_PASSWORD
    })
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip("Authentication failed - skipping authenticated tests")


@pytest.fixture(scope="module")
def api_client(auth_token):
    """Shared requests session with auth"""
    session = requests.Session()
    session.headers.update({
        "Content-Type": "application/json",
        "Authorization": f"Bearer {auth_token}"
    })
    return session


@pytest.fixture(scope="module")
def db():
    """MongoDB connection for direct verification"""
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    client = MongoClient(mongo_url)
    return client[db_name]


class TestOptimizerPriceCorrectness:
    """Test 1: Optimizer should find replacement at same price, not 213₽"""
    
    def test_cart_intents_has_caviar(self, api_client):
        """Verify cart has caviar item"""
        response = api_client.get(f"{BASE_URL}/api/v12/cart/intents?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        intents = data.get('intents', [])
        
        # Find caviar item
        caviar_items = [i for i in intents if 'икра' in i.get('product_name', '').lower()]
        
        if not caviar_items:
            pytest.skip("No caviar in cart - add caviar first")
        
        caviar = caviar_items[0]
        print(f"Found caviar: {caviar.get('product_name')}")
        print(f"Price: {caviar.get('price')}₽")
        
        # Price should be around 5724, not 213
        assert caviar.get('price', 0) > 1000, f"Caviar price too low: {caviar.get('price')}₽"
    
    def test_plan_returns_correct_price(self, api_client):
        """Verify plan returns correct price for caviar (5724₽, not 213₽)"""
        response = api_client.get(f"{BASE_URL}/api/v12/cart/plan?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        
        # Find caviar in plan
        all_items = []
        for supplier in data.get('suppliers', []):
            all_items.extend(supplier.get('items', []))
        
        caviar_items = [i for i in all_items if 'икра' in i.get('product_name', '').lower()]
        
        if not caviar_items:
            pytest.skip("No caviar in plan")
        
        caviar = caviar_items[0]
        price = caviar.get('price', 0)
        
        print(f"Plan caviar price: {price}₽")
        
        # CRITICAL: Price should be ~5724, not 213
        assert price > 1000, f"Optimizer returned wrong price: {price}₽ (expected ~5724₽)"
        assert price < 10000, f"Price too high: {price}₽"


class TestOriginalPriceInPlan:
    """Test 2: API plan should return original_price for each item"""
    
    def test_plan_has_original_price_field(self, api_client):
        """Verify plan items have original_price field"""
        response = api_client.get(f"{BASE_URL}/api/v12/cart/plan?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        
        for supplier in data.get('suppliers', []):
            for item in supplier.get('items', []):
                assert 'original_price' in item, f"Missing original_price in item: {item.get('product_name')}"
                print(f"Item: {item.get('product_name')[:40]}")
                print(f"  price: {item.get('price')}₽, original_price: {item.get('original_price')}₽")
    
    def test_original_price_matches_intent_price(self, api_client):
        """Verify original_price matches what user added to cart"""
        # Get intents
        intents_response = api_client.get(f"{BASE_URL}/api/v12/cart/intents?user_id={TEST_USER_ID}")
        intents = intents_response.json().get('intents', [])
        
        # Get plan
        plan_response = api_client.get(f"{BASE_URL}/api/v12/cart/plan?user_id={TEST_USER_ID}")
        plan = plan_response.json()
        
        # Build intent price map
        intent_prices = {}
        for intent in intents:
            item_id = intent.get('supplier_item_id')
            if item_id:
                intent_prices[item_id] = intent.get('price', 0)
        
        # Check plan items
        for supplier in plan.get('suppliers', []):
            for item in supplier.get('items', []):
                original_price = item.get('original_price', 0)
                item_id = item.get('supplier_item_id')
                
                if item_id in intent_prices:
                    expected = intent_prices[item_id]
                    assert abs(original_price - expected) < 0.01, \
                        f"original_price mismatch: {original_price} vs intent {expected}"


class TestLemmaTokensIndex:
    """Test 3: Verify lemma_tokens index exists and works"""
    
    def test_lemma_tokens_index_exists(self, db):
        """Verify lemma_tokens index is created"""
        indexes = list(db.supplier_items.list_indexes())
        index_names = [idx['name'] for idx in indexes]
        
        # Check for lemma_tokens index
        has_lemma_index = any('lemma' in name.lower() for name in index_names)
        assert has_lemma_index, f"No lemma_tokens index found. Indexes: {index_names}"
        
        print(f"Found indexes: {index_names}")
    
    def test_items_have_lemma_tokens(self, db):
        """Verify items have lemma_tokens populated"""
        with_lemma = db.supplier_items.count_documents({
            'lemma_tokens': {'$exists': True, '$ne': []}
        })
        total = db.supplier_items.count_documents({})
        
        print(f"Items with lemma_tokens: {with_lemma}/{total}")
        
        # At least 90% should have lemma_tokens
        coverage = with_lemma / total if total > 0 else 0
        assert coverage > 0.9, f"Low lemma_tokens coverage: {coverage*100:.1f}%"
    
    def test_search_uses_lemma_tokens(self, api_client):
        """Verify search works with morphology (singular/plural)"""
        # Search for "лосось" (singular)
        response1 = api_client.get(f"{BASE_URL}/api/v12/catalog?search=лосось&limit=5")
        assert response1.status_code == 200
        items1 = response1.json().get('items', [])
        
        # Search for "лососевая" (adjective form)
        response2 = api_client.get(f"{BASE_URL}/api/v12/catalog?search=лососевая&limit=5")
        assert response2.status_code == 200
        items2 = response2.json().get('items', [])
        
        print(f"'лосось' results: {len(items1)}")
        print(f"'лососевая' results: {len(items2)}")
        
        # Both should return results
        assert len(items1) > 0 or len(items2) > 0, "Search not working"


class TestCaviarClassification:
    """Test 4: Verify caviar is classified as seafood.caviar, not seafood.salmon"""
    
    def test_caviar_classification_in_db(self, db):
        """Verify caviar items have correct classification"""
        # Find caviar items
        caviar_items = list(db.supplier_items.find(
            {
                'active': True,
                'name_norm': {'$regex': 'икр.*лосос|лосос.*икр', '$options': 'i'}
            },
            {'_id': 0, 'name_raw': 1, 'product_core_id': 1, 'super_class': 1}
        ).limit(10))
        
        print(f"Found {len(caviar_items)} caviar items")
        
        for item in caviar_items:
            name = item.get('name_raw', '')[:50]
            core_id = item.get('product_core_id', '')
            super_class = item.get('super_class', '')
            
            print(f"  {name}")
            print(f"    product_core_id: {core_id}")
            print(f"    super_class: {super_class}")
            
            # Should be seafood.caviar, NOT seafood.salmon
            if 'икра' in name.lower():
                assert 'salmon' not in core_id.lower(), \
                    f"Caviar wrongly classified as salmon: {name}"
                # Ideally should be caviar
                if core_id:
                    assert 'caviar' in core_id.lower() or 'икра' in core_id.lower() or 'seafood' in core_id.lower(), \
                        f"Caviar has unexpected classification: {core_id}"
    
    def test_cart_caviar_has_correct_class(self, api_client):
        """Verify caviar in cart has correct super_class"""
        response = api_client.get(f"{BASE_URL}/api/v12/cart/intents?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        intents = response.json().get('intents', [])
        caviar_items = [i for i in intents if 'икра' in i.get('product_name', '').lower()]
        
        for caviar in caviar_items:
            super_class = caviar.get('super_class', '')
            print(f"Caviar super_class: {super_class}")
            
            # Should be seafood.caviar
            assert 'salmon' not in super_class.lower(), \
                f"Caviar wrongly classified as salmon: {super_class}"


class TestPriceChangeIndicator:
    """Test 5: Verify price change indicator data is available"""
    
    def test_plan_has_price_data_for_indicator(self, api_client):
        """Verify plan has both price and original_price for UI indicator"""
        response = api_client.get(f"{BASE_URL}/api/v12/cart/plan?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        
        for supplier in data.get('suppliers', []):
            for item in supplier.get('items', []):
                price = item.get('price')
                original_price = item.get('original_price')
                
                assert price is not None, "Missing price"
                assert original_price is not None, "Missing original_price"
                
                # Calculate change percentage
                if original_price and original_price > 0:
                    change = abs((price - original_price) / original_price)
                    print(f"Item: {item.get('product_name', '')[:40]}")
                    print(f"  Price change: {change*100:.1f}%")
                    
                    # If change > 25%, UI should show indicator
                    if change > 0.25:
                        print(f"  → Should show price change indicator!")


class TestOptimizerFlags:
    """Test 6: Verify optimizer flags are correct"""
    
    def test_plan_has_expected_flags(self, api_client):
        """Verify plan items have appropriate flags"""
        response = api_client.get(f"{BASE_URL}/api/v12/cart/plan?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        
        for supplier in data.get('suppliers', []):
            for item in supplier.get('items', []):
                flags = item.get('flags', [])
                print(f"Item: {item.get('product_name', '')[:40]}")
                print(f"  Flags: {flags}")
                
                # Verify flag consistency
                if item.get('supplier_changed'):
                    assert 'SUPPLIER_CHANGED' in flags, "Missing SUPPLIER_CHANGED flag"
                
                if item.get('qty_changed_by_topup'):
                    assert 'AUTO_TOPUP_10PCT' in flags, "Missing AUTO_TOPUP_10PCT flag"


class TestAPIEndpoints:
    """Test 7: Verify all required API endpoints work"""
    
    def test_catalog_endpoint(self, api_client):
        """Verify catalog endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/v12/catalog?limit=5")
        assert response.status_code == 200
        
        data = response.json()
        assert 'items' in data
        assert 'total' in data
        print(f"Catalog total: {data.get('total')}")
    
    def test_cart_intents_endpoint(self, api_client):
        """Verify cart intents endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/v12/cart/intents?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert 'intents' in data
        print(f"Cart intents: {data.get('count')}")
    
    def test_cart_plan_endpoint(self, api_client):
        """Verify cart plan endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/v12/cart/plan?user_id={TEST_USER_ID}")
        assert response.status_code == 200
        
        data = response.json()
        assert 'suppliers' in data
        assert 'total' in data
        assert 'plan_id' in data
        print(f"Plan total: {data.get('total')}₽")
    
    def test_diagnostics_endpoint(self, api_client):
        """Verify diagnostics endpoint works"""
        response = api_client.get(f"{BASE_URL}/api/v12/diagnostics")
        assert response.status_code == 200
        
        data = response.json()
        print(f"Diagnostics: {data}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
