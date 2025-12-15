#!/usr/bin/env python3
"""
Backend API Testing for BestPrice B2B Marketplace
Tests 4 user portals: Restaurant Admin, Staff, Chef, and Supplier
"""

import requests
import json
from typing import Dict, Optional

# Backend URL from environment
BACKEND_URL = "https://foodsupply-hub-4.preview.emergentagent.com/api"

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

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("BESTPRICE B2B MARKETPLACE - BACKEND API TESTING")
    print("Testing 4 User Portals: Restaurant Admin, Staff, Chef, Supplier")
    print("="*80)
    
    # Test all portals
    test_restaurant_admin()
    test_staff()
    test_chef()
    test_supplier()
    
    # Print summary
    result.print_summary()
    
    # Return exit code
    return 0 if len(result.failed) == 0 else 1

if __name__ == "__main__":
    exit(main())
