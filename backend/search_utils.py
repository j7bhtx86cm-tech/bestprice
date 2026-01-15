"""
Search Utilities for BestPrice v12 Catalog
- Query normalization
- Token generation  
- Brand detection from query
- Russian stemming/lemmatization
"""

import re
import unicodedata
from typing import List, Optional, Set, Tuple
from pymongo.database import Database

# Import Russian stemmer
from russian_stemmer import russian_stem, stem_token_safe, generate_lemma_tokens, is_special_token


# =====================
# NORMALIZATION
# =====================

# Pattern for special tokens like 31/40 (caliber/size)
CALIBER_PATTERN = re.compile(r'\d+/\d+')

def normalize_text(text: str, preserve_calibers: bool = True) -> str:
    """
    Normalize text for search:
    - lowercase
    - ё → е
    - remove punctuation (preserve / in caliber patterns like 31/40)
    - collapse whitespace
    """
    if not text:
        return ""
    
    # Lowercase
    text = text.lower()
    
    # ё → е
    text = text.replace('ё', 'е')
    
    if preserve_calibers:
        # Temporarily protect caliber patterns
        calibers = CALIBER_PATTERN.findall(text)
        for i, cal in enumerate(calibers):
            text = text.replace(cal, f'__CAL{i}__', 1)
        
        # Remove punctuation (keep letters, digits, spaces)
        text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
        
        # Restore calibers
        for i, cal in enumerate(calibers):
            text = text.replace(f'__cal{i}__', cal)
    else:
        # Remove all punctuation
        text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


# Stop words
STOP_WORDS = {
    'и', 'в', 'на', 'с', 'по', 'из', 'для', 'от', 'до', 'за', 'при', 
    'без', 'под', 'над', 'об', 'о', 'а', 'но', 'или', 'же', 'ли', 'бы', 
    'не', 'ни', 'что', 'как', 'так', 'то', 'это', 'все', 'вся', 'весь', 
    'его', 'ее', 'их', 'мы', 'вы', 'он', 'она', 'оно', 'они', 
    'мой', 'твой', 'наш', 'ваш', 'свой', 'кто', 'тот', 'этот', 
    'сам', 'самый', 'каждый', 'другой', 'такой', 'который', 'чей', 'сей'
}


def tokenize(text: str) -> List[str]:
    """
    Split normalized text into tokens.
    Filters out very short tokens (1 char) and common stop words.
    Preserves special tokens like calibers (31/40).
    """
    if not text:
        return []
    
    normalized = normalize_text(text, preserve_calibers=True)
    tokens = normalized.split()
    
    result = []
    for t in tokens:
        # Always keep special tokens (calibers, numbers)
        if is_special_token(t):
            result.append(t)
        # Filter: length > 1, not a stop word
        elif len(t) > 1 and t not in STOP_WORDS:
            result.append(t)
    
    return result


def tokenize_with_lemmas(text: str) -> Tuple[List[str], List[str]]:
    """
    Tokenize and also generate lemma tokens.
    Returns (raw_tokens, lemma_tokens)
    """
    tokens = tokenize(text)
    lemmas = generate_lemma_tokens(tokens)
    return tokens, lemmas


def generate_search_tokens(
    name_raw: str,
    brand_id: Optional[str] = None,
    super_class: Optional[str] = None,
    product_core_id: Optional[str] = None
) -> List[str]:
    """
    Generate search tokens for a supplier_item.
    Includes:
    - tokens from name_raw
    - brand_id (if present)
    - super_class parts (e.g., 'seafood.shrimp' → ['seafood', 'shrimp'])
    - product_core_id parts
    """
    tokens_set: Set[str] = set()
    
    # Tokens from name
    name_tokens = tokenize(name_raw)
    tokens_set.update(name_tokens)
    
    # Brand ID as token
    if brand_id:
        brand_normalized = normalize_text(brand_id.replace('_', ' '))
        tokens_set.update(tokenize(brand_normalized))
        # Also add raw brand_id without underscores normalization
        tokens_set.add(brand_id.lower())
    
    # Super class parts
    if super_class:
        parts = super_class.lower().replace('_', ' ').split('.')
        for part in parts:
            part_tokens = tokenize(part)
            tokens_set.update(part_tokens)
    
    # Product core parts
    if product_core_id and product_core_id != super_class:
        parts = product_core_id.lower().replace('_', ' ').split('.')
        for part in parts:
            part_tokens = tokenize(part)
            tokens_set.update(part_tokens)
    
    return sorted(list(tokens_set))


def generate_lemma_tokens_for_item(
    name_raw: str,
    brand_id: Optional[str] = None,
    super_class: Optional[str] = None,
    product_core_id: Optional[str] = None
) -> List[str]:
    """
    Generate lemma tokens for a supplier_item (with Russian stemming).
    """
    # First get regular search tokens
    search_tokens = generate_search_tokens(name_raw, brand_id, super_class, product_core_id)
    
    # Apply stemming
    return generate_lemma_tokens(search_tokens)


# =====================
# BRAND DETECTION
# =====================

def detect_brand_from_query(db: Database, query_tokens: List[str]) -> Optional[str]:
    """
    Detect brand_id from query tokens using brand_aliases collection.
    Returns the first matched brand_id or None.
    """
    if not query_tokens:
        return None
    
    # Check each token against brand_aliases
    for token in query_tokens:
        alias_doc = db.brand_aliases.find_one(
            {'alias_norm': token},
            {'_id': 0, 'brand_id': 1}
        )
        if alias_doc:
            return alias_doc['brand_id']
    
    # Also try combined tokens (2-word brands like "агро альянс")
    if len(query_tokens) >= 2:
        for i in range(len(query_tokens) - 1):
            combined = f"{query_tokens[i]} {query_tokens[i+1]}"
            combined_norm = normalize_text(combined)
            alias_doc = db.brand_aliases.find_one(
                {'alias_norm': combined_norm},
                {'_id': 0, 'brand_id': 1}
            )
            if alias_doc:
                return alias_doc['brand_id']
    
    return None


def get_brand_aliases_set(db: Database, brand_id: str) -> Set[str]:
    """
    Get all aliases for a brand_id as a set of normalized strings.
    """
    aliases = set()
    for doc in db.brand_aliases.find({'brand_id': brand_id}, {'_id': 0, 'alias_norm': 1}):
        aliases.add(doc['alias_norm'])
    
    # Also check brands collection for brand_ru and brand_en
    brand_doc = db.brands.find_one({'brand_id': brand_id}, {'_id': 0, 'brand_ru': 1, 'brand_en': 1})
    if brand_doc:
        if brand_doc.get('brand_ru'):
            aliases.add(normalize_text(brand_doc['brand_ru']))
        if brand_doc.get('brand_en'):
            aliases.add(normalize_text(brand_doc['brand_en']))
    
    return aliases


# =====================
# SCORING
# =====================

def calculate_match_score(item_tokens: List[str], query_tokens: List[str]) -> float:
    """
    Calculate match score based on token overlap.
    Returns a score between 0 and 1.
    """
    if not query_tokens or not item_tokens:
        return 0.0
    
    item_set = set(item_tokens)
    query_set = set(query_tokens)
    
    # Count how many query tokens are found in item
    matched = len(query_set & item_set)
    total = len(query_set)
    
    return matched / total if total > 0 else 0.0


def calculate_ppu_value(price: float, unit_type: str, pack_qty: float = 1) -> Optional[float]:
    """
    Calculate price-per-unit value for ranking.
    - WEIGHT: price per kg
    - VOLUME: price per liter
    - PIECE: None (no reliable PPU for pieces without pack info)
    """
    if not price or price <= 0:
        return None
    
    if unit_type == 'WEIGHT':
        # Assume price is per kg or per pack_qty kg
        return price / pack_qty if pack_qty > 0 else price
    elif unit_type == 'VOLUME':
        # Assume price is per liter or per pack_qty liters
        return price / pack_qty if pack_qty > 0 else price
    else:
        # PIECE - no reliable PPU
        return None


def calculate_min_line_total(price: float, min_order_qty: int = 1) -> float:
    """
    Calculate minimum line total = price * min_order_qty
    """
    return price * max(min_order_qty, 1)


# =====================
# BACKFILL UTILITY
# =====================

def backfill_search_tokens(db: Database, batch_size: int = 500, include_lemmas: bool = True) -> dict:
    """
    Backfill search_tokens and lemma_tokens fields for all supplier_items.
    Returns statistics.
    """
    from datetime import datetime, timezone
    
    total = db.supplier_items.count_documents({})
    updated = 0
    errors = 0
    
    cursor = db.supplier_items.find({}, {
        '_id': 1,
        'id': 1,
        'name_raw': 1,
        'brand_id': 1,
        'super_class': 1,
        'product_core_id': 1
    })
    
    batch = []
    for doc in cursor:
        tokens = generate_search_tokens(
            name_raw=doc.get('name_raw', ''),
            brand_id=doc.get('brand_id'),
            super_class=doc.get('super_class'),
            product_core_id=doc.get('product_core_id')
        )
        
        update_fields = {
            'search_tokens': tokens,
            'search_tokens_updated_at': datetime.now(timezone.utc).isoformat()
        }
        
        if include_lemmas:
            lemma_tokens = generate_lemma_tokens_for_item(
                name_raw=doc.get('name_raw', ''),
                brand_id=doc.get('brand_id'),
                super_class=doc.get('super_class'),
                product_core_id=doc.get('product_core_id')
            )
            update_fields['lemma_tokens'] = lemma_tokens
        
        batch.append({
            'filter': {'_id': doc['_id']},
            'update': {'$set': update_fields}
        })
        
        if len(batch) >= batch_size:
            try:
                for op in batch:
                    db.supplier_items.update_one(op['filter'], op['update'])
                updated += len(batch)
            except Exception as e:
                errors += len(batch)
                print(f"Error in batch: {e}")
            batch = []
    
    # Process remaining
    if batch:
        try:
            for op in batch:
                db.supplier_items.update_one(op['filter'], op['update'])
            updated += len(batch)
        except Exception as e:
            errors += len(batch)
            print(f"Error in final batch: {e}")
    
    return {
        'total': total,
        'updated': updated,
        'errors': errors
    }


def ensure_search_indexes(db: Database) -> dict:
    """
    Create necessary indexes for search.
    """
    indexes_created = []
    
    # Main search index
    try:
        db.supplier_items.create_index(
            [('active', 1), ('search_tokens', 1)],
            name='active_search_tokens'
        )
        indexes_created.append('active_search_tokens')
    except Exception as e:
        print(f"Index active_search_tokens: {e}")
    
    # Lemma tokens index (for RU morphology search)
    try:
        db.supplier_items.create_index(
            [('active', 1), ('lemma_tokens', 1)],
            name='active_lemma_tokens'
        )
        indexes_created.append('active_lemma_tokens')
    except Exception as e:
        print(f"Index active_lemma_tokens: {e}")
    
    # Name norm index (for prefix search)
    try:
        db.supplier_items.create_index(
            [('active', 1), ('name_norm', 1)],
            name='active_name_norm'
        )
        indexes_created.append('active_name_norm')
    except Exception as e:
        print(f"Index active_name_norm: {e}")
    
    # Compound index with super_class for filtered searches
    try:
        db.supplier_items.create_index(
            [('active', 1), ('super_class', 1), ('search_tokens', 1)],
            name='active_super_class_search_tokens'
        )
        indexes_created.append('active_super_class_search_tokens')
    except Exception as e:
        print(f"Index active_super_class_search_tokens: {e}")
    
    # Index on brand_id for brand boost
    try:
        db.supplier_items.create_index(
            [('active', 1), ('brand_id', 1)],
            name='active_brand_id'
        )
        indexes_created.append('active_brand_id')
    except Exception as e:
        print(f"Index active_brand_id: {e}")
    
    # Index for brand_aliases lookup
    try:
        db.brand_aliases.create_index(
            [('alias_norm', 1)],
            name='alias_norm_1'
        )
        indexes_created.append('brand_aliases.alias_norm_1')
    except Exception as e:
        print(f"Index brand_aliases.alias_norm: {e}")
    
    return {'indexes_created': indexes_created}


# =====================
# CLI
# =====================

if __name__ == '__main__':
    import argparse
    import os
    from pymongo import MongoClient
    
    parser = argparse.ArgumentParser(description='Search Utils CLI')
    parser.add_argument('--backfill', action='store_true', help='Backfill search_tokens')
    parser.add_argument('--create-indexes', action='store_true', help='Create search indexes')
    parser.add_argument('--test', type=str, help='Test tokenization on a string')
    
    args = parser.parse_args()
    
    client = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
    db = client[os.environ.get('DB_NAME', 'test_database')]
    
    if args.backfill:
        print("Backfilling search_tokens...")
        result = backfill_search_tokens(db)
        print(f"Result: {result}")
    
    if args.create_indexes:
        print("Creating indexes...")
        result = ensure_search_indexes(db)
        print(f"Result: {result}")
    
    if args.test:
        print(f"Input: {args.test}")
        print(f"Normalized: {normalize_text(args.test)}")
        print(f"Tokens: {tokenize(args.test)}")
