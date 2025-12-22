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
        return {'net_weight_kg': None, 'piece_weight_kg': None, 'variable_weight': False}
    
    # Rule: Use maximum weight (package weight)
    net_weight = max(weights_kg)
    
    # If range found, use smaller value as piece weight
    piece_weight = min(weights_kg) if len(weights_kg) > 1 else None
    
    return {
        'net_weight_kg': net_weight,
        'piece_weight_kg': piece_weight,
        'variable_weight': is_variable
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
    if any(w in name_lower for w in ['форель', 'trout']):
        return 'seafood.trout'
    if any(w in name_lower for w in ['кальмар', 'squid']):
        return 'seafood.squid'
    if any(w in name_lower for w in ['мидии', 'mussel']):
        return 'seafood.mussel'
    
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
        return 'condiments.sauce'
    if 'масло' in name_lower and 'олив' in name_lower:
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
    if 'водоросли' in name_lower or 'seaweed' in name_lower:
        return 'seafood.seaweed'
    
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
