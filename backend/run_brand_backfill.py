#!/usr/bin/env python3
"""Brand Backfill Script for Pricelists
Assigns brand_id to all pricelists based on Brand Master Dictionary
"""
import asyncio
import sys
import os
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent))

from motor.motor_asyncio import AsyncIOMotorClient
from brand_master import BrandMaster
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def run_brand_backfill():
    """Run brand backfill for all pricelists"""
    
    # Load environment variables
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'bestprice')
    
    logger.info(f"🚀 Starting brand backfill...")
    logger.info(f"   MongoDB: {mongo_url}")
    logger.info(f"   Database: {db_name}")
    
    # Connect to MongoDB
    client = AsyncIOMotorClient(mongo_url)
    db = client[db_name]
    
    # Load Brand Master
    logger.info("📋 Loading Brand Master Dictionary...")
    brand_master = BrandMaster()
    logger.info(f"   Brand Master loaded successfully")
    
    # Get all pricelists
    logger.info("🔍 Fetching all pricelists...")
    pricelists_cursor = db.pricelists.find({}, {"_id": 0})
    pricelists = await pricelists_cursor.to_list(length=None)
    logger.info(f"   Found {len(pricelists)} pricelists")
    
    # Get all products for joining
    logger.info("🔍 Fetching all products...")
    products_cursor = db.products.find({}, {"_id": 0})
    products = await products_cursor.to_list(length=None)
    product_map = {p['id']: p for p in products}
    logger.info(f"   Found {len(products)} products")
    
    # Statistics
    stats = {
        'total': len(pricelists),
        'with_brand': 0,
        'without_brand': 0,
        'updated': 0,
        'failed': 0
    }
    
    # Process each pricelist
    logger.info("⚙️  Processing pricelists...")
    for i, pricelist in enumerate(pricelists, 1):
        pricelist_id = pricelist.get('id')
        product_id = pricelist.get('productId')
        
        # Get product name
        product = product_map.get(product_id)
        if not product:
            logger.warning(f"   [{i}/{len(pricelists)}] Product not found for pricelist {pricelist_id}")
            stats['failed'] += 1
            continue
        
        product_name = product.get('name', '')
        
        # Detect brand
        brand_id, confidence, method = brand_master.detect_brand(product_name)
        
        if brand_id:
            # Update pricelist with brand_id
            result = await db.pricelists.update_one(
                {'id': pricelist_id},
                {'$set': {'brand_id': brand_id}}
            )
            
            if result.modified_count > 0:
                stats['updated'] += 1
                stats['with_brand'] += 1
                
                if i % 100 == 0:
                    logger.info(f"   [{i}/{len(pricelists)}] Updated: {stats['updated']}, "
                              f"Progress: {i/len(pricelists)*100:.1f}%")
            else:
                stats['with_brand'] += 1
        else:
            stats['without_brand'] += 1
            
            if i % 500 == 0:
                logger.info(f"   [{i}/{len(pricelists)}] Progress: {i/len(pricelists)*100:.1f}%")
    
    # Final statistics
    logger.info("✅ Brand backfill completed!")
    logger.info(f"   Total pricelists: {stats['total']}")
    logger.info(f"   Updated: {stats['updated']}")
    logger.info(f"   With brand: {stats['with_brand']} ({stats['with_brand']/stats['total']*100:.1f}%)")
    logger.info(f"   Without brand: {stats['without_brand']} ({stats['without_brand']/stats['total']*100:.1f}%)")
    logger.info(f"   Failed: {stats['failed']}")
    
    # Sample pricelists without brands
    if stats['without_brand'] > 0:
        logger.info("\\n📋 Sample pricelists without brands:")
        no_brand_cursor = db.pricelists.find({'brand_id': {'$exists': False}}, {"_id": 0}).limit(10)
        no_brand = await no_brand_cursor.to_list(length=10)
        
        for pl in no_brand:
            product = product_map.get(pl.get('productId'))
            if product:
                logger.info(f"   - {product.get('name', 'N/A')[:60]}")
    
    # Close connection
    client.close()


if __name__ == '__main__':
    asyncio.run(run_brand_backfill())
