"""
Product Intent Parser with Strict Primary Type Matching
"""
import re
from typing import Dict, Optional, Any

def extract_product_type(name_lower: str) -> str:
    """Extract PRIMARY food type only"""
    
    # Coconut milk special case
    if ('кокос' in name_lower or 'coconut' in name_lower) and ('молок' in name_lower or 'milk' in name_lower):
        return 'молоко_кокосовое'
    
    # Primary foods
    if 'креветк' in name_lower or 'shrimp' in name_lower or 'prawn' in name_lower:
        return 'креветки'
    if 'моцарелл' in name_lower or 'mozzarella' in name_lower:
        return 'моцарелла'
    if 'аппетайзер' in name_lower or 'appetizer' in name_lower:
        return 'аппетайзер'
    if 'кальмар' in name_lower or 'squid' in name_lower:
        return 'кальмар'
    if 'анчоус' in name_lower or 'anchov' in name_lower:
        return 'анчоус'
    if 'тунец' in name_lower or 'tuna' in name_lower:
        return 'тунец'
    if 'лосось' in name_lower or 'ласось' in name_lower or 'семга' in name_lower or 'salmon' in name_lower:
        return 'лосось'
    if 'сибас' in name_lower or 'сибасс' in name_lower or 'seabass' in name_lower:
        return 'сибас'
    if 'дорадо' in name_lower or 'дорада' in name_lower or 'dorado' in name_lower:
        return 'дорадо'
    if 'треска' in name_lower or 'cod' in name_lower:
        return 'треска'
    if 'минтай' in name_lower or 'pollock' in name_lower:
        return 'минтай'
    if 'курица' in name_lower or 'куриц' in name_lower or 'chicken' in name_lower:
        return 'курица'
    if 'говядин' in name_lower or 'beef' in name_lower:
        return 'говядина'
    if 'свинин' in name_lower or 'pork' in name_lower:
        return 'свинина'
    if 'кетчуп' in name_lower or 'ketchup' in name_lower:
        return 'кетчуп'
    if 'соль' in name_lower or 'salt' in name_lower:
        return 'соль'
    if 'сахар' in name_lower or 'sugar' in name_lower:
        return 'сахар'
    if 'мука' in name_lower or 'flour' in name_lower:
        return 'мука'
    if 'рис' in name_lower or 'rice' in name_lower:
        return 'рис'
    if 'молоко' in name_lower or 'milk' in name_lower:
        return 'молоко'
    if 'масло' in name_lower:
        return 'масло'
    
    # Composites
    if 'порошок' in name_lower and 'куриный' in name_lower:
        return 'порошок_куриный'
    if 'бульон' in name_lower and 'куриный' in name_lower:
        return 'бульон_куриный'
    
    return name_lower.split()[0] if name_lower.split() else "unknown"

def extract_brand(raw_name: str) -> Optional[str]:
    """Extract brand - exclude generic words"""
    
    known_brands = [
        'Heinz', 'Mutti', 'Aroy-D', 'COOK_ME', 'Sunfeel',
        'Бояринъ', 'Альфа-М', 'DAS', 'Подворье', 'Knorr',
        'PRB', 'Federici', 'Luxuria', 'Кara'
    ]
    
    for brand in known_brands:
        if brand.lower() in raw_name.lower():
            return brand
    
    # NEVER treat food category words as brands
    GENERIC = [
        'Напиток', 'Продукт', 'Аппетайзер', 'Аппетайзеры',  
        'Масло', 'Соус', 'Сыр', 'Молоко', 'Соль', 'Креветки',
        'Курица', 'Рыба', 'Филе', 'Кокос', 'Палочки',
        'Кондитерские', 'Консервация', 'Бакалея', 'Морепродукты',
        'КРЕВЕТКИ', 'АППЕТАЙЗЕРЫ', 'МОЦАРЕЛЛА', 'КУРИЦА'  # Uppercase versions
    ]
    
    words = raw_name.split()
    for word in words:
        # Check if it's a capitalized word
        if (word.isupper() or word.istitle()) and len(word) > 3:
            # Check against generic list (case-insensitive)
            if not any(word.upper() == g.upper() for g in GENERIC):
                return word
    
    return None

def normalize_unit(unit: str) -> str:
    unit_lower = unit.lower().strip()
    if unit_lower in ['kg', 'кг']: return 'kg'
    if unit_lower in ['g', 'г']: return 'g'
    if unit_lower in ['l', 'л']: return 'l'
    if unit_lower in ['ml', 'мл']: return 'ml'
    if unit_lower in ['pcs', 'шт']: return 'pcs'
    return unit_lower

def extract_weight_kg(text: str) -> Optional[float]:
    """Extract primary product weight in kg from product name
    
    Handles cases like:
    - "СИБАС тушка (300-400 гр) вес 5 кг" → extract 0.3-0.4 kg (product size), not 5kg (package)
    - "МИНТАЙ филе 1 кг" → extract 1 kg
    """
    if not text:
        return None
    
    # Pattern 1: Weight in parentheses (300-400 гр) - usually the actual product size
    paren_match = re.search(r'\((\d+(?:-\d+)?)\s*(?:гр|г|g)\)', text, re.IGNORECASE)
    if paren_match:
        # Extract the first number from range like "300-400"
        nums = re.findall(r'\d+', paren_match.group(1))
        if nums:
            # Use first number as the weight
            return float(nums[0]) / 1000
    
    # Pattern 2: Direct weight mention (not in parentheses)
    # Find all weight mentions
    matches = re.findall(r'(\d+(?:[.,]\d+)?)\s*(кг|kg|г|гр|g)\b', text, re.IGNORECASE)
    
    if not matches:
        return None
    
    weights_kg = []
    for num_str, unit in matches:
        try:
            num = float(num_str.replace(',', '.'))
            # Convert grams to kg
            if unit.lower() in ['г', 'гр', 'g']:
                num = num / 1000
            weights_kg.append(num)
        except:
            continue
    
    if not weights_kg:
        return None
    
    # If we have multiple weights, prefer the smaller one (likely product size, not package)
    # But if all weights are large (>2kg), use the smallest
    small_weights = [w for w in weights_kg if w <= 2.0]
    if small_weights:
        return min(small_weights)  # Smallest reasonable product size
    
    return min(weights_kg)  # All weights are large, use smallest

def extract_key_attributes(product_name: str) -> Dict[str, Any]:
    attributes = {}
    
    caliber_match = re.search(r'(\d+)/(\d+)', product_name)
    if caliber_match:
        attributes['caliber'] = caliber_match.group(0)
    
    percent_match = re.search(r'(\d+)%', product_name)
    if percent_match:
        attributes['percent'] = percent_match.group(0)
    
    if any(w in product_name.lower() for w in ['порци', 'стик', 'stick']):
        attributes['is_portion'] = True
    
    weight_match = re.search(r'(\d+(?:,\d+)?)\s*(кг|г|мл|л|kg|g|ml|l)', product_name, re.IGNORECASE)
    if weight_match:
        attributes['pack_size'] = weight_match.group(0)
        try:
            attributes['pack_size_num'] = float(weight_match.group(1).replace(',', '.'))
            attributes['pack_size_unit'] = weight_match.group(2).lower()
        except:
            pass
    
    return attributes

def extract_product_intent(product_name: str, unit: str) -> Dict[str, Any]:
    name_lower = product_name.lower()
    
    return {
        "productType": extract_product_type(name_lower),
        "baseUnit": normalize_unit(unit),
        "keyAttributes": extract_key_attributes(product_name),
        "brand": extract_brand(product_name),
        "strictBrand": False
    }

def find_matching_products(intent: Dict[str, Any], all_pricelists: list) -> list:
    matches = []
    intent_attrs = intent.get('keyAttributes', {})
    query_primary = intent.get('productType')
    
    for pl in all_pricelists:
        if not pl.get('productName') or not pl.get('unit') or pl.get('price', 0) <= 0:
            continue
        
        product_intent = extract_product_intent(pl['productName'], pl['unit'])
        candidate_primary = product_intent.get('productType')
        
        # PRIMARY TYPE MUST MATCH
        if query_primary != candidate_primary:
            continue
        
        # Base unit
        if product_intent['baseUnit'] != intent['baseUnit']:
            continue
        
        product_attrs = product_intent.get('keyAttributes', {})
        
        # Portions
        if intent_attrs.get('is_portion') != product_attrs.get('is_portion'):
            continue
        
        # Pack size ±30%
        if 'pack_size_num' in intent_attrs and 'pack_size_num' in product_attrs:
            intent_num = intent_attrs['pack_size_num']
            product_num = product_attrs['pack_size_num']
            intent_unit = intent_attrs.get('pack_size_unit', '')
            product_unit = product_attrs.get('pack_size_unit', '')
            
            if intent_unit in ['кг', 'kg'] and product_unit in ['г', 'g']:
                product_num /= 1000
            elif intent_unit in ['г', 'g'] and product_unit in ['кг', 'kg']:
                intent_num /= 1000
            
            if intent_num > 0 and product_num > 0:
                if abs(intent_num - product_num) / max(intent_num, product_num) > 0.3:
                    continue
        
        # Caliber/percent exact
        if 'caliber' in intent_attrs and product_attrs.get('caliber') != intent_attrs['caliber']:
            continue
        if 'percent' in intent_attrs and product_attrs.get('percent') != intent_attrs['percent']:
            continue
        
        matches.append(pl)
    
    return matches
