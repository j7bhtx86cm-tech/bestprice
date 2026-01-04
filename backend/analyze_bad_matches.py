"""
АНАЛИЗ ПЛОХИХ МАТЧЕЙ - ДО и ПОСЛЕ фикса

Показывает конкретные примеры где система выбирает неправильный товар
и что можно улучшить.
"""
import os
from pymongo import MongoClient
from universal_super_class_mapper import detect_super_class

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

print("="*120)
print("🔍 АНАЛИЗ 'ПЛОХИХ МАТЧЕЙ' - Детальный Разбор")
print("="*120)

all_items = list(db.supplier_items.find({'active': True}, {'_id': 0}))

# Тестовые кейсы, которые ПОТЕНЦИАЛЬНО могут давать плохие матчи
test_cases = [
    {"name": "Говядина фарш 80/20 5 кг", "expected_avoid": "растительн"},
    {"name": "Сыр моцарелла 125 г", "expected_avoid": "сырник"},
    {"name": "Креветки 16/20 1 кг", "expected_avoid": "без креветк"},
    {"name": "Кетчуп томатный 800 гр", "expected_avoid": "вода|майонез"},
    {"name": "Лосось филе 1.5 кг", "expected_avoid": "ягн|свин|курица"},
]

print(f"\nПроверяю {len(test_cases)} потенциально проблемных кейсов...\n")

bad_matches = []
good_matches = []

for test in test_cases:
    product_name = test['name']
    avoid_pattern = test['expected_avoid']
    
    # Detect super_class
    ref_super_class, conf = detect_super_class(product_name)
    
    if not ref_super_class:
        continue
    
    # Find candidates
    candidates = [i for i in all_items 
                 if i.get('super_class') == ref_super_class 
                 and i.get('price', 0) > 0]
    
    # Fallback
    if len(candidates) == 0:
        import re
        ref_keywords = {w for w in re.findall(r'\w+', product_name.lower()) if len(w) >= 4}
        
        for item in all_items:
            if item.get('super_class') == 'other':
                cand_keywords = set(re.findall(r'\w+', (item.get('name_raw') or '').lower()))
                if len(ref_keywords & cand_keywords) >= 2:
                    candidates.append(item)
    
    if not candidates:
        continue
    
    # Sort by price
    candidates.sort(key=lambda x: x.get('price', 999999))
    winner = candidates[0]
    winner_name = winner.get('name_raw', '').lower()
    
    # Check if bad match
    import re
    is_bad = bool(re.search(avoid_pattern, winner_name, re.IGNORECASE))
    
    match_info = {
        'reference': product_name,
        'ref_super_class': ref_super_class,
        'selected': winner.get('name_raw'),
        'selected_super_class': winner.get('super_class'),
        'price': winner.get('price'),
        'candidates_count': len(candidates),
        'is_bad_match': is_bad,
        'avoid_pattern': avoid_pattern
    }
    
    if is_bad:
        bad_matches.append(match_info)
    else:
        good_matches.append(match_info)

# Print results
print(f"={'='*120}")
print(f"РЕЗУЛЬТАТЫ АНАЛИЗА")
print(f"={'='*120}")

print(f"\n❌ ПЛОХИЕ МАТЧИ ({len(bad_matches)}):\n")
if bad_matches:
    for i, m in enumerate(bad_matches, 1):
        print(f"{i}. Reference: {m['reference']}")
        print(f"   → Selected: {m['selected'][:70]}")
        print(f"   super_class: {m['ref_super_class']} → {m['selected_super_class']}")
        print(f"   Price: {m['price']}₽")
        print(f"   Проблема: содержит '{m['avoid_pattern']}'")
        print(f"   Кандидатов было: {m['candidates_count']}")
        print()
else:
    print(f"   ✅ Не найдено! Все матчи корректные.")

print(f"\n✅ ХОРОШИЕ МАТЧИ ({len(good_matches)}):\n")
for i, m in enumerate(good_matches[:10], 1):
    print(f"{i}. {m['reference'][:40]:40} → {m['selected'][:40]:40} ({m['price']}₽)")

# Recommendations
print(f"\n{'='*120}")
print(f"💡 РЕКОМЕНДАЦИИ ДЛЯ УСТРАНЕНИЯ ПЛОХИХ МАТЧЕЙ")
print(f"={'='*120}")

if bad_matches:
    print(f"\nДля исправления {len(bad_matches)} плохих матчей:")
    
    for i, m in enumerate(bad_matches, 1):
        print(f"\n{i}. {m['reference']}")
        
        if 'говядина' in m['reference'].lower() and 'растительн' in m['selected'].lower():
            print(f"   Проблема: meat.beef содержит растительные продукты")
            print(f"   Решение: Добавить negative keywords ['растительн', 'веган', 'соев']")
            print(f"   Или создать отдельную категорию meat.substitute")
        
        elif 'сыр' in m['reference'].lower() and 'сырник' in m['selected'].lower():
            print(f"   Проблема: dairy.сыр включает сырники (готовый продукт)")
            print(f"   Решение: Создать dairy.сырники или prepared_food.syrniki")
        
        elif 'креветк' in m['reference'].lower() and 'креветк' not in m['selected'].lower():
            print(f"   Проблема: seafood.shrimp включает панировки без креветок")
            print(f"   Решение: Добавить anchor token validation - требовать 'креветк' в названии")
else:
    print(f"\n✅ Плохих матчей не обнаружено!")
    print(f"   Система работает корректно для всех проверенных категорий")

print(f"\n{'='*120}")
print(f"✅ Анализ завершён")
print(f"={'='*120}")
