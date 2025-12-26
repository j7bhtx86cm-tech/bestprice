"""Hybrid Matching Engine - Best of Spec + Simple Approach + Contract Rules"""
from typing import Dict, List, Optional
import re

WEIGHT_TOLERANCE = 0.20  # ±20%

# Import contract rules
try:
    from contract_rules import contract_rules
    RULES_LOADED = contract_rules is not None
except:
    RULES_LOADED = False
    contract_rules = None


def extract_brand_from_name(name: str) -> Optional[str]:
    """Extract brand from product name using contract rules"""
    if not RULES_LOADED:
        return None
    
    name_lower = name.lower()
    
    # Check for known brands in the name
    for alias in contract_rules.brand_aliases.keys():
        if alias in name_lower:
            return contract_rules.get_canonical_brand(alias)
    
    return None

def extract_key_identifiers(name: str) -> set:
    """Extract key identifying words from product name
    
    These are important words that differentiate products within the same category.
    """
    name_lower = name.lower()
    
    # Key identifying words (brand names, specific types, flavors)
    key_words = {
        # Sauce types
        'ворчестер', 'worcester', 'унаги', 'unagi', 'соев', 'soy', 'терияки', 'teriyaki',
        'барбекю', 'bbq', 'чесночн', 'garlic', 'сладк', 'sweet', 'остр', 'hot', 'spicy',
        'кисло', 'sour', 'кетчуп', 'ketchup', 'лукdow', 'onion', 'гриб', 'mushroom',
        
        # Seaweed types  
        'даши', 'dashi', 'комбу', 'kombu', 'нори', 'nori', 'вакаме', 'wakame',
        'онигири', 'onigiri', 'суши', 'sushi', 'роллы', 'rolls',
        
        # Meat cuts
        'филе', 'fillet', 'стейк', 'steak', 'корейка', 'rack', 'ребер', 'ribs',
        'ножка', 'leg', 'бедро', 'thigh', 'грудка', 'breast', 'крыло', 'wing',
        'фарш', 'ground', 'мякоть', 'tenderloin', 'вырезка', 'окорок',
        
        # Meat products
        'сосиск', 'sausage', 'колбас', 'salami', 'сардельк',
        
        # Cheese types
        'моцарелла', 'mozzarella', 'пармезан', 'parmesan', 'чеддер', 'cheddar',
        'фета', 'feta', 'бри', 'brie', 'рикотта', 'ricotta',
        
        # Dairy products
        'сливки', 'cream', 'сметана', 'sour cream', 'йогурт', 'yogurt',
        
        # Pasta types
        'спагетти', 'spaghetti', 'пенне', 'penne', 'фузилли', 'fusilli',
        'тальятелле', 'tagliatelle', 'феттучини', 'fettuccine',
        
        # Flour types (CRITICAL!)
        'миндал', 'almond', 'ржан', 'rye', 'пшенич', 'wheat', 'рисов', 'кокос', 'coconut', 'кукуруз', 'corn',
        
        # Prepared foods
        'гёдза', 'gyoza', 'пельмен', 'dumpling', 'донат', 'donut', 'блинчик', 'pancake',
        
        # Bakery
        'тортилья', 'tortilla', 'лаваш', 'lavash', 'пита', 'pita',
        
        # Seasonings/Spices (CRITICAL!)
        'корица', 'cinnamon', 'приправа', 'seasoning', 'ваниль', 'vanilla',
        
        # Specific flavors/ingredients
        'маракуйя', 'passion', 'клубника', 'strawberry', 'шоколад', 'chocolate', 
        'карамель', 'caramel', 'ананас', 'pineapple',
    }
    
    found_identifiers = set()
    for word in key_words:
        if word in name_lower:
            found_identifiers.add(word)
    
    return found_identifiers


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
    query_identifiers = extract_key_identifiers(query_product_name)
    
    # NEW: Seafood STRICT attributes (per MVP requirements)
    from pipeline.enricher import extract_seafood_head_status, extract_cooking_state, extract_trim_grade
    query_head_status = extract_seafood_head_status(query_product_name)
    query_cooking_state = extract_cooking_state(query_product_name)
    query_trim_grade = extract_trim_grade(query_product_name)
    
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
        if item.get('bulk_package'):
            # Item is bulk - only match if query is ALSO bulk (>2kg)
            if not query_weight or query_weight < 2.0:
                continue  # Query is single piece, item is bulk - skip
        
        # Gate 8: Key identifying words MUST match
        # If query has specific identifiers (worcester, unagi, dashi, etc.), item must have at least one
        if query_identifiers:
            item_identifiers = extract_key_identifiers(item.get('name_raw', ''))
            # Check if there's ANY overlap between query and item identifiers
            if not (query_identifiers & item_identifiers):  # No intersection
                continue
        
        # Gate 9: STRICT BRAND matching (from contract rules)
        if RULES_LOADED:
            query_brand = extract_brand_from_name(query_product_name)
            item_brand = item.get('brand')
            
            # If query has a strict brand, item MUST have the same brand
            if query_brand and contract_rules.is_strict_brand(query_brand):
                if not item_brand or contract_rules.get_canonical_brand(item_brand) != query_brand:
                    continue
        
        # Gate 10: SEAFOOD STRICT attributes (per MVP - critical for seafood)
        # For seafood, head status MUST match exactly
        if query_head_status:
            if item.get('seafood_head_status') != query_head_status:
                continue
        
        # Cooking state MUST match (с/м vs в/м is critical difference)
        if query_cooking_state:
            if item.get('cooking_state') != query_cooking_state:
                continue
        
        # Trim grade MUST match (trim A ≠ trim C ≠ trim D)
        if query_trim_grade:
            if item.get('trim_grade') != query_trim_grade:
                continue
        
        matches.append(item)
    
    if not matches:
        return None
    
    # Sort by price_per_base_unit (cheapest first), then by price
    matches.sort(key=lambda x: (x.get('price_per_base_unit', 999999), x.get('price', 999999)))
    
    return matches[0]
