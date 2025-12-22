"""Feature Extraction (Weight, Volume, Packaging, Caliber, Brand)"""
import re
from typing import Dict, Optional, List, Any

def extract_weights(text: str) -> Dict[str, Any]:
    """Extract all weight mentions and determine net_weight_kg
    
    Returns:
        net_weight_kg: float or None
        piece_weight_kg: float or None
        variable_weight: bool
    """
    if not text:
        return {'net_weight_kg': None, 'piece_weight_kg': None, 'variable_weight': False}
    
    # Find all weight mentions
    weight_pattern = r'(\d+(?:[.,]\d+)?)\s*[-~]?\s*(\d+(?:[.,]\d+)?)?\s*(кг|kg|г|гр|g)\b'
    matches = re.findall(weight_pattern, text, re.IGNORECASE)
    
    if not matches:
        return {'net_weight_kg': None, 'piece_weight_kg': None, 'variable_weight': False}
    
    weights_kg = []
    is_variable = False
    
    for match in matches:
        num1_str, num2_str, unit = match
        
        try:
            num1 = float(num1_str.replace(',', '.'))
            
            # Range detected
            if num2_str:
                num2 = float(num2_str.replace(',', '.'))
                # Use average of range
                num1 = (num1 + num2) / 2
                is_variable = True
            
            # Convert to kg
            if unit.lower() in ['г', 'гр', 'g']:
                num1 = num1 / 1000
            
            weights_kg.append(num1)
        except:
            continue
    
    if not weights_kg:
        return {'net_weight_kg': None, 'piece_weight_kg': None, 'variable_weight': False, 'bulk_package': False}
    
    # Detect BULK PACKAGING
    # If multiple weights and largest is 5x+ bigger than smallest, it's bulk
    bulk_package = False
    if len(weights_kg) > 1 and max(weights_kg) >= 2.0:
        ratio = max(weights_kg) / min(weights_kg)
        if ratio >= 5:  # Package is 5x+ larger than piece (e.g., 5kg / 0.35kg = 14x)
            bulk_package = True
    
    # Rule: If bulk package, use PIECE weight as net_weight (for proper comparison)
    # Otherwise use maximum weight
    if bulk_package:
        net_weight = min(weights_kg)  # Piece weight
        package_weight_kg = max(weights_kg)  # Total package weight
        piece_weight = min(weights_kg)
    else:
        net_weight = max(weights_kg)
        package_weight_kg = None
        piece_weight = min(weights_kg) if len(weights_kg) > 1 else None
    
    return {
        'net_weight_kg': net_weight,
        'package_weight_kg': package_weight_kg,
        'piece_weight_kg': piece_weight,
        'variable_weight': is_variable,
        'bulk_package': bulk_package
    }

def extract_volumes(text: str) -> Dict[str, Any]:
    """Extract volume in liters"""
    if not text:
        return {'net_volume_l': None}
    
    volume_pattern = r'(\d+(?:[.,]\d+)?)\s*(л|l|мл|ml)\b'
    matches = re.findall(volume_pattern, text, re.IGNORECASE)
    
    if not matches:
        return {'net_volume_l': None}
    
    volumes_l = []
    for num_str, unit in matches:
        try:
            num = float(num_str.replace(',', '.'))
            if unit.lower() in ['мл', 'ml']:
                num = num / 1000
            volumes_l.append(num)
        except:
            continue
    
    return {'net_volume_l': max(volumes_l) if volumes_l else None}

def extract_packaging(text: str) -> Dict[str, Any]:
    """Extract pack quantity
    
    Patterns:
    - 12 шт/упак
    - 80g×60pcs
    - 1 box / 480 pcs
    - 25g*225pcs
    """
    # Pattern: X pcs/pack, X шт/упак
    pack_patterns = [
        r'(\d+)\s*(?:шт|pcs|pieces)\s*[\/\*×x]\s*(?:упак|pack|box)',
        r'(\d+)\s*(?:шт|pcs)\/(?:кор|упак)',
        r'\*(\d+)\s*(?:шт|pcs)',
    ]
    
    for pattern in pack_patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            try:
                return {'pack_qty': int(match.group(1))}
            except:
                pass
    
    return {'pack_qty': None}

def extract_caliber(text: str) -> Optional[str]:
    """Extract caliber: 16/20, 4/5, 70/30, 100/110, etc."""
    match = re.search(r'\b(\d{1,3})\s*\/\s*(\d{1,3})(?:\s*\+)?\b', text)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None

def extract_fat_pct(text: str) -> Optional[int]:
    """Extract fat percentage: 45%, 2.5%, etc."""
    match = re.search(r'(\d{1,2}(?:[.,]\d+)?)\s*%', text)
    if match:
        try:
            return int(float(match.group(1).replace(',', '.')))
        except:
            pass
    return None

def extract_brand(text: str) -> Optional[str]:
    """Extract brand from name"""
    known_brands = [
        'Heinz', 'Mutti', 'Aroy-D', 'VICI', 'Knorr', 'Hellmann',
        'Балтийский', 'Махеев', 'Царский', 'Пятерочка',
        'Sunfeel', 'KOTANYI', 'Federici', 'Pomi', 'Bonduelle'
    ]
    
    for brand in known_brands:
        if brand.lower() in text.lower():
            return brand
    
    # Look for capitalized words that might be brands
    words = text.split()
    for word in words:
        # Check if it's capitalized and >3 chars
        if (word.isupper() or word.istitle()) and len(word) > 3:
            # Exclude generic words
            if word.upper() not in ['ФИЛЕ', 'СОУС', 'МАСЛО', 'КРЕВЕТКИ', 'РЫБА']:
                return word
    
    return None

def extract_super_class(name_lower: str) -> str:
    """Classify into super_class WITH sub-type granularity"""
    # Seafood
    if any(w in name_lower for w in ['креветк', 'shrimp', 'prawn']):
        return 'seafood.shrimp'
    if any(w in name_lower for w in ['лосось', 'семга', 'salmon']):
        return 'seafood.salmon'
    if any(w in name_lower for w in ['тунец', 'tuna']):
        return 'seafood.tuna'
    if any(w in name_lower for w in ['минтай', 'pollock']):
        return 'seafood.pollock'
    if any(w in name_lower for w in ['треска', 'cod']):
        return 'seafood.cod'
    if any(w in name_lower for w in ['сибас', 'seabass']):
        return 'seafood.seabass'
    if any(w in name_lower for w in ['дорадо', 'дорада', 'dorado']):
        return 'seafood.dorado'
    if any(w in name_lower for w in ['форель', 'trout']):
        return 'seafood.trout'
    if any(w in name_lower for w in ['кальмар', 'squid']):
        return 'seafood.squid'
    if any(w in name_lower for w in ['мидии', 'mussel']):
        return 'seafood.mussel'
    if any(w in name_lower for w in ['анчоус', 'anchov']):
        return 'seafood.anchovy'
    if 'водоросли' in name_lower or 'seaweed' in name_lower:
        return 'seafood.seaweed'
    
    # Meat
    if 'говядин' in name_lower or 'beef' in name_lower:
        if 'фарш' in name_lower or 'ground' in name_lower or 'молот' in name_lower:
            return 'meat.beef.ground'
        return 'meat.beef'
    if 'свинин' in name_lower or 'pork' in name_lower:
        if 'фарш' in name_lower:
            return 'meat.pork.ground'
        return 'meat.pork'
    if 'курица' in name_lower or 'куриц' in name_lower or 'chicken' in name_lower:
        return 'meat.chicken'
    
    # Dairy
    if 'молоко' in name_lower and ('кокос' in name_lower or 'coconut' in name_lower):
        return 'dairy.milk.coconut'
    if 'молоко' in name_lower:
        return 'dairy.milk'
    if 'сыр' in name_lower:
        return 'dairy.cheese'
    if 'моцарелл' in name_lower:
        return 'dairy.mozzarella'
    
    # Vegetables - Mushrooms (CRITICAL - granular types)
    if 'гриб' in name_lower or 'mushroom' in name_lower:
        # Check for MIX first
        has_oyster = 'вешенк' in name_lower or 'oyster' in name_lower
        has_champignon = 'шампиньон' in name_lower or 'champignon' in name_lower
        has_white = 'белые' in name_lower or 'белый' in name_lower
        
        # If it's a mix, mark as such
        if (has_oyster and (has_champignon or has_white)) or \
           (has_champignon and has_oyster):
            return 'vegetables.mushrooms.mix'
        
        # Single types
        if has_oyster:
            return 'vegetables.mushrooms.oyster'
        if has_champignon:
            return 'vegetables.mushrooms.champignon'
        if has_white:
            return 'vegetables.mushrooms.white'
        
        return 'vegetables.mushrooms'
    
    if 'огурц' in name_lower or 'cucumber' in name_lower:
        return 'vegetables.cucumber'
    if 'томат' in name_lower or 'помидор' in name_lower:
        return 'vegetables.tomato'
    
    # Condiments
    if 'кетчуп' in name_lower:
        if 'дип' in name_lower or 'порц' in name_lower or 'dip' in name_lower:
            return 'condiments.ketchup.portion'
        return 'condiments.ketchup'
    if 'соус' in name_lower:
        if 'томат' in name_lower:
            return 'condiments.sauce.tomato'
        if 'соев' in name_lower or 'soy' in name_lower:
            return 'condiments.sauce.soy'
        return 'condiments.sauce'
    if 'паста' in name_lower and 'томат' in name_lower:
        return 'condiments.tomato_paste'
    if 'масло' in name_lower and 'олив' in name_lower:
        return 'condiments.oil'
        return 'condiments.oil'
    
    # Staples
    if 'рис' in name_lower:
        return 'staples.rice'
    if 'мука' in name_lower:
        return 'staples.flour'
    if 'сахар' in name_lower:
        return 'staples.sugar'
    if 'соль' in name_lower:
        return 'staples.salt'
    if 'крупа' in name_lower:
        return 'staples.grain'
    if 'манк' in name_lower or 'semolina' in name_lower:
        return 'staples.semolina'
    if 'хлопья' in name_lower or 'flakes' in name_lower or 'овсян' in name_lower:
        return 'staples.flakes'
    if 'булгур' in name_lower or 'bulgur' in name_lower:
        return 'staples.bulgur'
    if 'греч' in name_lower or 'buckwheat' in name_lower:
        return 'staples.buckwheat'
    
    # Pasta
    if any(w in name_lower for w in ['макарон', 'мак. изд', 'паста', 'pasta', 'спагетти', 'spaghetti', 'фузилли', 'пенне', 'penne']):
        return 'pasta'
    
    # Fruits
    if 'ананас' in name_lower or 'pineapple' in name_lower:
        return 'fruits.pineapple'
    if 'яблок' in name_lower or 'apple' in name_lower:
        return 'fruits.apple'
    if 'банан' in name_lower or 'banana' in name_lower:
        return 'fruits.banana'
    if 'апельсин' in name_lower or 'orange' in name_lower:
        return 'fruits.orange'
    if 'лимон' in name_lower or 'lemon' in name_lower:
        return 'fruits.lemon'
    
    # Eggs
    if 'яйцо' in name_lower or 'яйц' in name_lower or 'egg' in name_lower:
        if 'перепел' in name_lower or 'quail' in name_lower:
            return 'eggs.quail'
        return 'eggs.chicken'
    
    # Condiments & Spices
    if 'горчиц' in name_lower or 'mustard' in name_lower:
        return 'condiments.mustard'
    if 'каперс' in name_lower or 'caper' in name_lower:
        return 'condiments.capers'
    if 'уксус' in name_lower or 'vinegar' in name_lower:
        return 'condiments.vinegar'
    if 'специи' in name_lower or 'spice' in name_lower:
        return 'condiments.spice'
    if 'перец' in name_lower and not any(w in name_lower for w in ['болгарск', 'сладк', 'bell']):
        return 'condiments.pepper'
    
    # Non-food items
    if any(w in name_lower for w in ['трубочк', 'соломка', 'straw']):
        return 'disposables.straws'
    if any(w in name_lower for w in ['салфетк', 'napkin']):
        return 'disposables.napkins'
    if any(w in name_lower for w in ['контейнер', 'container', 'упаковк']):
        return 'disposables.containers'
    if any(w in name_lower for w in ['перчатк', 'glove']):
        return 'disposables.gloves'
    
    return 'other'

def extract_processing_flags(name_lower: str) -> List[str]:
    """Extract processing/preparation flags"""
    flags = []
    
    if 'панировк' in name_lower or 'bread' in name_lower:
        flags.append('breaded')
    if 'маринов' in name_lower or 'marinat' in name_lower:
        flags.append('marinated')
    if 'копчен' in name_lower or 'smoked' in name_lower:
        flags.append('smoked')
    if 'соленый' in name_lower or 'salted' in name_lower:
        flags.append('salted')
    if 'жарен' in name_lower or 'fried' in name_lower:
        flags.append('fried')
    if 'вялен' in name_lower or 'dried' in name_lower:
        flags.append('dried')
    if 'целый' in name_lower or 'целая' in name_lower or 'whole' in name_lower:
        flags.append('whole')
    if 'резан' in name_lower or 'sliced' in name_lower or 'нарезк' in name_lower:
        flags.append('sliced')
    
    return flags
