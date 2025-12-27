"""Auto-detect if product is branded or commodity"""
from typing import Optional, Tuple

# Import contract rules for brand detection
try:
    from contract_rules import contract_rules
    RULES_LOADED = True
except:
    RULES_LOADED = False
    contract_rules = None

def detect_branded_product(product_name: str) -> Tuple[bool, Optional[str]]:
    """Detect if product is branded and extract brand
    
    Returns: (is_branded, brand_name)
    
    Branded: Has known brand (Knorr, Heinz, Aroy-D, etc.)
    Commodity: Raw products without brand (salmon, beef, potatoes)
    """
    
    name_lower = product_name.lower()
    
    # Check if product has a known brand using contract rules
    if RULES_LOADED and contract_rules:
        # Check all brand aliases
        for alias, canonical in contract_rules.brand_aliases.items():
            if alias in name_lower:
                # Found a brand!
                return (True, canonical.upper())
    
    # Fallback: Check for common brand indicators
    # Products with ALL CAPS words > 3 chars are often branded
    words = product_name.split()
    for word in words:
        if word.isupper() and len(word) > 3:
            # Exclude generic words
            if word not in ['ГОСТ', 'РОССИЯ', 'КИТАЙ', 'РФ', 'ТУ', 'КГ']:
                return (True, word)
    
    # Check for known commodity keywords (always unbranded)
    commodity_keywords = [
        'лосось', 'salmon', 'креветк', 'shrimp', 'говядин', 'beef',
        'свинин', 'pork', 'курица', 'chicken', 'картофель', 'potato',
        'лук', 'onion', 'морков', 'carrot', 'капуст', 'cabbage',
        'рыба', 'fish', 'мясо', 'meat', 'овощи', 'vegetables'
    ]
    
    # If product name contains ONLY commodity words and no brands, it's commodity
    has_commodity = any(word in name_lower for word in commodity_keywords)
    
    if has_commodity:
        # But only if NO brand detected
        return (False, None)
    
    # Default: if uncertain, treat as commodity (safer)
    return (False, None)


# For testing
if __name__ == '__main__':
    tests = [
        "БУЛЬОН грибной 2 кг. Knorr professional",
        "ЛОСОСЬ филе на коже трим D с/м вес 1,5 кг",
        "Кетчуп томатный 800 гр. Heinz",
        "Картофель красный свежий 1кг",
        "Соус терияки 1л Aroy-D",
        "Говядина вырезка охлажденная вес",
    ]
    
    print("Testing branded detection:\n")
    for product in tests:
        is_branded, brand = detect_branded_product(product)
        print(f"{'✅ BRANDED' if is_branded else '❌ COMMODITY'} {product[:50]:50} → {brand or 'No brand'}")
