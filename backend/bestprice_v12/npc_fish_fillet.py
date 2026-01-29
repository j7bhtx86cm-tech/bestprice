"""
BestPrice v12 - NPC Fish Fillet Module v1
==========================================

«Нулевой мусор» strict для домена FISH_FILLET.

АРХИТЕКТУРА:
По аналогии с npc_shrimp, но для рыбного филе.

HARD GATES (Strict 1-в-1):
- npc_domain: FISH_FILLET
- fish_species: треска ≠ минтай ≠ лосось
- cut_type: FILLET ≠ WHOLE ≠ STEAK (КЛЮЧЕВОЙ баг "тушка → филе")
- breaded_flag: в панировке ≠ без панировки
- skin_flag: на коже ≠ без кожи (если распознано)
- state: frozen ≠ chilled (если распознано)
- uom: kg ≠ pcs (с учётом net_weight_kg)
- pack tolerance: ±20% по весу

РАНЖИРОВАНИЕ Strict:
1. species_exact
2. cut_exact
3. breaded_exact
4. skin_exact
5. state_exact
6. brand_match
7. country_match
8. text_similarity
9. ppu (цена за кг)

Version: 1.0
Date: January 2026
"""

import re
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from enum import Enum
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS (FISH_FILLET specific)
# ============================================================================

class FishCutType(str, Enum):
    """Тип разделки рыбы"""
    FILLET = "FILLET"           # филе
    WHOLE = "WHOLE"             # тушка, целая, н/р, н/п
    STEAK = "STEAK"             # стейк, кусок, порция
    CARCASS = "CARCASS"         # каркас, хребет
    CHUNK = "CHUNK"             # кусок, ломтик
    MINCED = "MINCED"           # фарш
    LIVER = "LIVER"             # печень


class FishState(str, Enum):
    """Состояние рыбы"""
    FROZEN = "frozen"           # с/м, замороженное
    CHILLED = "chilled"         # охл, охлаждённое
    FRESH = "fresh"             # свежее
    UNKNOWN = "unknown"


class SkinFlag(str, Enum):
    """Состояние кожи"""
    SKIN_ON = "skin_on"         # на коже, с кожей
    SKIN_OFF = "skin_off"       # без кожи, б/к
    UNKNOWN = "unknown"


# ============================================================================
# CONSTANTS
# ============================================================================

# Термины, которые ЯВНО указывают на домен FISH (для определения FISH_FILLET)
FISH_SPECIES_MAP = {
    'salmon': ['лосось', 'лососев', 'лосося', 'сёмга', 'семга', 'сёмги', 'семги', 'атлантическ'],
    'trout': ['форель', 'форели'],
    'cod': ['треска', 'трески', 'трескова', 'трескового'],
    'pollock': ['минтай', 'минтая'],
    'tuna': ['тунец', 'тунца'],
    'halibut': ['палтус', 'палтуса'],
    'mackerel': ['скумбри'],
    'herring': ['сельд', 'сельди'],
    'seabass': ['сибас', 'сибаса'],
    'dorado': ['дорад', 'дорадо'],
    'tilapia': ['тилапи'],
    'perch': ['окун', 'окуня', 'судак'],
    'pike': ['щук', 'щуки'],
    'pangasius': ['пангасиус'],
    'hake': ['хек', 'хека', 'мерлуз'],
    'flounder': ['камбал'],
    'zander': ['судак', 'судака'],
    'carp': ['карп', 'сазан'],
    'catfish': ['сом', 'сома'],
    'haddock': ['пикш'],
    'redfish': ['окунь морск', 'красн рыб'],
    'pink_salmon': ['горбуш'],
    'chum_salmon': ['кета', 'кеты'],
    'coho_salmon': ['кижуч'],
    'sockeye_salmon': ['нерк'],
}

# FILLET паттерны (определяют cut_type=FILLET)
FILLET_PATTERNS = [
    'филе', 'fillet', 'filet', 'филей',
    'филе-кусок', 'филе-порц',
]

# WHOLE (тушка) паттерны
WHOLE_PATTERNS = [
    'тушка', 'тушки', 'целая', 'целый', 'whole',
    'н/р', 'н/п', 'неразд', 'непотр', 'потрош',
    'с головой', 'без голов', 'б/г', 'с/г',
]

# STEAK паттерны
STEAK_PATTERNS = [
    'стейк', 'steak', 'кусок', 'порц', 'ломт',
]

# CARCASS паттерны
CARCASS_PATTERNS = [
    'каркас', 'хребет', 'хребты', 'спинк', 'carcass',
]

# MINCED паттерны
MINCED_PATTERNS = [
    'фарш', 'mince', 'ground',
]

# Слова-исключения (НЕ fillet, даже если есть FISH)
FISH_FILLET_EXCLUDES = [
    'консерв', 'ж/б', 'в масле', 'в томат', 'пресерв',
    'солён', 'солен', 'посол', 'малосол', 'слабосол',
    'копч', 'х/к', 'г/к', 'вялен', 'сушен',
    'икра', 'молок', 'печень',
    'соус', 'паста', 'чука', 'нори',
    'крабов', 'сурими', 'палочк',
    'гёдза', 'гедза', 'пельмен', 'котлет', 'наггетс',
    'суп', 'салат', 'набор', 'ассорти', 'микс',
]

# Breaded паттерны (панировка)
BREADED_PATTERNS = [
    'панир', 'панко', 'breaded', 'batter',
    'в кляр', 'кляр', 'хрустящ',
    'tempura', 'темпур',
]

# Skin паттерны
SKIN_ON_PATTERNS = [
    r'\bна\s*кож', r'\bс\s*кож', r'\bskin[\s\-]?on\b', r'\bс/к\b',
]
SKIN_OFF_PATTERNS = [
    r'\bбез\s*кож', r'\bб/к\b', r'\bskin[\s\-]?off\b', r'\bskinless\b', r'\bбескож',
]

# State (состояние: frozen/chilled)
FROZEN_PATTERNS = ['с/м', 'зам', 'замор', 'мороз', 'frozen', 'свежемороженн']
CHILLED_PATTERNS = ['охл', 'охлажд', 'chilled', 'свеж']

# Country patterns
COUNTRY_MAP = {
    'russia': ['росси', 'рф', 'мурманск', 'дальн', 'камчат', 'сахалин'],
    'norway': ['норвег', 'norway'],
    'chile': ['чили', 'chile'],
    'faroe': ['фарер', 'faroe'],
    'china': ['китай', 'china', 'кнр'],
    'vietnam': ['вьетнам', 'vietnam'],
    'iceland': ['исланд', 'iceland'],
    'argentina': ['аргент', 'argentina'],
}

# FORBIDDEN_CLASS для FISH_FILLET (блокирует полностью)
FISH_FILLET_BLACKLIST_PATTERNS = [
    # Полуфабрикаты / готовые блюда
    r'\bгёдза\b', r'\bгедза\b', r'\bпельмен', r'\bваренник', r'\bвареник',
    r'\bхинкали\b', r'\bманты\b',
    r'\bполуфабрикат', r'\bп/ф\b', r'\bготовое\s+блюдо',
    # Супы/салаты/наборы
    r'\bсуп\b', r'\bсупа\b', r'\bсупов\b', r'\bсалат', r'\bнабор',
    r'\bассорти\b', r'\bмикс\b', r'\bсет\b',
    # Котлеты/наггетсы
    r'\bкотлет', r'\bнаггетс', r'\bфрикадел', r'\bтефтел', r'\bбургер',
    # Имитация
    r'\bсо\s+вкусом\b', r'\bкрабов\w*\s+палоч', r'\bсурими\b',
    # Консервы/пресервы
    r'\bконсерв', r'\bпресерв', r'\bж/б\b', r'\bв\s+масле\b', r'\bв\s+томат',
    # Копчёное/солёное
    r'\bкопч', r'\bх/к\b', r'\bг/к\b', r'\bсолён', r'\bсолен', r'\bмалосол',
    # Икра/субпродукты
    r'\bикра\b', r'\bмолок\b', r'\bпечень\b',
]

_FISH_FILLET_BLACKLIST_REGEX: Optional[re.Pattern] = None


def get_fish_fillet_blacklist_regex() -> re.Pattern:
    """Компилирует regex для blacklist."""
    global _FISH_FILLET_BLACKLIST_REGEX
    if _FISH_FILLET_BLACKLIST_REGEX is None:
        combined = '|'.join(f'({p})' for p in FISH_FILLET_BLACKLIST_PATTERNS)
        _FISH_FILLET_BLACKLIST_REGEX = re.compile(combined, re.IGNORECASE)
    return _FISH_FILLET_BLACKLIST_REGEX


def check_fish_fillet_blacklist(name_norm: str) -> Tuple[bool, Optional[str]]:
    """Проверяет, попадает ли название в Fish Fillet blacklist."""
    regex = get_fish_fillet_blacklist_regex()
    match = regex.search(name_norm)
    if match:
        return True, f"FORBIDDEN_CLASS:{match.group(0)}"
    return False, None


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class FishFilletSignature:
    """NPC сигнатура товара для FISH_FILLET домена"""
    name_raw: str = ""
    name_norm: str = ""
    
    # NPC классификация
    npc_domain: Optional[str] = None  # "FISH_FILLET"
    
    # Основные атрибуты
    fish_species: Optional[str] = None      # salmon, cod, pollock, etc.
    cut_type: Optional[FishCutType] = None  # FILLET, WHOLE, STEAK, etc.
    skin_flag: Optional[SkinFlag] = None    # skin_on, skin_off
    breaded_flag: bool = False              # в панировке
    state: Optional[FishState] = None       # frozen, chilled
    
    # UOM и вес
    uom: Optional[str] = None               # kg, pcs, pack
    net_weight_kg: Optional[float] = None   # нетто вес в кг
    
    # Brand & Country
    brand_id: Optional[str] = None
    brand_name: Optional[str] = None
    origin_country: Optional[str] = None
    
    # Box
    is_box: bool = False
    
    # Blacklist
    is_blacklisted: bool = False
    blacklist_reason: Optional[str] = None
    
    # Исключения
    is_excluded: bool = False
    exclude_reason: Optional[str] = None
    
    # Для ранжирования
    semantic_tokens: List[str] = field(default_factory=list)


@dataclass
class FishFilletMatchResult:
    """Результат matching для FISH_FILLET"""
    passed_strict: bool = False
    passed_similar: bool = False
    block_reason: Optional[str] = None
    rejected_reason: Optional[str] = None
    
    # Gate results
    same_domain: bool = False
    same_species: bool = False
    same_cut_type: bool = False
    same_skin_flag: bool = False
    same_breaded: bool = False
    same_state: bool = False
    same_uom: bool = False
    same_brand: bool = False
    same_country: bool = False
    
    # Weight tolerance
    weight_compatible: bool = False
    weight_diff_pct: float = 0.0
    
    # Similarity
    similarity_score: float = 0.0
    
    # Scoring
    npc_score: int = 0
    brand_score: int = 0
    country_score: int = 0
    weight_score: int = 0
    
    # Debug
    passed_gates: List[str] = field(default_factory=list)
    difference_labels: List[str] = field(default_factory=list)
    rank_features: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# ATTRIBUTE EXTRACTION
# ============================================================================

def extract_fish_species(name_norm: str) -> Optional[str]:
    """Извлекает вид рыбы."""
    for species, tokens in FISH_SPECIES_MAP.items():
        for token in tokens:
            if token in name_norm:
                return species
    return None


def extract_fish_cut_type(name_norm: str) -> Optional[FishCutType]:
    """Определяет тип разделки рыбы."""
    # LIVER
    if 'печень' in name_norm:
        return FishCutType.LIVER
    
    # Проверяем FILLET первым (приоритет)
    for pattern in FILLET_PATTERNS:
        if pattern in name_norm:
            return FishCutType.FILLET
    
    # MINCED
    for pattern in MINCED_PATTERNS:
        if pattern in name_norm:
            return FishCutType.MINCED
    
    # STEAK
    for pattern in STEAK_PATTERNS:
        if pattern in name_norm:
            return FishCutType.STEAK
    
    # CARCASS
    for pattern in CARCASS_PATTERNS:
        if pattern in name_norm:
            return FishCutType.CARCASS
    
    # WHOLE (тушка) — проверяем последним
    for pattern in WHOLE_PATTERNS:
        if pattern in name_norm:
            return FishCutType.WHOLE
    
    return None


def extract_skin_flag(name_norm: str) -> Optional[SkinFlag]:
    """Определяет skin_on/skin_off."""
    # Сначала проверяем skin_off (без кожи)
    for pattern in SKIN_OFF_PATTERNS:
        if re.search(pattern, name_norm, re.IGNORECASE):
            return SkinFlag.SKIN_OFF
    
    # Затем skin_on (на коже)
    for pattern in SKIN_ON_PATTERNS:
        if re.search(pattern, name_norm, re.IGNORECASE):
            return SkinFlag.SKIN_ON
    
    return None


def extract_breaded_flag(name_norm: str) -> bool:
    """Определяет наличие панировки."""
    return any(pattern in name_norm for pattern in BREADED_PATTERNS)


def extract_fish_state(name_norm: str) -> Optional[FishState]:
    """Определяет состояние (frozen/chilled)."""
    # Frozen
    if any(pattern in name_norm for pattern in FROZEN_PATTERNS):
        return FishState.FROZEN
    
    # Chilled
    if any(pattern in name_norm for pattern in CHILLED_PATTERNS):
        return FishState.CHILLED
    
    return None


def extract_fish_uom(name_norm: str, item: Dict) -> Tuple[Optional[str], Optional[float]]:
    """Извлекает UOM и net_weight_kg."""
    # Из item fields
    uom_from_item = item.get('uom') or item.get('unit') or item.get('unit_type')
    weight_from_item = item.get('net_weight_kg') or item.get('weight_kg')
    
    # Нормализованный вес
    weight_kg = None
    
    # Ищем вес в кг
    match_kg = re.search(r'(\d+(?:[.,]\d+)?)\s*кг\b', name_norm)
    if match_kg:
        weight_kg = float(match_kg.group(1).replace(',', '.'))
    
    # Ищем вес в граммах
    if not weight_kg:
        match_g = re.search(r'(\d+)\s*г(?:р)?\b', name_norm)
        if match_g:
            grams = int(match_g.group(1))
            if 50 <= grams <= 10000:
                weight_kg = grams / 1000
    
    # Используем вес из item если не нашли в тексте
    if not weight_kg and weight_from_item:
        weight_kg = float(weight_from_item)
    
    # Определяем UOM
    uom = None
    if uom_from_item:
        uom_lower = str(uom_from_item).lower()
        if uom_lower in ('кг', 'kg', 'kilogram', 'weight'):
            uom = 'kg'
        elif uom_lower in ('шт', 'pcs', 'piece', 'штука'):
            uom = 'pcs'
        elif uom_lower in ('уп', 'упак', 'pack', 'упаковка'):
            uom = 'pack'
    
    # Из текста
    if not uom:
        if re.search(r'\b(\d+)\s*шт\b', name_norm):
            uom = 'pcs'
        elif re.search(r'\b(\d+(?:[.,]\d+)?)\s*кг\b', name_norm):
            uom = 'kg'
        elif weight_kg:
            uom = 'kg'
    
    return uom, weight_kg


def extract_origin_country(name_norm: str) -> Optional[str]:
    """Извлекает страну происхождения."""
    for country, tokens in COUNTRY_MAP.items():
        for token in tokens:
            if token in name_norm:
                return country
    return None


def extract_is_box(name_norm: str) -> bool:
    """Определяет короб/ящик."""
    box_patterns = [
        r'\bкор\.?\b', r'\bкороб', r'\bящик', r'\bbox\b',
        r'\b10\s*кг\b', r'\b20\s*кг\b', r'\b5\s*кг\b.*кор',
        r'кг/кор', r'кг\s*/\s*кор', r'вес\s+\d+\s*кг',
    ]
    for pattern in box_patterns:
        if re.search(pattern, name_norm, re.IGNORECASE):
            return True
    return False


def extract_semantic_tokens(name: str) -> List[str]:
    """Извлекает смысловые токены для similarity."""
    STOPWORDS = {
        'с/м', 'в/у', 'б/г', 'с/г', 'н/р', 'н/п', 'х/к', 'г/к', 'ж/б', 'б/к', 'с/к',
        'кг', 'г', 'гр', 'шт', 'уп', 'упак', 'короб', 'кор', 'ящик', 'box',
        'гост', 'ту',
        'замор', 'охл', 'охлажд', 'свеж', 'frozen', 'chilled',
        '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
        'россия', 'росси', 'рф', 'мурманск', 'дальн', 'камчат', 'сахалин',
        'чили', 'chile', 'china', 'russia', 'норвег', 'norway', 'фарер', 'faroe',
    }
    name_lower = name.lower()
    # Удаляем числа с единицами
    name_clean = re.sub(r'\d+\s*(кг|г|гр|шт|уп|мл|л)\b', '', name_lower)
    # Удаляем чистые числа
    name_clean = re.sub(r'\b\d+\b', '', name_clean)
    # Токенизация
    tokens = re.findall(r'[а-яёa-z]+', name_clean)
    # Фильтруем stopwords
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    return tokens


# ============================================================================
# DOMAIN DETECTION
# ============================================================================

def looks_like_fish_fillet(name_norm: str) -> bool:
    """Проверяет, выглядит ли товар как рыбное филе.
    
    Условия:
    1. Есть fish species token
    2. Есть fillet pattern
    3. НЕ в EXCLUDES
    """
    # Исключения первыми
    if any(exc in name_norm for exc in FISH_FILLET_EXCLUDES):
        return False
    
    # Проверяем species
    has_fish_species = extract_fish_species(name_norm) is not None
    
    # Проверяем fillet pattern
    has_fillet = any(p in name_norm for p in FILLET_PATTERNS)
    
    return has_fish_species and has_fillet


def detect_fish_fillet_domain(name_norm: str) -> Optional[str]:
    """Определяет, относится ли товар к домену FISH_FILLET.
    
    Возвращает "FISH_FILLET" если:
    1. НЕ blacklisted
    2. Есть fish species
    3. Есть FILLET cut_type (или нет WHOLE/STEAK)
    """
    # Blacklist check
    is_blacklisted, _ = check_fish_fillet_blacklist(name_norm)
    if is_blacklisted:
        return None
    
    # Species check
    species = extract_fish_species(name_norm)
    if not species:
        return None
    
    # Cut type check - нужен FILLET
    cut_type = extract_fish_cut_type(name_norm)
    if cut_type == FishCutType.FILLET:
        return "FISH_FILLET"
    
    # Если есть species + breaded (панированное филе без явного слова "филе")
    # Пример: "Минтай в кляре" → тоже может быть fillet
    if extract_breaded_flag(name_norm):
        # Но только если НЕ тушка
        if cut_type not in (FishCutType.WHOLE, FishCutType.CARCASS):
            return "FISH_FILLET"
    
    return None


# ============================================================================
# MAIN SIGNATURE EXTRACTION
# ============================================================================

def extract_fish_fillet_signature(item: Dict) -> FishFilletSignature:
    """Извлекает полную сигнатуру для FISH_FILLET."""
    sig = FishFilletSignature()
    
    name_raw = item.get('name_raw', item.get('name', ''))
    name_norm = name_raw.lower()
    
    sig.name_raw = name_raw
    sig.name_norm = name_norm
    
    # Blacklist check FIRST
    is_blacklisted, blacklist_reason = check_fish_fillet_blacklist(name_norm)
    if is_blacklisted:
        sig.is_blacklisted = True
        sig.blacklist_reason = blacklist_reason
        # Продолжаем для debug
    
    # Excludes check
    if any(exc in name_norm for exc in FISH_FILLET_EXCLUDES):
        sig.is_excluded = True
        sig.exclude_reason = "FISH_FILLET_EXCLUDED"
    
    # Domain detection
    sig.npc_domain = detect_fish_fillet_domain(name_norm)
    
    # Brand & Country
    sig.brand_id = item.get('brand_id')
    sig.brand_name = item.get('brand_name')
    sig.origin_country = extract_origin_country(name_norm)
    
    # UOM и вес
    sig.uom, sig.net_weight_kg = extract_fish_uom(name_norm, item)
    
    # Box
    sig.is_box = extract_is_box(name_norm)
    
    # Domain-specific attributes
    if sig.npc_domain == "FISH_FILLET":
        sig.fish_species = extract_fish_species(name_norm)
        sig.cut_type = extract_fish_cut_type(name_norm) or FishCutType.FILLET
        sig.skin_flag = extract_skin_flag(name_norm)
        sig.breaded_flag = extract_breaded_flag(name_norm)
        sig.state = extract_fish_state(name_norm)
    
    # Semantic tokens
    sig.semantic_tokens = extract_semantic_tokens(name_raw)
    
    return sig


# ============================================================================
# SIMILARITY CALCULATION
# ============================================================================

def calculate_similarity(source_tokens: List[str], candidate_tokens: List[str]) -> float:
    """Вычисляет similarity score по токенам."""
    if not source_tokens or not candidate_tokens:
        return 0.0
    
    source_set = set(source_tokens)
    candidate_set = set(candidate_tokens)
    
    intersection = source_set & candidate_set
    union = source_set | candidate_set
    
    if not union:
        return 0.0
    
    # Jaccard similarity
    jaccard = len(intersection) / len(union)
    
    # Sequence similarity
    source_str = ' '.join(sorted(source_tokens))
    candidate_str = ' '.join(sorted(candidate_tokens))
    seq_ratio = SequenceMatcher(None, source_str, candidate_str).ratio()
    
    return (jaccard + seq_ratio) / 2


# ============================================================================
# STRICT MATCHING
# ============================================================================

def check_fish_fillet_strict(source: FishFilletSignature, candidate: FishFilletSignature) -> FishFilletMatchResult:
    """
    Строгая проверка NPC для FISH_FILLET (ZERO-TRASH).
    
    ПОРЯДОК GATES (важно!):
    0. FORBIDDEN_CLASS (blacklist)
    1. DOMAIN: FISH_FILLET ≠ другой
    2. SPECIES: треска ≠ минтай
    3. CUT_TYPE: FILLET ≠ WHOLE ≠ STEAK (КРИТИЧНО!)
    4. BREADED_FLAG: панировка ≠ без
    5. SKIN_FLAG: на коже ≠ без кожи (если известно)
    6. STATE: frozen ≠ chilled (если известно)
    7. UOM: kg ≠ pcs (с учётом net_weight)
    8. BOX: короб ↔ не короб
    9. WEIGHT_TOLERANCE: ±20%
    """
    result = FishFilletMatchResult()
    
    # === 0. FORBIDDEN_CLASS ===
    if candidate.is_blacklisted:
        result.block_reason = f"FORBIDDEN_CLASS:{candidate.blacklist_reason}"
        result.rejected_reason = result.block_reason
        return result
    
    if source.is_blacklisted:
        result.block_reason = f"SOURCE_BLACKLISTED:{source.blacklist_reason}"
        result.rejected_reason = result.block_reason
        return result
    
    if source.is_excluded:
        result.block_reason = f"SOURCE_EXCLUDED:{source.exclude_reason}"
        result.rejected_reason = result.block_reason
        return result
    
    if candidate.is_excluded:
        result.block_reason = f"CANDIDATE_EXCLUDED:{candidate.exclude_reason}"
        result.rejected_reason = result.block_reason
        return result
    
    # === 1. DOMAIN GATE ===
    if source.npc_domain == "FISH_FILLET":
        if candidate.npc_domain != "FISH_FILLET":
            result.block_reason = f"NOT_FISH_FILLET:{candidate.npc_domain or 'UNKNOWN'}"
            result.rejected_reason = result.block_reason
            return result
        result.same_domain = True
        result.passed_gates.append('FISH_FILLET_DOMAIN')
        
        # === 2. SPECIES GATE ===
        if source.fish_species:
            if not candidate.fish_species:
                result.block_reason = f"SPECIES_MISSING:source={source.fish_species}"
                result.rejected_reason = result.block_reason
                return result
            if source.fish_species != candidate.fish_species:
                result.block_reason = f"SPECIES_MISMATCH:{source.fish_species}!={candidate.fish_species}"
                result.rejected_reason = result.block_reason
                return result
            result.same_species = True
            result.passed_gates.append('SPECIES')
        
        # === 3. CUT_TYPE GATE (КРИТИЧНО: тушка ≠ филе ≠ стейк) ===
        if source.cut_type:
            if not candidate.cut_type:
                result.block_reason = f"CUT_TYPE_MISSING:source={source.cut_type.value}"
                result.rejected_reason = result.block_reason
                return result
            if source.cut_type != candidate.cut_type:
                result.block_reason = f"CUT_TYPE_MISMATCH:{source.cut_type.value}!={candidate.cut_type.value}"
                result.rejected_reason = result.block_reason
                return result
            result.same_cut_type = True
            result.passed_gates.append('CUT_TYPE')
        
        # === 4. BREADED_FLAG GATE ===
        if source.breaded_flag != candidate.breaded_flag:
            if source.breaded_flag:
                result.block_reason = "BREADED_MISMATCH:source_breaded_candidate_not"
            else:
                result.block_reason = "BREADED_MISMATCH:candidate_breaded"
            result.rejected_reason = result.block_reason
            return result
        result.same_breaded = True
        result.passed_gates.append('BREADED_FLAG')
        
        # === 5. SKIN_FLAG GATE (только если у REF известен) ===
        if source.skin_flag and source.skin_flag != SkinFlag.UNKNOWN:
            if candidate.skin_flag and candidate.skin_flag != SkinFlag.UNKNOWN:
                if source.skin_flag != candidate.skin_flag:
                    result.block_reason = f"SKIN_MISMATCH:{source.skin_flag.value}!={candidate.skin_flag.value}"
                    result.rejected_reason = result.block_reason
                    return result
                result.same_skin_flag = True
                result.passed_gates.append('SKIN_FLAG')
            # Если у кандидата skin unknown — пропускаем gate (не reject)
        
        # === 6. STATE GATE (только если у REF известен) ===
        if source.state and source.state != FishState.UNKNOWN:
            if candidate.state and candidate.state != FishState.UNKNOWN:
                if source.state != candidate.state:
                    result.block_reason = f"STATE_MISMATCH:{source.state.value}!={candidate.state.value}"
                    result.rejected_reason = result.block_reason
                    return result
                result.same_state = True
                result.passed_gates.append('STATE')
        
        # === 7. UOM GATE (с учётом net_weight_kg) ===
        if source.uom and candidate.uom:
            if source.uom != candidate.uom:
                # Если оба имеют net_weight_kg → можно сравнивать по весу
                if source.net_weight_kg and candidate.net_weight_kg:
                    result.same_uom = False
                    result.passed_gates.append('UOM_BY_WEIGHT')
                else:
                    result.block_reason = f"UOM_MISMATCH:{source.uom}!={candidate.uom}"
                    result.rejected_reason = result.block_reason
                    return result
            else:
                result.same_uom = True
                result.passed_gates.append('UOM')
        
        # === 8. BOX GATE ===
        if source.is_box != candidate.is_box:
            if source.is_box:
                result.block_reason = "IS_BOX_MISMATCH:ref_is_box_but_candidate_not"
            else:
                result.block_reason = "IS_BOX_MISMATCH:candidate_is_box"
            result.rejected_reason = result.block_reason
            return result
        result.passed_gates.append('BOX')
        
        # === 9. WEIGHT_TOLERANCE (±20%) ===
        if source.net_weight_kg and candidate.net_weight_kg:
            diff_pct = abs(source.net_weight_kg - candidate.net_weight_kg) / source.net_weight_kg
            result.weight_diff_pct = diff_pct
            if diff_pct <= 0.20:  # ±20% tolerance
                result.weight_compatible = True
                result.passed_gates.append('WEIGHT_TOLERANCE')
                result.weight_score = int(100 * (1 - diff_pct))
            else:
                # Не reject, но понижаем score
                result.weight_compatible = False
                result.weight_score = 0
        else:
            # Вес не известен — не применяем gate
            result.weight_compatible = True
    
    else:
        # === NON-FISH_FILLET (не должен сюда попасть) ===
        result.block_reason = f"DOMAIN_NOT_FISH_FILLET:{source.npc_domain}"
        result.rejected_reason = result.block_reason
        return result
    
    # === PASSED STRICT ===
    result.passed_strict = True
    result.passed_similar = True
    
    # === RANKING (не hard gates) ===
    # Brand match
    if source.brand_id and candidate.brand_id:
        result.same_brand = source.brand_id == candidate.brand_id
    elif source.brand_name and candidate.brand_name:
        result.same_brand = source.brand_name.lower() == candidate.brand_name.lower()
    
    # Country match
    if source.origin_country and candidate.origin_country:
        result.same_country = source.origin_country == candidate.origin_country
    
    # Text similarity
    result.similarity_score = calculate_similarity(source.semantic_tokens, candidate.semantic_tokens)
    
    # === SCORING ===
    score = 100
    if result.same_species:
        score += 30
    if result.same_cut_type:
        score += 25
    if result.same_breaded:
        score += 15
    if result.same_skin_flag:
        score += 10
    if result.same_state:
        score += 10
    if result.same_uom:
        score += 5
    if result.same_brand:
        result.brand_score = 50
        score += 50
    if result.same_country:
        result.country_score = 30
        score += 30
    
    result.npc_score = score + result.weight_score
    
    # === DEBUG: rank_features ===
    result.rank_features = {
        'species_exact': result.same_species,
        'cut_exact': result.same_cut_type,
        'breaded_exact': result.same_breaded,
        'skin_exact': result.same_skin_flag,
        'state_exact': result.same_state,
        'brand_match': result.same_brand,
        'country_match': result.same_country,
        'text_similarity': round(result.similarity_score, 2),
        'weight_compatible': result.weight_compatible,
        'weight_diff_pct': round(result.weight_diff_pct, 2) if result.weight_diff_pct else 0,
        'weight_score': result.weight_score,
        'npc_score': result.npc_score,
        'brand_score': result.brand_score,
        'country_score': result.country_score,
    }
    
    return result


def check_fish_fillet_similar(source: FishFilletSignature, candidate: FishFilletSignature) -> FishFilletMatchResult:
    """Мягкая проверка для Similar режима."""
    result = FishFilletMatchResult()
    
    # Blacklist check
    if candidate.is_blacklisted:
        result.block_reason = f"FORBIDDEN_CLASS:{candidate.blacklist_reason}"
        result.rejected_reason = result.block_reason
        return result
    
    if source.is_excluded or candidate.is_excluded:
        result.block_reason = "EXCLUDED"
        result.rejected_reason = result.block_reason
        return result
    
    if source.npc_domain != candidate.npc_domain:
        result.block_reason = f"DOMAIN_MISMATCH:{source.npc_domain}!={candidate.npc_domain}"
        result.rejected_reason = result.block_reason
        return result
    
    result.same_domain = True
    
    # Collect difference labels
    if source.fish_species and candidate.fish_species:
        if source.fish_species != candidate.fish_species:
            result.difference_labels.append(f"Другой вид ({candidate.fish_species})")
    
    if source.cut_type and candidate.cut_type:
        if source.cut_type != candidate.cut_type:
            result.difference_labels.append(f"Другая разделка ({candidate.cut_type.value})")
    
    if source.breaded_flag != candidate.breaded_flag:
        if candidate.breaded_flag:
            result.difference_labels.append("В панировке")
        else:
            result.difference_labels.append("Без панировки")
    
    if source.skin_flag and candidate.skin_flag:
        if source.skin_flag != candidate.skin_flag:
            result.difference_labels.append(f"Кожа: {candidate.skin_flag.value}")
    
    if source.state and candidate.state:
        if source.state != candidate.state:
            result.difference_labels.append(f"Состояние: {candidate.state.value}")
    
    if source.brand_id and candidate.brand_id:
        if source.brand_id != candidate.brand_id:
            result.difference_labels.append("Другой бренд")
    
    if source.origin_country and candidate.origin_country:
        if source.origin_country != candidate.origin_country:
            result.difference_labels.append(f"Другая страна ({candidate.origin_country})")
    
    result.passed_similar = True
    result.npc_score = 50 - len(result.difference_labels) * 10
    
    # Similarity
    result.similarity_score = calculate_similarity(source.semantic_tokens, candidate.semantic_tokens)
    
    # Brand/Country
    if source.brand_id and candidate.brand_id == source.brand_id:
        result.same_brand = True
        result.brand_score = 30
    if source.origin_country and candidate.origin_country == source.origin_country:
        result.same_country = True
        result.country_score = 20
    
    result.npc_score += result.brand_score + result.country_score
    
    result.rank_features = {
        'brand_match': result.same_brand,
        'country_match': result.same_country,
        'difference_labels': result.difference_labels,
        'npc_score': result.npc_score,
    }
    
    return result


# ============================================================================
# APPLY FILTER
# ============================================================================

def apply_fish_fillet_filter(
    source_item: Dict,
    candidates: List[Dict],
    limit: int = 10,
    mode: str = 'strict'
) -> Tuple[List[Dict], List[Dict], Dict[str, int]]:
    """
    Применяет FISH_FILLET фильтрацию (ZERO-TRASH).
    
    mode='strict': только точные аналоги
    mode='similar': Strict + Similar с лейблами
    
    ZERO-TRASH:
    - Если REF не классифицирован → пустой strict
    - Legacy fallback ЗАПРЕЩЁН
    
    РАНЖИРОВАНИЕ:
    1. species_exact
    2. cut_exact
    3. breaded_exact
    4. skin_exact
    5. state_exact
    6. weight_closest (ближе по граммовке)
    7. brand_match
    8. country_match
    9. text_similarity
    10. ppu (цена за кг)
    """
    source_sig = extract_fish_fillet_signature(source_item)
    
    name_norm = source_item.get('name_raw', source_item.get('name', '')).lower()
    is_fillet_like = looks_like_fish_fillet(name_norm)
    
    # Blacklisted source
    if source_sig.is_blacklisted:
        return [], [], {'SOURCE_BLACKLISTED': 1}
    
    if source_sig.is_excluded:
        return [], [], {'SOURCE_EXCLUDED': 1}
    
    # ZERO-TRASH: REF выглядит как fillet, но domain не определён
    if not source_sig.npc_domain:
        if is_fillet_like:
            logger.warning(f"ZERO-TRASH FISH_FILLET: REF fillet-like but not classified: {name_norm[:50]}")
            return [], [], {'REF_FILLET_LIKE_NOT_CLASSIFIED': 1}
        else:
            logger.warning(f"REF item not classified to FISH_FILLET: {name_norm[:50]}")
            return [], [], {'REF_NOT_CLASSIFIED': 1}
    
    strict_results = []
    similar_results = []
    rejected_reasons: Dict[str, int] = {}
    
    for cand in candidates:
        if cand.get('id') == source_item.get('id'):
            continue
        
        cand_sig = extract_fish_fillet_signature(cand)
        strict_result = check_fish_fillet_strict(source_sig, cand_sig)
        
        if strict_result.passed_strict:
            strict_results.append({
                'item': cand,
                'npc_result': strict_result,
                'npc_signature': cand_sig,
                'passed_gates': strict_result.passed_gates,
                'rank_features': strict_result.rank_features,
            })
        else:
            reason = strict_result.block_reason or 'UNKNOWN'
            reason_key = reason.split(':')[0]
            rejected_reasons[reason_key] = rejected_reasons.get(reason_key, 0) + 1
            
            if mode == 'similar':
                similar_result = check_fish_fillet_similar(source_sig, cand_sig)
                if similar_result.passed_similar:
                    similar_results.append({
                        'item': cand,
                        'npc_result': similar_result,
                        'npc_signature': cand_sig,
                        'rejected_reason': strict_result.rejected_reason,
                    })
    
    # RANKING
    def sort_key_strict(x):
        r = x['npc_result']
        item = x['item']
        # Порядок: species > cut > breaded > skin > state > weight_closest > brand > country > similarity > price
        return (
            -int(r.same_species),           # 1. species_exact
            -int(r.same_cut_type),          # 2. cut_exact
            -int(r.same_breaded),           # 3. breaded_exact
            -int(r.same_skin_flag),         # 4. skin_exact
            -int(r.same_state),             # 5. state_exact
            -r.weight_score,                # 6. weight_closest
            -r.brand_score,                 # 7. brand_match
            -r.country_score,               # 8. country_match
            -r.similarity_score,            # 9. text_similarity
            item.get('price', 999999),      # 10. price ASC (ppu)
        )
    
    strict_results.sort(key=sort_key_strict)
    strict_results = strict_results[:limit]
    
    if mode == 'similar':
        similar_results.sort(key=lambda x: (
            -x['npc_result'].brand_score,
            -x['npc_result'].country_score,
            -x['npc_result'].similarity_score,
            x['item'].get('price', 999999),
        ))
        similar_results = similar_results[:limit]
    else:
        similar_results = []
    
    return strict_results, similar_results, rejected_reasons


# ============================================================================
# DEBUG HELPERS
# ============================================================================

def build_fish_fillet_ref_debug(item: Dict) -> Dict:
    """Строит debug информацию для REF item (FISH_FILLET)."""
    name_raw = item.get('name_raw', item.get('name', ''))
    name_norm = name_raw.lower()
    
    sig = extract_fish_fillet_signature(item)
    
    is_fillet_like = looks_like_fish_fillet(name_norm)
    is_blacklisted, blacklist_reason = check_fish_fillet_blacklist(name_norm)
    
    # Determine ruleset
    if sig.npc_domain == "FISH_FILLET":
        ruleset_selected = 'npc_fish_fillet_v1'
        why_legacy = None
        why_empty_strict = None
    else:
        ruleset_selected = 'legacy_v3'
        if is_blacklisted:
            why_legacy = f'BLACKLISTED:{blacklist_reason}'
            why_empty_strict = f'FORBIDDEN_CLASS:{blacklist_reason}'
        elif sig.is_excluded:
            why_legacy = f'EXCLUDED:{sig.exclude_reason}'
            why_empty_strict = sig.exclude_reason
        elif is_fillet_like:
            why_legacy = 'FILLET_LIKE_BUT_NOT_CLASSIFIED'
            why_empty_strict = 'SPECIES_OR_CUT_UNKNOWN'
        else:
            why_legacy = 'NOT_FISH_FILLET'
            why_empty_strict = 'DOMAIN_NOT_DETECTED'
    
    return {
        'ref_text_source_field': 'name_raw' if item.get('name_raw') else 'name',
        'ref_text_used': name_raw,
        'ref_text_after_normalize': name_norm,
        'looks_like_fish_fillet': is_fillet_like,
        'is_blacklisted': is_blacklisted,
        'blacklist_reason': blacklist_reason,
        'npc_domain': sig.npc_domain,
        'fish_species': sig.fish_species,
        'cut_type': sig.cut_type.value if sig.cut_type else None,
        'skin_flag': sig.skin_flag.value if sig.skin_flag else None,
        'breaded_flag': sig.breaded_flag,
        'state': sig.state.value if sig.state else None,
        'uom': sig.uom,
        'net_weight_kg': sig.net_weight_kg,
        'ruleset_selected': ruleset_selected,
        'why_legacy': why_legacy,
        'why_empty_strict': why_empty_strict,
    }


def explain_fish_fillet_match(source_item: Dict, candidate_item: Dict) -> Dict:
    """Объясняет результат matching для пары товаров."""
    source_sig = extract_fish_fillet_signature(source_item)
    cand_sig = extract_fish_fillet_signature(candidate_item)
    
    result = check_fish_fillet_strict(source_sig, cand_sig)
    
    return {
        'passed_strict': result.passed_strict,
        'block_reason': result.block_reason,
        'passed_gates': result.passed_gates,
        'rank_features': result.rank_features,
        'source_parsed': {
            'npc_domain': source_sig.npc_domain,
            'fish_species': source_sig.fish_species,
            'cut_type': source_sig.cut_type.value if source_sig.cut_type else None,
            'skin_flag': source_sig.skin_flag.value if source_sig.skin_flag else None,
            'breaded_flag': source_sig.breaded_flag,
            'state': source_sig.state.value if source_sig.state else None,
        },
        'candidate_parsed': {
            'npc_domain': cand_sig.npc_domain,
            'fish_species': cand_sig.fish_species,
            'cut_type': cand_sig.cut_type.value if cand_sig.cut_type else None,
            'skin_flag': cand_sig.skin_flag.value if cand_sig.skin_flag else None,
            'breaded_flag': cand_sig.breaded_flag,
            'state': cand_sig.state.value if cand_sig.state else None,
        },
    }


# ============================================================================
# API HELPERS
# ============================================================================

def is_fish_fillet_item(item: Dict) -> bool:
    """Проверяет, является ли товар FISH_FILLET."""
    sig = extract_fish_fillet_signature(item)
    return sig.npc_domain == "FISH_FILLET" and not sig.is_excluded


def get_fish_fillet_domain(item: Dict) -> Optional[str]:
    """Возвращает domain для товара (FISH_FILLET или None)."""
    sig = extract_fish_fillet_signature(item)
    if sig.is_excluded:
        return None
    return sig.npc_domain
