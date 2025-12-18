"""
Advanced Product Matching System
Implements 7 scoring formulas with pack tolerance and strict modes
Based on Unified_Similar_Search_Spec_RU.docx
"""
import re
from typing import Dict, List, Optional, Any, Tuple
from datetime import datetime, timezone

# Constants
PACK_TOLERANCE = 0.10
MIN_SCORE = 70
P_PACK_MISMATCH = 60
P_PACK_MISSING = 30
P_SUPERCLASS_CONFLICT = 100
P_BRAND_STRICT = 100
P_UNIT_CONFLICT = 50

# Stopwords
STOPWORDS = [
    'зам', 'зам.', 'заморож', 'замороженная', 'замороженный', 'замороженные',
    'с/м', 'см', 'в/у', 'гост', 'вес', 'вес.', 'фас', 'фас.',
    'уп', 'упак', 'упаковка', 'кор', 'кор.', 'короб', 'коробка',
    'пак', 'пакет', 'блок'
]

def normalize_text(text: str) -> str:
    """Normalize text: lowercase, remove special chars, remove stopwords"""
    if not text:
        return ''
    
    # Step 1: lowercase
    text = text.lower()
    
    # Step 2: replace ё -> е
    text = text.replace('ё', 'е')
    
    # Step 3: keep only letters, digits, spaces, /, %, +
    text = re.sub(r'[^\w\s\/\%\+]', ' ', text)
    
    # Step 4: collapse multiple spaces
    text = ' '.join(text.split())
    
    # Step 5: remove stopwords
    words = text.split()
    filtered = [w for w in words if w not in STOPWORDS]
    
    return ' '.join(filtered)

def tokenize(text: str) -> List[str]:
    """Tokenize normalized text"""
    return [t for t in text.split() if t]

def extract_caliber(text: str) -> Optional[str]:
    """Extract caliber like 31/40"""
    match = re.search(r'\b(\d{1,3})\s*\/\s*(\d{1,3})\b', text)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None

def extract_fat_pct(text: str) -> Optional[int]:
    """Extract fat percentage"""
    match = re.search(r'\b(\d{1,2})\s*%\b', text)
    if match:
        return int(match.group(1))
    return None

def extract_pack_weight(text: str) -> Optional[float]:
    """Extract pack weight in kg"""
    matches = re.findall(r'(\d+[\.,]?\d*)\s*(кг|kg|г|гр)\b', text, re.IGNORECASE)
    
    if not matches:
        return None
    
    weights = []
    for num_str, unit in matches:
        num = float(num_str.replace(',', '.'))
        if unit.lower() in ['г', 'гр']:
            num = num / 1000
        weights.append(num)
    
    return max(weights) if weights else None

def extract_pack_volume(text: str) -> Optional[float]:
    """Extract pack volume in liters"""
    matches = re.findall(r'(\d+[\.,]?\d*)\s*(л|l|мл|ml)\b', text, re.IGNORECASE)
    
    if not matches:
        return None
    
    volumes = []
    for num_str, unit in matches:
        num = float(num_str.replace(',', '.'))
        if unit.lower() in ['мл', 'ml']:
            num = num / 1000
        volumes.append(num)
    
    return max(volumes) if volumes else None

def normalize_unit(unit: str) -> str:
    """Normalize unit"""
    unit_lower = unit.lower().strip()
    
    if unit_lower in ['кг', 'kg', 'килограмм']:
        return 'kg'
    if unit_lower in ['л', 'l', 'литр', 'liter']:
        return 'l'
    if unit_lower in ['шт', 'pcs', 'piece', 'штука']:
        return 'pcs'
    if unit_lower in ['кор', 'кор.', 'короб', 'box']:
        return 'box'
    
    return 'pcs'  # Default

def determine_super_class(tokens: List[str], raw_name: str) -> str:
    """Determine super class category"""
    name_lower = raw_name.lower()
    
    # Seafood
    if any(w in tokens for w in ['креветк', 'краб', 'омар', 'рыб', 'тунец', 'лосось', 'семга']):
        return 'seafood'
    
    # Dairy
    if any(w in tokens for w in ['молоко', 'сливки', 'масло', 'сыр', 'йогурт']):
        return 'dairy'
    
    # Sauce
    if any(w in tokens for w in ['соус', 'кетчуп', 'паста', 'пюре']):
        return 'sauce'
    
    # Drink
    if any(w in tokens for w in ['напиток', 'сок', 'вода']):
        return 'drink'
    
    # Canned
    if any(w in ['конс', 'консерв'] for w in tokens) or any(w in name_lower for w in ['ж/б', 'ст/б']):
        return 'canned'
    
    # Meat/Fish
    if any(w in tokens for w in ['филе', 'вырезка', 'лопатка', 'бедро', 'курица', 'говядин', 'свинин']):
        return 'meat_fish'
    
    # Grocery
    if any(w in tokens for w in ['мука', 'крупа', 'рис', 'макарон', 'крахмал', 'лапша']):
        return 'grocery'
    
    return 'other'

def determine_product_type(tokens: List[str], super_class: str) -> str:
    """Determine specific product type"""
    tokens_str = ' '.join(tokens)
    
    # Specific types by super class
    if super_class == 'seafood':
        if 'креветк' in tokens_str:
            return 'креветки'
        if 'краб' in tokens_str:
            return 'краб'
        if 'тунец' in tokens_str:
            return 'тунец'
        if 'лосось' in tokens_str or 'семга' in tokens_str:
            return 'лосось'
    
    if super_class == 'dairy':
        if 'молоко' in tokens_str:
            if 'кокос' in tokens_str:
                return 'молоко_кокосовое'
            return 'молоко'
        if 'масло' in tokens_str:
            if 'сливочн' in tokens_str:
                return 'масло_сливочное'
            return 'масло'
        if 'сыр' in tokens_str:
            return 'сыр'
    
    if super_class == 'sauce':
        if 'кетчуп' in tokens_str:
            return 'кетчуп'
        if 'соус' in tokens_str:
            return 'соус'
    
    # Default: first token
    return tokens[0] if tokens else 'unknown'

def extract_brand(raw_name: str) -> Optional[str]:
    """Extract brand name"""
    known_brands = [
        'Heinz', 'Mutti', 'Aroy-D', 'COOK_ME', 'Sunfeel', 'Baleno',
        'Бояринъ', 'Альфа-М', 'DAS', 'Подворье', 'Агро-Альянс',
        'Каскад', 'Праймфудс', 'Деревенское', 'Delicius', 'Knorr',
        'КНОРР', 'PRB', 'Federici', 'Luxuria'
    ]
    
    for brand in known_brands:
        if brand.lower() in raw_name.lower():
            return brand
    
    # Try to find capitalized words
    words = raw_name.split()
    for word in words:
        if (word.isupper() or word.istitle()) and len(word) > 3:
            if word not in ['Масло', 'Соус', 'Сыр', 'Молоко', 'Соль', 'Филе']:
                return word
    
    return None

def determine_formula_id(features: Dict[str, Any]) -> str:
    """Determine which formula to use (A-G or 0)"""
    tokens = features.get('tokens', [])
    tokens_str = ' '.join(tokens)
    
    # A: caliber
    if features.get('caliber'):
        return 'A'
    
    # B: fat% for oils/creams
    if features.get('fat_pct') and any(w in tokens_str for w in ['масло', 'майонез', 'сливк']):
        return 'B'
    
    # C: sauces
    if any(w in tokens_str for w in ['кетчуп', 'соус', 'паста', 'пюре']):
        return 'C'
    
    # D: drinks with volume
    if any(w in tokens_str for w in ['молоко', 'напиток', 'кокос']) and features.get('pack_volume_l'):
        return 'D'
    
    # E: grocery
    if any(w in tokens_str for w in ['крахмал', 'мука', 'лапша', 'крупа', 'рис', 'макарон']):
        return 'E'
    
    # F: canned
    if any(w in tokens_str for w in ['конс', 'консерв', 'кукуруз', 'горошек', 'оливк', 'маслин']):
        return 'F'
    
    # G: meat/fish cuts
    if any(w in tokens_str for w in ['филе', 'вырезк', 'лопатк', 'бедро', 'кож', 'кост']):
        return 'G'
    
    return '0'

def pack_match_10(query_features: Dict, candidate_features: Dict) -> bool:
    """Check if pack sizes match within 10% tolerance"""
    if query_features.get('pack_weight_kg'):
        q_pack = query_features['pack_weight_kg']
        c_pack = candidate_features.get('pack_weight_kg')
        if c_pack and q_pack > 0:
            return abs(c_pack - q_pack) / q_pack <= PACK_TOLERANCE
        return False
    
    if query_features.get('pack_volume_l'):
        q_pack = query_features['pack_volume_l']
        c_pack = candidate_features.get('pack_volume_l')
        if c_pack and q_pack > 0:
            return abs(c_pack - q_pack) / q_pack <= PACK_TOLERANCE
        return False
    
    return True  # No pack requirement

def calculate_s_name(query_tokens: List[str], candidate_tokens: List[str]) -> float:
    """Token recall: |Tq ∩ Tc| / |Tq|"""
    if not query_tokens:
        return 0.0
    
    q_set = set(query_tokens)
    c_set = set(candidate_tokens)
    intersection = q_set & c_set
    
    return len(intersection) / len(q_set)

def calculate_s_brand(query_brand: Optional[str], candidate_brand: Optional[str], strict_brand: bool) -> Tuple[float, int]:
    """Calculate brand similarity and penalty"""
    penalty = 0
    
    if strict_brand:
        if query_brand and candidate_brand:
            if query_brand.lower() == candidate_brand.lower():
                return 1.0, 0
            else:
                return 0.0, P_BRAND_STRICT
        else:
            return 0.0, P_BRAND_STRICT
    else:
        # Non-strict: IGNORE BRAND COMPLETELY for best price search
        # Always return neutral score, no penalty
        return 0.5, 0

def calculate_score(query: Dict, candidate: Dict, formula_id: str, strict_pack: bool, strict_brand: bool) -> Tuple[float, int]:
    """Calculate similarity score using specified formula"""
    
    # Calculate component scores
    s_name = calculate_s_name(query.get('tokens', []), candidate.get('tokens', []))
    s_brand, p_brand = calculate_s_brand(query.get('brand'), candidate.get('brand'), strict_brand)
    s_unit = 1.0 if query.get('unit_norm') == candidate.get('unit_norm') else 0.0
    s_pack = 1.0 if pack_match_10(query, candidate) else 0.0
    
    # Calculate penalties
    penalties = p_brand
    
    # Super class conflict
    if query.get('super_class') != 'other' and candidate.get('super_class') != 'other':
        if query.get('super_class') != candidate.get('super_class'):
            penalties += P_SUPERCLASS_CONFLICT
    
    # Pack penalties (only when strict_pack is False)
    if not strict_pack:
        if not s_pack:
            if query.get('pack_weight_kg') or query.get('pack_volume_l'):
                if candidate.get('pack_weight_kg') or candidate.get('pack_volume_l'):
                    penalties += P_PACK_MISMATCH
                else:
                    penalties += P_PACK_MISSING
    
    # Category-specific scores
    s_caliber = 1.0 if query.get('caliber') and query['caliber'] == candidate.get('caliber') else 0.0
    s_fat = 1.0 if query.get('fat_pct') and query['fat_pct'] == candidate.get('fat_pct') else 0.0
    s_type = 1.0 if query.get('product_type') == candidate.get('product_type') else 0.0
    s_processing = 0.5  # Simplified for now
    s_variant = s_type  # Simplified
    s_food = s_type  # Simplified
    s_packtype = 0.5  # Simplified
    s_species = s_type  # Simplified
    s_cut = 0.5  # Simplified
    
    # Formula-specific penalties
    if formula_id == 'A':
        if query.get('caliber') and not candidate.get('caliber'):
            penalties += 60
        elif query.get('caliber') and candidate.get('caliber') and query['caliber'] != candidate['caliber']:
            penalties += 80
    
    if formula_id == 'B':
        if query.get('fat_pct') and not candidate.get('fat_pct'):
            penalties += 40
    
    # Apply formula
    if formula_id == 'A':
        score = 100 * (0.25*s_name + 0.60*(0.70*s_caliber + 0.30*s_processing) + 0.10*s_brand + 0.03*s_unit + 0.02*s_pack)
    elif formula_id == 'B':
        score = 100 * (0.20*s_name + 0.65*(0.65*s_type + 0.35*s_fat) + 0.10*s_brand + 0.03*s_unit + 0.02*s_pack)
    elif formula_id == 'C':
        score = 100 * (0.40*s_name + 0.35*s_type + 0.20*s_brand + 0.05*s_pack)
    elif formula_id == 'D':
        score = 100 * (0.25*s_name + 0.35*s_type + 0.20*s_brand + 0.05*s_unit + 0.15*s_pack)
    elif formula_id == 'E':
        score = 100 * (0.65*s_name + 0.25*s_variant + 0.05*s_pack + 0.05*s_unit)
    elif formula_id == 'F':
        score = 100 * (0.35*s_name + 0.45*(0.50*s_food + 0.35*s_packtype + 0.15*s_variant) + 0.10*s_brand + 0.07*s_pack + 0.03*s_unit)
    elif formula_id == 'G':
        score = 100 * (0.20*s_name + 0.70*(0.40*s_species + 0.40*s_cut + 0.20*s_processing) + 0.05*s_pack + 0.05*s_unit)
    else:  # Formula 0
        score = 100 * (0.75*s_name + 0.15*s_brand + 0.05*s_unit + 0.05*s_pack)
    
    final_score = score - penalties
    
    return final_score, penalties

def extract_features(raw_name: str, unit: str, price: float) -> Dict[str, Any]:
    """Extract all features from product name"""
    
    # Normalize
    name_norm = normalize_text(raw_name)
    tokens = tokenize(name_norm)
    
    # Extract features
    features = {
        'raw_name': raw_name,
        'name_norm': name_norm,
        'tokens': tokens,
        'unit_norm': normalize_unit(unit),
        'caliber': extract_caliber(raw_name),
        'fat_pct': extract_fat_pct(raw_name),
        'pack_weight_kg': extract_pack_weight(raw_name),
        'pack_volume_l': extract_pack_volume(raw_name),
        'brand': extract_brand(raw_name),
        'price': price
    }
    
    # Determine categories
    features['super_class'] = determine_super_class(tokens, raw_name)
    features['product_type'] = determine_product_type(tokens, features['super_class'])
    
    return features

def search_similar_products(
    query_text: str,
    all_products: List[Dict],
    strict_pack: Optional[bool] = None,
    strict_brand: bool = False,
    brand: Optional[str] = None,
    top_n: int = 20
) -> List[Dict]:
    """Search for similar products using advanced matching"""
    
    # Extract query features
    query_features = extract_features(query_text, 'pcs', 0)
    if brand:
        query_features['brand'] = brand
    
    # Determine formula
    formula_id = determine_formula_id(query_features)
    
    # Determine strict_pack default
    if strict_pack is None:
        strict_pack = formula_id in ['D', 'F']
    
    # Filter candidates
    candidates = []
    for prod in all_products:
        # Pre-filter
        if not prod.get('active', True):
            continue
        
        if prod.get('unit_norm') != query_features['unit_norm']:
            continue
        
        # Super class filter
        if query_features['super_class'] != 'other' and prod.get('super_class') != 'other':
            if query_features['super_class'] != prod['super_class']:
                continue
        
        # Strict pack filter
        if strict_pack:
            if query_features.get('pack_weight_kg') or query_features.get('pack_volume_l'):
                if not pack_match_10(query_features, prod):
                    continue
        
        # Calculate score
        score, penalties = calculate_score(query_features, prod, formula_id, strict_pack, strict_brand)
        
        if score >= MIN_SCORE:
            candidates.append({
                **prod,
                'score': score,
                'penalties': penalties,
                'formula_id': formula_id
            })
    
    # Sort by score DESC, then price ASC
    candidates.sort(key=lambda x: (-x['score'], x['price']))
    
    return candidates[:top_n]
