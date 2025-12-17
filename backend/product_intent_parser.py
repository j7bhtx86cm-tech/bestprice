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
        "strictBrand": False  # Can be set by user
    }

def extract_product_type(name_lower: str) -> str:
    """Extract main product category"""
    
    # Define product type patterns
    patterns = {
        "креветки": ["креветк", "shrimp", "prawn"],
        "масло": ["масло растительное", "масло подсолнечное", "масло оливковое", "oil"],
        "соус": ["соус", "sauce", "кетчуп", "ketchup"],
        "сыр": ["сыр", "cheese"],
        "молоко": ["молоко", "milk"],
        "сливки": ["сливки", "cream"],
        "курица": ["курица", "куриный", "курин", "chicken"],
        "говядина": ["говядина", "говяжий", "beef"],
        "свинина": ["свинина", "свиной", "pork"],
        "рыба": ["рыба", "рыбный", "fish", "лосось", "семга", "форель"],
        "грибы": ["гриб", "шампиньон", "опята", "вешенки", "mushroom"],
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
        "ягоды": ["брусника", "вишня", "клюква", "berry"],
    }
    
    for product_type, keywords in patterns.items():
        for keyword in keywords:
            if keyword in name_lower:
                return product_type
    
    # Default: use first word
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
    
    # Extract weight/volume in name (e.g., 1кг, 500мл, 250г)
    weight_match = re.search(r'(\d+(?:,\d+)?)\s*(кг|г|мл|л|kg|g|ml|l)', product_name, re.IGNORECASE)
    if weight_match:
        attributes['pack_size'] = weight_match.group(0)
    
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
        'Каскад', 'Праймфудс', 'Деревенское'
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
            common_words = ['Масло', 'Соус', 'Сыр', 'Молоко', 'Курица']
            if word not in common_words:
                return word
    
    return None

def find_matching_products(intent: Dict[str, Any], all_pricelists: list) -> list:
    """
    Find all products matching the intent across all pricelists
    Used for CHEAPEST mode to find alternatives
    """
    matches = []
    
    for pl in all_pricelists:
        product_intent = extract_product_intent(pl['productName'], pl['unit'])
        
        # Match criteria
        if product_intent['productType'] != intent['productType']:
            continue
        
        if product_intent['baseUnit'] != intent['baseUnit']:
            continue
        
        # If strict brand is required
        if intent.get('strictBrand') and intent.get('brand'):
            if product_intent.get('brand') != intent['brand']:
                continue
        
        # Check key attributes match (if specified)
        if intent.get('keyAttributes'):
            intent_attrs = intent['keyAttributes']
            product_attrs = product_intent.get('keyAttributes', {})
            
            # Check caliber match
            if 'caliber' in intent_attrs:
                if product_attrs.get('caliber') != intent_attrs['caliber']:
                    continue
            
            # Check percent match
            if 'percent' in intent_attrs:
                if product_attrs.get('percent') != intent_attrs['percent']:
                    continue
        
        matches.append(pl)
    
    return matches
