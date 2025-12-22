#!/usr/bin/env python3
"""Migrate existing price_lists to new supplier_items collection"""
import os
import sys
sys.path.insert(0, '/app/backend')

from pymongo import MongoClient
from pipeline.processor import process_price_list_item
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def migrate_price_lists():
    """Transform all price_lists to supplier_items through pipeline"""
    client = MongoClient(os.environ.get('MONGO_URL'))
    db = client['test_database']
    
    logger.info("Starting migration...")
    
    # Get all price lists
    price_lists = list(db.price_lists.find({}, {'_id': 0}))
    logger.info(f"Found {len(price_lists)} price list items")
    
    # Process each item through pipeline
    supplier_items = []
    errors = 0
    
    for i, pl in enumerate(price_lists):
        try:
            # Get supplier ID
            supplier_id = pl.get('supplierId', 'unknown')
            
            # Build raw_item format
            raw_item = {
                'productName': pl.get('productName', ''),
                'price': pl.get('price', 0),
                'unit': pl.get('unit', 'pcs'),
                'article': pl.get('article', '')
            }
            
            # Process through pipeline
            processed = process_price_list_item(
                raw_item,
                supplier_company_id=supplier_id,
                price_list_id=pl.get('id', f'pl_{i}')
            )
            
            if processed:
                # Add original reference
                processed['original_pricelist_id'] = pl.get('id')
                processed['original_product_id'] = pl.get('productId')
                supplier_items.append(processed)
            
            if (i + 1) % 500 == 0:
                logger.info(f"Processed {i + 1}/{len(price_lists)} items...")
        
        except Exception as e:
            logger.error(f"Error processing item {i}: {e}")
            errors += 1
            continue
    
    logger.info(f"Processed {len(supplier_items)} items successfully, {errors} errors")
    
    # Create supplier_items collection with indexes
    logger.info("Creating supplier_items collection...")
    db.supplier_items.drop()  # Clear old data
    
    if supplier_items:
        db.supplier_items.insert_many(supplier_items)
        logger.info(f"Inserted {len(supplier_items)} supplier items")
        
        # Create indexes
        db.supplier_items.create_index('supplier_company_id')
        db.supplier_items.create_index('super_class')
        db.supplier_items.create_index('base_unit')
        db.supplier_items.create_index('price_per_base_unit')
        db.supplier_items.create_index([('name_norm', 'text')])
        logger.info("Created indexes")
    
    # Print statistics
    logger.info("\n" + "="*80)
    logger.info("MIGRATION STATISTICS")
    logger.info("="*80)
    
    total = len(supplier_items)
    with_base_price = len([i for i in supplier_items if not i.get('base_price_unknown')])
    with_weight = len([i for i in supplier_items if i.get('net_weight_kg')])
    with_caliber = len([i for i in supplier_items if i.get('caliber')])
    
    logger.info(f"Total items: {total}")
    logger.info(f"With price_per_base_unit: {with_base_price} ({with_base_price/total*100:.1f}%)")
    logger.info(f"With net_weight_kg: {with_weight} ({with_weight/total*100:.1f}%)")
    logger.info(f"With caliber: {with_caliber} ({with_caliber/total*100:.1f}%)")
    
    # Calc route breakdown
    route_counts = {}
    for item in supplier_items:
        route = item.get('calc_route', '0')
        route_counts[route] = route_counts.get(route, 0) + 1
    
    logger.info("\nCalc Route Distribution:")
    for route, count in sorted(route_counts.items()):
        logger.info(f"  Route {route}: {count} ({count/total*100:.1f}%)")
    
    logger.info("\n" + "="*80)
    logger.info("Migration complete!")
    logger.info("="*80)

if __name__ == '__main__':
    migrate_price_lists()
