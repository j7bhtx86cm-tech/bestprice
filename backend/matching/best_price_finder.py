"""Best Price Finder (Final Winner Selection)"""
from typing import Dict, List, Optional

def find_best_price(matches: List[Dict]) -> Optional[Dict]:
    """Find cheapest match by price_per_base_unit
    
    Args:
        matches: List of scored candidates (score >= 70)
    
    Returns:
        Winner with lowest price_per_base_unit, or None
    """
    if not matches:
        return None
    
    # Filter valid prices
    valid = [m for m in matches if m.get('price_per_base_unit') is not None]
    
    if not valid:
        return None
    
    # Sort by price_per_base_unit (ascending), then by score (descending)
    valid.sort(key=lambda x: (x['price_per_base_unit'], -x['match_score']))
    
    return valid[0]
