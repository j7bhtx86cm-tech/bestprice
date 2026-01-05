#!/usr/bin/env python3
"""
Backfill: Переклассификация ВАСАБИ items в condiments.wasabi
"""
import os
from pymongo import MongoClient

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

print("🔄 BACKFILL: Переклассификация ВАСАБИ")
print("=" * 60)

# Find all wasabi items
wasabi_items = list(db.supplier_items.find({
    'name_raw': {'$regex': 'васаби|wasabi', '$options': 'i'},
    'active': True
}, {'_id': 0, 'id': 1, 'name_raw': 1, 'super_class': 1}))

print(f"📊 Найдено {len(wasabi_items)} васаби items для переклассификации\n")

# Update super_class to condiments.wasabi
updated_count = 0
for item in wasabi_items:
    item_id = item['id']
    old_class = item.get('super_class')
    
    # Skip if already correct (skip рисовые шарики)
    if 'рисов' in item.get('name_raw', '').lower() or 'rice' in item.get('name_raw', '').lower():
        print(f"⏭️  SKIP: {item.get('name_raw', '')[:50]:50} (рисовый продукт)")
        continue
    
    # Update to condiments.wasabi
    result = db.supplier_items.update_one(
        {'id': item_id},
        {'$set': {'super_class': 'condiments.wasabi'}}
    )
    
    if result.modified_count > 0:
        updated_count += 1
        print(f"✅ {item.get('name_raw', '')[:50]:50} | {old_class} → condiments.wasabi")

print(f"\n📊 Summary:")
print(f"Total found: {len(wasabi_items)}")
print(f"Updated: {updated_count}")
print(f"\n✅ Backfill complete!")
