"""
Simple rule-based Product Intent Parser for Russian product names
Extracts: product_type, base_unit, key_attributes, brand
"""
import re
from typing import Dict, Optional, Any

def extract_product_intent(product_name: str, unit: str) -> Dict[str, Any]:
    """
    Parse product name and extract intent parameters
    Returns: {product_type, base_unit, key_attributes, brand, strict_brand}
    """
    name_lower = product_name.lower()
    
    # Extract product type (main category)
    product_type = extract_product_type(name_lower)
    
    # Normalize unit
    base_unit = normalize_unit(unit)
    
    # Extract key attributes (numbers, percentages, caliber)
    key_attributes = extract_key_attributes(product_name)
    
    # Extract brand (if identifiable)
    brand = extract_brand(product_name)
    
    return {
        "productType": product_type,
        "baseUnit": base_unit,
        "keyAttributes": key_attributes,
        "brand": brand,
        "strictBrand": False
    }

def extract_product_type(name_lower: str) -> str:
    """Extract main product category with STRICT matching - primary type must match first"""
    
    # CRITICAL: Check PRIMARY FOOD TYPE first - these must match exactly
    primary_foods = {
        'креветки': ['креветк', 'shrimp', 'prawn'],
        'моцарелла': ['моцарелл', 'mozzarella'],
        'сыр': ['сыр', 'cheese'],
        'кальмар': ['кальмар', 'squid'],
        'анчоус': ['анчоус', 'anchov'],
        'тунец': ['тунец', 'tuna'],
        'лосось': ['лосось', 'семга', 'salmon'],
        'сибас': ['сибас', 'сибасс', 'seabass'],
        'дорадо': ['дорадо', 'дорада', 'dorado'],
        'треска': ['треска', 'cod'],
        'минтай': ['минтай', 'pollock'],
        'курица': ['курица', 'куриц', 'chicken'],
        'говядина': ['говядин', 'beef'],
        'свинина': ['свинин', 'pork'],
        'молоко': ['молоко', 'milk'],
        'кетчуп': ['кетчуп', 'ketchup'],
        'соль': ['соль', 'salt'],
        'сахар': ['сахар', 'sugar'],
        'мука': ['мука', 'flour'],
        'рис': ['рис', 'rice'],
        'масло': ['масло', 'oil', 'butter'],
    }
    
    # Check primary foods first (STRICT)
    for food_type, keywords in primary_foods.items():
        for keyword in keywords:
            if keyword in name_lower:
                return food_type
    
    # Check specific combinations
    composite_patterns = {
        "порошок_куриный": ["порошок", "куриный"],
        "бульон_куриный": ["бульон", "куриный"],
        "бульон_грибной": ["бульон", "грибной"],
        "водоросли_нори": ["водоросл", "нори"],
        "водоросли_комбу": ["водоросл", "комбу"],
    }
    
    for ptype, keywords in composite_patterns.items():
        if all(kw in name_lower for kw in keywords):
            return ptype
    
    # Default: first word
    first_word = name_lower.split()[0] if name_lower.split() else "unknown"
    return first_word

def normalize_unit(unit: str) -> str:
    """Normalize unit to base measurement"""
    unit_lower = unit.lower().strip()
    
    # Weight conversions
    if unit_lower in ['kg', 'кг', 'килограмм']:
        return 'kg'
    if unit_lower in ['g', 'г', 'грамм']:
        return 'g'
    
    # Volume conversions
    if unit_lower in ['l', 'л', 'литр', 'liter']:
        return 'l'
    if unit_lower in ['ml', 'мл', 'миллилитр']:
        return 'ml'
    
    # Count
    if unit_lower in ['pcs', 'шт', 'piece', 'штука']:
        return 'pcs'
    if unit_lower in ['pack', 'упак', 'package']:
        return 'pack'
    
    return unit_lower

def extract_key_attributes(product_name: str) -> Dict[str, Any]:
    """Extract key attributes like caliber, fat percentage, weight"""
    attributes = {}
    
    # Extract caliber (e.g., 31/40, 21/25)
    caliber_match = re.search(r'(\d+)/(\d+)', product_name)
    if caliber_match:
        attributes['caliber'] = caliber_match.group(0)
    
    # Extract percentage (e.g., 82%, 67%)
    percent_match = re.search(r'(\d+)%', product_name)
    if percent_match:
        attributes['percent'] = percent_match.group(0)
    
    # Check for portion/stick packs (to exclude from bulk matching)
    if any(word in product_name.lower() for word in ['порци', 'стик', 'stick', 'sachet', 'пакетик']):
        attributes['is_portion'] = True
    
    # Extract weight/volume in name (e.g., 1кг, 500мл, 250г)
    weight_match = re.search(r'(\d+(?:,\d+)?)\s*(кг|г|мл|л|kg|g|ml|l)', product_name, re.IGNORECASE)
    if weight_match:
        attributes['pack_size'] = weight_match.group(0)
        # Extract just the number for comparison
        num_str = weight_match.group(1).replace(',', '.')
        try:
            attributes['pack_size_num'] = float(num_str)
            attributes['pack_size_unit'] = weight_match.group(2).lower()
        except:
            pass
    
    # Extract numbers (generic)
    numbers = re.findall(r'\d+(?:,\d+)?', product_name)
    if numbers and not attributes:
        attributes['numbers'] = numbers[:2]  # First 2 numbers
    
    return attributes

def extract_brand(product_name: str) -> Optional[str]:
    """Try to identify brand name"""
    
    # Common brands in Russian market
    known_brands = [
        'Heinz', 'Mutti', 'Aroy-D', 'COOK_ME', 'Sunfeel', 'Baleno',
        'Бояринъ', 'Альфа-М', 'DAS', 'Подворье', 'Агро-Альянс',
        'Каскад', 'Праймфудс', 'Деревенское', 'Delicius'
    ]
    
    for brand in known_brands:
        if brand.lower() in product_name.lower():
            return brand
    
    # Try to find capitalized words (often brands)
    words = product_name.split()
    for word in words:
        # If word is all caps or Title Case and length > 3
        if (word.isupper() or word.istitle()) and len(word) > 3:
            # Check if it's not a common Russian word
            common_words = ['Масло', 'Соус', 'Сыр', 'Молоко', 'Курица', 'Соль']
            if word not in common_words:
                return word
    
    return None

def find_matching_products(intent: Dict[str, Any], all_pricelists: list) -> list:
    """
    Find matching products with PRIMARY type check FIRST, secondary attributes SECOND
    """
    matches = []
    
    intent_attrs = intent.get('keyAttributes', {})
    query_primary = intent.get('productType')  # Primary food type
    
    for pl in all_pricelists:
        if not pl.get('productName') or not pl.get('unit'):
            continue
        
        # Skip 0 price products (category headers)
        if pl.get('price', 0) <= 0:
            continue
            
        product_intent = extract_product_intent(pl['productName'], pl['unit'])
        candidate_primary = product_intent.get('productType')
        product_attrs = product_intent.get('keyAttributes', {})
        
        # CRITICAL: PRIMARY TYPE MUST MATCH FIRST
        # креветки only matches креветки, NOT моцарелла/сыр/etc
        if query_primary and candidate_primary:
            # Remove secondary words for comparison
            query_base = query_primary.split('_')[0] if '_' in query_primary else query_primary
            candidate_base = candidate_primary.split('_')[0] if '_' in candidate_primary else candidate_primary
            
            # Primary types must match (krevetki != mozzarella)
            if query_base != candidate_base:
                continue  # Skip - different primary food type
        elif query_primary or candidate_primary:
            # One has type, other doesn't - incompatible
            continue
        
        # Base unit must match
        if product_intent['baseUnit'] != intent['baseUnit']:
            continue
        
        # SECONDARY FILTERS (after primary type matches):
        
        # Exclude portion packs when matching bulk
        if intent_attrs.get('is_portion') != product_attrs.get('is_portion'):
            continue
        
        # Check pack size similarity
        if 'pack_size_num' in intent_attrs and 'pack_size_num' in product_attrs:
            intent_num = intent_attrs['pack_size_num']
            product_num = product_attrs['pack_size_num']
            intent_unit = intent_attrs.get('pack_size_unit', '')
            product_unit = product_attrs.get('pack_size_unit', '')
            
            # Normalize units
            if intent_unit in ['кг', 'kg'] and product_unit in ['г', 'g']:
                product_num = product_num / 1000
            elif intent_unit in ['г', 'g'] and product_unit in ['кг', 'kg']:
                intent_num = intent_num / 1000
            elif intent_unit in ['л', 'l'] and product_unit in ['мл', 'ml']:
                product_num = product_num / 1000
            elif intent_unit in ['мл', 'ml'] and product_unit in ['л', 'l']:
                intent_num = intent_num / 1000
            
            # ±30% tolerance
            if intent_num > 0 and product_num > 0:
                diff_ratio = abs(intent_num - product_num) / max(intent_num, product_num)
                if diff_ratio > 0.3:
                    continue
        
        # Brand matching (if strict)
        if intent.get('strictBrand') and intent.get('brand'):
            if product_intent.get('brand') != intent['brand']:
                continue
        
        # Caliber (exact match required)
        if 'caliber' in intent_attrs:
            if product_attrs.get('caliber') != intent_attrs['caliber']:
                continue
        
        # Percentage (exact match)
        if 'percent' in intent_attrs:
            if product_attrs.get('percent') != intent_attrs['percent']:
                continue
        
        # All checks passed - this is a valid match
        matches.append(pl)
    
    return matches
