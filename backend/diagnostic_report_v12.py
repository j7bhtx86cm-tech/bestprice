"""
ДИАГНОСТИЧЕСКИЙ ОТЧЁТ - V12 Master Post-Import Analysis

Анализирует текущее состояние системы после внедрения v12:
1. Coverage по supplier_items (core, pack, brand, origin)
2. Статистика по favorites (если есть)
3. Примеры проблемных кейсов
4. Рекомендации по улучшению

БЕЗ ИСПРАВЛЕНИЙ - только сбор данных.
"""
import os
import sys
from pymongo import MongoClient
from collections import Counter
import json

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

print("="*120)
print("📊 ДИАГНОСТИЧЕСКИЙ ОТЧЁТ V12 - POST-IMPORT ANALYSIS")
print("="*120)

# ==================== 1) COVERAGE REPORT ====================
print("\n" + "="*120)
print("1️⃣ COVERAGE ОТЧЁТ ПО SUPPLIER_ITEMS (ACTIVE позиции)")
print("="*120)

all_items = list(db.supplier_items.find({'active': True}, {'_id': 0}))
total = len(all_items)

print(f"\nВсего ACTIVE supplier_items: {total}")

# Core coverage
with_super_class = sum(1 for item in all_items if item.get('super_class') and item.get('super_class') != 'other')
with_other = sum(1 for item in all_items if item.get('super_class') == 'other')

print(f"\n📋 Core Coverage:")
print(f"   С определённой категорией (super_class): {with_super_class:5} ({with_super_class/total*100:5.1f}%)")
print(f"   Категория 'other' (неопределено):        {with_other:5} ({with_other/total*100:5.1f}%)")
print(f"   БЕЗ super_class (null):                   {total-with_super_class-with_other:5} ({(total-with_super_class-with_other)/total*100:5.1f}%)")

# Pack coverage
with_pack = sum(1 for item in all_items if (item.get('net_weight_kg') or item.get('net_volume_l')))
print(f"\n📦 Pack Coverage:")
print(f"   С pack (net_weight_kg or net_volume_l):  {with_pack:5} ({with_pack/total*100:5.1f}%)")
print(f"   БЕЗ pack:                                 {total-with_pack:5} ({(total-with_pack)/total*100:5.1f}%)")

# Price per base unit
with_price_base = sum(1 for item in all_items if item.get('price_per_base_unit'))
print(f"\n💰 Price per Base Unit Coverage:")
print(f"   С price_per_base_unit:                   {with_price_base:5} ({with_price_base/total*100:5.1f}%)")
print(f"   БЕЗ price_per_base_unit:                 {total-with_price_base:5} ({(total-with_price_base)/total*100:5.1f}%)")

# Brand coverage
with_brand = sum(1 for item in all_items if item.get('brand_id'))
print(f"\n🏷️  Brand Coverage:")
print(f"   С brand_id:                              {with_brand:5} ({with_brand/total*100:5.1f}%)")
print(f"   БЕЗ brand_id (no brand):                 {total-with_brand:5} ({(total-with_brand)/total*100:5.1f}%)")

# Origin coverage
with_origin = sum(1 for item in all_items if item.get('origin_country'))
fresh_keywords = ['рыб', 'мяс', 'птиц', 'морепродукт', 'seafood', 'meat', 'fish']
fresh_items = [item for item in all_items 
               if any(kw in (item.get('name_norm', '')).lower() for kw in fresh_keywords)]
fresh_with_origin = sum(1 for item in fresh_items if item.get('origin_country'))

print(f"\n🌍 Origin Coverage:")
print(f"   Всего с origin_country:                  {with_origin:5} ({with_origin/total*100:5.1f}%)")
if fresh_items:
    print(f"   Fresh items (мясо/рыба):                 {len(fresh_items):5}")
    print(f"   Fresh с origin:                          {fresh_with_origin:5} ({fresh_with_origin/len(fresh_items)*100:5.1f}%)")

# ==================== 2) TOP SUPER_CLASS DISTRIBUTION ====================
print(f"\n{'='*120}")
print("2️⃣ РАСПРЕДЕЛЕНИЕ ПО КАТЕГОРИЯМ (TOP 30 super_class)")
print("="*120)

super_classes = [item.get('super_class') for item in all_items if item.get('super_class')]
super_class_counts = Counter(super_classes)

print(f"\nВсего уникальных категорий: {len(super_class_counts)}\n")
print(f"{'Категория':40} | {'Кол-во':>8} | {'% от total':>10} | Pack% | Brand%")
print("-" * 120)

for super_class, count in super_class_counts.most_common(30):
    items_in_class = [item for item in all_items if item.get('super_class') == super_class]
    pack_pct = sum(1 for i in items_in_class if (i.get('net_weight_kg') or i.get('net_volume_l'))) / len(items_in_class) * 100 if items_in_class else 0
    brand_pct = sum(1 for i in items_in_class if i.get('brand_id')) / len(items_in_class) * 100 if items_in_class else 0
    
    print(f"{super_class:40} | {count:8} | {count/total*100:9.1f}% | {pack_pct:4.0f}% | {brand_pct:4.0f}%")

# ==================== 3) CATEGORIES WITHOUT PACK ====================
print(f"\n{'='*120}")
print("3️⃣ КАТЕГОРИИ С НИЗКИМ PACK COVERAGE (<50%)")
print("="*120)

low_pack_categories = []
for super_class, count in super_class_counts.most_common(50):
    if count < 10:  # Skip small categories
        continue
    items_in_class = [item for item in all_items if item.get('super_class') == super_class]
    pack_pct = sum(1 for i in items_in_class if (i.get('net_weight_kg') or i.get('net_volume_l'))) / len(items_in_class) * 100
    
    if pack_pct < 50:
        low_pack_categories.append({
            'super_class': super_class,
            'count': count,
            'pack_coverage': pack_pct
        })

if low_pack_categories:
    print(f"\nНайдено {len(low_pack_categories)} категорий с pack coverage <50%:\n")
    for cat in low_pack_categories[:15]:
        print(f"   {cat['super_class']:40} : {cat['count']:4} items, {cat['pack_coverage']:5.1f}% pack")
else:
    print("\n✅ Все категории имеют pack coverage ≥50%")

# ==================== 4) SAMPLE: OTHER CATEGORY ====================
print(f"\n{'='*120}")
print("4️⃣ ПРИМЕРЫ КАТЕГОРИИ 'other' (неопределённые)")
print("="*120)

other_items = [item for item in all_items if item.get('super_class') == 'other'][:20]

if other_items:
    print(f"\nВсего 'other': {with_other} ({with_other/total*100:.1f}%)")
    print(f"\nПримеры (первые 20):")
    for item in other_items:
        name = item.get('name_raw', item.get('name_norm', ''))[:60]
        pack = item.get('net_weight_kg') or item.get('net_volume_l') or 'NO PACK'
        brand = item.get('brand_id') or 'NO BRAND'
        print(f"   {name:60} | pack={str(pack):8} | brand={brand}")

# ==================== 5) FAVORITES ANALYSIS ====================
print(f"\n{'='*120}")
print("5️⃣ АНАЛИЗ ТЕКУЩИХ FAVORITES")
print("="*120)

favorites = list(db.favorites.find({}, {'_id': 0}))
print(f"\nВсего favorites: {len(favorites)}")

if favorites:
    print(f"\nСтруктура favorites:")
    fav_sample = favorites[0]
    for key in sorted(fav_sample.keys()):
        print(f"   {key:25} : {fav_sample[key]}")
    
    # Check brand_critical distribution
    brand_critical_counts = Counter(fav.get('brand_critical', False) for fav in favorites)
    print(f"\nBrand critical распределение:")
    for mode, count in brand_critical_counts.items():
        print(f"   {mode:10} : {count}")
else:
    print("   ℹ️  Нет favorites (clean start)")

# ==================== 6) POTENTIAL MISMATCHES ====================
print(f"\n{'='*120}")
print("6️⃣ ПОТЕНЦИАЛЬНЫЕ ПРОБЛЕМЫ МАППИНГА")
print("="*120)

# Check if кетчуп items have consistent super_class
ketchup_items = list(db.supplier_items.find(
    {'active': True, 'name_norm': {'$regex': 'кетчуп', '$options': 'i'}},
    {'_id': 0, 'name_norm': 1, 'super_class': 1}
))

ketchup_classes = Counter(item.get('super_class') for item in ketchup_items)
print(f"\nКетчуп super_class distribution ({len(ketchup_items)} items):")
for sc, count in ketchup_classes.most_common():
    print(f"   {sc:40} : {count}")

# Check лосось
salmon_items = list(db.supplier_items.find(
    {'active': True, 'name_norm': {'$regex': 'лосось|сёмга', '$options': 'i'}},
    {'_id': 0, 'name_norm': 1, 'super_class': 1}
))

salmon_classes = Counter(item.get('super_class') for item in salmon_items)
print(f"\nЛосось/Сёмга super_class distribution ({len(salmon_items)} items):")
for sc, count in salmon_classes.most_common(5):
    print(f"   {sc:40} : {count}")

# ==================== SUMMARY ====================
print(f"\n{'='*120}")
print("📊 SUMMARY FINDINGS")
print("="*120)

print(f"\n✅ СИЛЬНЫЕ СТОРОНЫ:")
print(f"   • super_class покрытие: {(with_super_class+with_other)/total*100:.1f}% (100%)")
print(f"   • Pack покрытие: {with_pack/total*100:.1f}%")
print(f"   • Price per base unit: {with_price_base/total*100:.1f}%")

print(f"\n⚠️  СЛАБЫЕ СТОРОНЫ:")
if with_other / total > 0.2:
    print(f"   • 'other' категория: {with_other/total*100:.1f}% - много неопределённых товаров")
if with_brand / total < 0.6:
    print(f"   • Brand coverage: {with_brand/total*100:.1f}% - больше половины без бренда")
if len(fresh_items) > 0 and fresh_with_origin / len(fresh_items) < 0.5:
    print(f"   • Fresh origin coverage: {fresh_with_origin/len(fresh_items)*100:.1f}% - низкое для мяса/рыбы")

print(f"\n💡 РЕКОМЕНДАЦИИ:")
if with_other > 1000:
    print(f"   1. Расширить SEED_DICT_RULES для категории 'other' ({with_other} items)")
if len(low_pack_categories) > 5:
    print(f"   2. Улучшить PACK_RULES для {len(low_pack_categories)} категорий")
if with_brand / total < 0.6:
    print(f"   3. Расширить BRAND_ALIASES (покрытие {with_brand/total*100:.1f}%)")

print(f"\n{'='*120}")
print("✅ Диагностический отчёт завершён")
print("="*120)

# Save report to file
report_data = {
    'total_active_items': total,
    'coverage': {
        'super_class_defined': with_super_class,
        'super_class_other': with_other,
        'pack': with_pack,
        'price_per_base_unit': with_price_base,
        'brand': with_brand,
        'origin': with_origin,
        'fresh_with_origin': fresh_with_origin if fresh_items else 0
    },
    'percentages': {
        'super_class': (with_super_class+with_other)/total*100,
        'pack': with_pack/total*100,
        'brand': with_brand/total*100
    },
    'top_categories': dict(super_class_counts.most_common(30)),
    'low_pack_categories': low_pack_categories
}

with open('/app/backend/v12_diagnostic_report.json', 'w', encoding='utf-8') as f:
    json.dump(report_data, f, ensure_ascii=False, indent=2)

print(f"\n💾 Отчёт сохранён: /app/backend/v12_diagnostic_report.json")
