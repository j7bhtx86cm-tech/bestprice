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
    
    # Fallback: Check for brand indicators (ALL CAPS or Title Case brands > 4 chars)
    # Skip first word (usually product category)
    words = product_name.split()
    
    for i, word in enumerate(words):
        if i == 0:  # Skip first word (category name)
            continue
        
        # Check if it's a potential brand (ALL CAPS or Title Case, >4 chars)
        is_potential_brand = (word.isupper() or word.istitle()) and len(word) > 4
        
        if is_potential_brand:
            # Exclude generic/commodity words
            excluded = [
                'ГОСТ', 'РОССИЯ', 'КИТАЙ', 'РФ', 'ТУ', 'КГ', 'ГРАММ', 'ЛИТР',
                'ЛОСОСЬ', 'КРЕВЕТКИ', 'ТУНЕЦ', 'СИБАС', 'ДОРАДО', 'ФОРЕЛЬ', 'ТРЕСКА', 'МИНТАЙ',
                'БУЛЬОН', 'СОУС', 'КЕТЧУП', 'МАЙОНЕЗ', 'МАСЛО', 'МУКА', 'ПАСТА',
                'ГОВЯДИНА', 'СВИНИНА', 'КУРИЦА', 'БАРАНИНА', 'ИНДЕЙКА', 'ЯГНЯТИНА', 'УТИНА',
                'КАРТОФЕЛЬ', 'ЛУК', 'МОРКОВЬ', 'КАПУСТА', 'ОГУРЦЫ', 'ТОМАТЫ',
                'РЫБА', 'МЯСО', 'ОВОЩИ', 'ФИЛЕ', 'СТЕЙК', 'ТУШКА', 'ФАРШ',
                'СУХАРИ', 'ХЛЕБ', 'БУЛКА', 'БАТОН', 'ЧИАБАТТА', 'БАГЕТ',
                'РИС', 'ГРЕЧКА', 'ПШЕНО', 'МАНКА', 'БУЛГУР', 'ПЕРЛОВКА',
                'САХАР', 'СОЛЬ', 'ПЕРЕЦ', 'УКСУС', 'ГОРЧИЦА',
                'МОЛОКО', 'СМЕТАНА', 'ТВОРОГ', 'КЕФИР', 'ЙОГУРТ', 'СЛИВКИ',
                'ГЁДЗА', 'ПЕЛЬМЕНИ', 'ВАРЕНИКИ', 'РАВИОЛИ',
                'ПРИПРАВА', 'СПЕЦИИ',
                'БЕФСТРОГАНОВ', 'КОТЛЕТА', 'КОТЛЕТЫ', 'НАГГЕТСЫ', 'БУРГЕР',
                'ДОНАТ', 'ПИРОГ', 'ТОРТ',
                # Generic descriptors
                'ПРОФИ', 'PROFESSIONAL', 'PREMIUM', 'EXTRA', 'CLASSIC',
                'Россия', 'Китай', 'Russia', 'China',
            ]
            
            if word not in excluded and word.upper() not in excluded:
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
