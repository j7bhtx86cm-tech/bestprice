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

# Import auto-generated keywords
try:
    from auto_generated_keywords import AUTO_KEYWORDS
    AUTO_KEYWORDS_LOADED = True
    print(f"✅ Loaded {len(AUTO_KEYWORDS)} auto-generated keywords")
except:
    AUTO_KEYWORDS_LOADED = False
    AUTO_KEYWORDS = set()


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
    """Extract key identifying words - HYBRID: Manual + Auto-generated
    
    Combines:
    1. Manually curated critical keywords (200+)
    2. Auto-generated from catalog analysis (1,407)
    """
    name_lower = name.lower()
    
    # PART 1: Manually curated CRITICAL keywords (high priority)
    manual_keywords = {
        # Sauce types
        'ворчестер', 'worcester', 'унаги', 'unagi', 'соев', 'soy', 'терияки', 'teriyaki',
        'барбекю', 'bbq', 'чесночн', 'garlic', 'луков', 'onion', 'гриб', 'mushroom',
        
        # Noodle types
        'соба', 'soba', 'удон', 'udon', 'рамен', 'ramen', 'фунчоза', 'funchoza',
        'яичная', 'egg noodle',
        
        # Cake flavors
        'медовик', 'honey cake', 'фисташков', 'pistachio', 'наполеон', 'napoleon',
        
        # Broth types
        'курин', 'chicken', 'овощ', 'vegetable', 'говяж', 'beef', 'рыбн', 'fish', 'грибн',
        
        # Donut fillings
        'лимонн', 'lemon', 'карамель', 'caramel',
        
        # Pepper types
        'черн', 'black', '4 перца', '5 перцев',
        
        # Bean types
        'белая', 'white', 'красная', 'red',
        
        # Miso types
        'aka miso', 'shiro miso',
        
        # Fish types
        'тилапия', 'tilapia', 'щука', 'pike', 'судак', 'zander',
        
        # Honey types
        'цветочн', 'floral', 'липов', 'linden',
        
        # Puree flavors
        'лайм', 'lime', 'бергамот', 'bergamot', 'малин', 'raspberry',
        
        # Potato prep
        'панировк', 'breaded', 'без панировки',
        'мытый', 'washed', 'не мытый', 'unwashed',
        
        # Rice varieties
        'италика', 'italica', 'арборио', 'arborio',
    }
    
    found_identifiers = set()
    
    # Check manual keywords
    for word in manual_keywords:
        if word in name_lower:
            found_identifiers.add(word)
    
    # PART 2: Check auto-generated keywords (if loaded)
    if AUTO_KEYWORDS_LOADED:
        for word in AUTO_KEYWORDS:
            if word in name_lower:
                found_identifiers.add(word)
    
    return found_identifiers


def find_best_match_hybrid(query_product_name: str, original_price: float, 
                           all_items: List[Dict], strict_brand_override: bool = False) -> Optional[Dict]:
    """Hybrid matching: Spec infrastructure + Simple logic + STRICT validation
    
    Rules:
    1-7. Base gates (category, weight, caliber, etc.)
    8. Key identifiers overlap
    9. STRICT BRAND
    10. SEAFOOD STRICT
    11. MEAT TYPE STRICT (NEW!)
    12. SAUCE TYPE STRICT (NEW!)
    13. NAME SIMILARITY for broad categories (NEW!)
    
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
    
    # NEW: Meat type extraction (курин, говяд, свин)
    query_meat_type = extract_meat_type(query_product_name)
    
    # NEW: Rice type extraction (басмати, жасмин, для суши)
    query_rice_type = extract_rice_type(query_product_name)
    
    # NEW: Product subtypes (молочный vs горький шоколад, льна vs чиа семена, etc.)
    query_subtypes = extract_product_subtype(query_product_name)
    
    # Determine query base_unit
    query_base_unit = 'kg' if query_weight else 'pcs'
    
    # For broad categories, prepare word set for similarity check
    query_words = set(query_product_name.lower().split())
    
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
        if item.get('bulk_package'):
            if not query_weight or query_weight < 2.0:
                continue
        
        # Gate 8: Key identifying words - STRICTER logic
        item_identifiers = extract_key_identifiers(item.get('name_raw', ''))
        
        # If EITHER side has identifiers, they MUST overlap
        if query_identifiers or item_identifiers:
            overlap = query_identifiers & item_identifiers
            
            if not overlap:
                continue
            
            # ADDITIONAL CHECK: Overlap must include SPECIFIC identifiers, not just generic
            # Generic identifiers that don't help: филе, донат, котлета, пельмени, etc.
            generic_identifiers = {
                'филе', 'fillet', 'стейк', 'steak', 'донат', 'donut',
                'котлет', 'cutlet', 'пельмен', 'dumpling', 'гёдза', 'gyoza',
                'пюре', 'puree', 'салат', 'salad', 'торт', 'cake',
                'лапша', 'noodle', 'сыр', 'cheese', 'соус', 'sauce',
                'бульон', 'broth', 'крем', 'cream'
            }
            
            # Check if overlap contains at least one NON-generic identifier
            specific_overlap = overlap - generic_identifiers
            
            # If only generic words overlap (like "филе" or "донат"), block the match
            if not specific_overlap and len(overlap - generic_identifiers) == 0:
                continue
        
        # Gate 9: STRICT BRAND matching (from contract rules OR user preference)
        if RULES_LOADED or strict_brand_override:
            query_brand = extract_brand_from_name(query_product_name)
            item_brand = item.get('brand')
            
            # Check if brand must be strict (either from contract or user choice)
            brand_must_match = False
            
            if strict_brand_override and query_brand:
                # User explicitly wants this brand only
                brand_must_match = True
            elif query_brand and contract_rules and contract_rules.is_strict_brand(query_brand):
                # Brand is strict per contract (Mutti, Knorr, etc.)
                brand_must_match = True
            
            if brand_must_match:
                if not item_brand or contract_rules.get_canonical_brand(item_brand) != query_brand:
                    continue
        
        # Gate 10: SEAFOOD STRICT attributes
        if query_head_status:
            if item.get('seafood_head_status') != query_head_status:
                continue
        
        if query_cooking_state:
            if item.get('cooking_state') != query_cooking_state:
                continue
        
        if query_trim_grade:
            if item.get('trim_grade') != query_trim_grade:
                continue
        
        # Gate 11: MEAT TYPE STRICT (NEW! курин ≠ говяд ≠ свин)
        if query_meat_type:
            item_meat_type = extract_meat_type(item.get('name_raw', ''))
            if item_meat_type != query_meat_type:
                continue
        
        # Gate 12: SAUCE/CONDIMENT TYPE STRICT - MANDATORY! (NEW!)
        # For sauces, sauce keywords MUST overlap
        if query_super_class.startswith('condiments.sauce') or 'соус' in query_product_name.lower():
            sauce_keywords_query = extract_sauce_keywords(query_product_name)
            sauce_keywords_item = extract_sauce_keywords(item.get('name_raw', ''))
            
            # BOTH must have keywords AND they must overlap
            if sauce_keywords_query or sauce_keywords_item:
                if not (sauce_keywords_query & sauce_keywords_item):
                    continue
        
        # Gate 14: RICE TYPE STRICT (NEW! басмати ≠ жасмин ≠ для суши)
        if query_super_class == 'staples.rice' or 'рис' in query_product_name.lower():
            if query_rice_type:
                item_rice_type = extract_rice_type(item.get('name_raw', ''))
                # If query specifies rice type, item MUST match or have no type specified
                if item_rice_type and item_rice_type != query_rice_type:
                    continue
        
        # Gate 15: PRODUCT SUBTYPE STRICT (NEW! молочный≠горький, льна≠чиа, темная≠светлая)
        # If query has specific subtypes (chocolate type, seed type, bread color), they MUST overlap
        if query_subtypes:
            item_subtypes = extract_product_subtype(item.get('name_raw', ''))
            
            # If both have subtypes, they MUST overlap
            # This prevents: молочный шоколад ≠ горький шоколад
            if item_subtypes and not (query_subtypes & item_subtypes):
                continue
        
        # Gate 16: PREPARED vs RAW INGREDIENT (NEW!)
        # Prepared dishes should NOT match with raw ingredients
        # Example: котлета с сыром ≠ сыр, пельмени с мясом ≠ мясо
        query_is_prepared = is_prepared_dish(query_product_name)
        item_is_prepared = is_prepared_dish(item.get('name_raw', ''))
        
        # If one is prepared and other is raw ingredient, block
        if query_is_prepared != item_is_prepared:
            continue
        
        # Gate 13: NAME SIMILARITY - VERY STRICT! (applied last)
        # Require 50% word overlap for ALL categories to prevent false positives
        item_words = set(item.get('name_raw', '').lower().split())
        
        # Remove common generic words that don't help with matching
        generic_words = {'кг', 'гр', 'г', 'л', 'мл', 'шт', 'упак', 'пакет', 'кор', 
                        'ведро', 'бут', 'bottle', 'pack', 'box', '~', 'вес', 'weight',
                        'с/м', 'в/м', 'в/у', 'охл', 'зам', 'frozen', 'chilled'}
        
        query_words_clean = query_words - generic_words
        item_words_clean = item_words - generic_words
        
        if len(query_words_clean) > 0:
            # Calculate meaningful word overlap (excluding generic words)
            common_words = query_words_clean & item_words_clean
            similarity = len(common_words) / len(query_words_clean)
            
            # PRACTICAL: 70% similarity allows finding alternatives
            # Gate 17 (conflicting identifiers) prevents false positives
            if similarity < 0.70:
                continue
        
        # Gate 17: NO CONFLICTING IDENTIFIERS (NEW - FINAL DEFENSE!)
        # If query and item have DIFFERENT specific identifiers, block
        # Example: query has "липовый", item has "цветочный" → CONFLICT!
        if query_identifiers and item_identifiers:
            # Check for known conflicting pairs
            conflicts = [
                {'липов', 'цветочн', 'гречишн'},  # Honey types - mutually exclusive
                {'басмати', 'италика', 'жасмин', 'арборио'},  # Rice types - mutually exclusive
                {'красный', 'обычный', 'кровавый'},  # Orange types
                {'с хвост', 'без хвост'},  # With/without tail
                {'с голов', 'без голов'},  # With/without head
                {'панировк', 'без панировки'},  # With/without breading
                {'мытый', 'не мытый'},  # Washed/unwashed
                {'курин', 'овощ', 'говяж', 'рыбн', 'грибн'},  # Broth types - CRITICAL!
                {'соба', 'удон', 'рамен', 'фунчоза', 'яичная'},  # Noodle types
                {'медовик', 'фисташков', 'наполеон', 'тирамису'},  # Cake flavors
                {'тилапия', 'щука', 'судак', 'сом'},  # Fish types
            ]
            
            has_conflict = False
            for conflict_set in conflicts:
                query_has = query_identifiers & conflict_set
                item_has = item_identifiers & conflict_set
                
                # If both have identifiers from same conflict set but they differ → CONFLICT!
                if query_has and item_has and query_has != item_has:
                    has_conflict = True
                    break
            
            if has_conflict:
                continue
        
        matches.append(item)
    
    if not matches:
        return None
    
    # Sort by price_per_base_unit (cheapest first), then by price
    matches.sort(key=lambda x: (x.get('price_per_base_unit', 999999), x.get('price', 999999)))
    
    return matches[0]


def extract_meat_type(name: str) -> Optional[str]:
    """Extract meat type: курин, говяд, свин, индейк, etc."""
    name_lower = name.lower()
    
    if 'курин' in name_lower or 'куриц' in name_lower or 'chicken' in name_lower:
        return 'chicken'
    if 'говяд' in name_lower or 'говяж' in name_lower or 'beef' in name_lower:
        return 'beef'
    if 'свин' in name_lower or 'pork' in name_lower:
        return 'pork'
    if 'индейк' in name_lower or 'turkey' in name_lower:
        return 'turkey'
    if 'ягнят' in name_lower or 'баран' in name_lower or 'lamb' in name_lower:
        return 'lamb'
    
    return None


def extract_sauce_keywords(name: str) -> set:
    """Extract sauce flavor/type keywords"""
    name_lower = name.lower()
    
    sauce_types = {
        'соев', 'soy', 'терияки', 'teriyaki', 'унаги', 'unagi', 
        'ворчестер', 'worcester', 'барбекю', 'bbq', 'томат', 'tomato',
        'чесночн', 'garlic', 'лук', 'onion', 'гриб', 'mushroom',
        'сладк', 'sweet', 'остр', 'hot', 'кисло', 'sour',
        'сырн', 'cheese', 'сливочн', 'cream', 'карри', 'curry',
        'песто', 'pesto', 'цезарь', 'caesar', 'горчичн', 'mustard',
        'ананас', 'pineapple', 'чили', 'chili', 'перц', 'pepper',
        'пад тай', 'pad thai', 'кимчи', 'kimchi'
    }
    
    found = set()
    for keyword in sauce_types:
        if keyword in name_lower:
            found.add(keyword)
    
    return found


def extract_product_subtype(name: str) -> set:
    """Extract product subtypes that MUST match exactly
    
    Uses word boundaries to avoid false matches (чиа ≠ чиабатта)
    """
    name_lower = name.lower()
    
    subtypes_patterns = {
        # Chocolate types (with word boundaries)
        r'\bмолочный\b': 'молочный',
        r'\bmilk\b': 'milk',
        r'\bгорький\b': 'горький',
        r'\bдарк\b': 'dark',
        r'\bбелый\b': 'white',
        
        # Seed types (with word boundaries to avoid чиа in чиабатта!)
        r'\bльна\b': 'льна',
        r'\bflax\b': 'flax',
        r'\bчиа\b': 'чиа',  # Only match standalone "чиа", not in "чиабатта"
        r'\bchia\b': 'chia',
        r'\bкунжут': 'кунжут',
        r'\bсезам': 'sesame',
        r'\bподсолнечник': 'подсолнечник',
        
        # Root vegetables (word boundaries)
        r'\bсельдерей\b': 'сельдерей',
        r'\bcelery\b': 'celery',
        r'\bхрен\b': 'хрен',
        r'\bhorseradish\b': 'horseradish',
        r'\bимбирь\b': 'имбирь',
        r'\bginger\b': 'ginger',
        
        # Bread colors (word boundaries)
        r'\bтемн': 'темная',
        r'\bсветл': 'светлая',
        r'\bчерн': 'черная',
        
        # Nuts
        r'\bгрецк': 'грецкий',
        r'\bwalnut\b': 'walnut',
        r'\bфундук': 'фундук',
        r'\bминдаль': 'миндаль',
        r'\balmond\b': 'almond',
    }
    
    found = set()
    for pattern, canonical in subtypes_patterns.items():
        if re.search(pattern, name_lower):
            found.add(canonical)
    
    return found



def is_prepared_dish(name: str) -> bool:
    """Check if product is a prepared/cooked dish vs raw ingredient
    
    Prepared dishes: котлета, пельмени, пирог, гёдза, наггетсы, etc.
    Raw ingredients: сыр, мясо, овощи, etc.
    """
    name_lower = name.lower()
    
    prepared_markers = [
        'котлета', 'cutlet', 'пельмен', 'dumpling', 'гёдза', 'gyoza',
        'наггетс', 'nugget', 'бургер', 'burger', 'пирог', 'pie',
        'блинчик', 'pancake', 'чебурек', 'донат', 'donut',
        'голубц', 'тефтел', 'meatball', 'фрикадельк',
        'колбаск для гриля', 'шашлык', 'kebab',
        'полуфабрикат', 'п/ф', 'готов',
    ]
    
    for marker in prepared_markers:
        if marker in name_lower:
            return True
    
    return False


def extract_rice_type(name: str) -> Optional[str]:
    """Extract rice type: басмати, жасмин, для суши, круглозерный, etc."""
    name_lower = name.lower()
    
    if 'басмати' in name_lower or 'basmati' in name_lower:
        return 'basmati'
    if 'жасмин' in name_lower or 'jasmine' in name_lower:
        return 'jasmine'
    if 'италика' in name_lower or 'italica' in name_lower:
        return 'italica'
    if 'арборио' in name_lower or 'arborio' in name_lower:
        return 'arborio'
    if 'девзира' in name_lower or 'devzira' in name_lower:
        return 'devzira'
    if 'суши' in name_lower or 'sushi' in name_lower:
        return 'sushi'
    if 'круглозерн' in name_lower or 'round' in name_lower:
        return 'round_grain'
    if 'длиннозерн' in name_lower or 'long' in name_lower:
        return 'long_grain'
    if 'пропарен' in name_lower or 'parboiled' in name_lower:
        return 'parboiled'
    if 'дикий' in name_lower or 'wild' in name_lower:
        return 'wild'
    if 'бурый' in name_lower or 'brown' in name_lower:
        return 'brown'
    if 'черный' in name_lower or 'black' in name_lower:
        return 'black'
    
    return None
