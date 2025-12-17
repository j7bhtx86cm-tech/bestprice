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
    """Extract main product category with specific keywords"""
    
    # Define specific product patterns - prioritize multi-word matches
    # Format: type_name: [list of keywords that ALL must be present]
    composite_patterns = {
        "анчоус_филе": ["анчоус", "филе"],
        "тунец_филе": ["тунец", "филе"],
        "лосось_филе": ["лосось", "филе"],
        "семга_филе": ["семга", "филе"],
        "курица_филе": ["курица", "филе"],
        "порошок_куриный": ["порошок", "куриный"],
        "порошок_грибной": ["порошок", "грибной"],
        "бульон_куриный": ["бульон", "куриный"],
        "бульон_грибной": ["бульон", "грибной"],
        "водоросли_нори": ["водоросл", "нори"],
        "водоросли_вакаме": ["водоросл", "вакаме"],
        "водоросли_комбу": ["водоросл", "комбу"],
        "водоросли_чука": ["водоросл", "чука"],
        "масло_растительное": ["масло", "растительн"],
        "масло_подсолнечное": ["масло", "подсолнечн"],
        "масло_оливковое": ["масло", "оливков"],
    }
    
    # Check composite patterns first (more specific)
    for product_type, keywords in composite_patterns.items():
        if all(kw in name_lower for kw in keywords):
            return product_type
    
    # Then check simple patterns
    simple_patterns = {
        "креветки": ["креветк", "shrimp", "prawn"],
        "соус": ["соус", "sauce"],
        "кетчуп": ["кетчуп", "ketchup"],
        "сыр": ["сыр", "cheese"],
        "молоко": ["молоко", "milk"],
        "сливки": ["сливки", "cream"],
        "говядина": ["говядина", "говяжий", "beef"],
        "свинина": ["свинина", "свиной", "pork"],
        "грибы": ["гриб", "шампиньон", "опята"],
        "рис": ["рис", "rice"],
        "макароны": ["макарон", "pasta", "спагетти"],
        "мука": ["мука", "flour"],
        "сахар": ["сахар", "sugar"],
        "соль": ["соль", "salt"],
        "перец": ["перец", "pepper"],
        "томаты": ["томат", "помидор", "tomato"],
        "огурцы": ["огурец", "cucumber"],
        "лук": ["лук", "onion"],
        "чеснок": ["чеснок", "garlic"],
        "картофель": ["картофель", "картошка", "potato"],
        "ананасы": ["ананас", "pineapple"],
        "каперсы": ["каперс", "caper"],
        "арахис": ["арахис", "peanut"],
    }
    
    for product_type, keywords in simple_patterns.items():
        for keyword in keywords:
            if keyword in name_lower:
                return product_type
    
    # Default: use first meaningful word
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
    Find all products matching the intent across all pricelists
    Used for CHEAPEST mode to find alternatives
    """
    matches = []
    
    # Get intent attributes once
    intent_attrs = intent.get('keyAttributes', {})
    
    for pl in all_pricelists:
        if not pl.get('productName') or not pl.get('unit'):
            continue
            
        product_intent = extract_product_intent(pl['productName'], pl['unit'])
        product_attrs = product_intent.get('keyAttributes', {})
        
        # Match criteria
        if product_intent['productType'] != intent['productType']:
            continue
        
        if product_intent['baseUnit'] != intent['baseUnit']:
            continue
        
        # IMPORTANT: Exclude portion packs when matching bulk products
        if intent_attrs.get('is_portion') != product_attrs.get('is_portion'):
            continue  # Don't match bulk with portions or vice versa
        
        # Check pack size similarity (for bulk products)
        if 'pack_size_num' in intent_attrs and 'pack_size_num' in product_attrs:
            intent_num = intent_attrs['pack_size_num']
            product_num = product_attrs['pack_size_num']
            intent_unit = intent_attrs.get('pack_size_unit', '')
            product_unit = product_attrs.get('pack_size_unit', '')
            
            # Convert to same unit if needed (g to kg, ml to l)
            if intent_unit in ['кг', 'kg'] and product_unit in ['г', 'g']:
                product_num = product_num / 1000
            elif intent_unit in ['г', 'g'] and product_unit in ['кг', 'kg']:
                intent_num = intent_num / 1000
            elif intent_unit in ['л', 'l'] and product_unit in ['мл', 'ml']:
                product_num = product_num / 1000
            elif intent_unit in ['мл', 'ml'] and product_unit in ['л', 'l']:
                intent_num = intent_num / 1000
            
            # Only match if within 30% range
            if intent_num > 0 and product_num > 0:
                diff_ratio = abs(intent_num - product_num) / max(intent_num, product_num)
                if diff_ratio > 0.3:
                    continue  # Skip if more than 30% different
        
        # If strict brand is required
        if intent.get('strictBrand') and intent.get('brand'):
            if product_intent.get('brand') != intent['brand']:
                continue
        
        # Check caliber match (exact)
        if 'caliber' in intent_attrs:
            if product_attrs.get('caliber') != intent_attrs['caliber']:
                continue
        
        # Check percent match (exact)
        if 'percent' in intent_attrs:
            if product_attrs.get('percent') != intent_attrs['percent']:
                continue
        
        matches.append(pl)
    
    return matches
