"""
Enhanced Product Matching with Fuzzy Matching and Synonym Support
Implements all improvements from specification
"""
import re
from typing import Dict, List, Optional

# Synonym dictionary
SYNONYMS = {
    # Spelling variations
    'сибас': ['сибасс', 'сибаса', 'seabass'],
    'дорадо': ['дорада', 'dorado', 'dorada'],
    'лосось': ['ласось', 'лососе', 'salmon'],
    'креветка': ['креветки', 'креветок', 'shrimp', 'prawn'],
    'кальмар': ['кальмары', 'squid'],
    
    # Processing variations (skin)
    'на_коже': ['на коже', 'с кожей', 'on skin', 'with skin', 'skin on'],
    'без_кожи': ['без кожи', 'skinless', 'without skin', 'w/o skin', 'no skin'],
    
    # Breading
    'в_панировке': ['в панировке', 'панированный', 'breaded', 'в кляре'],
    'без_панировки': ['без панировки', 'не панированный', 'not breaded'],
    
    # Countries/regions to ignore in CHEAPEST mode
    'IGNORE_LOCATION': [
        'россия', 'russia', 'китай', 'china', 'вьетнам', 'vietnam',
        'индия', 'india', 'чили', 'chile', 'норвегия', 'norway',
        'исландия', 'iceland', 'фареры', 'faroe', 'мурманск', 'москва'
    ]
}

def normalize_with_synonyms(text: str) -> str:
    """Normalize text with synonym replacement"""
    text_lower = text.lower()
    
    # Replace spelling variations with canonical form
    for canonical, variants in SYNONYMS.items():
        if canonical == 'IGNORE_LOCATION':
            continue
        for variant in variants:
            text_lower = text_lower.replace(variant, canonical.replace('_', ' '))
    
    return text_lower

def remove_location_words(text: str) -> str:
    """Remove country/region/city names"""
    words = text.split()
    filtered = [w for w in words if w not in SYNONYMS['IGNORE_LOCATION']]
    return ' '.join(filtered)

def extract_primary_product_type(text: str) -> Optional[str]:
    """Extract main product category FIRST"""
    text_lower = text.lower()
    
    # Primary categories - check these first
    primary_types = {
        'креветка': ['креветк', 'shrimp', 'prawn'],
        'кальмар': ['кальмар', 'squid'],
        'осьминог': ['осьминог', 'octopus'],
        'сибас': ['сибас', 'сибасс', 'seabass'],
        'дорадо': ['дорадо', 'дорада', 'dorado'],
        'лосось': ['лосось', 'ласось', 'семга', 'salmon'],
        'тунец': ['тунец', 'tuna'],
        'треска': ['треска', 'cod'],
        'минтай': ['минтай', 'pollock'],
        'курица': ['курица', 'куриный', 'chicken'],
        'говядина': ['говядина', 'говяжий', 'beef'],
        'свинина': ['свинина', 'свиной', 'pork'],
    }
    
    for ptype, keywords in primary_types.items():
        for kw in keywords:
            if kw in text_lower:
                return ptype
    
    return None

def extract_secondary_attributes(text: str) -> Dict[str, bool]:
    """Extract secondary attributes like breading, marinade, etc."""
    text_lower = text.lower()
    
    attributes = {
        'breaded': any(w in text_lower for w in ['панировк', 'breaded', 'в кляре']),
        'on_skin': any(w in text_lower for w in ['на коже', 'с кожей', 'on skin']),
        'skinless': any(w in text_lower for w in ['без кожи', 'skinless', 'б/к']),
        'marinated': any(w in text_lower for w in ['маринован', 'marinated']),
        'smoked': any(w in text_lower for w in ['копчен', 'smoked']),
    }
    
    return {k: v for k, v in attributes.items() if v}

def normalize_weight_volume(text: str) -> Dict[str, float]:
    """Extract and normalize all weights and volumes"""
    result = {}
    
    # Weight normalization
    weight_matches = re.findall(r'(\\d+[\\.,]?\\d*)\\s*(кг|kg|г|гр)\\b', text, re.IGNORECASE)
    if weight_matches:
        weights = []
        for num_str, unit in weight_matches:
            num = float(num_str.replace(',', '.'))
            # Convert to kg (base unit)
            if unit.lower() in ['г', 'гр']:
                num = num / 1000
            weights.append(num)
        if weights:
            result['weight_kg'] = max(weights)
    
    # Volume normalization
    volume_matches = re.findall(r'(\\d+[\\.,]?\\d*)\\s*(л|l|мл|ml)\\b', text, re.IGNORECASE)
    if volume_matches:
        volumes = []
        for num_str, unit in volume_matches:
            num = float(num_str.replace(',', '.'))
            # Convert to liters (base unit)
            if unit.lower() in ['мл', 'ml']:
                num = num / 1000
            volumes.append(num)
        if volumes:
            result['volume_l'] = max(volumes)
    
    return result

def fuzzy_match(str1: str, str2: str, max_errors: int = 2) -> bool:
    """Simple fuzzy matching - allow up to max_errors character differences"""
    if not str1 or not str2:
        return False
    
    # Simple Levenshtein-like check
    len_diff = abs(len(str1) - len(str2))
    if len_diff > max_errors:
        return False
    
    # Count character differences
    errors = 0
    for i in range(min(len(str1), len(str2))):
        if str1[i] != str2[i]:
            errors += 1
        if errors > max_errors:
            return False
    
    return True

def enhanced_product_match(query_text: str, candidate_text: str, mode: str = 'cheapest') -> Dict[str, any]:
    """
    Enhanced matching with all improvements:
    1. Primary type first
    2. Ignore location in CHEAPEST mode
    3. Fuzzy matching
    4. Synonym support
    5. Weight/volume normalization
    """
    
    # Step 1: Normalize with synonyms
    query_norm = normalize_with_synonyms(query_text)
    candidate_norm = normalize_with_synonyms(candidate_text)
    
    # Step 2: Remove location words if CHEAPEST mode
    if mode == 'cheapest':
        query_norm = remove_location_words(query_norm)
        candidate_norm = remove_location_words(candidate_norm)
    
    # Step 3: Extract primary product type
    query_primary = extract_primary_product_type(query_norm)
    candidate_primary = extract_primary_product_type(candidate_norm)
    
    # Must match primary type
    if query_primary and candidate_primary:
        # Check exact match or fuzzy match
        if query_primary != candidate_primary:
            if not fuzzy_match(query_primary, candidate_primary):
                return {'match': False, 'score': 0, 'reason': 'Primary type mismatch'}
    
    # Step 4: Extract secondary attributes
    query_attrs = extract_secondary_attributes(query_norm)
    candidate_attrs = extract_secondary_attributes(candidate_norm)
    
    # Step 5: Normalize weights/volumes
    query_pack = normalize_weight_volume(query_norm)
    candidate_pack = normalize_weight_volume(candidate_norm)
    
    # Calculate match score
    score = 100
    
    # Primary type match bonus
    if query_primary == candidate_primary:
        score += 50
    
    # Secondary attributes match
    attr_matches = sum(1 for k, v in query_attrs.items() if candidate_attrs.get(k) == v)
    attr_total = len(query_attrs) if query_attrs else 1
    score += 30 * (attr_matches / attr_total)
    
    # Pack size tolerance ±10%
    if 'weight_kg' in query_pack and 'weight_kg' in candidate_pack:
        diff = abs(query_pack['weight_kg'] - candidate_pack['weight_kg'])
        if diff / query_pack['weight_kg'] <= 0.10:
            score += 20
    
    if 'volume_l' in query_pack and 'volume_l' in candidate_pack:
        diff = abs(query_pack['volume_l'] - candidate_pack['volume_l'])
        if diff / query_pack['volume_l'] <= 0.10:
            score += 20
    
    return {
        'match': score >= 70,
        'score': score,
        'primary_type': query_primary,
        'attributes_match': attr_matches,
        'pack_match': bool(query_pack and candidate_pack)
    }
