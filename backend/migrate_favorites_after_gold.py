#!/usr/bin/env python3
"""
Migration script: Update favorites after GOLD pricelist migration.

For each favorite:
1. Check if anchor_supplier_item_id is still active
2. If not, find a replacement by product_core_id + unit_type
3. Update the favorite with new anchor and price
4. Mark unavailable if no replacement found
"""

import os
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv(Path('/app/backend/.env'))

mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']


def migrate_favorites(dry_run: bool = True, user_id: str = None):
    """
    Migrate favorites to use active GOLD offers.
    
    Args:
        dry_run: If True, only report what would be changed
        user_id: If provided, only migrate for this user
    """
    client = MongoClient(mongo_url)
    db = client[db_name]
    
    print("="*70)
    print("🔄 FAVORITES MIGRATION AFTER GOLD")
    print(f"   Mode: {'DRY RUN' if dry_run else 'LIVE'}")
    print("="*70)
    
    # Build query
    query = {}
    if user_id:
        query['user_id'] = user_id
    
    favorites = list(db.favorites_v12.find(query, {'_id': 0}))
    print(f"📊 Total favorites to check: {len(favorites)}")
    
    stats = {
        'total': len(favorites),
        'still_active': 0,
        'updated': 0,
        'unavailable': 0,
        'no_product_core': 0,
    }
    
    updated_items = []
    unavailable_items = []
    
    for fav in favorites:
        fav_id = fav.get('id')
        ref_id = fav.get('reference_id')
        anchor_id = fav.get('anchor_supplier_item_id')
        product_name = fav.get('product_name', '')[:50]
        product_core_id = fav.get('product_core_id')
        unit_type = fav.get('unit_type', 'PIECE')
        
        # Check if anchor is still active
        if anchor_id:
            anchor = db.supplier_items.find_one(
                {'id': anchor_id, 'active': True},
                {'_id': 0, 'price': 1, 'supplier_company_id': 1}
            )
            if anchor:
                stats['still_active'] += 1
                continue
        
        # Anchor is inactive or missing - find replacement
        if not product_core_id:
            # Try to find by reference_id if it's a supplier_item UUID
            if ref_id and len(ref_id) == 36 and '-' in ref_id:
                # Looks like a UUID - might be old supplier_item.id
                old_item = db.supplier_items.find_one(
                    {'id': ref_id},
                    {'_id': 0, 'product_core_id': 1, 'unit_type': 1, 'name_raw': 1}
                )
                if old_item:
                    product_core_id = old_item.get('product_core_id')
                    unit_type = old_item.get('unit_type', unit_type)
                    if not product_name:
                        product_name = old_item.get('name_raw', '')[:50]
            
            if not product_core_id:
                stats['no_product_core'] += 1
                unavailable_items.append({
                    'id': fav_id,
                    'name': product_name,
                    'reason': 'No product_core_id'
                })
                continue
        
        # Find replacement by product_core_id + unit_type
        replacement = db.supplier_items.find_one(
            {
                'active': True,
                'price': {'$gt': 0},
                'product_core_id': product_core_id,
                'unit_type': unit_type
            },
            {'_id': 0, 'id': 1, 'price': 1, 'supplier_company_id': 1, 'name_raw': 1},
            sort=[('price', 1)]  # Cheapest first
        )
        
        if replacement:
            new_anchor_id = replacement['id']
            new_price = replacement['price']
            new_supplier_id = replacement.get('supplier_company_id')
            new_name = replacement.get('name_raw', product_name)
            
            stats['updated'] += 1
            updated_items.append({
                'id': fav_id,
                'old_name': product_name,
                'new_name': new_name[:50],
                'old_anchor': anchor_id,
                'new_anchor': new_anchor_id,
                'new_price': new_price,
            })
            
            if not dry_run:
                db.favorites_v12.update_one(
                    {'id': fav_id},
                    {'$set': {
                        'anchor_supplier_item_id': new_anchor_id,
                        'best_price': new_price,
                        'best_supplier_id': new_supplier_id,
                        'product_name': new_name,
                        'product_core_id': product_core_id,
                        'updated_at': datetime.now(timezone.utc).isoformat(),
                    }}
                )
        else:
            stats['unavailable'] += 1
            unavailable_items.append({
                'id': fav_id,
                'name': product_name,
                'product_core_id': product_core_id,
                'reason': 'No active offers found'
            })
    
    # Print report
    print()
    print("📊 MIGRATION RESULTS")
    print("-"*70)
    print(f"   Still active (no change needed): {stats['still_active']}")
    print(f"   Updated with new anchor: {stats['updated']}")
    print(f"   Unavailable (no replacement): {stats['unavailable']}")
    print(f"   No product_core_id: {stats['no_product_core']}")
    print()
    
    if updated_items:
        print("✅ UPDATED FAVORITES:")
        for item in updated_items[:20]:
            print(f"   {item['old_name']}")
            print(f"      → {item['new_name']} @ {item['new_price']}₽")
        if len(updated_items) > 20:
            print(f"   ... and {len(updated_items) - 20} more")
        print()
    
    if unavailable_items:
        print("⚠️ UNAVAILABLE FAVORITES:")
        for item in unavailable_items[:20]:
            print(f"   {item['name']} - {item['reason']}")
        if len(unavailable_items) > 20:
            print(f"   ... and {len(unavailable_items) - 20} more")
        print()
    
    if dry_run:
        print("💡 This was a DRY RUN. No changes were made.")
        print("   Run with dry_run=False to apply changes.")
    else:
        print("✅ Migration complete!")
    
    return stats


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='Migrate favorites after GOLD pricelist update')
    parser.add_argument('--apply', action='store_true', help='Apply changes (default is dry-run)')
    parser.add_argument('--user-id', help='Migrate only for specific user')
    
    args = parser.parse_args()
    
    migrate_favorites(dry_run=not args.apply, user_id=args.user_id)


if __name__ == '__main__':
    main()
