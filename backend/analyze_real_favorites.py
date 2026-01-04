"""
ДЕТАЛЬНЫЙ АНАЛИЗ: Проверка РЕАЛЬНЫХ favorites

Тестирует все 18 существующих favorites из БД и показывает:
- Какие работают
- Какие падают и ПОЧЕМУ
- Детальные логи фильтрации
"""
import os
from pymongo import MongoClient
from universal_super_class_mapper import detect_super_class

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

print("="*120)
print("🔍 ДЕТАЛЬНЫЙ АНАЛИЗ РЕАЛЬНЫХ FAVORITES")
print("="*120)

# Get all favorites
favorites = list(db.favorites.find({}, {'_id': 0}))
print(f"\nВсего favorites: {len(favorites)}\n")

# Get all supplier_items
all_items = list(db.supplier_items.find({'active': True}, {'_id': 0}))

results = {
    'ok': [],
    'not_found': [],
    'insufficient_data': []
}

for i, fav in enumerate(favorites, 1):
    product_name = fav.get('productName', fav.get('reference_name', ''))
    brand_critical = fav.get('brand_critical', False)
    brand_id = fav.get('brand_id')
    pack_size = fav.get('pack_size')
    
    print(f"{i}. {product_name[:60]:60}")
    print(f"   brand_critical={brand_critical}, brand_id={brand_id}, pack_size={pack_size}")
    
    # Step 1: Detect super_class
    ref_super_class, confidence = detect_super_class(product_name)
    
    if not ref_super_class:
        print(f"   ❌ INSUFFICIENT_DATA: super_class не определён (confidence={confidence:.2f})")
        results['insufficient_data'].append({
            'name': product_name,
            'reason': 'super_class_not_detected',
            'confidence': confidence
        })
        print()
        continue
    
    print(f"   super_class: {ref_super_class} (confidence={confidence:.2f})")
    
    # Step 2: Filter by super_class
    step1 = [
        item for item in all_items
        if item.get('super_class') == ref_super_class
        and item.get('price', 0) > 0
    ]
    
    print(f"   После super_class filter: {len(step1)}")
    
    if len(step1) == 0:
        print(f"   ❌ NOT_FOUND: no_candidates_after_super_class_filter")
        results['not_found'].append({
            'name': product_name,
            'reason': 'no_candidates_after_super_class_filter',
            'ref_super_class': ref_super_class
        })
        print()
        continue
    
    # Step 3: Brand filter
    if brand_critical and brand_id:
        step2 = [item for item in step1 if item.get('brand_id') == brand_id]
        print(f"   После brand filter (brand_id={brand_id}): {len(step2)}")
    else:
        step2 = step1
        print(f"   Brand filter: SKIP")
    
    if len(step2) == 0:
        print(f"   ❌ NOT_FOUND: no_candidates_after_brand_filter")
        results['not_found'].append({
            'name': product_name,
            'reason': 'no_candidates_after_brand_filter',
            'brand_id': brand_id
        })
        print()
        continue
    
    # Step 4: Pack filter
    if pack_size:
        min_pack = pack_size * 0.8
        max_pack = pack_size * 1.2
        step3 = []
        for item in step2:
            item_pack = item.get('net_weight_kg') or item.get('net_volume_l')
            if item_pack and min_pack <= item_pack <= max_pack:
                step3.append(item)
        print(f"   После pack filter (±20% от {pack_size}): {len(step3)}")
    else:
        step3 = step2
        print(f"   Pack filter: SKIP")
    
    if len(step3) == 0:
        print(f"   ❌ NOT_FOUND: no_candidates_after_pack_filter")
        results['not_found'].append({
            'name': product_name,
            'reason': 'no_candidates_after_pack_filter',
            'pack_size': pack_size
        })
        print()
        continue
    
    # Step 5: Select winner
    step3.sort(key=lambda x: x.get('price', 999999))
    winner = step3[0]
    
    print(f"   ✅ OK: {winner.get('name_raw', '')[:50]}")
    print(f"      Price: {winner.get('price')}₽")
    print(f"      Brand: {winner.get('brand_id') or 'NONE'}")
    
    results['ok'].append({
        'name': product_name,
        'selected': winner.get('name_raw'),
        'price': winner.get('price'),
        'candidates': len(step3)
    })
    
    print()

# ==================== SUMMARY ====================
print("="*120)
print("📊 SUMMARY - РЕАЛЬНЫЕ FAVORITES")
print("="*120)

ok_count = len(results['ok'])
not_found_count = len(results['not_found'])
insufficient_count = len(results['insufficient_data'])
total_fav = len(favorites)

print(f"\n✅ OK:                  {ok_count:3}/{total_fav} ({ok_count/total_fav*100:5.1f}%)")
print(f"❌ NOT_FOUND:           {not_found_count:3}/{total_fav} ({not_found_count/total_fav*100:5.1f}%)")
print(f"⚠️  INSUFFICIENT_DATA:  {insufficient_count:3}/{total_fav} ({insufficient_count/total_fav*100:5.1f}%)")

if not_found_count > 0:
    print(f"\n📋 NOT_FOUND причины:")
    reason_counts = {}
    for item in results['not_found']:
        reason = item['reason']
        reason_counts[reason] = reason_counts.get(reason, 0) + 1
    
    for reason, count in reason_counts.items():
        print(f"   {reason:50} : {count}")

if insufficient_count > 0:
    print(f"\n⚠️  INSUFFICIENT_DATA примеры:")
    for item in results['insufficient_data'][:5]:
        print(f"   {item['name'][:60]} (confidence={item['confidence']:.2f})")

print(f"\n{'='*120}")
print("✅ Анализ завершён")
print("="*120)
