"""Gate Filters (Pre-Scoring)"""
from typing import Dict, List

PACK_TOLERANCE = 0.10  # ±10%

def apply_gate_filters(query: Dict, candidates: List[Dict]) -> List[Dict]:
    """Apply gate filters before scoring
    
    Gates:
    1. super_class match
    2. base_unit match
    3. strict_pack (if enabled)
    4. brand_strict (if enabled)
    5. price_per_base_unit must exist
    
    Args:
        query: QueryFeatures dict
        candidates: List of supplier_items
    
    Returns:
        Filtered candidates
    """
    filtered = []
    
    for item in candidates:
        # Gate 1: super_class
        if item.get('super_class') != query.get('super_class'):
            continue
        
        # Gate 2: base_unit
        # Determine query's base unit
        query_base_unit = 'pcs'
        if query.get('target_weight_kg'):
            query_base_unit = 'kg'
        elif query.get('target_volume_l'):
            query_base_unit = 'l'
        
        if item.get('base_unit') != query_base_unit:
            continue
        
        # Gate 3: strict_pack (weight tolerance)
        if query.get('strict_pack') is not None:
            item_weight = item.get('net_weight_kg')
            if item_weight:
                diff = abs(item_weight - query['strict_pack']) / max(item_weight, query['strict_pack'])
                if diff > PACK_TOLERANCE:
                    continue
        
        # Gate 4: brand_strict
        if query.get('brand_strict') and query.get('brand'):
            if item.get('brand') != query['brand']:
                continue
        
        # Gate 5: price_per_base_unit must exist (unless comparing pcs-to-pcs)
        if item.get('base_price_unknown') and query_base_unit != 'pcs':
            continue
        
        filtered.append(item)
    
    return filtered
