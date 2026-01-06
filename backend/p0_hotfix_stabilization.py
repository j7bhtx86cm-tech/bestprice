"""
P0 HOTFIX - Критические исправления v12

1. match_percent clamp (0..100)
2. Negative keywords для плохих матчей
3. Improved pack parsing
4. Better brand matching
5. Structured logging
6. SEED_DICT_RULES support for mandatory attributes
"""
import os
import re
import json
import logging
from datetime import datetime
from typing import Dict, List, Tuple, Optional
from pymongo import MongoClient

logger = logging.getLogger(__name__)

# Cache for seed_dict_rules
_seed_dict_rules_cache = None

def load_seed_dict_rules():
    """Load seed_dict_rules from MongoDB (cached)"""
    global _seed_dict_rules_cache
    if _seed_dict_rules_cache is not None:
        return _seed_dict_rules_cache
    
    try:
        client = MongoClient(os.environ.get('MONGO_URL'))
        db = client[os.environ.get('DB_NAME', 'test_database')]
        rules = list(db.seed_dict_rules.find({}, {'_id': 0}))
        
        # Build lookup by type -> raw values (with action 'оставить' or 'обязательно')
        _seed_dict_rules_cache = {
            'fat': [],      # жирность: 0%, 1%, 3.2%, etc.
            'grade': [],    # сорт: choice, prime, первый_сорт, etc.
            'size': [],     # размер: 16/20, 21/25, etc. (for shrimp)
            'form': [],     # форма: без_головы, очищенная, etc.
            'process': [],  # обработка: сыровялен, варено_копчен, etc.
        }
        
        for rule in rules:
            rule_type = rule.get('type', '').lower()
            raw_value = rule.get('raw', '').lower()
            action = rule.get('action', '')
            
            if rule_type in _seed_dict_rules_cache and raw_value:
                # Include rules with actions that mean "keep/mandatory"
                if action in ['оставить', 'обязательно', 'учитывать']:
                    _seed_dict_rules_cache[rule_type].append(raw_value)
        
        logger.info(f"Loaded seed_dict_rules: fat={len(_seed_dict_rules_cache['fat'])}, grade={len(_seed_dict_rules_cache['grade'])}, size={len(_seed_dict_rules_cache['size'])}")
        return _seed_dict_rules_cache
    except Exception as e:
        logger.error(f"Failed to load seed_dict_rules: {e}")
        _seed_dict_rules_cache = {'fat': [], 'grade': [], 'size': [], 'form': [], 'process': []}
        return _seed_dict_rules_cache


def extract_seed_dict_attributes(text: str) -> Dict[str, str]:
    """
    Extract seed_dict_rules attributes from product name.
    Returns dict of found attributes by type.
    """
    rules = load_seed_dict_rules()
    text_lower = text.lower()
    found = {}
    
    # Check fat percentages (e.g., "3.2%", "0%")
    fat_pattern = re.search(r'(\d+[,.]?\d*)\s*%', text)
    if fat_pattern:
        fat_value = fat_pattern.group(0).replace(',', '.')
        found['fat'] = fat_value
    
    # Check grades (choice, prime, etc.)
    for grade in rules.get('grade', []):
        if grade in text_lower:
            found['grade'] = grade
            break
    
    # Check sizes (16/20, 21/25, etc.)
    size_pattern = re.search(r'(\d+/\d+)', text)
    if size_pattern:
        found['size'] = size_pattern.group(1)
    
    return found


def check_seed_dict_match(reference_name: str, candidate_name: str) -> Tuple[bool, str]:
    """
    Check if candidate matches seed_dict_rules attributes from reference.
    
    Returns:
        (match, reason) - True if candidate has same attributes or reference has none
    """
    ref_attrs = extract_seed_dict_attributes(reference_name)
    
    if not ref_attrs:
        return True, ""  # No seed_dict attributes to match
    
    cand_attrs = extract_seed_dict_attributes(candidate_name)
    
    # Check each attribute type
    for attr_type, ref_value in ref_attrs.items():
        cand_value = cand_attrs.get(attr_type)
        
        if attr_type == 'fat':
            # Fat percentages must match exactly
            if ref_value and cand_value != ref_value:
                return False, f"fat_mismatch:{ref_value}!={cand_value}"
        
        elif attr_type == 'grade':
            # Grades must match
            if ref_value and cand_value != ref_value:
                return False, f"grade_mismatch:{ref_value}!={cand_value}"
        
        elif attr_type == 'size':
            # Sizes (shrimp) must match exactly
            if ref_value and cand_value != ref_value:
                return False, f"size_mismatch:{ref_value}!={cand_value}"
    
    return True, ""


# Price sanity thresholds by category (min expected price per kg/unit)
CATEGORY_PRICE_THRESHOLDS = {
    # Expensive natural products
    'seafood.crab.kamchatka': 2000,  # Камчатский краб: min 2000₽/кг
    'seafood.crab.natural': 1500,    # Натуральный краб: min 1500₽/кг
    'seafood.crab.king': 2500,       # King crab: min 2500₽/кг
    'seafood.lobster': 2000,         # Лобстер: min 2000₽/кг
    'meat.beef.ribeye': 1000,        # Рибай: min 1000₽/кг
    'meat.beef.wagyu': 3000,         # Вагю: min 3000₽/кг
    # Cheap imitation products
    'seafood.crab_sticks': 50,       # Крабовые палочки: max ~300₽/кг
}


def check_price_sanity(reference_name: str, ref_price: float, candidate_name: str, cand_price: float, super_class: str) -> Tuple[bool, str]:
    """
    Check if candidate price makes sense compared to reference.
    Prevents absurd matches like natural crab (2500₽) → crab sticks (200₽).
    
    Returns:
        (is_sane, reason) - True if price is reasonable
    """
    if not ref_price or not cand_price or ref_price <= 0 or cand_price <= 0:
        return True, ""
    
    # Check 1: If reference is expensive category, candidate can't be too cheap
    if super_class in CATEGORY_PRICE_THRESHOLDS:
        min_price = CATEGORY_PRICE_THRESHOLDS[super_class]
        if cand_price < min_price * 0.5:  # Allow 50% margin
            return False, f"price_too_low:{cand_price}<{min_price*0.5}"
    
    # Check 2: Price ratio sanity
    # If candidate is 5x cheaper than reference, it's suspicious
    price_ratio = ref_price / cand_price if cand_price > 0 else 999
    if price_ratio > 5:
        # Check if this is expected (e.g., bulk discount)
        ref_lower = reference_name.lower()
        cand_lower = candidate_name.lower()
        
        # Keywords that indicate premium/natural products
        premium_keywords = ['натур', 'камчат', 'king', 'премиум', 'prime', 'choice', 'wagyu']
        ref_is_premium = any(kw in ref_lower for kw in premium_keywords)
        cand_is_premium = any(kw in cand_lower for kw in premium_keywords)
        
        # If reference is premium but candidate is not, reject
        if ref_is_premium and not cand_is_premium:
            return False, f"premium_mismatch:ratio={price_ratio:.1f}"
    
    return True, ""

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
    'meat.beef': ['растительн', 'веган', 'соев', 'заменител', 'тофу', 'substitute', 'сосиск', 'колбас'],  # Говядина не должна быть растительной или колбасой
    'meat.pork': ['растительн', 'веган', 'соев', 'заменител'],
    'meat.chicken': ['растительн', 'веган', 'соев', 'заменител'],
    'dairy.сыр': ['сырник'],  # Сыр не должен матчиться с сырниками
    'dairy.cheese': ['сырник', 'cheesecake'],
    'seafood.shrimp': [],  # Креветки обычно OK
    'condiments.spice': [],  # Wide category - будем полагаться на product-specific логику
    'staples.flour.wheat': ['ржан', 'rye', 'макарон', 'pasta'],  # Пшеничная мука не должна матчиться с ржаной
    'staples.flour.rye': ['пшенич', 'wheat'],  # Ржаная мука не должна матчиться с пшеничной
}

def has_negative_keywords(product_name: str, super_class: str) -> Tuple[bool, str]:
    """Check if product contains FORBIDDEN tokens for this category
    
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


# REQUIRED ANCHORS - обязательные токены (если НЕТ = кандидат выкидывается)
REQUIRED_ANCHORS = {
    'dairy.сыр': ['сыр', 'cheese', 'mozzarella', 'моцарелл', 'пармезан', 'гауда', 'чеддер', 'фета', 'брынз', 'сулугун'],
    'dairy.cheese': ['сыр', 'cheese', 'mozzarella', 'пармезан'],
    'meat.beef': ['говядин', 'beef'],
    'meat.pork': ['свинин', 'pork'],
    'meat.chicken': ['курин', 'chicken', 'цыпл', 'кура', 'бройлер'],  # FIX: добавлена "кура"
    'meat.turkey': ['индейк', 'turkey'],
    'seafood.salmon': ['лосос', 'семг', 'salmon', 'форел', 'нерк', 'кижуч', 'горбуш'],  # Extended
    'seafood.shrimp': ['креветк', 'shrimp', 'prawn'],
    'seafood.squid': ['кальмар', 'squid', 'calamari'],  # FIX: кальмар обязателен!
    'seafood.seabass': ['сибас', 'seabass'],
    'seafood.pollock': ['минтай', 'pollock'],
    # Crab categories - CRITICAL distinction
    'seafood.crab': ['краб', 'crab'],
    'seafood.crab.kamchatka': ['камчат', 'king crab', 'натур'],  # Натуральный камчатский
    'seafood.crab.natural': ['натур', 'камчат', 'king'],  # Натуральный краб
    'seafood.crab_sticks': ['палочк', 'сурими', 'surimi', 'имит', 'снежн'],  # Имитация
    # Condiments
    'condiments.ketchup': ['кетчуп', 'ketchup'],
    'condiments.mayo': ['майонез', 'mayo'],
    'condiments.wasabi': ['васаби', 'wasabi'],
    'condiments.spice': [],  # Wide category - use dynamic anchors
    'staples.flour': [],  # Wide category - use dynamic anchors
    'staples.мука': ['мука', 'flour'],
    'staples.мука.пшеничная': ['мука', 'flour', 'пшенич', 'wheat'],
    'staples.мука.ржаная': ['мука', 'flour', 'ржан', 'rye'],
    'staples.flour.wheat': ['пшенич', 'wheat'],
    'staples.flour.rye': ['ржан', 'rye'],
}

# FORBIDDEN CROSS-MATCHES - эти пары НИКОГДА не должны матчиться
FORBIDDEN_CROSS_MATCHES = {
    # Натуральный краб vs имитация
    'seafood.crab.kamchatka': ['палочк', 'сурими', 'surimi', 'имит', 'снежн'],
    'seafood.crab.natural': ['палочк', 'сурими', 'surimi', 'имит', 'снежн'],
    # Имитация vs натуральный
    'seafood.crab_sticks': ['камчат', 'натур', 'king crab'],
    # Кальмар vs птица
    'seafood.squid': ['курин', 'кура', 'chicken', 'цыпл', 'индейк', 'утк', 'гус'],
    # Морепродукты vs мясо
    'seafood.shrimp': ['говядин', 'свинин', 'курин', 'chicken'],
    'seafood.salmon': ['говядин', 'свинин', 'курин', 'chicken'],
}


def has_required_anchors(candidate_name: str, super_class: str, reference_name: str = None) -> Tuple[bool, str]:
    """Check if candidate contains REQUIRED anchor tokens for this category
    
    ENHANCED: If super_class is wide (e.g., condiments.spice), use reference_name 
    to detect specific product and require it in candidate.
    
    Args:
        candidate_name: Candidate product name
        super_class: Product category
        reference_name: Optional reference name for dynamic anchor detection
    
    Returns:
        (has_anchor, found_anchor) or (True, '') if anchors not required
    """
    if not super_class:
        return True, ""
    
    candidate_lower = candidate_name.lower()
    ref_lower = reference_name.lower() if reference_name else ""
    
    # Strategy 0: Check FORBIDDEN_CROSS_MATCHES first
    # This prevents absurd matches like "кальмар" → "курица"
    if super_class in FORBIDDEN_CROSS_MATCHES:
        forbidden_tokens = FORBIDDEN_CROSS_MATCHES[super_class]
        for forbidden in forbidden_tokens:
            if forbidden in candidate_lower:
                return False, f"cross_forbidden:{forbidden}"
    
    # Strategy 1: Check DYNAMIC anchors FIRST for specific categories
    # (for shrimp sizes, flour types, etc.)
    if reference_name and super_class in ['condiments.spice', 'staples.flour', 'staples.мука', 'staples.мука.пшеничная', 
                                           'staples.мука.ржаная', 'meat.beef', 'seafood.shrimp', 'other']:
        
        # List of specific product attributes that MUST match
        specific_attributes = [
            # Размеры креветок (CRITICAL for seafood.shrimp)
            '16/20', '21/25', '26/30', '31/35', '31/40', '41/50', '51/60', '61/70',
            '71/90', '90/120', '100/150', '150/200', '200/300', '300/500',
            # Специи
            'васаби', 'wasabi',
            'соль', 'salt', 'нитритн',
            'перец', 'pepper',
            'горчиц', 'mustard',
            'имбир', 'ginger',
            'кунжут', 'sesame',
            'кориандр', 'coriander',
            'куркум', 'turmeric',
            'паприк', 'paprika',
            'базилик', 'basil',
            'орегано', 'oregano',
            'тимьян', 'thyme',
            'розмарин', 'rosemary',
            # Мука типы
            'пшенич', 'wheat',
            'ржан', 'rye',
            'кукуруз', 'corn',
            'рисов', 'rice',
            'гречнев', 'buckwheat',
            'овсян', 'oat',
            # Мясо типы
            'фарш', 'minced', 'ground',
            'стейк', 'steak',
            'филе', 'fillet',
            'рёбр', 'ribs',
            'грудк', 'breast',
            'бедр', 'thigh',
        ]
        
        # Check if reference contains any specific attribute
        for attr in specific_attributes:
            if attr in ref_lower:
                # Candidate MUST also contain this attribute
                if attr in candidate_lower:
                    # Continue checking (may have multiple attributes)
                    continue
                else:
                    return False, f"missing:{attr}"
    
    # Strategy 2: Pre-defined REQUIRED_ANCHORS (base product type)
    if super_class in REQUIRED_ANCHORS:
        anchors = REQUIRED_ANCHORS[super_class]
        
        # If no anchors defined, pass
        if not anchors:
            return True, ""
        
        # At least ONE anchor must be present
        for anchor in anchors:
            if anchor in candidate_lower:
                return True, anchor
        return False, ""
    
    # No anchors required = pass
    return True, ""


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
    """Structured logger for search operations - SAFE (never breaks search)"""
    
    def __init__(self, reference_id: str):
        self.reference_id = reference_id
        self.log_data = {
            'reference_id': reference_id,
            'timestamp': datetime.utcnow().isoformat(),
            'request_context': {},
            'pipeline_counts': {},
            'selection': {},
            'brand_diagnostics': {},
            'outcome': 'unknown'
        }
    
    def set_context(self, **kwargs):
        """SAFE: Set request context"""
        try:
            self.log_data['request_context'].update(kwargs)
        except Exception:
            pass
    
    def set_count(self, stage: str, count: int):
        """SAFE: Set pipeline count"""
        try:
            self.log_data['pipeline_counts'][stage] = count
        except Exception:
            pass
    
    def set_selection(self, **kwargs):
        """SAFE: Set selection data"""
        try:
            self.log_data['selection'].update(kwargs)
        except Exception:
            pass
    
    def set_brand_diagnostics(self, **kwargs):
        """SAFE: Set brand diagnostics"""
        try:
            self.log_data['brand_diagnostics'].update(kwargs)
        except Exception:
            pass
    
    def set_outcome(self, outcome: str, reason_code: str = None):
        """SAFE: Set outcome"""
        try:
            self.log_data['outcome'] = outcome
            if reason_code:
                self.log_data['reason_code'] = reason_code
        except Exception:
            pass
    
    def get_log(self) -> Dict:
        """Get log data"""
        return self.log_data
    
    def log(self):
        """SAFE: Write structured log (never raises)"""
        try:
            logger.info(f"SEARCH_LOG: {json.dumps(self.log_data, ensure_ascii=False)}")
        except Exception as e:
            # Fallback: minimal log
            try:
                logger.warning(f"SearchLogger error: {str(e)}")
            except:
                pass  # Silent fail - logging cannot break search
    
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
