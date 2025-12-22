"""Universal Name & Unit Normalization (RULES FIRST)"""
import re
from typing import Dict, Optional, List, Tuple

# Stopwords to remove
STOPWORDS = [
    'зам', 'зам.', 'замороженный', 'замороженная', 'с/м', 'см', 'с/г',
    'в/у', 'гост', 'вес', 'фас', 'упак', 'кор', 'пак', 'блок',
    'frozen', 'pack', 'box', 'pcs', 'carton'
]

def normalize_name(raw_name: str) -> str:
    """Universal name normalization"""
    if not raw_name:
        return ''
    
    text = raw_name.lower()
    text = text.replace('ё', 'е')
    
    # Remove special characters, keep letters, digits, spaces, /, %
    text = re.sub(r'[^\w\s\/\%\-]', ' ', text)
    text = ' '.join(text.split())
    
    # Remove stopwords
    words = text.split()
    filtered = [w for w in words if w not in STOPWORDS and len(w) > 1]
    
    return ' '.join(filtered)

def normalize_unit(supplier_unit: str) -> str:
    """Universal unit standardization"""
    if not supplier_unit:
        return 'pcs'
    
    unit = supplier_unit.lower().strip()
    
    # Weight
    if unit in ['kg', 'кг', 'kilogram', 'кило']: return 'kg'
    if unit in ['g', 'г', 'gr', 'gram', 'грамм', 'гр']: return 'g'
    
    # Volume
    if unit in ['l', 'л', 'liter', 'литр']: return 'l'
    if unit in ['ml', 'мл', 'milliliter', 'миллилитр']: return 'ml'
    
    # Pieces
    if unit in ['pcs', 'шт', 'шт.', 'piece', 'штук', 'штука']: return 'pcs'
    if unit in ['box', 'кор', 'короб', 'коробка']: return 'box'
    
    return 'pcs'  # Default

def extract_item_code(raw_name: str) -> Tuple[str, str]:
    """Extract item code from beginning/end of name
    Returns: (cleaned_name, item_code or None)
    """
    # Pattern: 6+ digits at start or end
    start_match = re.match(r'^(\d{6,})\s+(.+)$', raw_name)
    if start_match:
        return (start_match.group(2), start_match.group(1))
    
    end_match = re.search(r'^(.+?)\s+(\d{6,})$', raw_name)
    if end_match:
        return (end_match.group(1), end_match.group(2))
    
    return (raw_name, None)
