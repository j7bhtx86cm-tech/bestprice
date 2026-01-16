"""
Script to extract and backfill critical attributes (fat_pct, cut) from product names.

Run once to populate missing critical attributes in supplier_items.
"""

import os
import re
from pymongo import MongoClient

MONGO_URL = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
DB_NAME = os.environ.get('DB_NAME', 'test_database')


def extract_fat_pct(name: str) -> float:
    """
    Extract fat percentage from product name.
    Examples:
    - "МАСЛО сладкосливочное 82,5%" -> 82.5
    - "Сливки 33%" -> 33.0
    - "Молоко 3.2%" -> 3.2
    """
    # Patterns to match fat percentage
    patterns = [
        r'(\d+)[,.](\d+)\s*%',  # 82,5% or 82.5%
        r'(\d+)\s*%',           # 33%
        r'жирн[а-я]*\.?\s*(\d+)[,.]?(\d*)',  # жирн. 33 или жирность 33,5
    ]
    
    for pattern in patterns:
        match = re.search(pattern, name, re.IGNORECASE)
        if match:
            groups = match.groups()
            if len(groups) == 2 and groups[1]:
                return float(f"{groups[0]}.{groups[1]}")
            elif len(groups) >= 1:
                return float(groups[0])
    
    return None


def extract_cut(name: str, super_class: str) -> str:
    """
    Extract cut/form from product name.
    Examples:
    - "Филе лосося" -> "fillet"
    - "Тушка форели" -> "whole"
    - "Стейк семги" -> "steak"
    """
    name_lower = name.lower()
    
    # Fish/seafood cuts
    if 'seafood' in super_class:
        if 'филе' in name_lower or 'фил.' in name_lower:
            return 'fillet'
        if 'тушк' in name_lower:
            return 'whole'
        if 'стейк' in name_lower:
            return 'steak'
        if 'кусок' in name_lower or 'кусоч' in name_lower:
            return 'pieces'
        if 'кольц' in name_lower:
            return 'rings'
        if 'хвост' in name_lower:
            return 'tail'
        if 'креветк' in name_lower:
            if 'очищ' in name_lower or 'б/г' in name_lower or 'без голов' in name_lower:
                return 'peeled'
            elif 'с голов' in name_lower or 'неочищ' in name_lower:
                return 'shell_on'
    
    # Meat cuts
    if 'meat' in super_class:
        if 'филе' in name_lower or 'фил.' in name_lower:
            return 'fillet'
        if 'грудк' in name_lower or 'грудин' in name_lower:
            return 'breast'
        if 'бедр' in name_lower or 'окорок' in name_lower:
            return 'thigh'
        if 'крыл' in name_lower:
            return 'wing'
        if 'голен' in name_lower:
            return 'drumstick'
        if 'тушк' in name_lower:
            return 'whole'
        if 'фарш' in name_lower:
            return 'ground'
        if 'печен' in name_lower:
            return 'liver'
        if 'сердц' in name_lower:
            return 'heart'
        if 'стейк' in name_lower:
            return 'steak'
        if 'ребр' in name_lower:
            return 'ribs'
        if 'шея' in name_lower or 'шейк' in name_lower:
            return 'neck'
        if 'лопатк' in name_lower:
            return 'shoulder'
        if 'вырезк' in name_lower:
            return 'tenderloin'
    
    return None


def backfill_fat_pct(db):
    """Backfill fat_pct for dairy products"""
    print("Backfilling fat_pct for dairy products...")
    
    dairy_items = list(db.supplier_items.find(
        {'super_class': {'$regex': '^dairy'}, 'fat_pct': {'$exists': False}},
        {'_id': 1, 'name_raw': 1}
    ))
    
    updated = 0
    for item in dairy_items:
        fat_pct = extract_fat_pct(item['name_raw'])
        if fat_pct is not None:
            db.supplier_items.update_one(
                {'_id': item['_id']},
                {'$set': {'fat_pct': fat_pct}}
            )
            updated += 1
    
    print(f"  Updated {updated} / {len(dairy_items)} dairy items with fat_pct")
    return updated


def backfill_cut(db):
    """Backfill cut for seafood and meat products"""
    print("Backfilling cut for seafood and meat products...")
    
    items = list(db.supplier_items.find(
        {'super_class': {'$regex': '^(seafood|meat)'}, 'cut': {'$exists': False}},
        {'_id': 1, 'name_raw': 1, 'super_class': 1}
    ))
    
    updated = 0
    for item in items:
        cut = extract_cut(item['name_raw'], item.get('super_class', ''))
        if cut is not None:
            db.supplier_items.update_one(
                {'_id': item['_id']},
                {'$set': {'cut': cut}}
            )
            updated += 1
    
    print(f"  Updated {updated} / {len(items)} seafood/meat items with cut")
    return updated


def show_stats(db):
    """Show statistics after backfill"""
    print("\n=== Statistics ===")
    
    # Fat percentage distribution
    dairy_with_fat = db.supplier_items.count_documents({
        'super_class': {'$regex': '^dairy'},
        'fat_pct': {'$exists': True}
    })
    dairy_total = db.supplier_items.count_documents({
        'super_class': {'$regex': '^dairy'}
    })
    print(f"Dairy with fat_pct: {dairy_with_fat} / {dairy_total}")
    
    # Show fat distribution
    pipeline = [
        {'$match': {'super_class': {'$regex': '^dairy'}, 'fat_pct': {'$exists': True}}},
        {'$group': {'_id': '$fat_pct', 'count': {'$sum': 1}}},
        {'$sort': {'_id': 1}}
    ]
    fat_dist = list(db.supplier_items.aggregate(pipeline))
    if fat_dist:
        print("  Fat % distribution:")
        for d in fat_dist[:10]:
            print(f"    {d['_id']}%: {d['count']} items")
    
    # Cut distribution
    seafood_with_cut = db.supplier_items.count_documents({
        'super_class': {'$regex': '^seafood'},
        'cut': {'$exists': True}
    })
    seafood_total = db.supplier_items.count_documents({
        'super_class': {'$regex': '^seafood'}
    })
    print(f"\nSeafood with cut: {seafood_with_cut} / {seafood_total}")
    
    meat_with_cut = db.supplier_items.count_documents({
        'super_class': {'$regex': '^meat'},
        'cut': {'$exists': True}
    })
    meat_total = db.supplier_items.count_documents({
        'super_class': {'$regex': '^meat'}
    })
    print(f"Meat with cut: {meat_with_cut} / {meat_total}")
    
    # Show cut distribution
    pipeline = [
        {'$match': {'super_class': {'$regex': '^(seafood|meat)'}, 'cut': {'$exists': True}}},
        {'$group': {'_id': '$cut', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]
    cut_dist = list(db.supplier_items.aggregate(pipeline))
    if cut_dist:
        print("  Cut distribution:")
        for d in cut_dist[:10]:
            print(f"    {d['_id']}: {d['count']} items")


def main():
    client = MongoClient(MONGO_URL)
    db = client[DB_NAME]
    
    print("Starting critical attributes backfill...")
    print(f"Database: {DB_NAME}")
    print()
    
    fat_updated = backfill_fat_pct(db)
    cut_updated = backfill_cut(db)
    
    show_stats(db)
    
    print(f"\n=== Done ===")
    print(f"Total updates: {fat_updated + cut_updated}")


if __name__ == '__main__':
    main()
