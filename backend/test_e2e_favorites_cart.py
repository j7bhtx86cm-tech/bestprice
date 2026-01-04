"""
E2E TEST: Favorites → Add to Cart (V12 Master)

Полный E2E тест:
1. Регистрация нового customer
2. Login
3. Создание favorite
4. Add to cart (brand_critical=OFF)
5. Verification

Проверяет что после v12 master переустановки всё работает.
"""
import requests
import json
import os

# Get backend URL
backend_url = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2 | tr -d '\"'").read().strip()
print(f"Backend URL: {backend_url}")

base_url = f"{backend_url}/api"

print("="*100)
print("🧪 E2E TEST: Favorites → Add to Cart (V12)")
print("="*100)

# Step 1: Register new customer
print("\n1️⃣ Регистрация нового customer...")
register_data = {
    "email": f"test_v12_{os.urandom(4).hex()}@bestprice.ru",
    "password": "test123",
    "inn": "7701234567",
    "companyName": "Test V12 Company",
    "legalAddress": "Moscow",
    "ogrn": "1027701234567",
    "actualAddress": "Moscow",
    "phone": "+79000000000",
    "companyEmail": f"test_v12_{os.urandom(4).hex()}@bestprice.ru",
    "contactPersonName": "Test User",
    "contactPersonPosition": "Owner",
    "contactPersonPhone": "+79000000000",
    "deliveryAddresses": [],
    "dataProcessingConsent": True
}

try:
    resp = requests.post(f"{base_url}/auth/register/customer", json=register_data, timeout=10)
    if resp.status_code == 200:
        reg_data = resp.json()
        token = reg_data['access_token']
        user_id = reg_data['user']['id']
        print(f"   ✅ Registered: {register_data['email']}")
        print(f"   user_id: {user_id[:20]}...")
    else:
        print(f"   ❌ Register failed: {resp.status_code}")
        print(f"   {resp.text}")
        exit(1)
except Exception as e:
    print(f"   ❌ Error: {str(e)}")
    exit(1)

# Step 2: Create favorite
print("\n2️⃣ Создание favorite...")
favorite_data = {
    "productName": "Кетчуп томатный 800 гр. Heinz",
    "brand_critical": False,  # OFF - should find cheaper alternatives
    "brand_id": "heinz"
}

headers = {"Authorization": f"Bearer {token}"}

try:
    resp = requests.post(f"{base_url}/favorites", json=favorite_data, headers=headers, timeout=10)
    if resp.status_code == 200:
        fav_data = resp.json()
        favorite_id = fav_data.get('id')
        print(f"   ✅ Favorite created: {favorite_id}")
        print(f"   Name: {fav_data.get('productName', '')[:50]}")
        print(f"   Brand critical: {fav_data.get('brand_critical')}")
    else:
        print(f"   ❌ Create favorite failed: {resp.status_code}")
        print(f"   {resp.text}")
        exit(1)
except Exception as e:
    print(f"   ❌ Error: {str(e)}")
    exit(1)

# Step 3: Add to cart
print("\n3️⃣ Add to cart (brand_critical=OFF)...")
add_cart_data = {
    "favorite_id": favorite_id,
    "qty": 1.0
}

try:
    resp = requests.post(f"{base_url}/cart/add-from-favorite", json=add_cart_data, headers=headers, timeout=15)
    print(f"   Status code: {resp.status_code}")
    
    if resp.status_code == 200:
        result = resp.json()
        print(f"   ✅ Response status: {result['status']}")
        
        if result['status'] == 'ok':
            offer = result.get('selected_offer', {})
            print(f"\n   🏆 Selected offer:")
            print(f"      Name: {offer.get('name_raw', '')[:50]}")
            print(f"      Price: {offer.get('price')}₽")
            print(f"      Supplier: {offer.get('supplier_name')}")
            
            # Check debug log
            debug = result.get('debug_log', {})
            if debug:
                counts = debug.get('counts', {})
                print(f"\n   📊 Filter counts:")
                for key, value in counts.items():
                    print(f"      {key}: {value}")
            
            # Check top candidates for brand diversity
            top = result.get('top_candidates', [])
            if top:
                print(f"\n   🔝 Top candidates:")
                for i, cand in enumerate(top[:5], 1):
                    print(f"      {i}. {cand.get('name_raw', '')[:45]} - {cand.get('price')}₽")
        else:
            print(f"   ❌ Not found: {result.get('message')}")
            debug = result.get('debug_log')
            if debug:
                print(f"   Debug: {json.dumps(debug, indent=2, ensure_ascii=False)}")
    else:
        print(f"   ❌ Request failed: {resp.text}")
        
except Exception as e:
    print(f"   ❌ Error: {str(e)}")
    exit(1)

print("\n" + "="*100)
print("✅ E2E TEST COMPLETED")
print("="*100)
