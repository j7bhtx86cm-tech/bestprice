"""
Backfill Geography - Извлечение и заполнение origin_country/region/city из названий

Запуск:
    python backfill_geography.py --collection supplier_items --dry-run
    python backfill_geography.py --collection supplier_items --apply
    python backfill_geography.py --collection favorites --apply
"""
import os
import sys
import argparse
from datetime import datetime, timezone
from pymongo import MongoClient

# Add backend to path
sys.path.insert(0, '/app/backend')

from geography_extractor import extract_geography_from_text

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


def backfill_collection(collection_name: str, dry_run: bool = True, min_confidence: float = 0.8):
    """
    Backfill geography fields from product names.
    
    Args:
        collection_name: 'supplier_items' or 'favorites'
        dry_run: If True, only print what would be done
        min_confidence: Minimum confidence to apply (0.0-1.0)
    """
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    collection = db[collection_name]
    
    # Get name field based on collection
    name_field = 'name_raw' if collection_name == 'supplier_items' else 'productName'
    
    # Query for items without geography or with empty geography
    query = {
        '$or': [
            {'origin_country': {'$exists': False}},
            {'origin_country': None},
            {'origin_country': ''}
        ]
    }
    
    if collection_name == 'supplier_items':
        query['active'] = True
    
    items = list(collection.find(query, {'_id': 1, 'id': 1, name_field: 1}))
    
    print(f"\n{'='*60}")
    print(f"BACKFILL GEOGRAPHY: {collection_name}")
    print(f"{'='*60}")
    print(f"Total items without geography: {len(items)}")
    print(f"Min confidence: {min_confidence}")
    print(f"Dry run: {dry_run}")
    print()
    
    stats = {
        'total': len(items),
        'extracted_country': 0,
        'extracted_region': 0,
        'extracted_city': 0,
        'skipped_low_conf': 0,
        'updated': 0,
        'errors': 0
    }
    
    samples = []
    
    for item in items:
        name = item.get(name_field, '')
        if not name:
            continue
        
        geo = extract_geography_from_text(name)
        
        # Skip if confidence too low
        if geo['geo_confidence'] < min_confidence:
            stats['skipped_low_conf'] += 1
            continue
        
        # Check what was extracted
        update_fields = {}
        
        if geo['origin_country']:
            update_fields['origin_country'] = geo['origin_country']
            stats['extracted_country'] += 1
        
        if geo['origin_region']:
            update_fields['origin_region'] = geo['origin_region']
            stats['extracted_region'] += 1
        
        if geo['origin_city']:
            update_fields['origin_city'] = geo['origin_city']
            stats['extracted_city'] += 1
        
        if not update_fields:
            continue
        
        # Collect samples
        if len(samples) < 20:
            samples.append({
                'name': name[:60],
                'country': geo['origin_country'],
                'region': geo['origin_region'],
                'city': geo['origin_city'],
                'conf': geo['geo_confidence']
            })
        
        # Apply update
        if not dry_run:
            try:
                update_fields['geo_updated_at'] = datetime.now(timezone.utc).isoformat()
                collection.update_one(
                    {'_id': item['_id']},
                    {'$set': update_fields}
                )
                stats['updated'] += 1
            except Exception as e:
                print(f"Error updating {item.get('id')}: {e}")
                stats['errors'] += 1
        else:
            stats['updated'] += 1
    
    # Print samples
    print("Sample extractions:")
    print("-" * 80)
    for s in samples:
        print(f"  '{s['name']}'")
        print(f"    → country={s['country']}, region={s['region']}, city={s['city']}, conf={s['conf']:.2f}")
    
    # Print stats
    print()
    print("=" * 60)
    print("STATISTICS:")
    print("=" * 60)
    print(f"  Total items processed: {stats['total']}")
    print(f"  Countries extracted: {stats['extracted_country']}")
    print(f"  Regions extracted: {stats['extracted_region']}")
    print(f"  Cities extracted: {stats['extracted_city']}")
    print(f"  Skipped (low confidence): {stats['skipped_low_conf']}")
    print(f"  {'Would update' if dry_run else 'Updated'}: {stats['updated']}")
    print(f"  Errors: {stats['errors']}")
    
    if dry_run:
        print()
        print("⚠️  DRY RUN - no changes applied. Use --apply to apply changes.")
    
    return stats


def verify_backfill(collection_name: str):
    """Verify backfill results."""
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    collection = db[collection_name]
    
    query = {'active': True} if collection_name == 'supplier_items' else {}
    
    total = collection.count_documents(query)
    
    print(f"\n{'='*60}")
    print(f"VERIFICATION: {collection_name}")
    print(f"{'='*60}")
    
    for field in ['origin_country', 'origin_region', 'origin_city']:
        with_field = collection.count_documents({
            **query,
            field: {'$exists': True, '$ne': None, '$ne': ''}
        })
        pct = (with_field / total * 100) if total > 0 else 0
        print(f"  {field}: {with_field}/{total} ({pct:.1f}%)")
    
    # Show top countries
    pipeline = [
        {'$match': {**query, 'origin_country': {'$exists': True, '$ne': None, '$ne': ''}}},
        {'$group': {'_id': '$origin_country', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 10}
    ]
    
    print("\n  Top countries:")
    for doc in collection.aggregate(pipeline):
        print(f"    {doc['_id']}: {doc['count']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Backfill geography from product names')
    parser.add_argument('--collection', choices=['supplier_items', 'favorites', 'both'], 
                        default='both', help='Collection to backfill')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry run)')
    parser.add_argument('--verify', action='store_true', help='Only verify current state')
    parser.add_argument('--min-confidence', type=float, default=0.8, 
                        help='Minimum confidence threshold (0.0-1.0)')
    
    args = parser.parse_args()
    
    if args.verify:
        if args.collection in ['supplier_items', 'both']:
            verify_backfill('supplier_items')
        if args.collection in ['favorites', 'both']:
            verify_backfill('favorites')
    else:
        dry_run = not args.apply
        
        if args.collection in ['supplier_items', 'both']:
            backfill_collection('supplier_items', dry_run=dry_run, min_confidence=args.min_confidence)
        
        if args.collection in ['favorites', 'both']:
            backfill_collection('favorites', dry_run=dry_run, min_confidence=args.min_confidence)
        
        # Verify after apply
        if not dry_run:
            if args.collection in ['supplier_items', 'both']:
                verify_backfill('supplier_items')
            if args.collection in ['favorites', 'both']:
                verify_backfill('favorites')
