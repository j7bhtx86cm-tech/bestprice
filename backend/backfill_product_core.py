#!/usr/bin/env python3
"""
P1 Backfill: Add product_core_id to all supplier_items
Без перезаливки прайсов - только enrichment поверх существующих данных
"""
import os
from pymongo import MongoClient
from universal_super_class_mapper import detect_super_class
from product_core_classifier import detect_product_core
from datetime import datetime

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

print("=" * 80)
print("P1 BACKFILL: Product Core Classification")
print("=" * 80)
print(f"Database: {DB_NAME}")
print(f"Timestamp: {datetime.now().isoformat()}")
print()

# Get all active supplier_items
print("📊 Loading supplier_items...")
items = list(db.supplier_items.find({'active': True}, {'_id': 0}))
print(f"   Total active items: {len(items)}")

# Statistics
stats = {
    'total': len(items),
    'with_super_class': 0,
    'with_product_core': 0,
    'core_high_conf': 0,  # conf >= 0.8
    'core_medium_conf': 0,  # 0.5 <= conf < 0.8
    'core_low_conf': 0,  # conf < 0.5
    'updated': 0,
}

core_distribution = {}

print("\n🔄 Processing items...")
updates = []

for i, item in enumerate(items, 1):
    item_id = item['id']
    name_raw = item.get('name_raw', '')
    current_super_class = item.get('super_class')
    
    # Step 1: ALWAYS re-detect super_class using GUARD RULES
    # This fixes corrupted data (e.g., "бобы" with seafood.shrimp)
    detected_super_class, conf_super = detect_super_class(name_raw)
    
    # Use detected class if it has high confidence, otherwise keep current
    if conf_super >= 0.7:
        current_super_class = detected_super_class
    elif not current_super_class or current_super_class == 'other':
        if conf_super >= 0.3:
            current_super_class = detected_super_class
    
    if current_super_class:
        stats['with_super_class'] += 1
    
    # Step 2: Detect product_core
    product_core, conf_core = detect_product_core(name_raw, current_super_class)
    
    if product_core:
        stats['with_product_core'] += 1
        
        # Confidence buckets
        if conf_core >= 0.8:
            stats['core_high_conf'] += 1
        elif conf_core >= 0.5:
            stats['core_medium_conf'] += 1
        else:
            stats['core_low_conf'] += 1
        
        # Distribution
        core_distribution[product_core] = core_distribution.get(product_core, 0) + 1
    
    # Prepare update
    update_fields = {}
    
    if current_super_class and current_super_class != item.get('super_class'):
        update_fields['super_class'] = current_super_class
    
    if product_core:
        update_fields['product_core_id'] = product_core
        update_fields['product_core_conf'] = round(conf_core, 2)
    
    if update_fields:
        updates.append({
            'filter': {'id': item_id},
            'update': {'$set': update_fields}
        })
        stats['updated'] += 1
    
    # Progress
    if i % 1000 == 0:
        print(f"   Processed: {i}/{len(items)} ({i*100//len(items)}%)")

# Execute batch update
if updates:
    print(f"\n💾 Executing {len(updates)} updates...")
    from pymongo import UpdateOne
    bulk_ops = [UpdateOne(u['filter'], u['update']) for u in updates]
    result = db.supplier_items.bulk_write(bulk_ops)
    print(f"   Modified: {result.modified_count}")
else:
    print("\n⚠️ No updates needed")

# Print statistics
print("\n" + "=" * 80)
print("📊 BACKFILL STATISTICS")
print("=" * 80)
print(f"Total items processed: {stats['total']}")
print(f"With super_class: {stats['with_super_class']} ({stats['with_super_class']*100//stats['total']}%)")
print(f"With product_core: {stats['with_product_core']} ({stats['with_product_core']*100//stats['total']}%)")
print(f"\nProduct Core Confidence:")
print(f"  High (>=0.8): {stats['core_high_conf']} ({stats['core_high_conf']*100//stats['total']}%)")
print(f"  Medium (0.5-0.8): {stats['core_medium_conf']} ({stats['core_medium_conf']*100//stats['total']}%)")
print(f"  Low (<0.5): {stats['core_low_conf']} ({stats['core_low_conf']*100//stats['total']}%)")
print(f"\nTotal updated: {stats['updated']}")

# Top 20 product cores
print("\n📋 Top 20 Product Cores:")
sorted_cores = sorted(core_distribution.items(), key=lambda x: -x[1])
for core, count in sorted_cores[:20]:
    pct = count * 100 / stats['total']
    print(f"  {core:40} | {count:4} items ({pct:5.1f}%)")

print("\n✅ Backfill complete!")
