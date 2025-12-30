"""Backfill brand_id for all products without reloading pricelists

This script:
1. Loads new brand dictionary from BESTPRICE_BRANDS_MASTER_EN_RU_SITE_STYLE_FINAL.xlsx
2. Iterates through all products
3. Detects brand using the new dictionary
4. Updates brand_id and brand_strict fields
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os

# Reload brand master to ensure we use the new file
import importlib
import brand_master
importlib.reload(brand_master)
from brand_master import BrandMaster


async def backfill_brands():
    """Backfill brand_id for all products"""
    # Force reload brand master
    bm = BrandMaster.reload()
    print(f"\n📋 Brand dictionary loaded: {len(bm.brands_by_id)} brands, {len(bm.alias_to_id)} aliases")
    
    # Connect to MongoDB
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    client = AsyncIOMotorClient(mongo_url)
    db = client['bestprice']
    
    # Get all products
    products = await db.products.find({}, {"_id": 0}).to_list(20000)
    print(f"\n📦 Found {len(products)} products to process")
    
    # Statistics
    stats = {
        'total': len(products),
        'branded': 0,
        'strict': 0,
        'no_brand': 0,
        'updated': 0,
        'errors': 0
    }
    
    # Process each product
    for i, product in enumerate(products):
        product_id = product.get('id')
        product_name = product.get('name', '')
        
        # Detect brand
        brand_id, brand_strict = bm.detect_brand(product_name)
        
        if brand_id:
            stats['branded'] += 1
            if brand_strict:
                stats['strict'] += 1
        else:
            stats['no_brand'] += 1
        
        # Update product if brand changed
        old_brand = product.get('brand_id')
        if brand_id != old_brand:
            try:
                await db.products.update_one(
                    {"id": product_id},
                    {"$set": {
                        "brand_id": brand_id,
                        "brand_strict": brand_strict
                    }}
                )
                stats['updated'] += 1
                
                # Log significant changes
                if old_brand or brand_id:
                    print(f"   🔄 Updated: {product_name[:50]}...")
                    print(f"      {old_brand} → {brand_id} (strict={brand_strict})")
            except Exception as e:
                stats['errors'] += 1
                print(f"   ❌ Error updating {product_id}: {e}")
        
        # Progress
        if (i + 1) % 500 == 0:
            print(f"   Processed {i + 1}/{len(products)}...")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"✅ BACKFILL COMPLETE")
    print(f"{'='*60}")
    print(f"   Total products:  {stats['total']}")
    print(f"   Branded:         {stats['branded']} ({100*stats['branded']/max(stats['total'],1):.1f}%)")
    print(f"   Strict brands:   {stats['strict']}")
    print(f"   No brand:        {stats['no_brand']}")
    print(f"   Updated:         {stats['updated']}")
    print(f"   Errors:          {stats['errors']}")
    
    # Sample branded products
    print(f"\n📋 Sample branded products:")
    branded = await db.products.find(
        {"brand_id": {"$ne": None}},
        {"_id": 0, "name": 1, "brand_id": 1, "brand_strict": 1}
    ).limit(10).to_list(10)
    
    for p in branded:
        strict_mark = "🔒" if p.get('brand_strict') else ""
        print(f"   {strict_mark} [{p.get('brand_id'):15}] {p.get('name')[:50]}")
    
    return stats


if __name__ == '__main__':
    print("="*60)
    print("BRAND BACKFILL SCRIPT")
    print("="*60)
    asyncio.run(backfill_brands())
