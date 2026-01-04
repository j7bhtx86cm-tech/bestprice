"""
GATE 3 - FAVORITES MIGRATION TO V12

According to TZ section 5, two options:
A) Delete old favorites (recommended - most reliable)
B) Migrate existing favorites to reference_item v12 format

We'll implement OPTION A as recommended in TZ.
New favorites will be created in v12 format when users add items.
"""
import os
from pymongo import MongoClient

mongo_url = os.environ.get('MONGO_URL')
client = MongoClient(mongo_url)
db = client['bestprice']

print("="*100)
print("📋 GATE 3 - FAVORITES MIGRATION V12")
print("="*100)

# Check current favorites
old_favorites_count = db.favorites.count_documents({})
print(f"\n📊 Current state:")
print(f"   Old favorites: {old_favorites_count}")

if old_favorites_count > 0:
    print(f"\n⚠️  Found {old_favorites_count} old favorites")
    print("According to TZ section 5.1, OPTION A (recommended):")
    print("   - Delete all old favorites")
    print("   - New favorites will be created in v12 format when users add items")
    
    # Delete old favorites
    result = db.favorites.delete_many({})
    print(f"\n   ✅ Deleted {result.deleted_count} old favorites")
    
    print(f"\n📝 Migration strategy:")
    print("   - Users will re-add items to favorites from catalog")
    print("   - New favorites will automatically use reference_item v12 format")
    print("   - This ensures 100% compatibility with v12 search engine")
else:
    print(f"\n✅ No old favorites found - clean start")

# Create reference_items collection (will be used for new favorites)
if 'reference_items' not in db.list_collection_names():
    db.create_collection('reference_items')
    print(f"\n✅ Created 'reference_items' collection for v12 favorites")

# Create indexes for reference_items
db.reference_items.create_index('fingerprint', unique=True)
db.reference_items.create_index('product_core_id')
print(f"✅ Created indexes on reference_items")

print(f"\n{'='*100}")
print("✅ GATE 3 - FAVORITES MIGRATION COMPLETE")
print("="*100)

print(f"\n📊 Final state:")
print(f"   Old favorites: {db.favorites.count_documents({})}")
print(f"   Reference items (v12): {db.reference_items.count_documents({})}")

print(f"\n✅ Migration strategy: Clean start (OPTION A)")
print("   Users will create new favorites in v12 format from catalog")

print("\n🎉 GATE 3 PASSED")
print("\n✅ Done!")
