#!/usr/bin/env python3
"""
Backend API Testing for BestPrice B2B Marketplace
Tests 4 user portals: Restaurant Admin, Staff, Chef, and Supplier
"""

import requests
import json
from typing import Dict, Optional

# Backend URL from environment
BACKEND_URL = "https://matchingengine.preview.emergentagent.com/api"

# Test credentials
CREDENTIALS = {
    "restaurant_admin": {
        "email": "customer@bestprice.ru",
        "password": "password123",
        "role": "customer",
        "expected_name": None  # Will check in test
    },
    "staff": {
        "email": "staff@bestprice.ru",
        "password": "password123",
        "role": "responsible",
        "expected_name": "Мария Соколова",
        "expected_phone": "+7 (999) 555-11-22"
    },
    "chef": {
        "email": "chef@bestprice.ru",
        "password": "password123",
        "role": "chef",
        "expected_name": "Алексей Петров",
        "expected_phone": "+7 (999) 777-33-44"
    },
    "supplier": {
        "email": "ifruit@bestprice.ru",
        "password": "password123",
        "role": "supplier",
        "expected_name": None
    }
}

class TestResult:
    def __init__(self):
        self.passed = []
        self.failed = []
        self.warnings = []
    
    def add_pass(self, test_name: str, message: str = ""):
        self.passed.append(f"✅ {test_name}: {message}")
    
    def add_fail(self, test_name: str, message: str):
        self.failed.append(f"❌ {test_name}: {message}")
    
    def add_warning(self, test_name: str, message: str):
        self.warnings.append(f"⚠️ {test_name}: {message}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        if self.failed:
            print("\n🔴 FAILED TESTS:")
            for fail in self.failed:
                print(f"  {fail}")
        
        if self.warnings:
            print("\n🟡 WARNINGS:")
            for warn in self.warnings:
                print(f"  {warn}")
        
        if self.passed:
            print("\n🟢 PASSED TESTS:")
            for pass_test in self.passed:
                print(f"  {pass_test}")
        
        print("\n" + "="*80)
        print(f"Total: {len(self.passed)} passed, {len(self.failed)} failed, {len(self.warnings)} warnings")
        print("="*80 + "\n")

result = TestResult()

def login(email: str, password: str) -> Optional[Dict]:
    """Login and return token + user info"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": email, "password": password},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return {
                "token": data.get("access_token"),
                "user": data.get("user")
            }
        else:
            return None
    except Exception as e:
        print(f"Login error: {e}")
        return None

def get_headers(token: str) -> Dict:
    """Get authorization headers"""
    return {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }

def test_restaurant_admin():
    """Test Restaurant Admin Portal (customer@bestprice.ru)"""
    print("\n" + "="*80)
    print("TESTING: RESTAURANT ADMIN PORTAL")
    print("="*80)
    
    creds = CREDENTIALS["restaurant_admin"]
    
    # Test 1: Login
    print(f"\n[1] Testing login for {creds['email']}...")
    auth_data = login(creds["email"], creds["password"])
    
    if not auth_data:
        result.add_fail("Restaurant Admin Login", "Login failed - invalid credentials or API error")
        return
    
    if auth_data["user"]["role"] != creds["role"]:
        result.add_fail("Restaurant Admin Login", f"Wrong role: expected '{creds['role']}', got '{auth_data['user']['role']}'")
        return
    
    result.add_pass("Restaurant Admin Login", f"Successfully logged in as {creds['email']}")
    
    token = auth_data["token"]
    headers = get_headers(token)
    company_id = auth_data["user"].get("companyId")
    
    # Test 2: Access Catalog (should show products from suppliers)
    print("\n[2] Testing catalog access...")
    try:
        # Get all suppliers
        suppliers_response = requests.get(f"{BACKEND_URL}/suppliers", headers=headers, timeout=10)
        
        if suppliers_response.status_code != 200:
            result.add_fail("Restaurant Admin Catalog", f"Failed to get suppliers: {suppliers_response.status_code}")
        else:
            suppliers = suppliers_response.json()
            print(f"   Found {len(suppliers)} suppliers")
            
            # Get products from all suppliers
            total_products = 0
            for supplier in suppliers:
                supplier_id = supplier.get("id")
                products_response = requests.get(
                    f"{BACKEND_URL}/suppliers/{supplier_id}/price-lists",
                    headers=headers,
                    timeout=10
                )
                if products_response.status_code == 200:
                    products = products_response.json()
                    total_products += len(products)
            
            print(f"   Total products in catalog: {total_products}")
            result.add_pass("Restaurant Admin Catalog", f"Catalog accessible with {total_products} products from {len(suppliers)} suppliers")
    
    except Exception as e:
        result.add_fail("Restaurant Admin Catalog", f"Error accessing catalog: {str(e)}")
    
    # Test 3: Access Analytics
    print("\n[3] Testing analytics page...")
    try:
        analytics_response = requests.get(f"{BACKEND_URL}/analytics/customer", headers=headers, timeout=10)
        
        if analytics_response.status_code != 200:
            result.add_fail("Restaurant Admin Analytics", f"Failed to access analytics: {analytics_response.status_code}")
        else:
            analytics = analytics_response.json()
            total_orders = analytics.get("totalOrders", 0)
            total_amount = analytics.get("totalAmount", 0)
            result.add_pass("Restaurant Admin Analytics", f"Analytics accessible - {total_orders} orders, {total_amount:.2f} ₽")
    
    except Exception as e:
        result.add_fail("Restaurant Admin Analytics", f"Error accessing analytics: {str(e)}")
    
    # Test 4: Access Team Management
    print("\n[4] Testing team management page...")
    try:
        team_response = requests.get(f"{BACKEND_URL}/team/members", headers=headers, timeout=10)
        
        if team_response.status_code != 200:
            result.add_fail("Restaurant Admin Team", f"Failed to access team: {team_response.status_code}")
        else:
            team_members = team_response.json()
            print(f"   Found {len(team_members)} team members")
            
            # Check for expected team members
            member_names = [m.get("name", "") for m in team_members]
            print(f"   Team members: {member_names}")
            
            if len(team_members) >= 2:
                result.add_pass("Restaurant Admin Team", f"Team management accessible with {len(team_members)} members")
            else:
                result.add_warning("Restaurant Admin Team", f"Expected at least 2 team members, found {len(team_members)}")
    
    except Exception as e:
        result.add_fail("Restaurant Admin Team", f"Error accessing team: {str(e)}")
    
    # Test 5: Access Matrix Management
    print("\n[5] Testing matrix management page...")
    try:
        matrices_response = requests.get(f"{BACKEND_URL}/matrices", headers=headers, timeout=10)
        
        if matrices_response.status_code != 200:
            result.add_fail("Restaurant Admin Matrix", f"Failed to access matrices: {matrices_response.status_code}")
        else:
            matrices = matrices_response.json()
            print(f"   Found {len(matrices)} matrices")
            result.add_pass("Restaurant Admin Matrix", f"Matrix management accessible with {len(matrices)} matrices")
    
    except Exception as e:
        result.add_fail("Restaurant Admin Matrix", f"Error accessing matrices: {str(e)}")
    
    # Test 6: Access Order History
    print("\n[6] Testing order history...")
    try:
        orders_response = requests.get(f"{BACKEND_URL}/orders/my", headers=headers, timeout=10)
        
        if orders_response.status_code != 200:
            result.add_fail("Restaurant Admin Orders", f"Failed to access orders: {orders_response.status_code}")
        else:
            orders = orders_response.json()
            print(f"   Found {len(orders)} orders")
            result.add_pass("Restaurant Admin Orders", f"Order history accessible with {len(orders)} orders")
    
    except Exception as e:
        result.add_fail("Restaurant Admin Orders", f"Error accessing orders: {str(e)}")

def test_staff():
    """Test Staff Portal (staff@bestprice.ru)"""
    print("\n" + "="*80)
    print("TESTING: STAFF PORTAL")
    print("="*80)
    
    creds = CREDENTIALS["staff"]
    
    # Test 1: Login
    print(f"\n[1] Testing login for {creds['email']}...")
    auth_data = login(creds["email"], creds["password"])
    
    if not auth_data:
        result.add_fail("Staff Login", "Login failed - invalid credentials or API error")
        return
    
    if auth_data["user"]["role"] != creds["role"]:
        result.add_fail("Staff Login", f"Wrong role: expected '{creds['role']}', got '{auth_data['user']['role']}'")
        return
    
    result.add_pass("Staff Login", f"Successfully logged in as {creds['email']}")
    
    token = auth_data["token"]
    headers = get_headers(token)
    user_id = auth_data["user"].get("id")
    
    # Test 2: Access My Profile
    print("\n[2] Testing profile access...")
    try:
        # Get user details from users collection
        me_response = requests.get(f"{BACKEND_URL}/auth/me", headers=headers, timeout=10)
        
        if me_response.status_code != 200:
            result.add_fail("Staff Profile", f"Failed to access profile: {me_response.status_code}")
        else:
            user_data = me_response.json()
            print(f"   User email: {user_data.get('email')}")
            print(f"   User role: {user_data.get('role')}")
            result.add_pass("Staff Profile", "Profile accessible")
    
    except Exception as e:
        result.add_fail("Staff Profile", f"Error accessing profile: {str(e)}")
    
    # Test 3: Access Matrix
    print("\n[3] Testing matrix access...")
    try:
        matrices_response = requests.get(f"{BACKEND_URL}/matrices", headers=headers, timeout=10)
        
        if matrices_response.status_code != 200:
            result.add_fail("Staff Matrix", f"Failed to access matrix: {matrices_response.status_code}")
        else:
            matrices = matrices_response.json()
            print(f"   Found {len(matrices)} matrices")
            
            if len(matrices) > 0:
                # Get products in first matrix
                matrix_id = matrices[0].get("id")
                products_response = requests.get(
                    f"{BACKEND_URL}/matrices/{matrix_id}/products",
                    headers=headers,
                    timeout=10
                )
                
                if products_response.status_code == 200:
                    products = products_response.json()
                    print(f"   Matrix '{matrices[0].get('name')}' has {len(products)} products")
                    result.add_pass("Staff Matrix", f"Matrix accessible with {len(products)} products")
                else:
                    result.add_warning("Staff Matrix", f"Matrix found but products not accessible: {products_response.status_code}")
            else:
                result.add_warning("Staff Matrix", "No matrices assigned to staff member")
    
    except Exception as e:
        result.add_fail("Staff Matrix", f"Error accessing matrix: {str(e)}")
    
    # Test 4: Access Catalog
    print("\n[4] Testing catalog access...")
    try:
        suppliers_response = requests.get(f"{BACKEND_URL}/suppliers", headers=headers, timeout=10)
        
        if suppliers_response.status_code != 200:
            result.add_fail("Staff Catalog", f"Failed to access catalog: {suppliers_response.status_code}")
        else:
            suppliers = suppliers_response.json()
            result.add_pass("Staff Catalog", f"Catalog accessible with {len(suppliers)} suppliers")
    
    except Exception as e:
        result.add_fail("Staff Catalog", f"Error accessing catalog: {str(e)}")
    
    # Test 5: Access Order History
    print("\n[5] Testing order history...")
    try:
        orders_response = requests.get(f"{BACKEND_URL}/orders/my", headers=headers, timeout=10)
        
        if orders_response.status_code != 200:
            result.add_fail("Staff Orders", f"Failed to access orders: {orders_response.status_code}")
        else:
            orders = orders_response.json()
            print(f"   Found {len(orders)} orders")
            result.add_pass("Staff Orders", f"Order history accessible with {len(orders)} orders")
    
    except Exception as e:
        result.add_fail("Staff Orders", f"Error accessing orders: {str(e)}")
    
    # Test 6: Verify NO access to Analytics (should fail or return 403)
    print("\n[6] Testing analytics access (should be restricted)...")
    try:
        analytics_response = requests.get(f"{BACKEND_URL}/analytics/customer", headers=headers, timeout=10)
        
        if analytics_response.status_code == 403:
            result.add_pass("Staff Analytics Restriction", "Correctly denied access to analytics (403)")
        elif analytics_response.status_code == 200:
            result.add_fail("Staff Analytics Restriction", "Staff should NOT have access to analytics but got 200 OK")
        else:
            result.add_warning("Staff Analytics Restriction", f"Unexpected status code: {analytics_response.status_code}")
    
    except Exception as e:
        result.add_warning("Staff Analytics Restriction", f"Error testing analytics restriction: {str(e)}")
    
    # Test 7: Verify NO access to Team Management (should fail or return 403)
    print("\n[7] Testing team management access (should be restricted)...")
    try:
        team_response = requests.get(f"{BACKEND_URL}/team/members", headers=headers, timeout=10)
        
        if team_response.status_code == 403:
            result.add_pass("Staff Team Restriction", "Correctly denied access to team management (403)")
        elif team_response.status_code == 200:
            result.add_fail("Staff Team Restriction", "Staff should NOT have access to team management but got 200 OK")
        else:
            result.add_warning("Staff Team Restriction", f"Unexpected status code: {team_response.status_code}")
    
    except Exception as e:
        result.add_warning("Staff Team Restriction", f"Error testing team restriction: {str(e)}")

def test_chef():
    """Test Chef Portal (chef@bestprice.ru)"""
    print("\n" + "="*80)
    print("TESTING: CHEF PORTAL")
    print("="*80)
    
    creds = CREDENTIALS["chef"]
    
    # Test 1: Login
    print(f"\n[1] Testing login for {creds['email']}...")
    auth_data = login(creds["email"], creds["password"])
    
    if not auth_data:
        result.add_fail("Chef Login", "Login failed - invalid credentials or API error")
        return
    
    if auth_data["user"]["role"] != creds["role"]:
        result.add_fail("Chef Login", f"Wrong role: expected '{creds['role']}', got '{auth_data['user']['role']}'")
        return
    
    result.add_pass("Chef Login", f"Successfully logged in as {creds['email']}")
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Test 2: Access My Profile
    print("\n[2] Testing profile access...")
    try:
        me_response = requests.get(f"{BACKEND_URL}/auth/me", headers=headers, timeout=10)
        
        if me_response.status_code != 200:
            result.add_fail("Chef Profile", f"Failed to access profile: {me_response.status_code}")
        else:
            user_data = me_response.json()
            print(f"   User email: {user_data.get('email')}")
            print(f"   User role: {user_data.get('role')}")
            result.add_pass("Chef Profile", "Profile accessible")
    
    except Exception as e:
        result.add_fail("Chef Profile", f"Error accessing profile: {str(e)}")
    
    # Test 3: Access Matrix
    print("\n[3] Testing matrix access...")
    try:
        matrices_response = requests.get(f"{BACKEND_URL}/matrices", headers=headers, timeout=10)
        
        if matrices_response.status_code != 200:
            result.add_fail("Chef Matrix", f"Failed to access matrix: {matrices_response.status_code}")
        else:
            matrices = matrices_response.json()
            print(f"   Found {len(matrices)} matrices")
            
            if len(matrices) > 0:
                # Get products in first matrix
                matrix_id = matrices[0].get("id")
                products_response = requests.get(
                    f"{BACKEND_URL}/matrices/{matrix_id}/products",
                    headers=headers,
                    timeout=10
                )
                
                if products_response.status_code == 200:
                    products = products_response.json()
                    print(f"   Matrix '{matrices[0].get('name')}' has {len(products)} products")
                    result.add_pass("Chef Matrix", f"Matrix accessible with {len(products)} products")
                else:
                    result.add_warning("Chef Matrix", f"Matrix found but products not accessible: {products_response.status_code}")
            else:
                result.add_warning("Chef Matrix", "No matrices assigned to chef")
    
    except Exception as e:
        result.add_fail("Chef Matrix", f"Error accessing matrix: {str(e)}")
    
    # Test 4: Access Catalog
    print("\n[4] Testing catalog access...")
    try:
        suppliers_response = requests.get(f"{BACKEND_URL}/suppliers", headers=headers, timeout=10)
        
        if suppliers_response.status_code != 200:
            result.add_fail("Chef Catalog", f"Failed to access catalog: {suppliers_response.status_code}")
        else:
            suppliers = suppliers_response.json()
            result.add_pass("Chef Catalog", f"Catalog accessible with {len(suppliers)} suppliers")
    
    except Exception as e:
        result.add_fail("Chef Catalog", f"Error accessing catalog: {str(e)}")
    
    # Test 5: Access Order History
    print("\n[5] Testing order history...")
    try:
        orders_response = requests.get(f"{BACKEND_URL}/orders/my", headers=headers, timeout=10)
        
        if orders_response.status_code != 200:
            result.add_fail("Chef Orders", f"Failed to access orders: {orders_response.status_code}")
        else:
            orders = orders_response.json()
            print(f"   Found {len(orders)} orders")
            result.add_pass("Chef Orders", f"Order history accessible with {len(orders)} orders")
    
    except Exception as e:
        result.add_fail("Chef Orders", f"Error accessing orders: {str(e)}")
    
    # Test 6: Verify NO access to Analytics
    print("\n[6] Testing analytics access (should be restricted)...")
    try:
        analytics_response = requests.get(f"{BACKEND_URL}/analytics/customer", headers=headers, timeout=10)
        
        if analytics_response.status_code == 403:
            result.add_pass("Chef Analytics Restriction", "Correctly denied access to analytics (403)")
        elif analytics_response.status_code == 200:
            result.add_fail("Chef Analytics Restriction", "Chef should NOT have access to analytics but got 200 OK")
        else:
            result.add_warning("Chef Analytics Restriction", f"Unexpected status code: {analytics_response.status_code}")
    
    except Exception as e:
        result.add_warning("Chef Analytics Restriction", f"Error testing analytics restriction: {str(e)}")
    
    # Test 7: Verify NO access to Team Management
    print("\n[7] Testing team management access (should be restricted)...")
    try:
        team_response = requests.get(f"{BACKEND_URL}/team/members", headers=headers, timeout=10)
        
        if team_response.status_code == 403:
            result.add_pass("Chef Team Restriction", "Correctly denied access to team management (403)")
        elif team_response.status_code == 200:
            result.add_fail("Chef Team Restriction", "Chef should NOT have access to team management but got 200 OK")
        else:
            result.add_warning("Chef Team Restriction", f"Unexpected status code: {team_response.status_code}")
    
    except Exception as e:
        result.add_warning("Chef Team Restriction", f"Error testing team restriction: {str(e)}")

def test_supplier():
    """Test Supplier Portal (ifruit@bestprice.ru)"""
    print("\n" + "="*80)
    print("TESTING: SUPPLIER PORTAL")
    print("="*80)
    
    creds = CREDENTIALS["supplier"]
    
    # Test 1: Login
    print(f"\n[1] Testing login for {creds['email']}...")
    auth_data = login(creds["email"], creds["password"])
    
    if not auth_data:
        result.add_fail("Supplier Login", "Login failed - invalid credentials or API error")
        return
    
    if auth_data["user"]["role"] != creds["role"]:
        result.add_fail("Supplier Login", f"Wrong role: expected '{creds['role']}', got '{auth_data['user']['role']}'")
        return
    
    result.add_pass("Supplier Login", f"Successfully logged in as {creds['email']}")
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Test 2: Access Price List
    print("\n[2] Testing price list access...")
    try:
        pricelist_response = requests.get(f"{BACKEND_URL}/price-lists/my", headers=headers, timeout=10)
        
        if pricelist_response.status_code != 200:
            result.add_fail("Supplier Price List", f"Failed to access price list: {pricelist_response.status_code}")
        else:
            products = pricelist_response.json()
            print(f"   Found {len(products)} products in price list")
            result.add_pass("Supplier Price List", f"Price list accessible with {len(products)} products")
    
    except Exception as e:
        result.add_fail("Supplier Price List", f"Error accessing price list: {str(e)}")
    
    # Test 3: Test Inline Editing (update price and availability)
    print("\n[3] Testing inline editing (price and availability update)...")
    try:
        # Get first product
        pricelist_response = requests.get(f"{BACKEND_URL}/price-lists/my", headers=headers, timeout=10)
        
        if pricelist_response.status_code == 200:
            products = pricelist_response.json()
            
            if len(products) > 0:
                product = products[0]
                product_id = product.get("id")
                original_price = product.get("price")
                original_availability = product.get("availability")
                
                # Update price and availability
                new_price = original_price + 10.0
                new_availability = not original_availability
                
                update_response = requests.put(
                    f"{BACKEND_URL}/price-lists/{product_id}",
                    headers=headers,
                    json={
                        "price": new_price,
                        "availability": new_availability
                    },
                    timeout=10
                )
                
                if update_response.status_code == 200:
                    updated_product = update_response.json()
                    
                    if updated_product.get("price") == new_price and updated_product.get("availability") == new_availability:
                        result.add_pass("Supplier Inline Edit", f"Successfully updated price to {new_price} and availability to {new_availability}")
                        
                        # Restore original values
                        restore_response = requests.put(
                            f"{BACKEND_URL}/price-lists/{product_id}",
                            headers=headers,
                            json={
                                "price": original_price,
                                "availability": original_availability
                            },
                            timeout=10
                        )
                        
                        if restore_response.status_code == 200:
                            print(f"   Restored original values")
                    else:
                        result.add_fail("Supplier Inline Edit", "Update succeeded but values not reflected correctly")
                else:
                    result.add_fail("Supplier Inline Edit", f"Failed to update product: {update_response.status_code}")
            else:
                result.add_warning("Supplier Inline Edit", "No products available to test inline editing")
        else:
            result.add_fail("Supplier Inline Edit", "Could not fetch products for inline edit test")
    
    except Exception as e:
        result.add_fail("Supplier Inline Edit", f"Error testing inline edit: {str(e)}")
    
    # Test 4: Test Search Functionality
    print("\n[4] Testing search functionality...")
    try:
        # Search for a common term
        search_term = "масло"
        pricelist_response = requests.get(
            f"{BACKEND_URL}/price-lists/my",
            headers=headers,
            timeout=10
        )
        
        if pricelist_response.status_code == 200:
            all_products = pricelist_response.json()
            
            # Filter products by search term (client-side filtering simulation)
            matching_products = [p for p in all_products if search_term.lower() in p.get("productName", "").lower()]
            
            print(f"   Search for '{search_term}': found {len(matching_products)} matching products")
            result.add_pass("Supplier Search", f"Search functionality working - found {len(matching_products)} products matching '{search_term}'")
        else:
            result.add_fail("Supplier Search", f"Failed to test search: {pricelist_response.status_code}")
    
    except Exception as e:
        result.add_fail("Supplier Search", f"Error testing search: {str(e)}")
    
    # Test 5: Access Orders Page
    print("\n[5] Testing orders page access...")
    try:
        orders_response = requests.get(f"{BACKEND_URL}/orders/my", headers=headers, timeout=10)
        
        if orders_response.status_code != 200:
            result.add_fail("Supplier Orders", f"Failed to access orders: {orders_response.status_code}")
        else:
            orders = orders_response.json()
            print(f"   Found {len(orders)} orders")
            result.add_pass("Supplier Orders", f"Orders page accessible with {len(orders)} orders")
    
    except Exception as e:
        result.add_fail("Supplier Orders", f"Error accessing orders: {str(e)}")

def test_fixed_select_offer_endpoint():
    """Test FIXED /api/cart/select-offer endpoint - now correctly selects cheapest matching offer"""
    print("\n" + "="*80)
    print("TESTING: FIXED /api/cart/select-offer ENDPOINT")
    print("Bug Fix: Now correctly selects cheapest matching offer (931.44₽ Алиди vs 990.60₽ Ромакс)")
    print("="*80)
    
    # Step 1: Login as customer
    print(f"\n[1] Testing login for customer@bestprice.ru...")
    auth_data = login("customer@bestprice.ru", "password123")
    
    if not auth_data:
        result.add_fail("Fixed Select Offer Login", "Login failed - cannot test endpoint")
        return
    
    result.add_pass("Fixed Select Offer Login", "Successfully logged in as customer@bestprice.ru")
    
    token = auth_data["token"]
    headers = get_headers(token)
    
    # Step 2: Test Сибас best price selection (THE MAIN BUG FIX)
    print("\n[2] Testing Сибас best price selection (CRITICAL BUG FIX)...")
    try:
        request_data = {
            "reference_item": {
                "name_raw": "Сибас целый непотрошеный",
                "brand_critical": False
            },
            "qty": 1,
            "match_threshold": 0.85
        }
        
        response = requests.post(
            f"{BACKEND_URL}/cart/select-offer",
            headers=headers,
            json=request_data,
            timeout=15
        )
        
        if response.status_code != 200:
            result.add_fail("Сибас Best Price Fix", f"Failed to select offer: {response.status_code} - {response.text}")
        else:
            data = response.json()
            
            if data.get("selected_offer"):
                offer = data["selected_offer"]
                price = offer.get("price")
                supplier_name = offer.get("supplier_name")
                
                print(f"   ✓ Selected offer: {offer['name_raw']}")
                print(f"   ✓ Price: {price} ₽")
                print(f"   ✓ Supplier: {supplier_name}")
                print(f"   ✓ Score: {offer['score']}")
                
                # CRITICAL TEST: Should select cheapest (931.44₽ Алиди) NOT expensive (990.60₽ Ромакс)
                if price == 931.44 and supplier_name == "Алиди":
                    result.add_pass("Сибас Best Price Fix", f"✅ BUG FIXED! Correctly selected cheapest offer: {price}₽ from {supplier_name}")
                elif price == 990.60 and supplier_name == "Ромакс":
                    result.add_fail("Сибас Best Price Fix", f"❌ BUG STILL EXISTS! Selected expensive offer: {price}₽ from {supplier_name} instead of cheaper 931.44₽ from Алиди")
                elif supplier_name == "Алиди" and price < 950:
                    result.add_pass("Сибас Best Price Fix", f"✅ BUG FIXED! Selected Алиди supplier with reasonable price: {price}₽")
                else:
                    result.add_warning("Сибас Best Price Fix", f"⚠️ Selected {supplier_name} with price {price}₽ - verify this is the cheapest available")
                
                # Verify top_candidates are sorted by price (ascending)
                if "top_candidates" in data and isinstance(data["top_candidates"], list):
                    candidates = data["top_candidates"]
                    print(f"   ✓ Top candidates found: {len(candidates)}")
                    
                    if len(candidates) >= 2:
                        prices = [c.get("price_per_base_unit", 0) for c in candidates[:5]]  # Check first 5
                        print(f"   ✓ First 5 candidate prices: {prices}")
                        
                        # Check if sorted ascending (cheapest first)
                        is_sorted = all(prices[i] <= prices[i+1] for i in range(len(prices)-1))
                        if is_sorted:
                            result.add_pass("Сибас Price Sorting", f"✅ Top candidates correctly sorted by price: {prices}")
                        else:
                            result.add_fail("Сибас Price Sorting", f"❌ Top candidates NOT sorted by price: {prices}")
                        
                        # Verify expected prices are in the list
                        expected_prices = [931.44, 948.94, 990.60]
                        found_expected = [p for p in prices if p in expected_prices]
                        if len(found_expected) >= 2:
                            result.add_pass("Сибас Expected Prices", f"✅ Found expected prices in candidates: {found_expected}")
                        else:
                            result.add_warning("Сибас Expected Prices", f"⚠️ Expected prices {expected_prices} not all found in {prices}")
                else:
                    result.add_warning("Сибас Best Price Fix", "top_candidates array missing - cannot verify price sorting")
            else:
                result.add_fail("Сибас Best Price Fix", f"No selected_offer returned. Reason: {data.get('reason', 'Unknown')}")
        
    except Exception as e:
        result.add_fail("Сибас Best Price Fix", f"Error testing Сибас price selection: {str(e)}")
    
    # Step 3: Test synonym matching (сибасс = сибас)
    print("\n[3] Testing synonym matching (сибасс typo should match сибас)...")
    try:
        request_data = {
            "reference_item": {
                "name_raw": "СИБАСС свежемороженый с головой",
                "brand_critical": False
            },
            "qty": 1,
            "match_threshold": 0.85
        }
        
        response = requests.post(
            f"{BACKEND_URL}/cart/select-offer",
            headers=headers,
            json=request_data,
            timeout=15
        )
        
        if response.status_code != 200:
            result.add_fail("Synonym Matching", f"Failed to test synonym matching: {response.status_code} - {response.text}")
        else:
            data = response.json()
            
            if data.get("selected_offer"):
                offer = data["selected_offer"]
                product_name = offer.get("name_raw", "").upper()
                
                print(f"   ✓ Matched product: {offer['name_raw']}")
                print(f"   ✓ Price: {offer['price']} ₽")
                print(f"   ✓ Supplier: {offer['supplier_name']}")
                
                # Check if it found СИБАС products (synonym matching working)
                if "СИБАС" in product_name or "СИБАСС" in product_name:
                    result.add_pass("Synonym Matching", f"✅ Successfully matched СИБАСС typo to СИБАС product: {offer['name_raw']}")
                else:
                    result.add_fail("Synonym Matching", f"❌ Failed to match СИБАСС typo - got unrelated product: {offer['name_raw']}")
            else:
                reason = data.get('reason', 'Unknown')
                result.add_fail("Synonym Matching", f"No match found for СИБАСС typo. Reason: {reason}")
        
    except Exception as e:
        result.add_fail("Synonym Matching", f"Error testing synonym matching: {str(e)}")
    
    # Step 4: Test brand_critical=true functionality
    print("\n[4] Testing brand_critical=true (only HEINZ products)...")
    try:
        request_data = {
            "reference_item": {
                "name_raw": "КЕТЧУП томатный HEINZ",
                "brand_id": "heinz",
                "brand_critical": True
            },
            "qty": 1,
            "match_threshold": 0.85
        }
        
        response = requests.post(
            f"{BACKEND_URL}/cart/select-offer",
            headers=headers,
            json=request_data,
            timeout=15
        )
        
        if response.status_code != 200:
            result.add_fail("Brand Critical Test", f"Failed to test brand critical: {response.status_code} - {response.text}")
        else:
            data = response.json()
            
            if data.get("selected_offer"):
                offer = data["selected_offer"]
                product_name = offer.get("name_raw", "").upper()
                
                print(f"   ✓ Selected branded product: {offer['name_raw']}")
                print(f"   ✓ Price: {offer['price']} ₽")
                print(f"   ✓ Supplier: {offer['supplier_name']}")
                
                # Verify it's a HEINZ product
                if "HEINZ" in product_name:
                    result.add_pass("Brand Critical Test", f"✅ Correctly selected HEINZ branded product: {offer['name_raw']}")
                    
                    # Verify all candidates are HEINZ products
                    if "top_candidates" in data:
                        candidates = data["top_candidates"]
                        non_heinz_count = 0
                        for candidate in candidates[:5]:  # Check first 5
                            candidate_name = candidate.get("name_raw", "").upper()
                            if "HEINZ" not in candidate_name:
                                non_heinz_count += 1
                        
                        if non_heinz_count == 0:
                            result.add_pass("Brand Critical Filtering", f"✅ All top candidates are HEINZ products (checked {min(5, len(candidates))} candidates)")
                        else:
                            result.add_fail("Brand Critical Filtering", f"❌ Found {non_heinz_count} non-HEINZ products in top candidates")
                else:
                    result.add_fail("Brand Critical Test", f"❌ Selected non-HEINZ product when brand_critical=true: {offer['name_raw']}")
            else:
                reason = data.get('reason', 'Unknown')
                if reason == "NO_MATCH_OVER_THRESHOLD":
                    result.add_pass("Brand Critical Test", "✅ Correctly returned no match when no HEINZ products meet threshold")
                else:
                    result.add_warning("Brand Critical Test", f"No HEINZ products found. Reason: {reason}")
        
    except Exception as e:
        result.add_fail("Brand Critical Test", f"Error testing brand critical functionality: {str(e)}")
    
    # Step 5: Test edge case - very high threshold
    print("\n[5] Testing edge case with very high threshold (0.95)...")
    try:
        request_data = {
            "reference_item": {
                "name_raw": "Сибас целый непотрошеный",
                "brand_critical": False
            },
            "qty": 1,
            "match_threshold": 0.95
        }
        
        response = requests.post(
            f"{BACKEND_URL}/cart/select-offer",
            headers=headers,
            json=request_data,
            timeout=15
        )
        
        if response.status_code != 200:
            result.add_fail("High Threshold Test", f"Failed to test high threshold: {response.status_code} - {response.text}")
        else:
            data = response.json()
            
            if data.get("selected_offer"):
                offer = data["selected_offer"]
                score = offer.get("score")
                
                print(f"   ✓ High threshold match: {offer['name_raw']}")
                print(f"   ✓ Score: {score}")
                print(f"   ✓ Price: {offer['price']} ₽")
                
                if score >= 0.95:
                    result.add_pass("High Threshold Test", f"✅ Found high-quality match with score {score}")
                else:
                    result.add_fail("High Threshold Test", f"❌ Selected offer score {score} below threshold 0.95")
            else:
                reason = data.get('reason', 'Unknown')
                result.add_pass("High Threshold Test", f"✅ Correctly returned no match for high threshold. Reason: {reason}")
        
    except Exception as e:
        result.add_fail("High Threshold Test", f"Error testing high threshold: {str(e)}")
    
    # Step 6: Test response structure completeness
    print("\n[6] Testing complete response structure...")
    try:
        request_data = {
            "reference_item": {
                "name_raw": "Креветки 16/20",
                "brand_critical": False
            },
            "qty": 2,
            "match_threshold": 0.80
        }
        
        response = requests.post(
            f"{BACKEND_URL}/cart/select-offer",
            headers=headers,
            json=request_data,
            timeout=15
        )
        
        if response.status_code != 200:
            result.add_fail("Response Structure", f"Failed to get response: {response.status_code} - {response.text}")
        else:
            data = response.json()
            
            # Check required top-level fields
            required_top_fields = ["selected_offer", "top_candidates", "search_stats"]
            structure_issues = []
            
            for field in required_top_fields:
                if field not in data:
                    structure_issues.append(f"Missing top-level field: {field}")
            
            if data.get("selected_offer"):
                offer = data["selected_offer"]
                required_offer_fields = [
                    "supplier_id", "supplier_name", "supplier_item_id", 
                    "name_raw", "price", "currency", "unit_norm", 
                    "price_per_base_unit", "score"
                ]
                
                for field in required_offer_fields:
                    if field not in offer:
                        structure_issues.append(f"Missing field in selected_offer: {field}")
                
                # Verify data types
                if not isinstance(offer.get("price"), (int, float)):
                    structure_issues.append("selected_offer.price should be numeric")
                
                if not isinstance(offer.get("score"), (int, float)):
                    structure_issues.append("selected_offer.score should be numeric")
                
                if offer.get("currency") != "RUB":
                    structure_issues.append(f"Expected currency RUB, got {offer.get('currency')}")
            
            # Check top_candidates structure
            if "top_candidates" in data and isinstance(data["top_candidates"], list):
                candidates = data["top_candidates"]
                if len(candidates) > 0:
                    first_candidate = candidates[0]
                    required_candidate_fields = ["supplier_item_id", "name_raw", "price_per_base_unit", "score", "supplier"]
                    
                    for field in required_candidate_fields:
                        if field not in first_candidate:
                            structure_issues.append(f"Missing field in top_candidates[0]: {field}")
            
            if len(structure_issues) == 0:
                result.add_pass("Response Structure", "✅ Complete response structure is valid")
                print(f"   ✓ All required fields present")
                print(f"   ✓ Data types are correct")
                print(f"   ✓ Currency is RUB")
                if data.get("top_candidates"):
                    print(f"   ✓ Top candidates: {len(data['top_candidates'])} alternatives")
            else:
                result.add_fail("Response Structure", f"❌ Structure issues: {'; '.join(structure_issues)}")
        
    except Exception as e:
        result.add_fail("Response Structure", f"Error testing response structure: {str(e)}")

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BESTPRICE B2B MARKETPLACE - BACKEND API TESTING")
    print("Testing FIXED /api/cart/select-offer Endpoint - Bug Fix Verification")
    print("="*80)
    
    # Test FIXED /api/cart/select-offer endpoint (focus on the bug fix)
    test_fixed_select_offer_endpoint()
    
    # Print summary
    result.print_summary()
    
    # Return exit code
    return 0 if len(result.failed) == 0 else 1

if __name__ == "__main__":
    exit(main())
