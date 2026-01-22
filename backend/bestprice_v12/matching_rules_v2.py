"""
BestPrice v12 - Unified Matching Rules Module v2
================================================

Полностью переписанный модуль для сопоставления товаров.
Реализует ТЗ P0: "Сравнить предложения - убрать мусор и сделать корректные замены"

Ключевые принципы:
1. Кандидаты ТОЛЬКО из того же product_core_id
2. Hard-blocks для строгой фильтрации
3. Приоритет бренда
4. Правильная сортировка (атрибуты → бренд → фасовка → цена)
5. Не смешивать коробки и штуки

Version: 2.0
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


# ============================================================================
# CONSTANTS AND PATTERNS
# ============================================================================

# Допуски по упаковке (pack_qty/net_weight)
PACK_TOLERANCE = {
    'spices_portion': 0.10,     # Специи порционные: ±10%
    'regular': 0.20,            # Обычная еда: ±20%
    'strict': 0.0,              # Крышки: 0% (строго 1:1)
    'container_relaxed': 0.10,  # Контейнеры после первых 4: ±10%
}

# Паттерны для извлечения размеров из названия (для одноразки)
SIZE_PATTERNS = [
    r'(\d+)\s*мм',              # 250мм
    r'(\d+)\s*мл',              # 250мл
    r'd\s*(\d+)',               # d 115
    r'D-?(\d+)',                # D-115 или D115
    r'(\d+)\s*x\s*(\d+)',       # 145x119
    r'(\d+)\*(\d+)',            # 108*82
]

# Паттерны для вкусов (hard-block если присутствует)
FLAVOR_PATTERNS = {
    'клубника': ['клубник', 'strawberry'],
    'манго': ['манго', 'mango'],
    'ваниль': ['ванил', 'vanilla'],
    'шоколад': ['шоколад', 'chocolate', 'какао', 'cocoa'],
    'лимон': ['лимон', 'lemon'],
    'апельсин': ['апельсин', 'orange'],
    'вишня': ['вишн', 'cherry'],
    'малина': ['малин', 'raspberry'],
    'черника': ['черник', 'blueberry'],
    'банан': ['банан', 'banana'],
    'карамель': ['карамел', 'caramel'],
    'мята': ['мят', 'mint'],
}

# Типы молока (СТРОГО не смешивать)
MILK_TYPE_PATTERNS = {
    'condensed': ['сгущ', 'сгущен', 'сгущён'],  # Сгущёнка
    'plant': ['растит', 'соев', 'овсян', 'миндал', 'рисов'],  # Растительное
    'lactose_free': ['безлактоз', 'без лактоз'],  # Безлактозное
    'coconut': ['кокос'],  # Кокосовое
    'substitute': ['молокосодерж', 'заменит'],  # Молокосодержащий продукт (не молоко!)
    'dairy': [],  # Обычное молочное (default)
}

# Состояние овощей/фруктов
VEGGIE_STATE_PATTERNS = {
    'peeled': ['очищен', 'чищен'],  # Очищенная
    'washed': ['мытая', 'мыт'],  # Мытая
    'cut': ['нарезан', 'резан', 'кубик', 'полоск', 'ломтик'],  # Нарезанная
}

# Калибры креветок
SHRIMP_CALIBER_PATTERN = r'(\d+)[/-](\d+)'  # 16/20, 31/40, 200/300

# Состояния креветок
SHRIMP_STATE_PATTERNS = {
    'peeled': ['очищен', 'чищен', 'б/панц'],
    'shell_on': ['в панцир', 'неочищ', 'с панцир'],
    'tail_on': ['с хвост'],
    'tail_off': ['б/хвост', 'без хвост'],
    'headless': ['б/г', 'без голов', 'бг'],
    'head_on': ['с/г', 'с голов'],
}

# Виды креветок
SHRIMP_SPECIES_PATTERNS = {
    'vannamei': ['ваннамей', 'vannamei'],
    'tiger': ['тигров', 'tiger'],
    'cocktail': ['коктейл'],
    'king': ['королевск', 'king'],
}

# Типы одноразовой упаковки (для строгого matching)
DISPOSABLE_TYPES = {
    'lid': ['крышк'],
    'cup': ['стакан'],
    'container': ['контейнер'],
    'plate': ['тарелк'],
    'fork': ['вилк'],
    'spoon': ['ложк'],
    'knife': ['нож'],
    'straw': ['трубочк', 'соломинк'],
    'napkin': ['салфетк'],
    'bag': ['пакет'],
}

# Типы продуктов, которые нельзя смешивать
PRODUCT_TYPE_EXCLUSIONS = {
    # Колбасные изделия vs сырое мясо
    'sausage_types': ['сосиск', 'сардельк', 'колбас', 'ветчин', 'бекон', 'балык', 'карбонад', 'буженин'],
    'raw_meat_types': ['филе', 'грудк', 'бедр', 'голень', 'крыл', 'тушк', 'фарш', 'стейк', 'вырезк'],
    
    # Полуфабрикаты vs сырьё
    'semi_finished': ['гедза', 'гёдза', 'пельмен', 'вареник', 'котлет', 'наггетс', 'чебурек', 'блинчик', 'манты', 'хинкали'],
    
    # Сырые креветки vs готовые/полуфабрикаты
    'raw_shrimp_markers': ['б/г', 'с/м', 'очищен', 'в панцир', 'сырая', 'сырые'],
    'cooked_shrimp_markers': ['в панировке', 'в кляре', 'варен', 'готов'],
}


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class ProductSignature:
    """Сигнатура товара для matching"""
    # Базовые атрибуты
    product_core_id: Optional[str] = None
    brand_id: Optional[str] = None
    
    # Упаковка
    pack_qty: Optional[float] = None
    net_weight_kg: Optional[float] = None
    unit_type: Optional[str] = None
    
    # Специфические атрибуты
    flavor: Optional[str] = None
    milk_type: Optional[str] = None
    
    # Для одноразки
    disposable_type: Optional[str] = None
    size_mm: Optional[int] = None
    size_ml: Optional[int] = None
    
    # Для овощей
    veggie_state: List[str] = field(default_factory=list)
    
    # Для креветок
    shrimp_caliber: Optional[str] = None
    shrimp_species: Optional[str] = None
    shrimp_state: List[str] = field(default_factory=list)
    
    # Тип продукта (для exclusions)
    is_sausage: bool = False
    is_raw_meat: bool = False
    is_semi_finished: bool = False
    is_raw_shrimp: bool = False
    is_cooked_shrimp: bool = False
    
    # Сырое название
    name_raw: str = ""
    name_norm: str = ""


@dataclass
class MatchResult:
    """Результат matching одного кандидата"""
    passed: bool = False
    block_reason: Optional[str] = None
    score: int = 0
    badges: List[str] = field(default_factory=list)
    
    # Флаги для сортировки
    exact_size: bool = False
    same_brand: bool = False
    pack_diff_pct: float = 0.0


# ============================================================================
# SIGNATURE EXTRACTION
# ============================================================================

def extract_signature(item: Dict) -> ProductSignature:
    """
    Извлекает сигнатуру из товара.
    
    Args:
        item: Dict с полями name_raw, name_norm, product_core_id, brand_id, etc.
    
    Returns:
        ProductSignature
    """
    sig = ProductSignature()
    
    name_raw = item.get('name_raw', '')
    name_norm = item.get('name_norm', name_raw.lower())
    
    sig.name_raw = name_raw
    sig.name_norm = name_norm
    sig.product_core_id = item.get('product_core_id')
    sig.brand_id = item.get('brand_id')
    sig.pack_qty = item.get('pack_qty')
    sig.net_weight_kg = item.get('net_weight_kg')
    sig.unit_type = item.get('unit_type')
    
    # === ИЗВЛЕЧЕНИЕ ВКУСА ===
    for flavor_name, patterns in FLAVOR_PATTERNS.items():
        for p in patterns:
            if p in name_norm:
                sig.flavor = flavor_name
                break
        if sig.flavor:
            break
    
    # === ИЗВЛЕЧЕНИЕ ТИПА МОЛОКА ===
    for milk_type, patterns in MILK_TYPE_PATTERNS.items():
        if not patterns:  # dairy - default
            continue
        for p in patterns:
            if p in name_norm:
                sig.milk_type = milk_type
                break
        if sig.milk_type:
            break
    # Если молочка но не специальный тип - это dairy
    if not sig.milk_type and sig.product_core_id and 'dairy' in sig.product_core_id:
        sig.milk_type = 'dairy'
    
    # === ИЗВЛЕЧЕНИЕ ТИПА ОДНОРАЗКИ ===
    for disp_type, patterns in DISPOSABLE_TYPES.items():
        for p in patterns:
            if p in name_norm:
                sig.disposable_type = disp_type
                break
        if sig.disposable_type:
            break
    
    # === ИЗВЛЕЧЕНИЕ РАЗМЕРА (для одноразки) ===
    for pattern in SIZE_PATTERNS:
        match = re.search(pattern, name_norm)
        if match:
            try:
                size_val = int(match.group(1))
                if 'мл' in pattern or 'ml' in name_norm.lower():
                    sig.size_ml = size_val
                else:
                    sig.size_mm = size_val
            except (ValueError, IndexError):
                pass
            break
    
    # === СОСТОЯНИЕ ОВОЩЕЙ ===
    for state, patterns in VEGGIE_STATE_PATTERNS.items():
        for p in patterns:
            if p in name_norm:
                sig.veggie_state.append(state)
                break
    
    # === КРЕВЕТКИ ===
    if 'кревет' in name_norm or 'креветка' in name_norm or sig.product_core_id == 'seafood.shrimp':
        # Калибр
        caliber_match = re.search(SHRIMP_CALIBER_PATTERN, name_raw)
        if caliber_match:
            sig.shrimp_caliber = f"{caliber_match.group(1)}/{caliber_match.group(2)}"
        
        # Вид
        for species, patterns in SHRIMP_SPECIES_PATTERNS.items():
            for p in patterns:
                if p in name_norm:
                    sig.shrimp_species = species
                    break
            if sig.shrimp_species:
                break
        
        # Состояние
        for state, patterns in SHRIMP_STATE_PATTERNS.items():
            for p in patterns:
                if p in name_norm:
                    sig.shrimp_state.append(state)
                    break
    
    # === ТИП ПРОДУКТА (для exclusions) ===
    for p in PRODUCT_TYPE_EXCLUSIONS['sausage_types']:
        if p in name_norm:
            sig.is_sausage = True
            break
    
    for p in PRODUCT_TYPE_EXCLUSIONS['raw_meat_types']:
        if p in name_norm:
            sig.is_raw_meat = True
            break
    
    for p in PRODUCT_TYPE_EXCLUSIONS['semi_finished']:
        if p in name_norm:
            sig.is_semi_finished = True
            break
    
    # Сырые vs готовые креветки
    for p in PRODUCT_TYPE_EXCLUSIONS['raw_shrimp_markers']:
        if p in name_norm:
            sig.is_raw_shrimp = True
            break
    
    for p in PRODUCT_TYPE_EXCLUSIONS['cooked_shrimp_markers']:
        if p in name_norm:
            sig.is_cooked_shrimp = True
            break
    
    return sig


# ============================================================================
# HARD-BLOCK CHECKS
# ============================================================================

def check_pack_tolerance(
    source_sig: ProductSignature, 
    cand_sig: ProductSignature
) -> Tuple[bool, Optional[str], float]:
    """
    Проверяет совместимость упаковки/веса.
    
    Returns:
        (passed, block_reason, pack_diff_pct)
    """
    # Определяем источник размера
    source_size = source_sig.pack_qty or source_sig.net_weight_kg
    cand_size = cand_sig.pack_qty or cand_sig.net_weight_kg
    
    if source_size is None or cand_size is None:
        return True, None, 0.0
    
    if source_size == 0:
        return True, None, 0.0
    
    diff_pct = abs(source_size - cand_size) / source_size
    
    # Определяем тип допуска
    tolerance = PACK_TOLERANCE['regular']
    
    # Специи/порционные
    if source_sig.product_core_id and 'spice' in source_sig.product_core_id:
        tolerance = PACK_TOLERANCE['spices_portion']
    
    # Одноразка - крышки строго
    if source_sig.disposable_type == 'lid':
        tolerance = PACK_TOLERANCE['strict']
    
    if diff_pct > tolerance:
        return False, f"PACK_MISMATCH: source={source_size}, cand={cand_size}, diff={diff_pct*100:.0f}%", diff_pct
    
    return True, None, diff_pct


def check_disposable_size(
    source_sig: ProductSignature, 
    cand_sig: ProductSignature
) -> Tuple[bool, Optional[str], bool]:
    """
    Проверяет совместимость размеров одноразовой упаковки.
    
    Returns:
        (passed, block_reason, is_exact_size)
    """
    # Только для одноразки
    if not source_sig.disposable_type:
        return True, None, True
    
    # Тип должен совпадать (крышка != стакан)
    if source_sig.disposable_type != cand_sig.disposable_type:
        return False, f"DISPOSABLE_TYPE_MISMATCH: {source_sig.disposable_type} != {cand_sig.disposable_type}", False
    
    # Крышки - строго 1:1
    if source_sig.disposable_type == 'lid':
        if source_sig.size_mm and cand_sig.size_mm:
            if source_sig.size_mm != cand_sig.size_mm:
                return False, f"LID_SIZE_MISMATCH: {source_sig.size_mm}mm != {cand_sig.size_mm}mm", False
        if source_sig.size_ml and cand_sig.size_ml:
            if source_sig.size_ml != cand_sig.size_ml:
                return False, f"LID_SIZE_MISMATCH: {source_sig.size_ml}ml != {cand_sig.size_ml}ml", False
    
    # Проверяем точность размера
    is_exact = True
    if source_sig.size_mm and cand_sig.size_mm:
        is_exact = source_sig.size_mm == cand_sig.size_mm
    if source_sig.size_ml and cand_sig.size_ml:
        is_exact = is_exact and (source_sig.size_ml == cand_sig.size_ml)
    
    return True, None, is_exact


def check_flavor(
    source_sig: ProductSignature, 
    cand_sig: ProductSignature
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет совместимость вкусов (hard-block если source имеет вкус).
    """
    if source_sig.flavor:
        if cand_sig.flavor and source_sig.flavor != cand_sig.flavor:
            return False, f"FLAVOR_MISMATCH: {source_sig.flavor} != {cand_sig.flavor}"
        # Если у source есть вкус, а у кандидата нет - тоже блокируем
        if not cand_sig.flavor:
            return False, f"FLAVOR_MISSING: source={source_sig.flavor}, cand=None"
    
    return True, None


def check_milk_type(
    source_sig: ProductSignature, 
    cand_sig: ProductSignature
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет совместимость типов молока (СТРОГО не смешивать).
    """
    if source_sig.milk_type:
        if cand_sig.milk_type and source_sig.milk_type != cand_sig.milk_type:
            return False, f"MILK_TYPE_MISMATCH: {source_sig.milk_type} != {cand_sig.milk_type}"
    
    return True, None


def check_veggie_state(
    source_sig: ProductSignature, 
    cand_sig: ProductSignature
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет совместимость состояния овощей.
    
    Правила:
    - Очищенная запрещена если source не очищенная
    - Мытая: source мытая → сначала мытая, немытая только если нет мытой
    """
    # Очищенная запрещена если source не очищенная
    if 'peeled' in cand_sig.veggie_state and 'peeled' not in source_sig.veggie_state:
        return False, "VEGGIE_PEELED_MISMATCH: source not peeled, cand is peeled"
    
    # Нарезанная запрещена если source не нарезанная
    if 'cut' in cand_sig.veggie_state and 'cut' not in source_sig.veggie_state:
        return False, "VEGGIE_CUT_MISMATCH: source not cut, cand is cut"
    
    return True, None


def check_shrimp_attributes(
    source_sig: ProductSignature, 
    cand_sig: ProductSignature
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет атрибуты креветок (вид, калибр, состояние).
    """
    # Если это не креветки - пропускаем
    if not source_sig.shrimp_caliber and not source_sig.shrimp_species:
        return True, None
    
    # Вид должен совпадать (если указан)
    if source_sig.shrimp_species and cand_sig.shrimp_species:
        if source_sig.shrimp_species != cand_sig.shrimp_species:
            return False, f"SHRIMP_SPECIES_MISMATCH: {source_sig.shrimp_species} != {cand_sig.shrimp_species}"
    
    # Калибр должен совпадать (если указан)
    if source_sig.shrimp_caliber and cand_sig.shrimp_caliber:
        if source_sig.shrimp_caliber != cand_sig.shrimp_caliber:
            return False, f"SHRIMP_CALIBER_MISMATCH: {source_sig.shrimp_caliber} != {cand_sig.shrimp_caliber}"
    
    # Состояние (очищенные/неочищенные)
    if 'peeled' in source_sig.shrimp_state:
        if 'shell_on' in cand_sig.shrimp_state or ('peeled' not in cand_sig.shrimp_state and cand_sig.shrimp_state):
            return False, "SHRIMP_STATE_MISMATCH: source peeled, cand not"
    if 'shell_on' in source_sig.shrimp_state:
        if 'peeled' in cand_sig.shrimp_state:
            return False, "SHRIMP_STATE_MISMATCH: source shell_on, cand peeled"
    
    return True, None


def check_product_type_exclusions(
    source_sig: ProductSignature, 
    cand_sig: ProductSignature
) -> Tuple[bool, Optional[str]]:
    """
    Проверяет исключения по типу продукта (сосиски ≠ филе).
    """
    # Колбасные ≠ сырое мясо
    if source_sig.is_sausage and cand_sig.is_raw_meat:
        return False, "TYPE_EXCLUSION: sausage cannot match raw_meat"
    if source_sig.is_raw_meat and cand_sig.is_sausage:
        return False, "TYPE_EXCLUSION: raw_meat cannot match sausage"
    
    # Полуфабрикаты ≠ сырьё
    if source_sig.is_semi_finished and cand_sig.is_raw_meat:
        return False, "TYPE_EXCLUSION: semi_finished cannot match raw_meat"
    if source_sig.is_raw_meat and cand_sig.is_semi_finished:
        return False, "TYPE_EXCLUSION: raw_meat cannot match semi_finished"
    
    return True, None


# ============================================================================
# MAIN MATCHING FUNCTION
# ============================================================================

def match_candidate(
    source_sig: ProductSignature,
    cand_sig: ProductSignature,
    source_item: Dict,
    cand_item: Dict
) -> MatchResult:
    """
    Проверяет одного кандидата против source.
    
    Returns:
        MatchResult с passed, block_reason, score, badges
    """
    result = MatchResult()
    
    # === HARD-BLOCK: product_core_id должен совпадать ===
    if source_sig.product_core_id != cand_sig.product_core_id:
        result.passed = False
        result.block_reason = f"CORE_MISMATCH: {source_sig.product_core_id} != {cand_sig.product_core_id}"
        return result
    
    # === HARD-BLOCK: Тип продукта (сосиски ≠ филе) ===
    passed, reason = check_product_type_exclusions(source_sig, cand_sig)
    if not passed:
        result.passed = False
        result.block_reason = reason
        return result
    
    # === HARD-BLOCK: Вкус ===
    passed, reason = check_flavor(source_sig, cand_sig)
    if not passed:
        result.passed = False
        result.block_reason = reason
        return result
    
    # === HARD-BLOCK: Тип молока ===
    passed, reason = check_milk_type(source_sig, cand_sig)
    if not passed:
        result.passed = False
        result.block_reason = reason
        return result
    
    # === HARD-BLOCK: Упаковка/масштаб ===
    passed, reason, pack_diff = check_pack_tolerance(source_sig, cand_sig)
    if not passed:
        result.passed = False
        result.block_reason = reason
        return result
    result.pack_diff_pct = pack_diff
    
    # === HARD-BLOCK: Одноразка (тип + размер) ===
    passed, reason, is_exact_size = check_disposable_size(source_sig, cand_sig)
    if not passed:
        result.passed = False
        result.block_reason = reason
        return result
    result.exact_size = is_exact_size
    
    # === HARD-BLOCK: Состояние овощей ===
    passed, reason = check_veggie_state(source_sig, cand_sig)
    if not passed:
        result.passed = False
        result.block_reason = reason
        return result
    
    # === HARD-BLOCK: Креветки ===
    passed, reason = check_shrimp_attributes(source_sig, cand_sig)
    if not passed:
        result.passed = False
        result.block_reason = reason
        return result
    
    # === PASSED ALL HARD-BLOCKS ===
    result.passed = True
    
    # === SCORING ===
    score = 100  # Base score
    
    # Бренд совпадает
    if source_sig.brand_id and cand_sig.brand_id:
        if source_sig.brand_id == cand_sig.brand_id:
            result.same_brand = True
            score += 50
            result.badges.append("SAME_BRAND")
    
    # Точный размер (для одноразки)
    if result.exact_size:
        score += 30
        result.badges.append("EXACT_SIZE")
    
    # Близкая фасовка
    if result.pack_diff_pct == 0:
        score += 20
        result.badges.append("EXACT_PACK")
    elif result.pack_diff_pct <= 0.05:
        score += 10
        result.badges.append("CLOSE_PACK")
    
    # Вкус совпадает (если оба указаны)
    if source_sig.flavor and cand_sig.flavor == source_sig.flavor:
        score += 15
        result.badges.append("SAME_FLAVOR")
    
    result.score = score
    return result


def find_alternatives(
    source_item: Dict,
    candidates: List[Dict],
    limit: int = 10,
    require_exact_size_first: int = 4  # Для контейнеров: первые N должны быть точного размера
) -> Dict:
    """
    Находит альтернативы для source_item.
    
    Алгоритм:
    1. Фильтруем по hard-blocks
    2. Сортируем:
       - Точные по атрибутам (size/flavor/etc)
       - Тот же бренд
       - Ближайшие по фасовке
       - По цене
    3. Не смешиваем коробки и штуки (если source коробка - сначала коробки)
    
    Args:
        source_item: Исходный товар
        candidates: Список кандидатов
        limit: Максимум результатов
        require_exact_size_first: Для контейнеров - первые N должны быть точного размера
    
    Returns:
        {
            'source': {..., 'signature': {...}},
            'alternatives': [...],
            'total_candidates': int,
            'passed_hard_blocks': int,
            'rejected_reasons': {...}
        }
    """
    source_sig = extract_signature(source_item)
    
    # Статистика отсеянных
    rejected_reasons: Dict[str, int] = {}
    
    # Результаты
    passed_candidates = []
    
    for cand in candidates:
        # Пропускаем тот же товар
        if cand.get('id') == source_item.get('id'):
            continue
        
        cand_sig = extract_signature(cand)
        match_result = match_candidate(source_sig, cand_sig, source_item, cand)
        
        if not match_result.passed:
            # Считаем причины отсева
            reason_key = match_result.block_reason.split(':')[0] if match_result.block_reason else 'UNKNOWN'
            rejected_reasons[reason_key] = rejected_reasons.get(reason_key, 0) + 1
            continue
        
        passed_candidates.append({
            'item': cand,
            'signature': cand_sig,
            'match_result': match_result,
        })
    
    # === СОРТИРОВКА ===
    # Приоритет:
    # 1. Точный размер (для одноразки)
    # 2. Тот же бренд
    # 3. Ближайшая фасовка
    # 4. Score (match quality)
    # 5. Цена
    
    def sort_key(item):
        mr = item['match_result']
        cand = item['item']
        
        return (
            not mr.exact_size,        # Точный размер первым (False < True)
            not mr.same_brand,        # Тот же бренд первым
            mr.pack_diff_pct,         # Ближайшая фасовка
            -mr.score,                # Выше score лучше
            cand.get('price', 0),     # Дешевле лучше
        )
    
    passed_candidates.sort(key=sort_key)
    
    # === СПЕЦИАЛЬНАЯ ЛОГИКА ДЛЯ КОНТЕЙНЕРОВ ===
    # Первые N должны быть точного размера, потом можно ±10%
    if source_sig.disposable_type == 'container':
        exact_size_items = [c for c in passed_candidates if c['match_result'].exact_size]
        non_exact_items = [c for c in passed_candidates if not c['match_result'].exact_size]
        
        # Если точных меньше чем require_exact_size_first - берём все точные + остальные
        if len(exact_size_items) < require_exact_size_first:
            passed_candidates = exact_size_items + non_exact_items
        else:
            passed_candidates = exact_size_items[:require_exact_size_first] + non_exact_items
    
    # === РАЗДЕЛЕНИЕ КОРОБКИ vs ШТУКИ ===
    # Если source продаётся коробкой (pack_qty > 1 и PIECE), сначала показываем коробки
    source_is_box = (
        source_sig.unit_type == 'PIECE' and 
        source_sig.pack_qty and 
        source_sig.pack_qty > 10  # Больше 10 штук = коробка
    )
    
    if source_is_box:
        boxes = [c for c in passed_candidates if c['item'].get('pack_qty', 1) > 10]
        singles = [c for c in passed_candidates if c['item'].get('pack_qty', 1) <= 10]
        passed_candidates = boxes + singles
    
    # === ФОРМИРУЕМ РЕЗУЛЬТАТ ===
    alternatives = []
    for item in passed_candidates[:limit]:
        cand = item['item']
        mr = item['match_result']
        
        alternatives.append({
            'id': cand.get('id'),
            'name': cand.get('name_raw', ''),
            'name_raw': cand.get('name_raw', ''),
            'price': cand.get('price', 0),
            'pack_qty': cand.get('pack_qty'),
            'net_weight_kg': cand.get('net_weight_kg'),
            'unit_type': cand.get('unit_type'),
            'brand_id': cand.get('brand_id'),
            'supplier_company_id': cand.get('supplier_company_id'),
            'match_score': mr.score,
            'match_badges': mr.badges,
            'exact_size': mr.exact_size,
            'same_brand': mr.same_brand,
        })
    
    return {
        'source': {
            'id': source_item.get('id'),
            'name': source_item.get('name_raw', ''),
            'name_raw': source_item.get('name_raw', ''),
            'price': source_item.get('price', 0),
            'pack_qty': source_item.get('pack_qty'),
            'unit_type': source_item.get('unit_type'),
            'brand_id': source_item.get('brand_id'),
            'product_core_id': source_sig.product_core_id,
            'signature': {
                'flavor': source_sig.flavor,
                'milk_type': source_sig.milk_type,
                'disposable_type': source_sig.disposable_type,
                'size_mm': source_sig.size_mm,
                'size_ml': source_sig.size_ml,
                'shrimp_caliber': source_sig.shrimp_caliber,
                'shrimp_species': source_sig.shrimp_species,
            }
        },
        'alternatives': alternatives,
        'total_candidates': len(candidates),
        'passed_hard_blocks': len(passed_candidates),
        'rejected_reasons': rejected_reasons,
    }


# ============================================================================
# UTILITY FUNCTIONS
# ============================================================================

def explain_match(source_name: str, candidate_name: str, 
                  source_core_id: str = None, cand_core_id: str = None) -> Dict:
    """
    Объясняет решение о matching между двумя товарами.
    Полезно для отладки.
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
    match_result = match_candidate(source_sig, cand_sig, source_item, cand_item)
    
    return {
        'source': {
            'name': source_name,
            'signature': {
                'product_core_id': source_sig.product_core_id,
                'flavor': source_sig.flavor,
                'milk_type': source_sig.milk_type,
                'disposable_type': source_sig.disposable_type,
                'size_mm': source_sig.size_mm,
                'is_sausage': source_sig.is_sausage,
                'is_raw_meat': source_sig.is_raw_meat,
                'shrimp_caliber': source_sig.shrimp_caliber,
            }
        },
        'candidate': {
            'name': candidate_name,
            'signature': {
                'product_core_id': cand_sig.product_core_id,
                'flavor': cand_sig.flavor,
                'milk_type': cand_sig.milk_type,
                'disposable_type': cand_sig.disposable_type,
                'size_mm': cand_sig.size_mm,
                'is_sausage': cand_sig.is_sausage,
                'is_raw_meat': cand_sig.is_raw_meat,
                'shrimp_caliber': cand_sig.shrimp_caliber,
            }
        },
        'result': {
            'passed': match_result.passed,
            'block_reason': match_result.block_reason,
            'score': match_result.score,
            'badges': match_result.badges,
        }
    }
