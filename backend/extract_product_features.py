"""
Extract features for all existing products and store in supplier_item_features collection
"""
from pymongo import MongoClient
import os
from advanced_product_matcher import extract_features
from datetime import datetime, timezone

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
client = MongoClient(MONGO_URL)
db = client[DB_NAME]

print("=" * 80)
print("EXTRACTING FEATURES FOR ALL PRODUCTS")
print("=" * 80)

# Get all pricelists
pricelists = list(db.pricelists.find({}, {'_id': 0}))
print(f"\nFound {len(pricelists)} pricelist items")

# Clear existing features
db.supplier_item_features.delete_many({})
print("Cleared old features")

# Process each pricelist item
features_batch = []
processed = 0
errors = 0

for pl in pricelists:
    try:
        # Get product details
        product = db.products.find_one({'id': pl['productId']}, {'_id': 0})
        
        if not product:
            errors += 1
            continue
        
        # Extract features
        features = extract_features(product['name'], product['unit'], pl['price'])
        
        # Add metadata
        feature_doc = {
            'supplier_item_id': pl['id'],
            'supplier_id': pl['supplierId'],
            'product_id': pl['productId'],
            'active': pl.get('availability', True),
            'features_version': 1,
            'updated_at': datetime.now(timezone.utc).isoformat(),
            **features
        }
        
        features_batch.append(feature_doc)
        processed += 1
        
        # Batch insert every 1000
        if len(features_batch) >= 1000:
            db.supplier_item_features.insert_many(features_batch)
            features_batch = []
            print(f"  Processed {processed}/{len(pricelists)}...")
            
    except Exception as e:
        errors += 1
        print(f"  Error processing {product.get('name', 'unknown')[:50]}: {e}")

# Insert remaining
if features_batch:
    db.supplier_item_features.insert_many(features_batch)

print("\n" + "=" * 80)
print("FEATURE EXTRACTION COMPLETE")
print("=" * 80)
print(f"Processed: {processed}")
print(f"Errors: {errors}")
print(f"Total features in DB: {db.supplier_item_features.count_documents({})}")

# Show some examples
print("\n" + "=" * 80)
print("SAMPLE EXTRACTED FEATURES")
print("=" * 80)

samples = list(db.supplier_item_features.find({}, {'_id': 0}).limit(5))
for i, sample in enumerate(samples, 1):
    print(f"\n{i}. {sample.get('raw_name', 'N/A')[:60]}")
    print(f"   Normalized: {sample.get('name_norm', 'N/A')[:50]}")
    print(f"   Tokens: {sample.get('tokens', [])[:8]}")
    print(f"   Super Class: {sample.get('super_class')}")
    print(f"   Product Type: {sample.get('product_type')}")
    print(f"   Caliber: {sample.get('caliber')}")
    print(f"   Fat%: {sample.get('fat_pct')}")
    print(f"   Pack Weight: {sample.get('pack_weight_kg')} kg")
    print(f"   Pack Volume: {sample.get('pack_volume_l')} l")
    print(f"   Brand: {sample.get('brand')}")
    print(f"   Unit: {sample.get('unit_norm')}")

print("\n" + "=" * 80)
