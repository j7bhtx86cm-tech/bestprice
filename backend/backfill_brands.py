"""Backfill brand_id for all products without reloading pricelists

UPDATED VERSION (December 2025):
- Uses BESTPRICE_BRANDS_MASTER_UNIFIED_RF_HORECA_ULTRA_SAFE.xlsx
- Connects to the correct database (test_database from .env)
- Updates brand_id and brand_strict fields in products collection
"""
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from backend directory
ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# Reload brand master to ensure we use the new file
import importlib
import brand_master
importlib.reload(brand_master)
from brand_master import BrandMaster


async def backfill_brands():
    """Backfill brand_id for all products"""
    # Force reload brand master with new file
    bm = BrandMaster.reload()
    stats = bm.get_stats()
    print(f"\n📋 Brand dictionary loaded: {stats['total_brands']} brands, {stats['total_aliases']} aliases")
    
    # Connect to MongoDB - USE SAME DB AS SERVER!
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')  # CRITICAL: use same DB as server
    
    print(f"📊 Connecting to database: {db_name}")
    
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Get all products
    products = await db.products.find({}, {"_id": 0}).to_list(20000)
    print(f"📦 Found {len(products)} products to process")
    
    # Statistics
    result_stats = {
        'total': len(products),
        'branded': 0,
        'strict': 0,
        'no_brand': 0,
        'updated': 0,
        'errors': 0,
        'brand_counts': {}
    }
    
    # Process each product
    for i, product in enumerate(products):
        product_id = product.get('id')
        product_name = product.get('name', '')
        
        # Detect brand
        brand_id, brand_strict = bm.detect_brand(product_name)
        
        if brand_id:
            result_stats['branded'] += 1
            if brand_strict:
                result_stats['strict'] += 1
            # Track brand counts
            result_stats['brand_counts'][brand_id] = result_stats['brand_counts'].get(brand_id, 0) + 1
        else:
            result_stats['no_brand'] += 1
        
        # Update product if brand changed
        old_brand = product.get('brand_id')
        old_strict = product.get('brand_strict', False)
        
        if brand_id != old_brand or brand_strict != old_strict:
            try:
                await db.products.update_one(
                    {"id": product_id},
                    {"$set": {
                        "brand_id": brand_id,
                        "brand_strict": brand_strict
                    }}
                )
                result_stats['updated'] += 1
                
                # Log significant changes
                if old_brand or brand_id:
                    if (i + 1) <= 20:  # Only log first 20 changes
                        print(f"   🔄 Updated: {product_name[:50]}...")
                        print(f"      {old_brand} → {brand_id} (strict={brand_strict})")
            except Exception as e:
                result_stats['errors'] += 1
                print(f"   ❌ Error updating {product_id}: {e}")
        
        # Progress
        if (i + 1) % 1000 == 0:
            print(f"   Processed {i + 1}/{len(products)}...")
    
    # Print summary
    print(f"\n{'='*60}")
    print(f"✅ BACKFILL COMPLETE")
    print(f"{'='*60}")
    print(f"   Database:        {db_name}")
    print(f"   Total products:  {result_stats['total']}")
    print(f"   Branded:         {result_stats['branded']} ({100*result_stats['branded']/max(result_stats['total'],1):.1f}%)")
    print(f"   Strict brands:   {result_stats['strict']}")
    print(f"   No brand:        {result_stats['no_brand']}")
    print(f"   Updated:         {result_stats['updated']}")
    print(f"   Errors:          {result_stats['errors']}")
    
    # Top 15 brands by count
    top_brands = sorted(
        result_stats['brand_counts'].items(),
        key=lambda x: -x[1]
    )[:15]
    
    print(f"\n📋 Top 15 brands by product count:")
    for brand_id, count in top_brands:
        brand_info = bm.get_brand_info(brand_id)
        brand_ru = brand_info.get('brand_ru', '') if brand_info else ''
        print(f"   {count:4d} | {brand_id:15} | {brand_ru}")
    
    # Sample branded products
    print(f"\n📋 Sample branded products:")
    branded = await db.products.find(
        {"brand_id": {"$ne": None}},
        {"_id": 0, "name": 1, "brand_id": 1, "brand_strict": 1}
    ).limit(10).to_list(10)
    
    for p in branded:
        strict_mark = "🔒" if p.get('brand_strict') else "  "
        print(f"   {strict_mark} [{p.get('brand_id', ''):15}] {p.get('name', '')[:50]}")
    
    client.close()
    return result_stats


if __name__ == '__main__':
    print("="*60)
    print("BRAND BACKFILL SCRIPT - UNIFIED RF HORECA ULTRA SAFE")
    print("="*60)
    asyncio.run(backfill_brands())
