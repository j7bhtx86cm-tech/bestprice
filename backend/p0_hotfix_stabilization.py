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
    
    # MEAT - Critical meat type anchors
    'meat.beef': ['говядин', 'beef', 'говяж'],
    'meat.pork': ['свинин', 'pork', 'свиной', 'свиная'],
    'meat.chicken': ['курин', 'chicken', 'цыпл', 'кура', 'бройлер', 'куриц'],
    'meat.turkey': ['индейк', 'turkey'],
    'meat.lamb': ['баранин', 'ягнятин', 'lamb', 'mutton'],
    'meat.mutton': ['баранин', 'ягнятин', 'lamb', 'mutton'],
    'meat.duck': ['утк', 'утин', 'duck'],
    'meat.venison': ['оленин', 'venison'],
    
    # Meat cuts - require meat type OR cut name
    'meat.pork.loin': ['свинин', 'pork', 'корейк', 'карбонад'],
    'meat.pork.leg': ['свинин', 'pork', 'окорок'],
    'meat.pork.shoulder': ['свинин', 'pork', 'лопатк'],
    'meat.pork.belly': ['свинин', 'pork', 'грудинк'],
    'meat.pork.neck': ['свинин', 'pork', 'шея', 'шей'],
    'meat.pork.ribs': ['свинин', 'pork', 'ребр'],
    'meat.pork.tenderloin': ['свинин', 'pork', 'вырезк'],
    'meat.pork.shank': ['свинин', 'pork', 'голяшк'],
    
    'meat.beef.round': ['говядин', 'beef', 'тазобедр', 'окорок'],
    'meat.beef.loin': ['говядин', 'beef', 'филей', 'вырезк'],
    'meat.beef.brisket': ['говядин', 'beef', 'грудинк'],
    'meat.beef.shoulder': ['говядин', 'beef', 'лопатк'],
    'meat.beef.ribs': ['говядин', 'beef', 'ребр'],
    
    'meat.lamb.rack': ['баранин', 'ягнятин', 'lamb', 'корейк'],
    'meat.lamb.leg': ['баранин', 'ягнятин', 'lamb', 'окорок'],
    'meat.lamb.shoulder': ['баранин', 'ягнятин', 'lamb', 'лопатк'],
    
    # Seafood
    'seafood.salmon': ['лосос', 'семг', 'salmon', 'форел', 'нерк', 'кижуч', 'горбуш'],
    'seafood.shrimp': ['креветк', 'shrimp', 'prawn'],
    'seafood.squid': ['кальмар', 'squid', 'calamari'],
    'seafood.seabass': ['сибас', 'seabass'],
    'seafood.pollock': ['минтай', 'pollock'],
    'seafood.fillet': ['филе', 'fillet'],  # Only for fish fillets
    
    # Crab categories - CRITICAL distinction
    'seafood.crab': ['краб', 'crab'],
    'seafood.crab.kamchatka': ['камчат', 'king crab', 'натур'],
    'seafood.crab.natural': ['натур', 'камчат', 'king'],
    'seafood.crab_sticks': ['палочк', 'сурими', 'surimi', 'имит', 'снежн'],
    
    # Condiments
    'condiments.ketchup': ['кетчуп', 'ketchup'],
    'condiments.mayo': ['майонез', 'mayo'],
    'condiments.wasabi': ['васаби', 'wasabi'],
    'condiments.spice': [],
    
    # Flour
    'staples.flour': [],
    'staples.мука': ['мука', 'flour'],
    'staples.мука.пшеничная': ['мука', 'flour', 'пшенич', 'wheat'],
    'staples.мука.ржаная': ['мука', 'flour', 'ржан', 'rye'],
    'staples.flour.wheat': ['пшенич', 'wheat'],
    'staples.flour.rye': ['ржан', 'rye'],
}

# FORBIDDEN CROSS-MATCHES - эти пары НИКОГДА не должны матчиться
# CRITICAL P0 FIX: Полная блокировка SEAFOOD vs MEAT в обе стороны
FORBIDDEN_CROSS_MATCHES = {
    # Натуральный краб vs имитация
    'seafood.crab.kamchatka': ['палочк', 'сурими', 'surimi', 'имит', 'снежн'],
    'seafood.crab.natural': ['палочк', 'сурими', 'surimi', 'имит', 'снежн'],
    'seafood.crab_sticks': ['камчат', 'натур', 'king crab'],
    
    # ==================== SEAFOOD vs MEAT - ABSOLUTE BLOCK ====================
    # Кальмар НИКОГДА не должен матчиться с мясом птицы или другим мясом
    'seafood.squid': ['курин', 'кура', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер', 
                      'индейк', 'turkey', 'утк', 'duck', 'гус', 'goose',
                      'говядин', 'beef', 'свинин', 'pork', 'баранин', 'lamb', 'ягнятин'],
    'seafood.squid.fillet': ['курин', 'кура', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер', 
                             'индейк', 'утк', 'гус', 'говядин', 'свинин', 'баранин'],
    
    # Кальмар: без кожи vs с хитиновой пластиной - CRITICAL
    'seafood.squid.cleaned': ['хитинов', 'с кожей', 'нечищен'],
    'seafood.squid.uncleaned': ['без кож', 'чищен', 'филе без'],
    
    # Креветки - ПОЛНАЯ блокировка с мясом
    'seafood.shrimp': ['курин', 'кура', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер',
                       'индейк', 'turkey', 'утк', 'duck', 'гус', 'goose',
                       'говядин', 'beef', 'свинин', 'pork', 'баранин', 'lamb', 'ягнятин'],
    
    # Креветки: с хвостом vs без хвоста - CRITICAL
    'seafood.shrimp.tail_on': ['без хвост', 'без голов и хвост', 'очищен полност', 'хвосты удален'],
    'seafood.shrimp.tail_off': ['с хвост', 'в панцир', 'неочищен'],
    'seafood.shrimp.peeled': ['в панцир', 'неочищен', 'с головой'],
    'seafood.shrimp.unpeeled': ['очищен', 'без панцир', 'без головы'],
    
    # Лосось и другая рыба - полная блокировка с мясом
    'seafood.salmon': ['курин', 'кура', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер',
                       'индейк', 'turkey', 'утк', 'duck', 'гус', 'goose',
                       'говядин', 'beef', 'свинин', 'pork', 'баранин', 'lamb', 'ягнятин'],
    'seafood.fillet': ['курин', 'кура', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер',
                       'индейк', 'turkey', 'утк', 'duck', 'гус', 'goose',
                       'говядин', 'beef', 'свинин', 'pork', 'баранин', 'lamb', 'ягнятин'],
    'seafood.pollock': ['курин', 'кура', 'курица', 'chicken', 'говядин', 'свинин', 'баранин'],
    'seafood.seabass': ['курин', 'кура', 'курица', 'chicken', 'говядин', 'свинин', 'баранин'],
    'seafood.crab': ['курин', 'кура', 'курица', 'chicken', 'говядин', 'свинин', 'баранин'],
    
    # ==================== MEAT vs SEAFOOD - ОБРАТНАЯ БЛОКИРОВКА ====================
    # Курица НИКОГДА не должна матчиться с морепродуктами
    'meat.chicken': ['кальмар', 'squid', 'calamari', 'креветк', 'shrimp', 'prawn',
                     'лосос', 'salmon', 'семг', 'форел', 'trout', 'сибас', 'seabass',
                     'минтай', 'pollock', 'краб', 'crab', 'мидии', 'mussel', 'устриц', 'oyster',
                     'осьминог', 'octopus', 'рыб', 'fish', 'тунец', 'tuna', 'дорад'],
    'meat.chicken.thigh': ['кальмар', 'squid', 'креветк', 'shrimp', 'лосос', 'семг', 'рыб',
                           'говядин', 'свинин', 'баранин'],
    'meat.chicken.breast': ['кальмар', 'squid', 'креветк', 'shrimp', 'лосос', 'семг', 'рыб',
                            'говядин', 'свинин', 'баранин'],
    'meat.chicken.fillet': ['кальмар', 'squid', 'креветк', 'shrimp', 'лосос', 'семг', 'рыб'],
    
    # Индейка vs морепродукты
    'meat.turkey': ['кальмар', 'squid', 'креветк', 'shrimp', 'лосос', 'семг', 'рыб', 'краб'],
    
    # Утка vs морепродукты  
    'meat.duck': ['кальмар', 'squid', 'креветк', 'shrimp', 'лосос', 'семг', 'рыб', 'краб'],
    
    # ==================== MEAT TYPE CROSS-MATCHES ====================
    # Lamb/Mutton should not match with Pork
    'meat.lamb': ['свинин', 'pork', 'свиной', 'свиная', 'кальмар', 'squid', 'креветк', 'рыб'],
    'meat.lamb.rack': ['свинин', 'pork', 'свиной', 'свиная', 'кальмар', 'squid', 'креветк'],
    'meat.lamb.leg': ['свинин', 'pork', 'свиной', 'свиная', 'кальмар', 'squid', 'креветк'],
    'meat.mutton': ['свинин', 'pork', 'свиной', 'свиная', 'кальмар', 'squid', 'креветк', 'рыб'],
    
    # Pork should not match with Lamb or Seafood
    'meat.pork': ['баранин', 'ягнятин', 'lamb', 'mutton', 'кальмар', 'squid', 'креветк', 'рыб'],
    'meat.pork.loin': ['баранин', 'ягнятин', 'lamb', 'mutton', 'кальмар', 'squid', 'креветк'],
    'meat.pork.leg': ['баранин', 'ягнятин', 'lamb', 'mutton', 'кальмар', 'squid', 'креветк'],
    
    # Beef should not match with Pork, Lamb or Seafood
    'meat.beef': ['свинин', 'pork', 'баранин', 'ягнятин', 'кальмар', 'squid', 'креветк', 'рыб'],
    'meat.beef.round': ['свинин', 'pork', 'баранин', 'ягнятин', 'кальмар', 'squid', 'креветк'],
    'meat.beef.ribeye': ['свинин', 'pork', 'баранин', 'ягнятин', 'кальмар', 'squid', 'креветк'],
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
                                           'staples.мука.ржаная', 'meat.beef', 'seafood.shrimp', 'seafood.squid', 'other']:
        
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
        
        # CRITICAL: Проверка атрибутов креветок (с хвостом/без хвоста)
        shrimp_attributes = [
            ('с хвост', 'без хвост'),  # С хвостом vs Без хвоста
            ('без хвост', 'с хвост'),
            ('очищен', 'неочищен'),    # Очищенные vs Неочищенные
            ('неочищен', 'очищен'),
            ('в панцир', 'без панцир'),
            ('без панцир', 'в панцир'),
            ('с головой', 'без головы'),
            ('без головы', 'с головой'),
        ]
        
        # CRITICAL: Проверка атрибутов кальмаров (без кожи/с кожей)
        squid_attributes = [
            ('без кож', 'с кож'),       # Без кожи vs С кожей
            ('с кож', 'без кож'),
            ('без хитин', 'с хитин'),   # Без хитиновой пластины vs С хитиновой
            ('с хитин', 'без хитин'),
            ('хитинов', 'без хитин'),
            ('чищен', 'нечищен'),
            ('нечищен', 'чищен'),
        ]
        
        # Check conflicting attributes for shrimp
        if 'shrimp' in super_class or 'креветк' in ref_lower:
            for has_attr, not_attr in shrimp_attributes:
                if has_attr in ref_lower and not_attr in candidate_lower:
                    return False, f"attribute_conflict:{has_attr}_vs_{not_attr}"
        
        # Check conflicting attributes for squid
        if 'squid' in super_class or 'кальмар' in ref_lower:
            for has_attr, not_attr in squid_attributes:
                if has_attr in ref_lower and not_attr in candidate_lower:
                    return False, f"attribute_conflict:{has_attr}_vs_{not_attr}"
        
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


# ==================== CATEGORY MISMATCH DETECTION ====================

# Seafood keywords - if ANY of these are in the reference, candidate must NOT contain meat keywords
SEAFOOD_KEYWORDS = [
    'кальмар', 'squid', 'calamari', 'креветк', 'shrimp', 'prawn',
    'лосос', 'salmon', 'семг', 'форел', 'trout', 'сибас', 'seabass',
    'минтай', 'pollock', 'краб', 'crab', 'мидии', 'mussel', 'устриц', 'oyster',
    'осьминог', 'octopus', 'тунец', 'tuna', 'дорад', 'dorado', 'треск', 'cod',
    'морепродукт', 'seafood', 'рыб', 'fish', 'окунь', 'perch', 'судак', 'pike',
    'карп', 'carp', 'щук', 'сёмг', 'горбуш', 'кижуч', 'нерк', 'чавыч',
    'морской язык', 'sole', 'камбал', 'flounder', 'палтус', 'halibut'
]

# Meat/Poultry keywords - if ANY of these are in the reference, candidate must NOT contain seafood keywords
MEAT_KEYWORDS = [
    'курин', 'кура', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер',
    'индейк', 'turkey', 'утк', 'duck', 'утин', 'гус', 'goose', 'гусин',
    'говядин', 'beef', 'говяж', 'телятин', 'veal',
    'свинин', 'pork', 'свиной', 'свиная',
    'баранин', 'lamb', 'mutton', 'ягнятин', 'ягнёнок',
    'оленин', 'venison', 'кролик', 'rabbit', 'крольчат'
]


def check_category_mismatch(reference_name: str, candidate_name: str, ref_super_class: str = None) -> Tuple[bool, str]:
    """
    CRITICAL P0 FIX: Check if candidate crosses major category boundaries.
    
    This function prevents absurd matches like:
    - "Кальмар филе" → "КУРИЦА филе" (SEAFOOD vs MEAT)
    - "Креветки с хвостом" → "Курица бедро" (SEAFOOD vs MEAT)
    
    Returns:
        (is_valid, reason) - True if categories are compatible, False if cross-category mismatch
    """
    ref_lower = reference_name.lower()
    cand_lower = candidate_name.lower()
    
    # Check if reference is SEAFOOD
    ref_is_seafood = any(kw in ref_lower for kw in SEAFOOD_KEYWORDS)
    
    # Check if reference is MEAT  
    ref_is_meat = any(kw in ref_lower for kw in MEAT_KEYWORDS)
    
    # Also use super_class if available
    if ref_super_class:
        if ref_super_class.startswith('seafood'):
            ref_is_seafood = True
        elif ref_super_class.startswith('meat'):
            ref_is_meat = True
    
    # If reference is SEAFOOD, candidate must NOT contain meat keywords
    if ref_is_seafood:
        for meat_kw in MEAT_KEYWORDS:
            if meat_kw in cand_lower:
                return False, f"CATEGORY_MISMATCH:seafood_vs_meat:{meat_kw}"
    
    # If reference is MEAT, candidate must NOT contain seafood keywords
    if ref_is_meat:
        for seafood_kw in SEAFOOD_KEYWORDS:
            if seafood_kw in cand_lower:
                return False, f"CATEGORY_MISMATCH:meat_vs_seafood:{seafood_kw}"
    
    return True, ""


def check_attribute_compatibility(reference_name: str, candidate_name: str) -> Tuple[bool, str]:
    """
    Check if candidate has compatible attributes with reference.
    
    Critical attribute pairs that must match:
    - "с хвостом" ↔ "без хвоста" (shrimp)
    - "очищенные" ↔ "неочищенные" (shrimp)
    - "без кожи" ↔ "с кожей" (squid)
    - "филе" ↔ "целый/тушка" (fish)
    
    Returns:
        (is_compatible, reason) - True if attributes are compatible
    """
    ref_lower = reference_name.lower()
    cand_lower = candidate_name.lower()
    
    # Critical attribute pairs (positive_attr, negative_attr, conflict_name)
    ATTRIBUTE_PAIRS = [
        # Shrimp attributes
        ('с хвост', 'без хвост', 'tail'),
        ('без хвост', 'с хвост', 'tail'),
        ('очищен', 'неочищен', 'peeled'),
        ('неочищен', 'очищен', 'peeled'),
        ('в панцир', 'без панцир', 'shell'),
        ('без панцир', 'в панцир', 'shell'),
        ('с головой', 'без голов', 'head'),
        ('без голов', 'с головой', 'head'),
        
        # Squid attributes
        ('без кож', 'с кож', 'skin'),
        ('с кож', 'без кож', 'skin'),
        ('чищен', 'нечищен', 'cleaned'),
        ('нечищен', 'чищен', 'cleaned'),
        ('без хитин', 'с хитин', 'chitin'),
        ('с хитин', 'без хитин', 'chitin'),
        
        # Fish attributes
        ('филе', 'тушка', 'cut'),
        ('филе', 'целый', 'cut'),
        ('филе', 'непотрош', 'cut'),
        ('стейк', 'филе', 'cut_type'),
    ]
    
    for ref_attr, forbidden_attr, conflict_name in ATTRIBUTE_PAIRS:
        if ref_attr in ref_lower and forbidden_attr in cand_lower:
            return False, f"ATTRIBUTE_CONFLICT:{conflict_name}:{ref_attr}_vs_{forbidden_attr}"
    
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
