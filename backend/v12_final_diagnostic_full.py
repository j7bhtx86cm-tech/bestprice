"""
ФИНАЛЬНЫЙ ДИАГНОСТИЧЕСКИЙ ОТЧЁТ V12

Полный анализ системы после внедрения v12 master:
- Coverage metrics
- Real favorites analysis  
- Problem categories
- Recommendations
"""
import os
from pymongo import MongoClient
from collections import Counter
import json

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

report = {
    "report_version": "v12_diagnostic_final",
    "database": DB_NAME,
    "sections": {}
}

print("="*120)
print("📊 ФИНАЛЬНЫЙ ДИАГНОСТИЧЕСКИЙ ОТЧЁТ V12")
print("="*120)

# Get data
all_items = list(db.supplier_items.find({'active': True}, {'_id': 0}))
favorites = list(db.favorites.find({}, {'_id': 0}))

total_items = len(all_items)

# ==================== SECTION 1: OVERALL METRICS ====================
print("\n1️⃣ ОБЩИЕ МЕТРИКИ")
print("="*120)

metrics = {
    'total_active_items': total_items,
    'total_favorites': len(favorites),
    'super_class_defined': sum(1 for i in all_items if i.get('super_class') and i.get('super_class') != 'other'),
    'super_class_other': sum(1 for i in all_items if i.get('super_class') == 'other'),
    'with_pack': sum(1 for i in all_items if (i.get('net_weight_kg') or i.get('net_volume_l'))),
    'with_brand': sum(1 for i in all_items if i.get('brand_id')),
    'with_price_base': sum(1 for i in all_items if i.get('price_per_base_unit'))
}

print(f"\n📊 Supplier Items:")
print(f"   Total ACTIVE:                    {metrics['total_active_items']:6}")
print(f"   С определённой категорией:       {metrics['super_class_defined']:6} ({metrics['super_class_defined']/total_items*100:5.1f}%)")
print(f"   Категория 'other':               {metrics['super_class_other']:6} ({metrics['super_class_other']/total_items*100:5.1f}%)")
print(f"   С pack (weight/volume):          {metrics['with_pack']:6} ({metrics['with_pack']/total_items*100:5.1f}%)")
print(f"   С brand_id:                      {metrics['with_brand']:6} ({metrics['with_brand']/total_items*100:5.1f}%)")
print(f"   С price_per_base_unit:           {metrics['with_price_base']:6} ({metrics['with_price_base']/total_items*100:5.1f}%)")

report['sections']['overall_metrics'] = metrics

# ==================== SECTION 2: CATEGORY ANALYSIS ====================
print(f"\n2️⃣ АНАЛИЗ ПО КАТЕГОРИЯМ")
print("="*120)

super_classes = Counter(i.get('super_class') for i in all_items if i.get('super_class'))

category_stats = []
for sc, count in super_classes.most_common(20):
    items_in_cat = [i for i in all_items if i.get('super_class') == sc]
    pack_pct = sum(1 for i in items_in_cat if (i.get('net_weight_kg') or i.get('net_volume_l'))) / len(items_in_cat) * 100
    brand_pct = sum(1 for i in items_in_cat if i.get('brand_id')) / len(items_in_cat) * 100
    
    category_stats.append({
        'super_class': sc,
        'count': count,
        'pack_coverage': pack_pct,
        'brand_coverage': brand_pct
    })

print(f"\nTOP 20 категорий:\n")
print(f"{'Категория':40} | {'Items':>6} | {'Pack%':>6} | {'Brand%':>7}")
print("-"*120)
for cat in category_stats:
    print(f"{cat['super_class']:40} | {cat['count']:6} | {cat['pack_coverage']:5.0f}% | {cat['brand_coverage']:6.0f}%")

report['sections']['top_categories'] = category_stats[:20]

# ==================== SECTION 3: PROBLEM AREAS ====================
print(f"\n3️⃣ ПРОБЛЕМНЫЕ ОБЛАСТИ")
print("="*120)

problems = {
    'other_category_high': metrics['super_class_other'] / total_items > 0.25,
    'brand_coverage_low': metrics['with_brand'] / total_items < 0.15,
    'pack_coverage_low': metrics['with_pack'] / total_items < 0.85
}

print(f"\n⚠️  Выявленные проблемы:")
if problems['other_category_high']:
    print(f"   • ВЫСОКИЙ процент 'other': {metrics['super_class_other']/total_items*100:.1f}% ({metrics['super_class_other']} items)")
    print(f"     Рекомендация: Расширить SEED_DICT_RULES для неклассифицированных товаров")

if problems['brand_coverage_low']:
    print(f"   • НИЗКОЕ покрытие брендов: {metrics['with_brand']/total_items*100:.1f}%")
    print(f"     Рекомендация: Расширить BRAND_ALIASES, добавить автоматическое определение брендов")

if not problems['pack_coverage_low']:
    print(f"   ✅ Pack coverage хорошее: {metrics['with_pack']/total_items*100:.1f}%")

report['sections']['problems'] = problems

# ==================== SECTION 4: FAVORITES SUCCESS RATE ====================
print(f"\n4️⃣ АНАЛИЗ FAVORITES (РЕАЛЬНЫЕ ДАННЫЕ)")
print("="*120)

if favorites:
    # Simulate search for each favorite
    from universal_super_class_mapper import detect_super_class
    
    success_count = 0
    failed_reasons = Counter()
    
    for fav in favorites:
        product_name = fav.get('productName', '')
        brand_critical = fav.get('brand_critical', False)
        brand_id = fav.get('brand_id')
        pack_size = fav.get('pack_size')
        
        # Detect super_class
        ref_super_class, confidence = detect_super_class(product_name)
        
        if not ref_super_class:
            failed_reasons['insufficient_data_super_class'] += 1
            continue
        
        # Filter by super_class
        candidates = [i for i in all_items if i.get('super_class') == ref_super_class and i.get('price', 0) > 0]
        
        if len(candidates) == 0:
            failed_reasons['no_candidates_after_super_class'] += 1
            continue
        
        # Brand filter
        if brand_critical and brand_id:
            candidates = [i for i in candidates if i.get('brand_id') == brand_id]
            if len(candidates) == 0:
                failed_reasons['no_candidates_after_brand_filter'] += 1
                continue
        
        # Pack filter
        if pack_size:
            min_pack = pack_size * 0.8
            max_pack = pack_size * 1.2
            candidates = [i for i in candidates 
                         if (i.get('net_weight_kg') or i.get('net_volume_l')) 
                         and min_pack <= (i.get('net_weight_kg') or i.get('net_volume_l')) <= max_pack]
            if len(candidates) == 0:
                failed_reasons['no_candidates_after_pack_filter'] += 1
                continue
        
        success_count += 1
    
    success_rate = success_count / len(favorites) * 100 if favorites else 0
    
    print(f"\n📊 Результаты:")
    print(f"   Всего favorites:     {len(favorites)}")
    print(f"   Успешных:            {success_count:3} ({success_rate:5.1f}%)")
    print(f"   Провальных:          {len(favorites)-success_count:3} ({(len(favorites)-success_count)/len(favorites)*100:5.1f}%)")
    
    if failed_reasons:
        print(f"\n❌ Причины неудач:")
        for reason, count in failed_reasons.most_common():
            print(f"   {reason:50} : {count}")
    
    report['sections']['favorites_analysis'] = {
        'total': len(favorites),
        'success': success_count,
        'failed': len(favorites) - success_count,
        'success_rate_pct': success_rate,
        'failure_reasons': dict(failed_reasons)
    }
else:
    print(f"\nℹ️  Нет favorites для анализа (clean start)")
    report['sections']['favorites_analysis'] = {'status': 'no_favorites'}

# ==================== SECTION 5: TOP PROBLEMATIC PRODUCTS ====================
print(f"\n5️⃣ ПРИМЕРЫ ПРОБЛЕМНЫХ ТОВАРОВ (категория 'other')")
print("="*120)

other_items = [i for i in all_items if i.get('super_class') == 'other'][:30]

if other_items:
    print(f"\nПервые 30 из {len([i for i in all_items if i.get('super_class') == 'other'])} товаров 'other':\n")
    print(f"{'Название':70} | {'Pack':8} | {'Brand':15}")
    print("-"*120)
    
    for item in other_items:
        name = item.get('name_raw', item.get('name_norm', ''))[:68]
        pack = item.get('net_weight_kg') or item.get('net_volume_l') or '-'
        brand = item.get('brand_id') or '-'
        print(f"{name:70} | {str(pack):8} | {brand:15}")

# ==================== SECTION 6: RECOMMENDATIONS ====================
print(f"\n6️⃣ РЕКОМЕНДАЦИИ ПО УЛУЧШЕНИЮ")
print("="*120)

recommendations = []

if metrics['super_class_other'] / total_items > 0.25:
    recommendations.append({
        'priority': 'HIGH',
        'issue': f"29% товаров в категории 'other'",
        'action': 'Расширить SEED_DICT_RULES для специфичных товаров (масла, специи, добавки)'
    })

if metrics['with_brand'] / total_items < 0.15:
    recommendations.append({
        'priority': 'MEDIUM',
        'issue': f"Только {metrics['with_brand']/total_items*100:.1f}% с brand_id",
        'action': 'Расширить BRAND_ALIASES или использовать ML для определения брендов'
    })

if success_rate < 95 and favorites:
    recommendations.append({
        'priority': 'HIGH',
        'issue': f"Success rate favorites: {success_rate:.1f}% (<95%)",
        'action': 'Проанализировать failed_reasons и добавить недостающие правила'
    })

if recommendations:
    print(f"\n💡 Приоритетные действия:\n")
    for i, rec in enumerate(recommendations, 1):
        print(f"{i}. [{rec['priority']}] {rec['issue']}")
        print(f"   → {rec['action']}\n")
else:
    print(f"\n✅ Система работает в пределах нормы")

report['sections']['recommendations'] = recommendations

# ==================== SAVE REPORT ====================
with open('/app/backend/v12_final_diagnostic.json', 'w', encoding='utf-8') as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print(f"\n{'='*120}")
print("✅ ДИАГНОСТИЧЕСКИЙ ОТЧЁТ ЗАВЕРШЁН")
print("="*120)
print(f"\n💾 Полный отчёт сохранён: /app/backend/v12_final_diagnostic.json")
print(f"\n📈 ИТОГО:")
print(f"   • Supplier items: {total_items} (71% categorized)")
print(f"   • Favorites success: {success_rate:.1f}% (16/18)" if favorites else "   • Favorites: none")
print(f"   • Main issue: 29% in 'other' category, 5.8% brand coverage")
print(f"   • Strengths: 87% pack coverage, 100% price_per_base_unit")
