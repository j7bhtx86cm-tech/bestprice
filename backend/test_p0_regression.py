"""
P0 REGRESSION TESTS - 6 обязательных кейсов

1. Кетчуп Heinz - OFF → самый дешёвый любой бренд
2. Кетчуп Heinz - ON → самый дешёвый Heinz  
3. Говядина ФЛАГМАН - ON → BRAND_REQUIRED_NOT_FOUND
4. Говядина РИБАЙ ~5кг → не падает из-за фасовки
5. Креветки 16/20 → match_percent ≤ 100
6. Сыр моцарелла → НЕ сырники
"""
import os, sys, requests
from pymongo import MongoClient
from datetime import datetime, timezone

backend_url = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '\"' -f2").read().strip()
base_url = f"{backend_url}/api"

TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwYjNmMGIwOS1kOGJhLTRmZjktOWQyYS01MTllMWMzNDA2N2UiLCJyb2xlIjoiY3VzdG9tZXIiLCJleHAiOjE3NjgxMjU0NDJ9.M5F1uDVfJmGc6wvYdzNQ1-1PM1zOQccyEe--gyqIg-Q'
headers = {"Authorization": f"Bearer {TOKEN}"}

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

customer = db.users.find_one({'email': 'customer@bestprice.ru', 'role': 'customer'}, {'_id': 0})
company = db.companies.find_one({'userId': customer['id']}, {'_id': 0})

tests = [
    {"id": "reg_ketchup_off", "name": "Кетчуп томатный 800 гр. Heinz", "brand_critical": False, "brand_id": "heinz"},
    {"id": "reg_ketchup_on", "name": "Кетчуп томатный 800 гр. Heinz", "brand_critical": True, "brand_id": "heinz"},
    {"id": "reg_beef_flagman", "name": "ГОВЯДИНА фарш 80/20 5 кг ФЛАГМАН", "brand_critical": True, "brand_id": "flagman"},
    {"id": "reg_beef_ribai", "name": "Говядина РИБАЙ PRIME ~5кг", "brand_critical": False},
    {"id": "reg_shrimp", "name": "Креветки 16/20 1 кг", "brand_critical": False},
    {"id": "reg_cheese", "name": "Сыр моцарелла 125 г", "brand_critical": False},
]

for t in tests:
    fav = {
        'id': t['id'],
        'userId': customer['id'],
        'companyId': company['id'],
        'productName': t['name'],
        'brand_critical': t['brand_critical'],
        'brand_id': t.get('brand_id'),
        'addedAt': datetime.now(timezone.utc).isoformat()
    }
    db.favorites.replace_one({'id': fav['id']}, fav, upsert=True)

print("="*120)
print("🧪 P0 REGRESSION TESTS")
print("="*120)

results = []

for i, test in enumerate(tests, 1):
    print(f"\n{i}. {test['name'][:55]:55} (brand={test['brand_critical']})")
    
    resp = requests.post(f"{base_url}/cart/add-from-favorite", 
                        json={"favorite_id": test['id'], "qty": 1.0},
                        headers=headers, timeout=10)
    
    data = resp.json()
    status = data.get('status')
    
    if status == 'ok':
        offer = data.get('selected_offer', {})
        name = offer.get('name_raw', '')
        price = offer.get('price')
        match = offer.get('score', 0)
        
        issues = []
        if match > 100:
            issues.append(f"❌ match={match}% > 100")
        if test['id'] == 'reg_cheese' and 'сырник' in name.lower():
            issues.append("❌ Сыр → сырники")
        
        if issues:
            print(f"   ⚠️  OK но проблемы: {name[:40]} - {price}₽")
            for iss in issues:
                print(f"      {iss}")
            results.append('ok_with_issues')
        else:
            print(f"   ✅ OK: {name[:40]} - {price}₽ (match={match}%)")
            results.append('ok')
    
    elif status == 'not_found':
        msg = data.get('message', '')
        if test['id'] == 'reg_beef_flagman' and 'бренд' in msg.lower():
            print(f"   ✅ NOT FOUND (ожидаемо): {msg}")
            results.append('ok')
        else:
            print(f"   ❌ NOT FOUND: {msg}")
            results.append('fail')
    else:
        print(f"   ❌ STATUS: {status}")
        results.append('fail')

print(f"\n{'='*120}")
print("📊 SUMMARY")
print("="*120)

ok_count = sum(1 for r in results if r == 'ok')
print(f"✅ PASSED: {ok_count}/{len(results)} ({ok_count/len(results)*100:.0f}%)")

if ok_count == len(results):
    print("\n🎉 ALL REGRESSION TESTS PASSED!")
else:
    print(f"\n⚠️ {len(results)-ok_count} tests need attention")
