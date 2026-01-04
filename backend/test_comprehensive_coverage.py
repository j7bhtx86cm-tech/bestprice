"""
COMPREHENSIVE TEST: Favorites → Cart для разных категорий

Тестирует что v12 master работает не только для кетчупа, но и для:
- Мясо (говядина, свинина)
- Рыба (лосось, креветки, сибас)
- Молочка (сыр, молоко)
- Крупы (рис, мука)

Проверяет покрытие универсального маппера.
"""
import os
import sys
import requests

backend_url = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2 | tr -d '\"'").read().strip()
base_url = f"{backend_url}/api"

# Get token from env or create
TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwYjNmMGIwOS1kOGJhLTRmZjktOWQyYS01MTllMWMzNDA2N2UiLCJyb2xlIjoiY3VzdG9tZXIiLCJleHAiOjE3NjgxMjU0NDJ9.M5F1uDVfJmGc6wvYdzNQ1-1PM1zOQccyEe--gyqIg-Q'

headers = {"Authorization": f"Bearer {TOKEN}"}

# Create favorites for different categories
test_products = [
    {"name": "Кетчуп томатный 800 гр. Heinz", "category": "Condiments"},
    {"name": "Говядина фарш 80/20 5 кг", "category": "Meat"},
    {"name": "ЛОСОСЬ филе трим D Чили с/м вес 1.5 кг", "category": "Seafood"},
    {"name": "Креветки 16/20 варено-мороженые 1 кг", "category": "Seafood"},
    {"name": "СИБАС целый 300-400 гр", "category": "Seafood"},
    {"name": "Масло оливковое Extra Virgin 1 л", "category": "Staples"},
    {"name": "Мука пшеничная высший сорт 2 кг", "category": "Staples"},
    {"name": "Рис басмати 1 кг", "category": "Staples"},
    {"name": "Молоко 3.2% 1 л", "category": "Dairy"},
    {"name": "Сыр моцарелла 125 г", "category": "Dairy"}
]

print("="*100)
print("🧪 COMPREHENSIVE TEST: Favorites → Cart Coverage")
print("="*100)

results = []

for i, product in enumerate(test_products, 1):
    print(f"\n{i}. {product['name'][:50]:50} ({product['category']})")
    
    # Create favorite via DB (bypass POST /api/favorites bug)
    from pymongo import MongoClient
    from datetime import datetime, timezone
    
    mongo_url = os.environ.get('MONGO_URL')
    db_name = os.environ.get('DB_NAME')
    db = MongoClient(mongo_url)[db_name]
    
    customer = db.users.find_one({'email': 'customer@bestprice.ru', 'role': 'customer'}, {'_id': 0})
    
    if not customer:
        print("   ❌ Customer not found")
        continue
    
    fav_id = f"test_product_{i}"
    favorite = {
        'id': fav_id,
        'userId': customer['id'],
        'companyId': db.companies.find_one({'userId': customer['id']}, {'_id': 0}).get('id'),
        'productName': product['name'],
        'brand_critical': False,
        'addedAt': datetime.now(timezone.utc).isoformat()
    }
    
    db.favorites.replace_one({'id': fav_id}, favorite, upsert=True)
    
    # Test add-to-cart
    try:
        resp = requests.post(
            f"{base_url}/cart/add-from-favorite",
            json={"favorite_id": fav_id, "qty": 1.0},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code == 200:
            data = resp.json()
            status = data.get('status')
            
            if status == 'ok':
                offer = data.get('selected_offer', {})
                debug = data.get('debug_log', {})
                
                print(f"   ✅ OK: {offer.get('name_raw', '')[:40]} - {offer.get('price')}₽")
                print(f"      Candidates: {debug.get('after_super_class_filter', 0)}")
                
                results.append({'product': product['name'], 'status': 'ok', 'candidates': debug.get('after_super_class_filter', 0)})
            else:
                message = data.get('message', 'Unknown')
                print(f"   ❌ NOT FOUND: {message}")
                results.append({'product': product['name'], 'status': 'not_found', 'reason': message})
        else:
            print(f"   ❌ HTTP {resp.status_code}: {resp.text[:100]}")
            results.append({'product': product['name'], 'status': 'error', 'reason': resp.status_code})
            
    except Exception as e:
        print(f"   ❌ ERROR: {str(e)}")
        results.append({'product': product['name'], 'status': 'error', 'reason': str(e)})

# Summary
print(f"\n{'='*100}")
print("📊 SUMMARY")
print("="*100)

ok_count = sum(1 for r in results if r['status'] == 'ok')
not_found_count = sum(1 for r in results if r['status'] == 'not_found')
error_count = sum(1 for r in results if r['status'] == 'error')

print(f"\n✅ OK: {ok_count}/{len(results)} ({ok_count/len(results)*100:.1f}%)")
print(f"❌ NOT FOUND: {not_found_count}/{len(results)} ({not_found_count/len(results)*100:.1f}%)")
print(f"⚠️  ERROR: {error_count}/{len(results)} ({error_count/len(results)*100:.1f}%)")

if ok_count / len(results) >= 0.9:
    print(f"\n🎉 GOAL ACHIEVED: ≥90% coverage!")
else:
    print(f"\n⚠️  Need improvement: {ok_count/len(results)*100:.1f}% < 90%")

print(f"\n{'='*100}")
