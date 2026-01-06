#!/usr/bin/env python3
"""
Brand Extraction and Backfill for BestPrice
Извлекает бренды из названий товаров и обновляет brand_id
"""
import os
import re
from pymongo import MongoClient
from datetime import datetime

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

# Known brands dictionary (normalized_name -> brand_id)
KNOWN_BRANDS = {
    # Major international brands
    'heinz': 'heinz',
    'knorr': 'knorr',
    'hellmann': 'hellmanns',
    'hellmanns': 'hellmanns',
    'hellmann`s': 'hellmanns',
    'tamaki': 'tamaki',
    'kotanyi': 'kotanyi',
    'aroy-d': 'aroyd',
    'aroy': 'aroyd',
    'barinoff': 'barinoff',
    'monin': 'monin',
    
    # Russian brands
    'агро-альянс': 'agroalyans',
    'агроальянс': 'agroalyans',
    'колобок': 'kolobok',
    'националь': 'national',
    'простоквашино': 'prostokvashino',
    'домик в деревне': 'domik',
    'макфа': 'makfa',
    'барилла': 'barilla',
    'barilla': 'barilla',
    
    # Asian brands
    'kikkoman': 'kikkoman',
    'кикккоман': 'kikkoman',
    'genso': 'genso',
    'kingzest': 'kingzest',
    'real tang': 'realtang',
    'hansey': 'hansey',
    'shinaki': 'shinaki',
    'oshi': 'oshi',
    'sen soy': 'sensoy',
    'prb': 'prb',
    'pearl river bridge': 'prb',
    'bg': 'bg',
    'chang': 'chang',
    'yoshimi': 'yoshimi',
    'todoford': 'todoford',
    'midori': 'midori',
    
    # Spice/Seasoning brands
    'spiceexpert': 'spiceexpert',
    'spicеexpert': 'spiceexpert',
    'суприм': 'suprim',
    'pikador': 'pikador',
    'provil': 'provil',
    'cea': 'cea',
    
    # Oil brands
    'sunny gold': 'sunnygold',
    'sunnygold': 'sunnygold',
    'ideal': 'ideal',
    'granoliva': 'granoliva',
    'borges': 'borges',
    'filippo berio': 'filippoberio',
    'solpro': 'solpro',
    
    # Dairy brands
    'unagrande': 'unagrande',
    'president': 'president',
    'président': 'president',
    'galbani': 'galbani',
    'parmalat': 'parmalat',
    'valio': 'valio',
    'петмол': 'petmol',
    'домашний': 'domashny',
    
    # Meat brands  
    'флагман': 'flagman',
    'primebeef': 'primebeef',
    'мираторг': 'miratorg',
    'черкизово': 'cherkizovo',
    'рузком': 'ruzkom',
    'праймфудс': 'primefoods',
    'останкино': 'ostankino',
    'ветис': 'vetis',
    'рубикон': 'rubicon',
    'qummy': 'qummy',
    
    # Beverage brands
    'coca-cola': 'cocacola',
    'pepsi': 'pepsi',
    'fanta': 'fanta',
    'sprite': 'sprite',
    'lipton': 'lipton',
    'ahmad': 'ahmad',
    'twinings': 'twinings',
    'greenfield': 'greenfield',
    'vinut': 'vinut',
    'santal': 'santal',
    
    # Seafood brands
    'vici': 'vici',
    'санта бремор': 'santabremor',
    'polar': 'polar',
    'agama': 'agama',
    'risma': 'risma',
    
    # Confectionery/Bakery
    'irca': 'irca',
    'callebaut': 'callebaut',
    'puratos': 'puratos',
    'lesaffre': 'lesaffre',
    'lutik': 'lutik',
    'falcone': 'falcone',
    
    # Canned goods
    'mamminger': 'mamminger',
    'bonduelle': 'bonduelle',
    'horeca select': 'horecaselect',
    'metro chef': 'metrochef',
    'aro': 'aro',
    'fine life': 'finelife',
    'got2eat': 'got2eat',
    
    # Additional brands from catalog
    'agrobar': 'agrobar',
    'textoplast': 'textoplast',
    'сырникофф': 'syrnikoff',
    'казанский': 'kazansky',
    'клинский': 'klinsky',
    'кинг': 'king',
    'long men': 'longmen',
    'печагин': 'pechagin',
}

# Country names to exclude from brand detection
COUNTRY_NAMES = {
    'россия', 'рф', 'китай', 'китая', 'чили', 'таиланд', 'вьетнам', 'india', 
    'индия', 'италия', 'испания', 'германия', 'франция', 'сша', 'usa',
    'беларусь', 'казахстан', 'турция', 'греция', 'норвегия', 'peru', 'перу'
}

# Common non-brand words to exclude
NON_BRAND_WORDS = {
    'пэт', 'стекло', 'ст/б', 'ж/б', 'вес', 'шт', 'уп', 'упак', 'кр', 'блок',
    'балк', 'дип-пот', 'пакет', 'банка', 'бутылка', 'тетра', 'призма',
    'гост', 'категория', 'сорт', 'экстра', 'премиум', 'premium', 'extra',
    'il', 'prb', 'хэ', 'pro'
}


def normalize_brand(brand_text):
    """Normalize brand name for matching"""
    if not brand_text:
        return None
    normalized = brand_text.lower().strip()
    normalized = normalized.replace('ё', 'е').replace('`', "'")
    normalized = re.sub(r'[^\w\s\-]', '', normalized)
    return normalized.strip()


def extract_brand_from_name(name_raw):
    """
    Extract brand from product name using multiple patterns
    Returns (brand_id, confidence)
    """
    if not name_raw:
        return None, 0.0
    
    name = name_raw.strip()
    name_lower = name.lower()
    
    # Pattern 1: Check for known brands anywhere in name (highest priority)
    for known_brand, brand_id in KNOWN_BRANDS.items():
        if known_brand in name_lower:
            return brand_id, 1.0
    
    # Pattern 2: Brand after comma at end: "ПРОДУКТ, БРЕНД" or "ПРОДУКТ, БРЕНД, СТРАНА"
    comma_pattern = re.compile(r',\s*([A-ZА-ЯЁ][A-Za-zА-Яа-яЁё\-\'\`\s]{2,25})(?:,|\s*$)')
    matches = comma_pattern.findall(name)
    for match in matches:
        normalized = normalize_brand(match)
        if normalized and normalized not in COUNTRY_NAMES and normalized not in NON_BRAND_WORDS:
            if len(normalized) >= 2:
                return normalized.replace(' ', '_'), 0.7
    
    # Pattern 3: Brand after units: "500 гр. БРЕНД" or "1 кг БРЕНД"
    unit_pattern = re.compile(r'(?:\d+[,.]?\d*)\s*(?:кг|г|гр|л|мл|шт)[\.]*\s+([A-ZА-ЯЁ][A-Za-zА-Яа-яЁё\-\'\`\s]{2,25})(?:\s|,|$)')
    matches = unit_pattern.findall(name)
    for match in matches:
        normalized = normalize_brand(match)
        if normalized and normalized not in COUNTRY_NAMES and normalized not in NON_BRAND_WORDS:
            # Check if this looks like a brand (starts with capital, reasonable length)
            if len(normalized) >= 2 and len(normalized) <= 25:
                return normalized.replace(' ', '_'), 0.6
    
    # Pattern 4: Brand in quotes: "ПРОДУКТ \"БРЕНД\""
    quote_pattern = re.compile(r'["\«]([A-ZА-ЯЁa-zа-яё][A-Za-zА-Яа-яЁё\-\'\`\s]{1,25})["\»]')
    matches = quote_pattern.findall(name)
    for match in matches:
        normalized = normalize_brand(match)
        if normalized and normalized not in COUNTRY_NAMES and normalized not in NON_BRAND_WORDS:
            if len(normalized) >= 2:
                return normalized.replace(' ', '_'), 0.8
    
    return None, 0.0


def run_brand_backfill(dry_run=False):
    """Run brand extraction and update database"""
    print("=" * 80)
    print("BRAND EXTRACTION BACKFILL")
    print("=" * 80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Dry run: {dry_run}")
    print()
    
    # Load items
    print("📊 Loading supplier_items...")
    items = list(db.supplier_items.find({'active': True}, {'_id': 0, 'id': 1, 'name_raw': 1, 'brand_id': 1}))
    print(f"   Total: {len(items)}")
    
    # Stats
    stats = {
        'total': len(items),
        'already_has_brand': 0,
        'brand_extracted': 0,
        'no_brand_found': 0,
        'high_conf': 0,
        'medium_conf': 0,
        'low_conf': 0,
    }
    
    brand_distribution = {}
    updates = []
    
    print("\n🔄 Processing items...")
    for i, item in enumerate(items, 1):
        item_id = item['id']
        name_raw = item.get('name_raw', '')
        current_brand = item.get('brand_id')
        
        if current_brand:
            stats['already_has_brand'] += 1
            continue
        
        # Extract brand
        brand_id, confidence = extract_brand_from_name(name_raw)
        
        if brand_id:
            stats['brand_extracted'] += 1
            brand_distribution[brand_id] = brand_distribution.get(brand_id, 0) + 1
            
            if confidence >= 0.8:
                stats['high_conf'] += 1
            elif confidence >= 0.6:
                stats['medium_conf'] += 1
            else:
                stats['low_conf'] += 1
            
            updates.append({
                'filter': {'id': item_id},
                'update': {'$set': {'brand_id': brand_id, 'brand_conf': round(confidence, 2)}}
            })
        else:
            stats['no_brand_found'] += 1
        
        if i % 1000 == 0:
            print(f"   Progress: {i}/{len(items)} ({i*100//len(items)}%)")
    
    # Execute updates
    if updates and not dry_run:
        print(f"\n💾 Executing {len(updates)} updates...")
        from pymongo import UpdateOne
        bulk_ops = [UpdateOne(u['filter'], u['update']) for u in updates]
        result = db.supplier_items.bulk_write(bulk_ops)
        print(f"   Modified: {result.modified_count}")
    elif dry_run:
        print(f"\n🔍 Dry run - would update {len(updates)} items")
    
    # Report
    print("\n" + "=" * 80)
    print("📊 BRAND EXTRACTION SUMMARY")
    print("=" * 80)
    print(f"Total items: {stats['total']}")
    print(f"Already had brand: {stats['already_has_brand']}")
    print(f"Brand extracted: {stats['brand_extracted']} ({stats['brand_extracted']*100//stats['total']}%)")
    print(f"No brand found: {stats['no_brand_found']}")
    print()
    print("Confidence distribution:")
    print(f"  High (>=0.8): {stats['high_conf']}")
    print(f"  Medium (0.6-0.8): {stats['medium_conf']}")
    print(f"  Low (<0.6): {stats['low_conf']}")
    print()
    print("📋 Top 20 Extracted Brands:")
    for brand, count in sorted(brand_distribution.items(), key=lambda x: -x[1])[:20]:
        print(f"  {brand:25} | {count:4} items")
    
    print("\n✅ Brand extraction complete!")
    return stats


if __name__ == "__main__":
    import sys
    dry_run = '--dry-run' in sys.argv
    run_brand_backfill(dry_run=dry_run)
