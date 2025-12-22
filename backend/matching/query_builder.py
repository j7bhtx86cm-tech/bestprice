"""Query Features Builder"""
import re
from typing import Dict, Optional, List
from pipeline.enricher import extract_caliber, extract_fat_pct, extract_super_class, extract_processing_flags
from pipeline.normalizer import normalize_name

def build_query_features(query_text: str, strict_pack: Optional[float] = None, 
                         strict_brand: bool = False, brand: Optional[str] = None) -> Dict:
    """Build QueryFeatures from user input or favorite product
    
    Args:
        query_text: Product name to search for
        strict_pack: If set, require exact weight match
        strict_brand: If True, brand must match
        brand: Specific brand to search for
    
    Returns:
        QueryFeatures dict
    """
    name_norm = normalize_name(query_text)
    name_lower = query_text.lower()
    
    # Extract target weight/volume
    weight_match = re.search(r'(\d+(?:[.,]\d+)?)\s*[-~]?\s*(\d+(?:[.,]\d+)?)?\s*(кг|kg|г|гр|g)\b', query_text, re.IGNORECASE)
    target_weight_kg = None
    if weight_match:
        try:
            num1 = float(weight_match.group(1).replace(',', '.'))
            num2_str = weight_match.group(2)
            unit = weight_match.group(3).lower()
            
            if num2_str:
                num2 = float(num2_str.replace(',', '.'))
                num1 = (num1 + num2) / 2  # Average of range
            
            if unit in ['г', 'гр', 'g']:
                num1 = num1 / 1000
            
            target_weight_kg = num1
        except:
            pass
    
    volume_match = re.search(r'(\d+(?:[.,]\d+)?)\s*(л|l|мл|ml)\b', query_text, re.IGNORECASE)
    target_volume_l = None
    if volume_match:
        try:
            num = float(volume_match.group(1).replace(',', '.'))
            unit = volume_match.group(2).lower()
            if unit in ['мл', 'ml']:
                num = num / 1000
            target_volume_l = num
        except:
            pass
    
    return {
        'name_raw': query_text,
        'name_norm': name_norm,
        'name_tokens': set(name_norm.split()),
        'super_class': extract_super_class(name_lower),
        'brand': brand,
        'brand_strict': strict_brand,
        'caliber': extract_caliber(query_text),
        'fat_pct': extract_fat_pct(query_text),
        'target_weight_kg': target_weight_kg,
        'target_volume_l': target_volume_l,
        'strict_pack': strict_pack,
        'processing_flags': extract_processing_flags(name_lower)
    }
