"""Hybrid Matching Engine - Best of Spec + Simple Approach"""
from typing import Dict, List, Optional

WEIGHT_TOLERANCE = 0.20  # ±20%

def find_best_match_hybrid(query_product_name: str, original_price: float, 
                           all_items: List[Dict]) -> Optional[Dict]:
    """Hybrid matching: Spec infrastructure + Simple logic
    
    Rules:
    1. super_class must match (from spec)
    2. base_unit must match (from spec)
    3. caliber must match if present (from spec)
    4. weight within ±20% (simple)
    5. Select by price_per_base_unit (from spec)
    
    Returns winner or None
    """
    from pipeline.enricher import extract_caliber, extract_super_class
    from pipeline.normalizer import normalize_name
    from pipeline.enricher import extract_weights, extract_volumes
    
    # Extract query features
    query_super_class = extract_super_class(query_product_name.lower())
    query_caliber = extract_caliber(query_product_name)
    query_weight_data = extract_weights(query_product_name)
    query_weight = query_weight_data.get('net_weight_kg')
    
    # Determine query base_unit
    query_base_unit = 'kg' if query_weight else 'pcs'
    
    matches = []
    
    for item in all_items:
        # Gate 1: super_class match
        if item.get('super_class') != query_super_class:
            continue
        
        # Gate 2: base_unit match
        if item.get('base_unit') != query_base_unit:
            continue
        
        # Gate 3: Must have valid price_per_base_unit
        if item.get('base_price_unknown'):
            continue
        
        # Gate 4: Must be cheaper
        if item.get('price', 999999) >= original_price:
            continue
        
        # Gate 5: Caliber MUST match (if query has caliber)
        if query_caliber:
            item_caliber = item.get('caliber')
            if not item_caliber or item_caliber != query_caliber:
                continue
        
        # Gate 6: Weight tolerance (±20%)
        if query_weight:
            item_weight = item.get('net_weight_kg')
            if item_weight:
                diff = abs(query_weight - item_weight) / max(query_weight, item_weight)
                if diff > WEIGHT_TOLERANCE:
                    continue
            else:
                # Query has weight but item doesn't - skip
                continue
        
        # Gate 7: Skip bulk packages when query is single piece
        # If item is bulk package (5kg containing 300g pieces), don't match with single 300g piece
        if item.get('bulk_package') and not query_weight or (query_weight and query_weight < 2.0):
            # Item is bulk, query is single piece - skip
            continue
        
        matches.append(item)
    
    if not matches:
        return None
    
    # Sort by price_per_base_unit (cheapest first), then by price
    matches.sort(key=lambda x: (x.get('price_per_base_unit', 999999), x.get('price', 999999)))
    
    return matches[0]
