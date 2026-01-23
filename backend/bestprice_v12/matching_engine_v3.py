"""
BestPrice v12 - Matching Engine v3.0
=====================================

Реализация ТЗ v12: "Offer Matching & Сравнить предложения"

Ключевые принципы:
1. Двухрежимная выдача: Strict + Similar (если Strict < N)
2. Hard-атрибуты per group (матрица правил по категориям)
3. Фасовка с допусками: ±10% (посуда/порционка), ±20% (бакалея)
4. Ранжирование: hard-атрибуты → бренд → фасовка → ppu → min_line_total
5. Лейблы отличий для UI

Version: 3.0
Date: 22 января 2026
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS AND CONSTANTS
# ============================================================================

class ProductForm(Enum):
    """Форма продукта (hard-атрибут для всех)"""
    RAW = "raw"
    FROZEN = "frozen"
    CHILLED = "chilled"
    CANNED = "canned"
    SAUCE = "sauce"
    MIX = "mix"
    SEASONING = "seasoning"
    UTENSIL = "utensil"
    PACKAGING = "packaging"
    UNKNOWN = "unknown"


class UnitType(Enum):
    """Тип единицы измерения"""
    WEIGHT = "WEIGHT"
    VOLUME = "VOLUME"
    PIECE = "PIECE"


# Минимальное количество Strict для показа Similar
STRICT_THRESHOLD = 4

# Допуски по фасовке
PACK_TOLERANCE = {
    'strict': 0.10,      # Посуда/крышки/порционка: ±10%
    'relaxed': 0.20,     # Бакалея/снеки: ±20%
    'exact_first': 4,    # Для посуды: сначала N точных совпадений
}

# Категории с жёстким допуском (±10%)
STRICT_PACK_CATEGORIES = {
    'utensil', 'packaging', 'disposables', 'portion', 'tableware',
    'lid', 'cup', 'container', 'plate', 'fork', 'spoon', 'knife',
}

# ============================================================================
# PATTERN DICTIONARIES
# ============================================================================

# Форма продукта
PRODUCT_FORM_PATTERNS = {
    ProductForm.FROZEN: ['с/м', 'с.м', 'с\\м', 'свежеморож', 'свежемор', 'заморож', 'морож', 'frozen'],
    ProductForm.CHILLED: ['охл', 'охлажд', 'chilled', 'fresh'],
    ProductForm.CANNED: ['консерв', 'ж/б', 'жестян', 'canned', 'в масле', 'в собств'],
    ProductForm.SAUCE: ['соус', 'sauce', 'кетчуп', 'майонез', 'горчиц'],
    ProductForm.SEASONING: ['приправ', 'специ', 'seasoning', 'spice'],
    ProductForm.UTENSIL: ['вилк', 'ложк', 'нож', 'тарелк', 'стакан', 'крышк', 'контейнер'],
    ProductForm.PACKAGING: ['пакет', 'плёнк', 'пленк', 'фольг', 'мешок', 'коробк'],
}

# Часть туши (мясо/рыба)
PART_TYPE_PATTERNS = {
    'fillet': ['филе', 'fillet', 'filet'],
    'breast': ['грудк', 'грудин', 'breast'],
    'thigh': ['бедр', 'thigh'],
    'wing': ['крыл', 'wing'],
    'drumstick': ['голень', 'drumstick'],
    'carcass': ['тушк', 'тушка', 'carcass', 'whole'],
    'mince': ['фарш', 'mince', 'ground'],
    'steak': ['стейк', 'steak'],
    'loin': ['вырезк', 'карбонад', 'loin'],
    'rib': ['ребр', 'rib'],
    'liver': ['печен', 'liver'],
    'heart': ['сердц', 'heart'],
}

# Кожа (мясо/рыба)
SKIN_PATTERNS = {
    'skin_on': ['на коже', 'с кож', 'skin on', 'skin-on'],
    'skinless': ['без кож', 'б/к', 'skinless', 'skin off'],
}

# Панировка
BREADING_PATTERNS = {
    'breaded': ['в панир', 'панир', 'в кляр', 'breaded', 'battered'],
    'plain': [],  # default
}

# Типы молока
MILK_TYPE_PATTERNS = {
    'condensed': ['сгущ', 'сгущен', 'сгущён', 'condensed'],
    'plant': ['растит', 'соев', 'овсян', 'миндал', 'рисов', 'кокос', 'plant', 'oat', 'soy', 'almond'],
    'lactose_free': ['безлактоз', 'без лактоз', 'lactose free', 'lactose-free'],
    'dairy': [],  # default
}

# Вкусы (hard-block)
FLAVOR_PATTERNS = {
    'strawberry': ['клубник', 'strawberry'],
    'mango': ['манго', 'mango'],
    'vanilla': ['ванил', 'vanilla'],
    'chocolate': ['шоколад', 'chocolate', 'какао'],
    'lemon': ['лимон', 'lemon'],
    'orange': ['апельсин', 'orange'],
    'cherry': ['вишн', 'cherry'],
    'raspberry': ['малин', 'raspberry'],
    'banana': ['банан', 'banana'],
    'caramel': ['карамел', 'caramel'],
}

# Типы продукта (hard-block - бульон ≠ соус ≠ филе)
PRODUCT_TYPE_PATTERNS = {
    'bouillon': ['бульон', 'хондаши', 'даши', 'dashi', 'bouillon', 'stock'],  # Бульоны
    'sauce': ['соус', 'sauce', 'кетчуп', 'майонез', 'горчиц'],  # Соусы
    'fillet': ['филе', 'fillet', 'filet'],  # Филе
    'whole_fish': ['тушк', 'целая', 'whole'],  # Целая рыба/тушка
    'roe': ['икра', 'caviar', 'roe'],  # Икра
    'liver': ['печень', 'liver'],  # Печень
    'canned': ['консерв', 'ж/б'],  # Консервы
}

# Типы посуды/упаковки (hard-block внутри категории)
UTENSIL_TYPE_PATTERNS = {
    'lid': ['крышк'],
    'cup': ['стакан'],
    'container': ['контейнер'],
    'plate': ['тарелк'],
    'fork': ['вилк'],
    'spoon': ['ложк'],
    'knife': ['нож'],
    'napkin': ['салфетк'],
    'bag': ['пакет'],
    'straw': ['трубочк', 'соломинк'],
}

# Категории товаров для определения группы правил
CATEGORY_GROUPS = {
    'meat_fish': ['meat.', 'poultry.', 'seafood.', 'fish.'],
    'dairy': ['dairy.'],
    'sauce': ['sauce.', 'condiment.'],
    'utensil': ['utensil.', 'packaging.', 'disposable.', 'tableware.'],
    'portion': ['spice.', 'seasoning.', 'sugar.portion', 'coffee.portion'],
}

# Размеры для посуды (извлечение из названия)
SIZE_PATTERNS = [
    (r'(\d+)\s*мм', 'mm'),
    (r'(\d+)\s*мл', 'ml'),
    (r'd\s*(\d+)', 'mm'),
    (r'D-?(\d+)', 'mm'),
    (r'(\d+)\s*[xх×]\s*(\d+)', 'dimensions'),
    (r'(\d+)\s*\*\s*(\d+)', 'dimensions'),
]

# Порционные паттерны (N×X g)
PORTION_PATTERNS = [
    r'(\d+)\s*[xх×]\s*(\d+(?:[.,]\d+)?)\s*[гg]',  # 100x5г
    r'(\d+(?:[.,]\d+)?)\s*[гg]\s*[/\\]\s*(\d+)\s*шт',  # 5г/100шт
    r'(\d+)\s*шт\s*[/\\]\s*(\d+(?:[.,]\d+)?)\s*[гg]',  # 100шт/5г
    r'в стиках?\s*(\d+(?:[.,]\d+)?)\s*[гg]',  # в стиках 5г
    r'порцион\w*\s*(\d+(?:[.,]\d+)?)\s*[гg]',  # порционный 5г
]

# Известные бренды для извлечения из названия (когда brand_id не заполнен)
KNOWN_BRAND_PATTERNS = {
    'heinz': ['хайнц', 'heinz'],
    'hellmanns': ['хелманс', 'hellmann'],
    'knorr': ['кнорр', 'knorr'],
    'calve': ['кальве', 'calve'],
    'maggi': ['магги', 'maggi'],
    'mccormick': ['мккормик', 'mccormick'],
    'tabasco': ['табаско', 'tabasco'],
    'sriracha': ['сирач', 'sriracha'],
    'kikkoman': ['киккоман', 'kikkoman'],
    'barilla': ['барилла', 'barilla'],
    'dolmio': ['долмио', 'dolmio'],
    'bonduelle': ['бондюэль', 'bonduelle'],
    'aroy': ['арой', 'aroy'],
    'president': ['президент', 'president'],
    'parmalat': ['пармалат', 'parmalat'],
    'valio': ['валио', 'valio'],
    'hochland': ['хохланд', 'hochland'],
    'danone': ['данон', 'danone'],
}


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class ProductSignature:
    """Сигнатура товара для matching v3"""
    # Базовые
    product_core_id: Optional[str] = None
    brand_id: Optional[str] = None
    name_raw: str = ""
    name_norm: str = ""
    
    # Unit и упаковка
    unit_type: Optional[str] = None
    pack_qty: Optional[float] = None
    pack_value: Optional[float] = None  # Вычисленное значение фасовки
    pack_unit: Optional[str] = None
    price: float = 0.0
    ppu_value: float = 0.0  # Price per unit
    min_order_qty: int = 1
    
    # Hard-атрибуты
    product_form: ProductForm = ProductForm.UNKNOWN
    category_group: Optional[str] = None
    product_type: Optional[str] = None  # bouillon/sauce/fillet/etc (hard-block)
    
    # Мясо/рыба
    part_type: Optional[str] = None
    skin: Optional[str] = None
    breaded: bool = False
    
    # Молочка
    milk_type: Optional[str] = None
    
    # Вкус
    flavor: Optional[str] = None
    
    # Посуда
    utensil_type: Optional[str] = None
    size_value: Optional[float] = None
    size_unit: Optional[str] = None
    
    # Порционные
    is_portion: bool = False
    portion_weight: Optional[float] = None  # Вес одной порции (г)


@dataclass
class MatchResult:
    """Результат сопоставления одного кандидата"""
    passed_strict: bool = False
    passed_similar: bool = False
    block_reason: Optional[str] = None
    
    # Для ранжирования
    score: int = 0
    brand_match: bool = False
    pack_diff_pct: float = 0.0
    ppu_value: float = 0.0
    min_line_total: float = 0.0
    
    # Лейблы отличий
    difference_labels: List[str] = field(default_factory=list)


@dataclass
class AlternativesResult:
    """Результат поиска альтернатив"""
    source: Dict
    strict: List[Dict]
    similar: List[Dict]
    total_candidates: int = 0
    strict_count: int = 0
    similar_count: int = 0
    rejected_reasons: Dict[str, int] = field(default_factory=dict)


# ============================================================================
# SIGNATURE EXTRACTION
# ============================================================================

def extract_signature(item: Dict) -> ProductSignature:
    """
    Извлекает полную сигнатуру товара из данных БД.
    """
    sig = ProductSignature()
    
    name_raw = item.get('name_raw', '')
    name_norm = item.get('name_norm', name_raw.lower())
    
    sig.name_raw = name_raw
    sig.name_norm = name_norm
    sig.product_core_id = item.get('product_core_id')
    sig.brand_id = item.get('brand_id')
    sig.unit_type = item.get('unit_type')
    sig.pack_qty = item.get('pack_qty')
    sig.price = item.get('price', 0) or 0
    sig.min_order_qty = item.get('min_order_qty', 1) or 1
    
    # === Извлекаем бренд из названия если не указан ===
    if not sig.brand_id:
        sig.brand_id = _extract_brand_from_name(name_norm)
    
    # === Вычисляем pack_value ===
    sig.pack_value = _extract_pack_value(name_norm, item)
    
    # === Вычисляем ppu_value ===
    if sig.pack_value and sig.pack_value > 0:
        sig.ppu_value = sig.price / sig.pack_value
    elif sig.pack_qty and sig.pack_qty > 0:
        sig.ppu_value = sig.price / sig.pack_qty
    else:
        sig.ppu_value = sig.price
    
    # === Определяем category_group ===
    sig.category_group = _determine_category_group(sig.product_core_id)
    
    # === Извлекаем product_form ===
    sig.product_form = _extract_product_form(name_norm)
    
    # === Мясо/рыба атрибуты ===
    if sig.category_group == 'meat_fish':
        sig.part_type = _extract_pattern_match(name_norm, PART_TYPE_PATTERNS)
        sig.skin = _extract_pattern_match(name_norm, SKIN_PATTERNS)
        sig.breaded = _check_patterns(name_norm, BREADING_PATTERNS.get('breaded', []))
    
    # === Молочка ===
    if sig.category_group == 'dairy' or 'молок' in name_norm or 'сгущ' in name_norm:
        sig.milk_type = _extract_milk_type(name_norm)
    
    # === Вкус ===
    sig.flavor = _extract_pattern_match(name_norm, FLAVOR_PATTERNS)
    
    # === Посуда ===
    if sig.category_group == 'utensil' or _is_utensil(name_norm):
        sig.utensil_type = _extract_pattern_match(name_norm, UTENSIL_TYPE_PATTERNS)
        size_val, size_unit = _extract_size(name_norm)
        sig.size_value = size_val
        sig.size_unit = size_unit
    
    # === Порционные ===
    sig.is_portion, sig.portion_weight = _extract_portion_info(name_norm)
    
    # === Тип продукта (бульон/соус/филе/etc) ===
    sig.product_type = _extract_product_type(name_norm)
    
    return sig


def _extract_product_type(name_norm: str) -> Optional[str]:
    """Извлекает тип продукта (бульон/соус/филе/etc)"""
    for ptype, patterns in PRODUCT_TYPE_PATTERNS.items():
        if _check_patterns(name_norm, patterns):
            return ptype
    return None


def _extract_pack_value(name_norm: str, item: Dict) -> Optional[float]:
    """Извлекает значение фасовки из названия или данных"""
    # Сначала пробуем net_weight_kg
    net_weight = item.get('net_weight_kg')
    if net_weight and net_weight > 0:
        return net_weight
    
    # Пробуем извлечь из названия
    patterns = [
        (r'(\d+(?:[.,]\d+)?)\s*кг', 1.0),      # кг
        (r'(\d+(?:[.,]\d+)?)\s*[гg]р?(?!\w)', 0.001),  # г/гр
        (r'(\d+(?:[.,]\d+)?)\s*мл', 0.001),    # мл (примерно = г)
        (r'(\d+(?:[.,]\d+)?)\s*л(?!\w)', 1.0), # л
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, name_norm)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                return value * multiplier
            except ValueError:
                continue
    
    return item.get('pack_qty')


def _extract_brand_from_name(name_norm: str) -> Optional[str]:
    """Извлекает известный бренд из названия товара"""
    for brand_id, patterns in KNOWN_BRAND_PATTERNS.items():
        if _check_patterns(name_norm, patterns):
            return brand_id
    return None


def _determine_category_group(product_core_id: Optional[str]) -> Optional[str]:
    """Определяет группу категории для применения правил"""
    if not product_core_id:
        return None
    
    for group, prefixes in CATEGORY_GROUPS.items():
        for prefix in prefixes:
            if product_core_id.startswith(prefix):
                return group
    
    return None


def _extract_product_form(name_norm: str) -> ProductForm:
    """Извлекает форму продукта"""
    for form, patterns in PRODUCT_FORM_PATTERNS.items():
        if _check_patterns(name_norm, patterns):
            return form
    return ProductForm.UNKNOWN


def _extract_pattern_match(name_norm: str, patterns_dict: Dict[str, List[str]]) -> Optional[str]:
    """Извлекает значение по словарю паттернов"""
    for key, patterns in patterns_dict.items():
        if patterns and _check_patterns(name_norm, patterns):
            return key
    return None


def _check_patterns(name_norm: str, patterns: List[str]) -> bool:
    """Проверяет наличие хотя бы одного паттерна"""
    return any(p in name_norm for p in patterns)


def _extract_milk_type(name_norm: str) -> Optional[str]:
    """Извлекает тип молока"""
    for milk_type, patterns in MILK_TYPE_PATTERNS.items():
        if patterns and _check_patterns(name_norm, patterns):
            return milk_type
    
    # Если молочный продукт без спец. типа - это dairy
    if 'молок' in name_norm and 'сгущ' not in name_norm:
        return 'dairy'
    
    return None


def _is_utensil(name_norm: str) -> bool:
    """Проверяет является ли товар посудой/упаковкой"""
    for patterns in UTENSIL_TYPE_PATTERNS.values():
        if _check_patterns(name_norm, patterns):
            return True
    return False


def _extract_size(name_norm: str) -> Tuple[Optional[float], Optional[str]]:
    """Извлекает размер для посуды"""
    for pattern, unit in SIZE_PATTERNS:
        match = re.search(pattern, name_norm)
        if match:
            try:
                if unit == 'dimensions':
                    # Берём первое измерение
                    return float(match.group(1)), 'mm'
                return float(match.group(1)), unit
            except (ValueError, IndexError):
                continue
    return None, None


def _extract_portion_info(name_norm: str) -> Tuple[bool, Optional[float]]:
    """Извлекает информацию о порционности"""
    # Проверяем ключевые слова
    if any(kw in name_norm for kw in ['порцион', 'стик', 'саше', 'пакетик']):
        # Пытаемся извлечь вес порции
        for pattern in PORTION_PATTERNS:
            match = re.search(pattern, name_norm)
            if match:
                try:
                    # Ищем число в граммах
                    for group in match.groups():
                        if group:
                            val = float(group.replace(',', '.'))
                            if val < 100:  # Порция обычно < 100г
                                return True, val
                except ValueError:
                    continue
        return True, None
    
    return False, None


# ============================================================================
# HARD-BLOCK CHECKS
# ============================================================================

def check_hard_blocks(source: ProductSignature, cand: ProductSignature) -> Tuple[bool, Optional[str], List[str]]:
    """
    Проверяет все hard-blocks для Strict режима.
    
    Returns:
        (passed, block_reason, difference_labels)
    """
    labels = []
    
    # === HB1: product_core_id должен совпадать ===
    if source.product_core_id != cand.product_core_id:
        return False, "CORE_MISMATCH", []
    
    # === HB2: unit_type должен быть совместим ===
    if source.unit_type and cand.unit_type:
        if source.unit_type != cand.unit_type:
            # WEIGHT ↔ PIECE запрещено, WEIGHT ↔ VOLUME запрещено
            return False, "UNIT_TYPE_MISMATCH", []
    
    # === HB3: product_form (frozen/chilled/canned) ===
    if source.product_form != ProductForm.UNKNOWN and cand.product_form != ProductForm.UNKNOWN:
        if source.product_form != cand.product_form:
            # Для мяса/рыбы это hard-block
            if source.category_group == 'meat_fish':
                return False, "PRODUCT_FORM_MISMATCH", []
            else:
                labels.append(f"Форма: {cand.product_form.value}")
    
    # === HB4: Вкус (если указан) ===
    if source.flavor:
        if cand.flavor and source.flavor != cand.flavor:
            return False, "FLAVOR_MISMATCH", []
        if not cand.flavor:
            return False, "FLAVOR_MISSING", []
    
    # === HB5: Тип молока ===
    if source.milk_type and cand.milk_type:
        if source.milk_type != cand.milk_type:
            return False, "MILK_TYPE_MISMATCH", []
    
    # === HB6: Мясо/рыба специфичные ===
    if source.category_group == 'meat_fish':
        # part_type (филе ≠ тушка)
        if source.part_type and cand.part_type:
            if source.part_type != cand.part_type:
                return False, "PART_TYPE_MISMATCH", []
        
        # skin (на коже ≠ без кожи)
        if source.skin and cand.skin:
            if source.skin != cand.skin:
                return False, "SKIN_MISMATCH", []
        
        # breaded - в Strict запрещено если source не breaded
        if cand.breaded and not source.breaded:
            return False, "BREADED_IN_STRICT", []
    
    # === HB7: Посуда - тип должен совпадать ===
    if source.utensil_type:
        if source.utensil_type != cand.utensil_type:
            return False, "UTENSIL_TYPE_MISMATCH", []
        
        # Для крышек - размер строго 1:1
        if source.utensil_type == 'lid':
            if source.size_value and cand.size_value:
                if source.size_value != cand.size_value:
                    return False, "LID_SIZE_MISMATCH", []
    
    # === HB8: Порционные ===
    if source.is_portion:
        if not cand.is_portion:
            return False, "PORTION_MISMATCH", []
        # Порционный вес должен быть близким
        if source.portion_weight and cand.portion_weight:
            diff = abs(source.portion_weight - cand.portion_weight) / source.portion_weight
            if diff > 0.5:  # ±50% для порций
                return False, "PORTION_WEIGHT_MISMATCH", []
    
    return True, None, labels


def check_pack_compatibility(source: ProductSignature, cand: ProductSignature) -> Tuple[bool, float, List[str]]:
    """
    Проверяет совместимость фасовки.
    
    Returns:
        (passed, diff_pct, labels)
    """
    labels = []
    
    if not source.pack_value or not cand.pack_value:
        return True, 0.0, []
    
    if source.pack_value == 0:
        return True, 0.0, []
    
    diff_pct = abs(source.pack_value - cand.pack_value) / source.pack_value
    
    # Определяем допуск
    tolerance = PACK_TOLERANCE['relaxed']  # default ±20%
    
    # Для посуды/порционки - строже
    if source.category_group == 'utensil' or source.is_portion:
        tolerance = PACK_TOLERANCE['strict']  # ±10%
    
    if diff_pct > tolerance:
        return False, diff_pct, []
    
    if diff_pct > 0.05:
        labels.append(f"Фасовка: {cand.pack_value:.2f} vs {source.pack_value:.2f}")
    
    return True, diff_pct, labels


# ============================================================================
# MATCHING FUNCTIONS
# ============================================================================

def match_candidate(
    source: ProductSignature,
    cand: ProductSignature,
    check_strict: bool = True
) -> MatchResult:
    """
    Проверяет одного кандидата против source.
    
    Args:
        source: Сигнатура исходного товара
        cand: Сигнатура кандидата
        check_strict: Проверять для Strict или Similar режима
    
    Returns:
        MatchResult с результатами проверки
    """
    result = MatchResult()
    result.ppu_value = cand.ppu_value
    result.min_line_total = cand.price * cand.min_order_qty
    
    # === HARD-BLOCKS ===
    passed_hard, block_reason, hard_labels = check_hard_blocks(source, cand)
    
    if not passed_hard:
        result.block_reason = block_reason
        return result
    
    result.difference_labels.extend(hard_labels)
    
    # === PACK COMPATIBILITY ===
    passed_pack, pack_diff, pack_labels = check_pack_compatibility(source, cand)
    result.pack_diff_pct = pack_diff
    result.difference_labels.extend(pack_labels)
    
    if not passed_pack:
        result.block_reason = "PACK_MISMATCH"
        return result
    
    # === БРЕНД ===
    if source.brand_id and cand.brand_id:
        if source.brand_id == cand.brand_id:
            result.brand_match = True
        else:
            result.difference_labels.append("Бренд другой")
    
    # === PASSED STRICT ===
    result.passed_strict = True
    result.passed_similar = True
    
    # === SCORING ===
    score = 100
    
    if result.brand_match:
        score += 50
    
    if result.pack_diff_pct == 0:
        score += 30
    elif result.pack_diff_pct <= 0.05:
        score += 20
    elif result.pack_diff_pct <= 0.10:
        score += 10
    
    # Для посуды - точный размер
    if source.utensil_type and source.size_value:
        if source.size_value == cand.size_value:
            score += 25
    
    result.score = score
    return result


def match_for_similar(
    source: ProductSignature,
    cand: ProductSignature
) -> MatchResult:
    """
    Более мягкая проверка для Similar режима.
    Позволяет breaded, другой бренд, более широкий допуск по фасовке.
    """
    result = MatchResult()
    result.ppu_value = cand.ppu_value
    result.min_line_total = cand.price * cand.min_order_qty
    
    # product_core_id должен совпадать даже для Similar
    if source.product_core_id != cand.product_core_id:
        result.block_reason = "CORE_MISMATCH"
        return result
    
    # unit_type должен совпадать
    if source.unit_type and cand.unit_type:
        if source.unit_type != cand.unit_type:
            result.block_reason = "UNIT_TYPE_MISMATCH"
            return result
    
    # Вкус - hard-block даже для Similar
    if source.flavor and cand.flavor and source.flavor != cand.flavor:
        result.block_reason = "FLAVOR_MISMATCH"
        return result
    
    # Тип молока - hard-block
    if source.milk_type and cand.milk_type and source.milk_type != cand.milk_type:
        result.block_reason = "MILK_TYPE_MISMATCH"
        return result
    
    # Посуда - тип должен совпадать
    if source.utensil_type and source.utensil_type != cand.utensil_type:
        result.block_reason = "UTENSIL_TYPE_MISMATCH"
        return result
    
    # === ЛЕЙБЛЫ ОТЛИЧИЙ ===
    
    # Форма продукта
    if source.product_form != cand.product_form and cand.product_form != ProductForm.UNKNOWN:
        result.difference_labels.append(f"Форма: {cand.product_form.value}")
    
    # Часть туши
    if source.part_type != cand.part_type and cand.part_type:
        result.difference_labels.append(f"Часть: {cand.part_type}")
    
    # Кожа
    if source.skin != cand.skin and cand.skin:
        label = "На коже" if cand.skin == 'skin_on' else "Без кожи"
        result.difference_labels.append(label)
    
    # Панировка
    if cand.breaded and not source.breaded:
        result.difference_labels.append("В панировке")
    
    # Бренд
    if source.brand_id and cand.brand_id != source.brand_id:
        result.difference_labels.append("Бренд другой")
    
    # Фасовка
    if source.pack_value and cand.pack_value:
        diff_pct = abs(source.pack_value - cand.pack_value) / source.pack_value
        result.pack_diff_pct = diff_pct
        
        # Для Similar допуск шире - ±30%
        if diff_pct > 0.30:
            result.block_reason = "PACK_TOO_DIFFERENT"
            return result
        
        if diff_pct > 0.05:
            result.difference_labels.append(f"Фасовка: {cand.pack_value:.2f} vs {source.pack_value:.2f}")
    
    result.passed_similar = True
    
    # Scoring для Similar (ниже чем Strict)
    score = 50
    if source.brand_id == cand.brand_id:
        result.brand_match = True
        score += 20
    if result.pack_diff_pct <= 0.10:
        score += 15
    
    result.score = score
    return result


# ============================================================================
# MAIN FUNCTION
# ============================================================================

def find_alternatives_v3(
    source_item: Dict,
    candidates: List[Dict],
    limit: int = 10,
    strict_threshold: int = STRICT_THRESHOLD
) -> AlternativesResult:
    """
    Находит альтернативы для товара по ТЗ v12.
    
    Двухрежимная выдача:
    - Strict: точные аналоги по hard-атрибутам
    - Similar: если Strict < threshold, добавляем похожие с лейблами
    
    Args:
        source_item: Исходный товар
        candidates: Список кандидатов
        limit: Максимум результатов на режим
        strict_threshold: Порог для включения Similar
    
    Returns:
        AlternativesResult с Strict и Similar списками
    """
    source_sig = extract_signature(source_item)
    
    rejected_reasons: Dict[str, int] = {}
    strict_results = []
    similar_results = []
    
    for cand in candidates:
        if cand.get('id') == source_item.get('id'):
            continue
        
        cand_sig = extract_signature(cand)
        
        # Сначала пробуем Strict
        strict_match = match_candidate(source_sig, cand_sig, check_strict=True)
        
        if strict_match.passed_strict:
            strict_results.append({
                'item': cand,
                'result': strict_match,
            })
        else:
            # Записываем причину отказа
            reason = strict_match.block_reason or 'UNKNOWN'
            reason_key = reason.split(':')[0]
            rejected_reasons[reason_key] = rejected_reasons.get(reason_key, 0) + 1
            
            # Пробуем Similar
            similar_match = match_for_similar(source_sig, cand_sig)
            if similar_match.passed_similar:
                similar_results.append({
                    'item': cand,
                    'result': similar_match,
                })
    
    # === СОРТИРОВКА STRICT ===
    # Приоритет: бренд → pack_diff → ppu → min_line_total
    def strict_sort_key(x):
        r = x['result']
        return (
            not r.brand_match,        # Бренд первым
            r.pack_diff_pct,          # Ближе по фасовке
            r.ppu_value,              # Дешевле по PPU
            r.min_line_total,         # Меньше минимальная сумма
        )
    
    strict_results.sort(key=strict_sort_key)
    
    # === СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ ПОСУДЫ ===
    # Сначала 4 точных по размеру, потом остальные
    if source_sig.utensil_type and source_sig.size_value:
        exact_size = [x for x in strict_results if x['item'].get('size_value') == source_sig.size_value]
        other = [x for x in strict_results if x['item'].get('size_value') != source_sig.size_value]
        
        exact_needed = PACK_TOLERANCE['exact_first']
        if len(exact_size) >= exact_needed:
            strict_results = exact_size[:exact_needed] + other
        else:
            strict_results = exact_size + other
    
    # === СОРТИРОВКА SIMILAR ===
    def similar_sort_key(x):
        r = x['result']
        return (
            len(r.difference_labels),  # Меньше отличий лучше
            not r.brand_match,
            r.ppu_value,
        )
    
    similar_results.sort(key=similar_sort_key)
    
    # === ФОРМИРУЕМ РЕЗУЛЬТАТ ===
    def format_item(x, mode: str) -> Dict:
        item = x['item']
        result = x['result']
        cand_sig = extract_signature(item)
        
        return {
            'id': item.get('id'),
            'name': item.get('name_raw', ''),
            'name_raw': item.get('name_raw', ''),
            'price': item.get('price', 0),
            'pack_qty': item.get('pack_qty'),
            'pack_value': cand_sig.pack_value,
            'unit_type': item.get('unit_type'),
            'brand_id': cand_sig.brand_id,  # Используем извлечённый из названия
            'supplier_company_id': item.get('supplier_company_id'),
            'min_order_qty': item.get('min_order_qty', 1),
            'ppu_value': result.ppu_value,
            'min_line_total': result.min_line_total,
            'match_score': result.score,
            'match_mode': mode,
            'brand_match': result.brand_match,
            'pack_diff_pct': result.pack_diff_pct,
            'difference_labels': result.difference_labels,
        }
    
    strict_formatted = [format_item(x, 'strict') for x in strict_results[:limit]]
    
    # Similar показываем только если Strict < threshold
    similar_formatted = []
    if len(strict_formatted) < strict_threshold:
        similar_formatted = [format_item(x, 'similar') for x in similar_results[:limit]]
    
    return AlternativesResult(
        source={
            'id': source_item.get('id'),
            'name': source_item.get('name_raw', ''),
            'price': source_item.get('price', 0),
            'pack_qty': source_item.get('pack_qty'),
            'pack_value': source_sig.pack_value,
            'unit_type': source_item.get('unit_type'),
            'brand_id': source_sig.brand_id,  # Используем извлечённый из названия
            'product_core_id': source_sig.product_core_id,
            'category_group': source_sig.category_group,
            'signature': {
                'product_form': source_sig.product_form.value,
                'part_type': source_sig.part_type,
                'skin': source_sig.skin,
                'breaded': source_sig.breaded,
                'milk_type': source_sig.milk_type,
                'flavor': source_sig.flavor,
                'utensil_type': source_sig.utensil_type,
                'size_value': source_sig.size_value,
                'is_portion': source_sig.is_portion,
                'portion_weight': source_sig.portion_weight,
            }
        },
        strict=strict_formatted,
        similar=similar_formatted,
        total_candidates=len(candidates),
        strict_count=len(strict_formatted),
        similar_count=len(similar_formatted),
        rejected_reasons=rejected_reasons,
    )


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def explain_match_v3(source_name: str, candidate_name: str,
                     source_core_id: str = None, cand_core_id: str = None) -> Dict:
    """
    Объясняет решение о matching между двумя товарами.
    """
    source_item = {
        'name_raw': source_name,
        'name_norm': source_name.lower(),
        'product_core_id': source_core_id,
    }
    cand_item = {
        'name_raw': candidate_name,
        'name_norm': candidate_name.lower(),
        'product_core_id': cand_core_id,
    }
    
    source_sig = extract_signature(source_item)
    cand_sig = extract_signature(cand_item)
    
    strict_result = match_candidate(source_sig, cand_sig)
    similar_result = match_for_similar(source_sig, cand_sig)
    
    return {
        'source': {
            'name': source_name,
            'signature': {
                'product_core_id': source_sig.product_core_id,
                'product_form': source_sig.product_form.value,
                'category_group': source_sig.category_group,
                'part_type': source_sig.part_type,
                'milk_type': source_sig.milk_type,
                'utensil_type': source_sig.utensil_type,
                'is_portion': source_sig.is_portion,
                'pack_value': source_sig.pack_value,
            }
        },
        'candidate': {
            'name': candidate_name,
            'signature': {
                'product_core_id': cand_sig.product_core_id,
                'product_form': cand_sig.product_form.value,
                'category_group': cand_sig.category_group,
                'part_type': cand_sig.part_type,
                'milk_type': cand_sig.milk_type,
                'utensil_type': cand_sig.utensil_type,
                'is_portion': cand_sig.is_portion,
                'pack_value': cand_sig.pack_value,
            }
        },
        'strict_result': {
            'passed': strict_result.passed_strict,
            'block_reason': strict_result.block_reason,
            'difference_labels': strict_result.difference_labels,
        },
        'similar_result': {
            'passed': similar_result.passed_similar,
            'block_reason': similar_result.block_reason,
            'difference_labels': similar_result.difference_labels,
        }
    }
