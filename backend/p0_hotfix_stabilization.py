"""
P0 HOTFIX - Критические исправления v12

1. match_percent clamp (0..100)
2. Negative keywords для плохих матчей
3. Improved pack parsing
4. Better brand matching
5. Structured logging
"""
import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional

logger = logging.getLogger(__name__)

# ==================== 1) MATCH PERCENT FIX ====================

def calculate_match_percent(confidence: float, score_raw: float = None) -> int:
    """Calculate match_percent with strict 0..100 clamp
    
    Args:
        confidence: Confidence from mapper (0..1)
        score_raw: Optional raw score for logging
    
    Returns:
        int in range 0..100
    """
    # Convert confidence to percentage
    match_pct = confidence * 100
    
    # STRICT CLAMP
    match_pct = max(0, min(100, match_pct))
    
    return int(match_pct)


# ==================== 2) NEGATIVE KEYWORDS ====================

NEGATIVE_KEYWORDS = {
    'meat.beef': ['растительн', 'веган', 'соев', 'заменител', 'тофу'],
    'meat.pork': ['растительн', 'веган', 'соев', 'заменител'],
    'meat.chicken': ['растительн', 'веган', 'соев', 'заменител'],
    'dairy.сыр': ['сырник'],  # Сыр не должен матчиться с сырниками
    'dairy.cheese': ['сырник', 'cheesecake'],
    'seafood.shrimp': []  # Креветки обычно OK
}

def has_negative_keywords(product_name: str, super_class: str) -> Tuple[bool, str]:
    """Check if product contains negative keywords for this category
    
    Returns:
        (has_negative, keyword_found)
    """
    if not super_class or super_class not in NEGATIVE_KEYWORDS:
        return False, ""
    
    name_lower = product_name.lower()
    
    for neg_keyword in NEGATIVE_KEYWORDS[super_class]:
        if neg_keyword in name_lower:
            return True, neg_keyword
    
    return False, ""


# ==================== 3) IMPROVED PACK PARSING ====================

def parse_pack_value(product_name: str) -> Optional[float]:
    """Enhanced pack parsing with support for ranges and approximations
    
    Supports:
    - ~5кг, ≈5кг
    - 4-5 кг, 300-400г
    - 4/5 (weight range)
    - 10х200, 6x1.5 (multipack)
    - Standard: 1кг, 500г, 2л, 250мл
    
    Returns:
        Pack value in base units (kg/l), or None if cannot parse
    """
    if not product_name:
        return None
    
    name = product_name.lower()
    
    # Pattern 1: Approximate (~, ≈)
    approx_patterns = [
        (r'[~≈]\s*(\d+[\.,]?\d*)\s*кг', 1.0),
        (r'[~≈]\s*(\d+[\.,]?\d*)\s*г', 0.001),
        (r'[~≈]\s*(\d+[\.,]?\d*)\s*л', 1.0),
        (r'[~≈]\s*(\d+[\.,]?\d*)\s*мл', 0.001),
    ]
    
    for pattern, multiplier in approx_patterns:
        match = re.search(pattern, name)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                return value * multiplier
            except:
                continue
    
    # Pattern 2: Range (300-400, 4-5)
    range_patterns = [
        (r'(\d+)[-–](\d+)\s*кг', 1.0),
        (r'(\d+)[-–](\d+)\s*г', 0.001),
        (r'(\d+)[-–](\d+)\s*л', 1.0),
        (r'(\d+)[-–](\d+)\s*мл', 0.001),
        (r'(\d+)/(\d+)', 1.0),  # 4/5 (weight category)
    ]
    
    for pattern, multiplier in range_patterns:
        match = re.search(pattern, name)
        if match:
            try:
                val1 = float(match.group(1))
                val2 = float(match.group(2))
                # Use middle of range
                value = (val1 + val2) / 2
                return value * multiplier
            except:
                continue
    
    # Pattern 3: Standard (1кг, 500г, etc.)
    standard_patterns = [
        (r'(\d+[\.,]?\d*)\s*кг', 1.0),
        (r'(\d+[\.,]?\d*)\s*г', 0.001),
        (r'(\d+[\.,]?\d*)\s*л', 1.0),
        (r'(\d+[\.,]?\d*)\s*мл', 0.001),
        (r'(\d+[\.,]?\d*)\s*шт', 1.0),
    ]
    
    for pattern, multiplier in standard_patterns:
        match = re.search(pattern, name)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                return value * multiplier
            except:
                continue
    
    return None


# ==================== 4) BRAND TEXT EXTRACTION ====================

def normalize_brand_text(text: str) -> str:
    """Normalize brand text for matching
    
    - Lowercase
    - ё→е
    - Remove punctuation, quotes, ™, ®
    - Collapse spaces
    """
    if not text:
        return ""
    
    text = str(text).upper()
    text = text.replace('Ё', 'Е').replace('ё', 'е')
    
    # Remove trademark symbols
    text = text.replace('™', '').replace('®', '').replace('©', '')
    
    # Remove punctuation and quotes
    text = re.sub(r'["\'\«\»\.\,\;\:\!\?]', ' ', text)
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    
    # Collapse spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text.lower()


def extract_brand_from_text(product_name: str, brand_aliases: dict) -> Optional[str]:
    """Extract brand_id from product name using brand_aliases
    
    Args:
        product_name: Product name
        brand_aliases: dict {alias_norm: brand_id}
    
    Returns:
        brand_id or None
    """
    if not product_name or not brand_aliases:
        return None
    
    name_norm = normalize_brand_text(product_name)
    name_words = set(name_norm.split())
    
    # Sort by length (longest first) for better matching
    sorted_aliases = sorted(brand_aliases.items(), key=lambda x: len(x[0]), reverse=True)
    
    for alias_norm, brand_id in sorted_aliases:
        # Short aliases require exact word match
        if len(alias_norm) < 4:
            if alias_norm in name_words:
                return brand_id
        else:
            # Longer aliases - substring at word boundary
            if alias_norm in name_norm:
                # Check word boundary
                pattern = r'(^|\s)' + re.escape(alias_norm) + r'($|\s)'
                if re.search(pattern, name_norm):
                    return brand_id
    
    return None


# Global brand aliases cache
_brand_aliases_cache = None

def load_brand_aliases() -> dict:
    """Load brand aliases from MongoDB
    
    Returns:
        dict {alias_norm: brand_id}
    """
    global _brand_aliases_cache
    
    if _brand_aliases_cache is not None:
        return _brand_aliases_cache
    
    try:
        from pymongo import MongoClient
        import os
        
        DB_NAME = os.environ.get('DB_NAME', 'test_database')
        db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]
        
        # Load from brand_aliases collection
        aliases_cursor = db.brand_aliases.find({}, {'_id': 0, 'alias_norm': 1, 'brand_id': 1})
        _brand_aliases_cache = {doc['alias_norm']: doc['brand_id'] 
                                for doc in aliases_cursor if doc.get('alias_norm')}
        
        logger.info(f"📚 Loaded {len(_brand_aliases_cache)} brand aliases for text extraction")
        
    except Exception as e:
        logger.warning(f"⚠️ Could not load brand aliases: {e}")
        _brand_aliases_cache = {}
    
    return _brand_aliases_cache


# ==================== 4) STRUCTURED LOGGING ====================

class SearchLogger:
    """Structured logger for search operations"""
    
    def __init__(self, reference_id: str):
        self.reference_id = reference_id
        self.log_data = {
            'reference_id': reference_id,
            'timestamp': datetime.utcnow().isoformat(),
            'request_context': {},
            'pipeline_counts': {},
            'selection': {},
            'outcome': 'unknown'
        }
    
    def set_context(self, **kwargs):
        self.log_data['request_context'].update(kwargs)
    
    def set_count(self, stage: str, count: int):
        self.log_data['pipeline_counts'][stage] = count
    
    def set_brand_diagnostics(self, **kwargs):
        """Set brand diagnostics for debugging brand matching"""
        if 'brand_diagnostics' not in self.log_data:
            self.log_data['brand_diagnostics'] = {}
        self.log_data['brand_diagnostics'].update(kwargs)
    
    def set_outcome(self, outcome: str, reason_code: str = None):
        self.log_data['outcome'] = outcome
        if reason_code:
            self.log_data['reason_code'] = reason_code
    
    def get_log(self) -> Dict:
        return self.log_data
    
    def log(self):
        """Write structured log"""
        logger.info(f"SEARCH_LOG: {json.dumps(self.log_data, ensure_ascii=False)}")


# ==================== TESTING ====================

if __name__ == '__main__':
    print("🧪 P0 Hotfix Components Test\n")
    
    # Test match_percent
    print("1. match_percent clamp:")
    test_values = [0.5, 1.0, 95.0, 150.0, -10.0]
    for val in test_values:
        result = calculate_match_percent(val)
        print(f"   {val:6.1f} → {result} {'✅' if 0 <= result <= 100 else '❌'}")
    
    # Test negative keywords
    print("\n2. Negative keywords:")
    test_products = [
        ("ГОВЯДИНА PRIME 5кг", "meat.beef", False),
        ("РАСТИТЕЛЬНЫЕ СТРИПСЫ вместо говядины", "meat.beef", True),
        ("Сыр моцарелла 125г", "dairy.сыр", False),
        ("СЫРНИКИ 50г", "dairy.сыр", True)
    ]
    
    for name, sc, expected_negative in test_products:
        has_neg, keyword = has_negative_keywords(name, sc)
        status = "✅" if has_neg == expected_negative else "❌"
        print(f"   {status} {name[:40]:40} → {has_neg} ('{keyword}')")
    
    # Test pack parsing
    print("\n3. Pack parsing:")
    test_packs = [
        "Говядина РИБАЙ ~5кг",
        "СИБАС 300-400г",
        "Рис 4/5 кг",
        "Кетчуп 800г",
        "Масло 1,5л"
    ]
    
    for product in test_packs:
        pack = parse_pack_value(product)
        print(f"   {product[:40]:40} → {pack}")
    
    print("\n✅ All components tested")
