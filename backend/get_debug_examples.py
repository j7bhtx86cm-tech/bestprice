"""
Создаёт 3 DEBUG примера с детальными counts по стадиям

Для понимания где именно ломается pipeline.
"""
import os
import sys
import json
import requests

backend_url = os.popen("grep REACT_APP_BACKEND_URL /app/frontend/.env | cut -d '=' -f2 | tr -d '\"'").read().strip()
base_url = f"{backend_url}/api"

TOKEN = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIwYjNmMGIwOS1kOGJhLTRmZjktOWQyYS01MTllMWMzNDA2N2UiLCJyb2xlIjoiY3VzdG9tZXIiLCJleHAiOjE3NjgxMjU0NDJ9.M5F1uDVfJmGc6wvYdzNQ1-1PM1zOQccyEe--gyqIg-Q'
headers = {"Authorization": f"Bearer {TOKEN}"}

# Create test favorites in DB for debug
from pymongo import MongoClient
from datetime import datetime, timezone

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

customer = db.users.find_one({'email': 'customer@bestprice.ru', 'role': 'customer'}, {'_id': 0})
company = db.companies.find_one({'userId': customer['id']}, {'_id': 0})

# 3 debug cases
debug_cases = [
    {"id": "debug_1_ok", "name": "Кетчуп томатный 800г Heinz", "brand_critical": False},
    {"id": "debug_2_not_found", "name": "ГОВЯДИНА РИБАЙ PRIME ~5кг", "brand_critical": False},
    {"id": "debug_3_brand_fail", "name": "Говядина фарш ФЛАГМАН 5кг", "brand_critical": True, "brand_id": "flagman"},
]

for case in debug_cases:
    fav = {
        'id': case['id'],
        'userId': customer['id'],
        'companyId': company['id'],
        'productName': case['name'],
        'brand_critical': case['brand_critical'],
        'brand_id': case.get('brand_id'),
        'addedAt': datetime.now(timezone.utc).isoformat()
    }
    db.favorites.replace_one({'id': fav['id']}, fav, upsert=True)

print("="*120)
print("🔍 DEBUG EXAMPLES - Детальные counts по стадиям")
print("="*120)

debug_results = []

for i, case in enumerate(debug_cases, 1):
    print(f"\n{i}. {case['name'][:60]}")
    print(f"   brand_critical={case['brand_critical']}, brand_id={case.get('brand_id', 'None')}")
    
    try:
        resp = requests.post(
            f"{base_url}/cart/add-from-favorite",
            json={"favorite_id": case['id'], "qty": 1.0},
            headers=headers,
            timeout=10
        )
        
        if resp.status_code == 200:
            data = resp.json()
            
            debug_info = {
                'case_id': case['id'],
                'reference_name': case['name'],
                'status': data.get('status'),
                'message': data.get('message', ''),
                'debug_log': data.get('debug_log', {}),
                'selected_offer': data.get('selected_offer')
            }
            
            debug_results.append(debug_info)
            
            print(f"   Status: {debug_info['status']}")
            
            if debug_info['status'] == 'ok':
                offer = debug_info['selected_offer']
                print(f"   ✅ Selected: {offer.get('name_raw', '')[:50]}")
                print(f"      Price: {offer.get('price')}₽")
                print(f"      match_percent: {offer.get('score')}%")
            
            # Print counts
            debug_log = debug_info['debug_log']
            if debug_log:
                print(f"\n   📊 Pipeline counts:")
                for key, value in debug_log.items():
                    if 'after' in key or 'rejected' in key or 'candidates' in key:
                        print(f"      {key}: {value}")
        else:
            print(f"   ❌ HTTP {resp.status_code}")
    
    except Exception as e:
        print(f"   ❌ Error: {str(e)}")

# Save debug results
with open('/app/backend/debug_examples.json', 'w', encoding='utf-8') as f:
    json.dump(debug_results, f, ensure_ascii=False, indent=2)

print(f"\n{'='*120}")
print(f"✅ Debug examples saved to: /app/backend/debug_examples.json")
print("="*120)
