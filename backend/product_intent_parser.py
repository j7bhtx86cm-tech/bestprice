"""
FIXED Product Intent Parser with Strict Primary Type Matching
"""
import re
from typing import Dict, Optional, Any, List

def extract_product_type(name_lower: str) -> str:
    """Extract PRIMARY food type with strict word boundaries"""
    
    # PRIMARY FOOD TYPES - checked with word boundaries to avoid partial matches
    primary_foods = {
        'креветки': ['креветк', 'shrimp', 'prawn'],
        'моцарелла': ['моцарелл', 'mozzarella'],
        'аппетайзер': ['аппетайзер', 'appetizer'],
        'сыр': ['сыр'],  # Careful - don't match "сыром" etc
        'кальмар': ['кальмар', 'squid'],
        'анчоус': ['анчоус', 'anchov'],
        'тунец': ['тунец', 'tuna'],
        'лосось': ['лосось', 'ласось', 'семга', 'salmon'],
        'сибас': ['сибас', 'сибасс', 'seabass'],
        'дорадо': ['дорадо', 'дорада', 'dorado'],
        'треска': ['треска', 'cod'],
        'минтай': ['минтай', 'pollock'],
        'курица': ['курица', 'куриц', 'chicken'],
        'говядина': ['говядин', 'beef'],
        'свинина': ['свинин', 'pork'],
        'молоко_кокосовое': [],  # Special case handled separately
        'молоко': ['молоко', 'milk'],
        'кетчуп': ['кетчуп', 'ketchup'],
        'соль': ['соль', 'salt'],
        'сахар': ['сахар', 'sugar'],
        'мука': ['мука', 'flour'],
        'рис': ['рис', 'rice'],
        'масло': ['масло', 'oil', 'butter'],
    }
    
    # Special case: Coconut milk
    if ('кокос' in name_lower or 'coconut' in name_lower) and ('молок' in name_lower or 'milk' in name_lower):
        return 'молоко_кокосовое'
    
    # Check each primary type with word boundary awareness
    for food_type, keywords in primary_foods.items():
        for keyword in keywords:
            # Check if keyword appears as whole word or at start
            pattern = f'\\b{re.escape(keyword)}'
            if re.search(pattern, name_lower):
                return food_type
    
    # Composite patterns
    if 'порошок' in name_lower and 'куриный' in name_lower:
        return 'порошок_куриный'
    if 'бульон' in name_lower and 'куриный' in name_lower:
        return 'бульон_куриный'
    if 'бульон' in name_lower and 'грибной' in name_lower:
        return 'бульон_грибной'
    
    # Default
    first_word = name_lower.split()[0] if name_lower.split() else "unknown"
    return first_word

def extract_brand(raw_name: str) -> Optional[str]:
    """Extract brand - EXCLUDE GENERIC WORDS"""
    
    known_brands = [
        'Heinz', 'Mutti', 'Aroy-D', 'COOK_ME', 'Sunfeel', 'Baleno',
        'Бояринъ', 'Альфа-М', 'DAS', 'Подворье', 'Агро-Альянс',
        'Каскад', 'Праймфудс', 'Деревенское', 'Delicius', 'Knorr',
        'КНОРР', 'PRB', 'Federici', 'Luxuria', 'Кara'
    ]
    
    for brand in known_brands:
        if brand.lower() in raw_name.lower():
            return brand
    
    # CRITICAL: Never treat these as brands
    GENERIC_WORDS = [
        'Напиток', 'Продукт', 'Аппетайзер', 'Аппетайзеры',
        'Масло', 'Соус', 'Сыр', 'Молоко', 'Соль', 'Филе',
        'Креветки', 'Курица', 'Рыба', 'Мясо', 'Кондитерские'
    ]
    
    words = raw_name.split()
    for word in words:
        if (word.isupper() or word.istitle()) and len(word) > 3:
            if word not in GENERIC_WORDS:
                return word
    
    return None

def normalize_unit(unit: str) -> str:
    """Normalize unit to base measurement"""
    unit_lower = unit.lower().strip()
    
    if unit_lower in ['kg', 'кг', 'килограмм']:
        return 'kg'
    if unit_lower in ['g', 'г', 'грамм']:
        return 'g'
    if unit_lower in ['l', 'л', 'литр', 'liter']:
        return 'l'
    if unit_lower in ['ml', 'мл', 'миллилитр']:
        return 'ml'
    if unit_lower in ['pcs', 'шт', 'piece', 'штука']:
        return 'pcs'
    if unit_lower in ['pack', 'упак', 'package']:
        return 'pack'
    
    return unit_lower

def extract_key_attributes(product_name: str) -> Dict[str, Any]:
    \"\"\"Extract secondary attributes - NOT for primary type matching\"\"\"
    attributes = {}
    
    # Caliber
    caliber_match = re.search(r'(\\d+)/(\\d+)', product_name)
    if caliber_match:
        attributes['caliber'] = caliber_match.group(0)
    
    # Percentage
    percent_match = re.search(r'(\\d+)%', product_name)
    if percent_match:
        attributes['percent'] = percent_match.group(0)
    
    # Check for portion packs
    if any(word in product_name.lower() for word in ['порци', 'стик', 'stick', 'sachet']):
        attributes['is_portion'] = True
    
    # Extract pack size
    weight_match = re.search(r'(\\d+(?:,\\d+)?)\\s*(кг|г|мл|л|kg|g|ml|l)', product_name, re.IGNORECASE)
    if weight_match:
        attributes['pack_size'] = weight_match.group(0)
        num_str = weight_match.group(1).replace(',', '.')
        try:
            attributes['pack_size_num'] = float(num_str)
            attributes['pack_size_unit'] = weight_match.group(2).lower()
        except:
            pass
    
    return attributes

def extract_product_intent(product_name: str, unit: str) -> Dict[str, Any]:
    \"\"\"Extract product intent with strict primary type\"\"\"
    name_lower = product_name.lower()
    
    product_type = extract_product_type(name_lower)
    base_unit = normalize_unit(unit)
    key_attributes = extract_key_attributes(product_name)
    brand = extract_brand(product_name)
    
    return {
        "productType": product_type,
        "baseUnit": base_unit,
        "keyAttributes": key_attributes,
        "brand": brand,
        "strictBrand": False
    }

def find_matching_products(intent: Dict[str, Any], all_pricelists: list) -> list:
    \"\"\"Find matches with STRICT primary type check\"\"\"
    matches = []
    intent_attrs = intent.get('keyAttributes', {})
    query_primary = intent.get('productType')
    
    for pl in all_pricelists:
        if not pl.get('productName') or not pl.get('unit'):
            continue
        
        # Filter 0 price
        if pl.get('price', 0) <= 0:
            continue
            
        product_intent = extract_product_intent(pl['productName'], pl['unit'])
        candidate_primary = product_intent.get('productType')
        product_attrs = product_intent.get('keyAttributes', {})
        
        # PRIMARY TYPE MUST MATCH (strict!)
        if query_primary != candidate_primary:
            continue  # креветки != моцарелла != сыр
        
        # Base unit must match
        if product_intent['baseUnit'] != intent['baseUnit']:
            continue
        
        # Secondary filters (only after primary matches)
        if intent_attrs.get('is_portion') != product_attrs.get('is_portion'):
            continue
        
        # Pack size
        if 'pack_size_num' in intent_attrs and 'pack_size_num' in product_attrs:
            intent_num = intent_attrs['pack_size_num']
            product_num = product_attrs['pack_size_num']
            intent_unit = intent_attrs.get('pack_size_unit', '')
            product_unit = product_attrs.get('pack_size_unit', '')
            
            # Normalize
            if intent_unit in ['кг', 'kg'] and product_unit in ['г', 'g']:
                product_num = product_num / 1000
            elif intent_unit in ['г', 'g'] and product_unit in ['кг', 'kg']:
                intent_num = intent_num / 1000
            elif intent_unit in ['л', 'l'] and product_unit in ['мл', 'ml']:
                product_num = product_num / 1000
            elif intent_unit in ['мл', 'ml'] and product_unit in ['л', 'l']:
                intent_num = intent_num / 1000
            
            if intent_num > 0 and product_num > 0:
                diff_ratio = abs(intent_num - product_num) / max(intent_num, product_num)
                if diff_ratio > 0.3:
                    continue
        
        # Caliber
        if 'caliber' in intent_attrs:
            if product_attrs.get('caliber') != intent_attrs['caliber']:
                continue
        
        # Percentage
        if 'percent' in intent_attrs:
            if product_attrs.get('percent') != intent_attrs['percent']:
                continue
        
        matches.append(pl)
    
    return matches
