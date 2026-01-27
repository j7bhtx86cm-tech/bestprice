"""
BestPrice v12 - NPC Matching Module v10
=======================================

«Нулевой мусор» + приоритет идентичности для SHRIMP/FISH+SEAFOOD/MEAT

АРХИТЕКТУРА:
1. NPC-layer поверх matching_engine_v3 (topK=200)
2. Strict по умолчанию — только идентичные товары
3. Similar — только по mode=similar
4. Если Strict пуст → пустой список (OK)

HARD GATES (Strict 1-в-1):
- PROCESSING_FORM: CANNED ≠ SMOKED ≠ FROZEN_RAW ≠ CHILLED
- CUT_TYPE: WHOLE ≠ FILLET ≠ STEAK ≠ MINCED
- SPECIES: окунь ≠ сибас ≠ тилапия
- SHRIMP: species/form/state/caliber 1-в-1
- IS_BOX: короб ↔ не короб (в обе стороны)
- BRAND: если у REF есть brand → только тот же бренд
- 85% GUARD: если бренда нет → similarity >= 0.85

РАНЖИРОВАНИЕ Strict:
1. Близость размера/калибра
2. Страна (та же выше)
3. Бренд (бонус если совпадает)
4. PPU

Version: 10.0 («Нулевой мусор» + приоритет идентичности)
Date: January 2026
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum
from difflib import SequenceMatcher

import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS
# ============================================================================

class ProcessingForm(str, Enum):
    """Тип обработки продукта"""
    CANNED = "CANNED"                    # ж/б, консервы, в масле
    SMOKED = "SMOKED"                    # х/к, г/к, копчёное
    FROZEN_RAW = "FROZEN_RAW"            # с/м, замороженное сырьё
    CHILLED_RAW = "CHILLED_RAW"          # охл, охлаждённое
    READY_SEMIFINISHED = "READY_SEMIFINISHED"  # п/ф, гёдза, котлеты
    SALTED_CURED = "SALTED_CURED"        # солёное, пресервы
    DRIED = "DRIED"                      # сушёное, вяленое
    COOKED_BLANCHED = "COOKED_BLANCHED"  # варёное, бланшированное
    SAUCE_MIX_OTHER = "SAUCE_MIX_OTHER"  # соусы, пасты (не NPC)
    RAW_UNSPECIFIED = "RAW_UNSPECIFIED"  # сырьё без состояния


class CutType(str, Enum):
    """Тип разделки"""
    WHOLE_TUSHKA = "WHOLE"      # тушка, целая, н/р, н/п
    FILLET = "FILLET"           # филе
    STEAK_PORTION = "STEAK"     # стейк, кусок, порция
    MINCED = "MINCED"           # фарш
    LIVER = "LIVER"             # печень
    BREAST = "BREAST"           # грудка
    THIGH = "THIGH"             # бедро
    WING = "WING"               # крыло
    DRUMSTICK = "DRUMSTICK"     # голень
    TENDERLOIN = "TENDERLOIN"   # вырезка
    RIB = "RIB"                 # рёбра
    SAUSAGE = "SAUSAGE"         # колбаса, сосиски


# ============================================================================
# NPC DATA LOADING
# ============================================================================

_NPC_SCHEMA: Dict[str, pd.DataFrame] = {}
_NPC_LEXICON: Dict = {}
_NPC_LOADED = False

NPC_SCHEMA_PATH = Path(__file__).parent / "npc_schema_v9.xlsx"
NPC_LEXICON_PATH = Path(__file__).parent / "lexicon_npc_v9.json"


def load_npc_data():
    global _NPC_SCHEMA, _NPC_LEXICON, _NPC_LOADED
    if _NPC_LOADED:
        return
    try:
        if NPC_SCHEMA_PATH.exists():
            xls = pd.ExcelFile(NPC_SCHEMA_PATH)
            for sheet in xls.sheet_names:
                if sheet.startswith('NPC_nodes_'):
                    domain = sheet.replace('NPC_nodes_', '').replace('_top50', '').replace('_top80', '')
                    _NPC_SCHEMA[domain] = pd.read_excel(xls, sheet)
        if NPC_LEXICON_PATH.exists():
            with open(NPC_LEXICON_PATH, 'r', encoding='utf-8') as f:
                _NPC_LEXICON = json.load(f)
        _NPC_LOADED = True
    except Exception as e:
        logger.error(f"Failed to load NPC data: {e}")
        _NPC_LOADED = True


def get_npc_schema(domain: str) -> Optional[pd.DataFrame]:
    load_npc_data()
    return _NPC_SCHEMA.get(domain)


def get_npc_lexicon() -> Dict:
    load_npc_data()
    return _NPC_LEXICON


# ============================================================================
# CONSTANTS
# ============================================================================

NPC_DOMAINS = {'SHRIMP', 'FISH', 'SEAFOOD', 'MEAT'}
SIMILARITY_THRESHOLD = 0.85  # 85% guard when no brand


# ============================================================================
# EXCLUSION PATTERNS
# ============================================================================

_EXCLUSION_PATTERNS: Dict[str, re.Pattern] = {}


def compile_exclusion_patterns() -> Dict[str, re.Pattern]:
    lexicon = get_npc_lexicon()
    patterns = {}
    oos = lexicon.get('out_of_scope_patterns', {})
    for category, pattern_list in oos.items():
        combined = '|'.join(f'({p})' for p in pattern_list)
        try:
            patterns[f'oos_{category}'] = re.compile(combined, re.IGNORECASE)
        except re.error:
            pass
    return patterns


def get_exclusion_patterns() -> Dict[str, re.Pattern]:
    global _EXCLUSION_PATTERNS
    if not _EXCLUSION_PATTERNS:
        _EXCLUSION_PATTERNS = compile_exclusion_patterns()
    return _EXCLUSION_PATTERNS


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class NPCSignature:
    """NPC сигнатура товара v11 (SHRIMP Zero-Trash)"""
    name_raw: str = ""
    name_norm: str = ""
    
    # NPC классификация
    npc_domain: Optional[str] = None
    npc_node_id: Optional[str] = None
    
    # Глобальные атрибуты
    processing_form: Optional[ProcessingForm] = None
    cut_type: Optional[CutType] = None
    species: Optional[str] = None
    is_box: bool = False
    
    # v10: Brand & Country (только для ранжирования, не hard gate)
    brand_id: Optional[str] = None
    brand_name: Optional[str] = None
    origin_country: Optional[str] = None
    
    # Размер/граммовка
    size_gram_min: Optional[int] = None
    size_gram_max: Optional[int] = None
    
    # Креветки
    shrimp_species: Optional[str] = None
    shrimp_caliber: Optional[str] = None
    shrimp_caliber_min: Optional[int] = None
    shrimp_caliber_max: Optional[int] = None
    shrimp_state: Optional[str] = None
    shrimp_form: Optional[str] = None
    
    # v11: Новые SHRIMP атрибуты
    shrimp_tail_state: Optional[str] = None  # tail_on / tail_off
    shrimp_breaded: bool = False  # панировка/темпура/кляр
    
    # Рыба
    fish_species: Optional[str] = None
    fish_cut: Optional[CutType] = None
    fish_skin: Optional[str] = None
    
    # Морепродукты
    seafood_type: Optional[str] = None
    
    # Мясо
    meat_animal: Optional[str] = None
    meat_cut: Optional[CutType] = None
    
    # Общие
    state_frozen: bool = False
    state_chilled: bool = False
    
    # Исключения
    is_excluded: bool = False
    exclude_reason: Optional[str] = None
    
    # v11: Global NEVER blacklist
    is_blacklisted: bool = False
    blacklist_reason: Optional[str] = None
    
    # Фасовка
    pack_qty: Optional[float] = None
    
    # v11: UOM (единица измерения)
    uom: Optional[str] = None  # 'kg' / 'pcs' / 'pack'
    weight_kg: Optional[float] = None  # нормализованный вес в кг
    
    # v10: Similarity tokens
    semantic_tokens: List[str] = field(default_factory=list)


@dataclass
class NPCMatchResult:
    """Результат NPC matching v12 (SHRIMP Zero-Trash)"""
    passed_strict: bool = False
    passed_similar: bool = False
    block_reason: Optional[str] = None
    
    # Совпадения
    same_domain: bool = False
    same_processing_form: bool = False
    same_cut_type: bool = False
    same_species: bool = False
    same_caliber: bool = False
    same_size_range: bool = False
    same_brand: bool = False
    same_country: bool = False
    
    # v11: SHRIMP-specific matches
    same_shrimp_state: bool = False
    same_shrimp_form: bool = False
    same_tail_state: bool = False
    same_breaded: bool = False
    same_uom: bool = False
    
    # v12: Caliber exact flag (для ранжирования)
    caliber_exact: bool = False
    
    # v10: Similarity score
    similarity_score: float = 0.0
    
    # Scoring
    npc_score: int = 0
    size_score: int = 0
    country_score: int = 0
    brand_score: int = 0
    
    # Лейблы
    difference_labels: List[str] = field(default_factory=list)
    
    # v11: Debug output
    passed_gates: List[str] = field(default_factory=list)
    rejected_reason: Optional[str] = None
    rank_features: Dict[str, Any] = field(default_factory=dict)


# ============================================================================
# SIMILARITY CALCULATION (85% guard)
# ============================================================================

# Служебные слова для исключения из similarity
STOPWORDS = {
    'с/м', 'в/у', 'б/г', 'с/г', 'н/р', 'н/п', 'х/к', 'г/к', 'ж/б', 'ст/б',
    'кг', 'г', 'гр', 'шт', 'уп', 'упак', 'короб', 'кор', 'ящик', 'box',
    'гост', 'ту',
    'замор', 'охл', 'охлажд', 'свеж', 'frozen', 'chilled',
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
    # Страны — исключаем из similarity (влияют на ранжирование, не на strict)
    'россия', 'росси', 'рф', 'мурманск', 'дальн', 'камчат', 'сахалин',
    'чили', 'chile', 'china', 'russia',
    'китай', 'кнр', 'вьетнам', 'vietnam', 'инди', 'индия', 'india',
    'аргент', 'аргентина', 'argentina', 'норвег', 'норвегия', 'norway', 'фарер', 'faroe',
    'эквадор', 'ecuador', 'индонез', 'индонезия', 'indonesia', 'таиланд', 'thailand',
}

# ============================================================================
# v11: GLOBAL NEVER BLACKLIST (Strict + Similar)
# ============================================================================

GLOBAL_BLACKLIST_PATTERNS = [
    # Полуфабрикаты / готовые блюда
    r'\bгёдза\b', r'\bгедза\b', r'\bпельмен', r'\bваренник', r'\bвареник', r'\bхинкали\b',
    r'\bполуфабрикат', r'\bп/ф\b', r'\bготовое\s+блюдо', r'\bзакуска\b',
    # Супы/салаты/наборы/миксы
    r'\bсуп\b', r'\bсупа\b', r'\bсупов\b', r'\bсалат', r'\bнабор', r'\bассорти\b', r'\bмикс\b',
    # Котлеты/наггетсы
    r'\bкотлет', r'\bнаггетс', r'\bфрикадел',
    # Лапша/паста
    r'\bлапша\b', r'\bудон\b', r'\bрамен\b', r'\bспагетти\b',
    # Соусы/снеки
    r'\bсоус', r'\bчипс', r'\bснек', r'\bкрекер',
    # Имитация
    r'\bсо\s+вкусом\b', r'\bвкус\s+кревет',
    # Крабовые палочки (имитация)
    r'\bкрабов\w*\s+палоч', r'\bсурими\b',
]

_BLACKLIST_REGEX: Optional[re.Pattern] = None


def get_blacklist_regex() -> re.Pattern:
    """Компилирует regex для blacklist."""
    global _BLACKLIST_REGEX
    if _BLACKLIST_REGEX is None:
        combined = '|'.join(f'({p})' for p in GLOBAL_BLACKLIST_PATTERNS)
        _BLACKLIST_REGEX = re.compile(combined, re.IGNORECASE)
    return _BLACKLIST_REGEX


def check_blacklist(name_norm: str) -> Tuple[bool, Optional[str]]:
    """Проверяет, попадает ли название в Global NEVER blacklist."""
    regex = get_blacklist_regex()
    match = regex.search(name_norm)
    if match:
        return True, f"FORBIDDEN_CLASS:{match.group(0)}"
    return False, None


def extract_semantic_tokens(name: str) -> List[str]:
    """Извлекает смысловые токены для similarity."""
    name_lower = name.lower()
    
    # Удаляем числа с единицами (1кг, 500г, 10шт)
    name_clean = re.sub(r'\d+\s*(кг|г|гр|шт|уп|мл|л)\b', '', name_lower)
    # Удаляем калибры (16/20, 21-25)
    name_clean = re.sub(r'\d+[/\-]\d+', '', name_clean)
    # Удаляем чистые числа
    name_clean = re.sub(r'\b\d+\b', '', name_clean)
    
    # Токенизация
    tokens = re.findall(r'[а-яёa-z]+', name_clean)
    
    # Фильтруем stopwords
    tokens = [t for t in tokens if t not in STOPWORDS and len(t) > 1]
    
    return tokens


def calculate_similarity(source_tokens: List[str], candidate_tokens: List[str]) -> float:
    """Вычисляет similarity score по токенам."""
    if not source_tokens or not candidate_tokens:
        return 0.0
    
    # Множественное пересечение
    source_set = set(source_tokens)
    candidate_set = set(candidate_tokens)
    
    intersection = source_set & candidate_set
    union = source_set | candidate_set
    
    if not union:
        return 0.0
    
    # Jaccard similarity
    jaccard = len(intersection) / len(union)
    
    # Sequence similarity для более точной оценки
    source_str = ' '.join(sorted(source_tokens))
    candidate_str = ' '.join(sorted(candidate_tokens))
    seq_ratio = SequenceMatcher(None, source_str, candidate_str).ratio()
    
    # Комбинированный score
    return (jaccard + seq_ratio) / 2


# ============================================================================
# ATTRIBUTE EXTRACTION
# ============================================================================

def extract_processing_form(name_norm: str) -> Optional[ProcessingForm]:
    """Определяет тип обработки."""
    # CANNED
    if any(x in name_norm for x in ['ж/б', 'ст/б', 'консерв', 'в масле', 'в собств', 
                                      'в томат', 'банка', 'ключ']):
        return ProcessingForm.CANNED
    
    # SMOKED - regex для точного match
    smoked_patterns = [r'\bх/к\b', r'\bг/к\b', r'копч', r'холодн\.?коп', r'горяч\.?коп']
    for pattern in smoked_patterns:
        if re.search(pattern, name_norm, re.IGNORECASE):
            return ProcessingForm.SMOKED
    
    # DRIED
    if any(x in name_norm for x in ['сушён', 'сушен', 'вялен', 'dried']):
        return ProcessingForm.DRIED
    
    # SALTED/CURED
    if any(x in name_norm for x in ['пресерв', 'солён', 'солен', 'посол', 'малосол', 'слабосол']):
        return ProcessingForm.SALTED_CURED
    
    # COOKED/BLANCHED
    if any(x in name_norm for x in ['варён', 'варен', 'бланш', 'в/м', 'cooked', 'blanch']):
        return ProcessingForm.COOKED_BLANCHED
    
    # READY_SEMIFINISHED
    if any(x in name_norm for x in ['п/ф', 'гёдза', 'гедза', 'пельмен', 'котлет', 
                                      'наггетс', 'панир', 'темпур', 'кляр', 'фрикадел']):
        return ProcessingForm.READY_SEMIFINISHED
    
    # SAUCE_MIX_OTHER
    if any(x in name_norm for x in ['соус', 'паста', 'маринад', 'чука', 'нори', 'водоросл']):
        return ProcessingForm.SAUCE_MIX_OTHER
    
    # CHILLED_RAW
    if any(x in name_norm for x in ['охл', 'охлажд', 'свеж', 'с/г']):
        return ProcessingForm.CHILLED_RAW
    
    # FROZEN_RAW
    if any(x in name_norm for x in ['с/м', 'зам', 'замор', 'мороз', 'frozen']):
        return ProcessingForm.FROZEN_RAW
    
    return ProcessingForm.RAW_UNSPECIFIED


def extract_cut_type(name_norm: str, domain: str) -> Optional[CutType]:
    """Определяет тип разделки."""
    # Универсальные
    if any(x in name_norm for x in ['филе', 'fillet', 'filet']):
        return CutType.FILLET
    if any(x in name_norm for x in ['фарш', 'mince', 'ground']):
        return CutType.MINCED
    
    # Рыба
    if domain in ('FISH', 'SEAFOOD'):
        if any(x in name_norm for x in ['тушка', 'целая', 'whole', 'н/р', 'потрош', 
                                          'непотрош', 'неразд']):
            return CutType.WHOLE_TUSHKA
        if any(x in name_norm for x in ['стейк', 'steak', 'кусок', 'порц']):
            return CutType.STEAK_PORTION
        if 'печень' in name_norm:
            return CutType.LIVER
    
    # Мясо/птица
    if domain == 'MEAT':
        if any(x in name_norm for x in ['грудк', 'breast']):
            return CutType.BREAST
        if any(x in name_norm for x in ['бедр', 'thigh', 'окорочок', 'окорочк']):
            return CutType.THIGH
        if any(x in name_norm for x in ['крыл', 'wing']):
            return CutType.WING
        if any(x in name_norm for x in ['голень', 'drumstick']):
            return CutType.DRUMSTICK
        if any(x in name_norm for x in ['вырезк', 'tenderloin']):
            return CutType.TENDERLOIN
        if any(x in name_norm for x in ['рёбр', 'ребр', 'rib']):
            return CutType.RIB
        if any(x in name_norm for x in ['колбас', 'сосиск', 'сардельк']):
            return CutType.SAUSAGE
        if any(x in name_norm for x in ['стейк', 'steak']):
            return CutType.STEAK_PORTION
    
    return None


def extract_species(name_norm: str, domain: str) -> Optional[str]:
    """Извлекает вид продукта."""
    if domain == 'FISH':
        species_map = {
            'salmon': ['лосось', 'лосос', 'сёмга', 'семга', 'сёмги', 'семги'],
            'trout': ['форель', 'форели'],
            'cod': ['треска', 'трески', 'трескова'],
            'tuna': ['тунец', 'тунца'],
            'halibut': ['палтус', 'палтуса'],
            'pollock': ['минтай', 'минтая'],
            'mackerel': ['скумбри'],
            'herring': ['сельд', 'сельди'],
            'seabass': ['сибас'],
            'dorado': ['дорад'],
            'tilapia': ['тилапи'],
            'perch': ['окун', 'окуня'],
            'pike': ['щук'],
            'pangasius': ['пангасиус'],
        }
        for species, tokens in species_map.items():
            for token in tokens:
                if token in name_norm:
                    return species
    
    elif domain == 'MEAT':
        animal_map = {
            'beef': ['говядин', 'телятин', 'рибай', 'ribeye'],
            'pork': ['свинин', 'свиной', 'свиная'],
            'chicken': ['курин', 'курица', 'куриц', 'цыпл', 'бройлер'],
            'turkey': ['индейк', 'индюш'],
            'lamb': ['баранин', 'ягнят', 'ягненок'],
            'duck': ['утк', 'утин'],
        }
        for animal, tokens in animal_map.items():
            for token in tokens:
                if token in name_norm:
                    return animal
    
    elif domain == 'SHRIMP':
        shrimp_map = {
            'vannamei': ['ваннам', 'белоног'],
            'tiger': ['тигр'],
            'argentine': ['аргент'],
            'north': ['северн', 'ботан'],
            'king': ['королев'],
        }
        for species, tokens in shrimp_map.items():
            for token in tokens:
                if token in name_norm:
                    return species
        return 'unspecified'
    
    elif domain == 'SEAFOOD':
        seafood_map = {
            'mussels': ['мидии', 'мидия'],
            'squid': ['кальмар'],
            'octopus': ['осьминог'],
            'scallop': ['гребешок'],
            'crab': ['краб'],
            'lobster': ['лобстер', 'омар'],
        }
        for seafood_type, tokens in seafood_map.items():
            for token in tokens:
                if token in name_norm:
                    return seafood_type
    
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


def extract_size_grams(name_norm: str) -> Tuple[Optional[int], Optional[int]]:
    """Извлекает размер в граммах."""
    # Диапазон: 255-311г
    match = re.search(r'(\d{2,4})\s*[-–]\s*(\d{2,4})\s*г', name_norm)
    if match:
        return int(match.group(1)), int(match.group(2))
    
    # oz: 9-11oz
    match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*oz', name_norm, re.IGNORECASE)
    if match:
        return int(float(match.group(1)) * 28.35), int(float(match.group(2)) * 28.35)
    
    # Единичный: 150г
    match = re.search(r'(\d{2,4})\s*г(?!р)', name_norm)
    if match:
        size = int(match.group(1))
        if 50 <= size <= 2000:
            return size, size
    
    return None, None


def extract_shrimp_caliber(name_norm: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Извлекает калибр креветок.
    
    Поддерживаемые форматы:
    - 16/20, 16-20, 16 / 20, 16 - 20
    - 16:20, 16 : 20
    - 16/20*, 16/20шт
    """
    # Расширенный паттерн: digit separator digit (с опциональными пробелами)
    # Separators: / - : 
    match = re.search(r'(\d{1,3})\s*[/\-:]\s*(\d{1,3})', name_norm)
    if match:
        min_cal = int(match.group(1))
        max_cal = int(match.group(2))
        # Нормализуем к формату "min/max"
        return f"{min_cal}/{max_cal}", min_cal, max_cal
    return None, None, None


def has_caliber_pattern(name_norm: str) -> bool:
    """Проверяет наличие паттерна калибра в тексте (для ZERO-TRASH)."""
    return bool(re.search(r'\d{1,3}\s*[/\-:]\s*\d{1,3}', name_norm))


# ============================================================================
# SHRIMP DETECTION CONSTANTS (P0 ZERO-TRASH)
# ============================================================================

# Термины, которые ЯВНО указывают на креветки
SHRIMP_TERMS = [
    'креветк', 'креветоч', 'shrimp', 'prawn',
    'ваннамей', 'ванамей', 'vannamei', 'vanamei', 'vannameii',
    'тигров', 'tiger',
    'королевск', 'king', 'royal',
    'лангустин', 'langoustine', 'langostin',
    'северн', 'северян', 'north', 'northern',
    'аргентин', 'argentin', 'argentina',
    'черномор',  # черноморская
]

# Атрибуты, которые В СОЧЕТАНИИ с калибром указывают на креветки
SHRIMP_ATTRS = [
    # Форма
    'б/г', 'с/г', 'без голов', 'с голов', 'headless', 'head on', 'head-on',
    'очищ', 'неочищ', 'peeled', 'unpeeled', 'shell on', 'shell-on',
    'б/хв', 'с/хв', 'без хвост', 'с хвост', 'tail on', 'tail off', 'tail-on', 'tail-off',
    # Состояние
    'с/м', 'в/м', 'в/п', 'raw', 'cooked', 'бланш',
    # Упаковка/форма
    'шт/ф', 'штуч', 'iqf', 'block', 'блок', 'во льду', 'глазур',
    # Размер (вспомогательные)
    'калибр', 'размер', 'size',
]

# Слова-исключения (не креветки, даже если есть калибр)
SHRIMP_EXCLUDES = [
    'со вкусом', 'вкус кревет', 'ароматизатор', 'чипс', 'снек',
    'сухар', 'крекер', 'соус', 'заправ', 'маринад',
]


def looks_like_shrimp(name_norm: str) -> bool:
    """Проверяет выглядит ли название как креветки (для ZERO-TRASH).
    
    P0: Расширенная логика:
    1. Если есть SHRIMP_TERM → True
    2. Если есть калибр-паттерн И есть SHRIMP_ATTR → True
    3. Если есть SHRIMP_EXCLUDE → False
    """
    # Исключения
    if any(exc in name_norm for exc in SHRIMP_EXCLUDES):
        return False
    
    # Явные термины креветок
    if any(term in name_norm for term in SHRIMP_TERMS):
        return True
    
    # Калибр + атрибуты креветок
    if has_caliber_pattern(name_norm):
        if any(attr in name_norm for attr in SHRIMP_ATTRS):
            return True
    
    return False


def detect_shrimp_by_context(name_norm: str) -> bool:
    """Определяет SHRIMP по контексту (калибр + атрибуты).
    
    Используется для расширения npc_domain detection.
    Возвращает True если:
    - Есть калибр-паттерн И
    - Есть хотя бы 2 SHRIMP_ATTR
    """
    if not has_caliber_pattern(name_norm):
        return False
    
    attr_count = sum(1 for attr in SHRIMP_ATTRS if attr in name_norm)
    return attr_count >= 2


def extract_shrimp_state(name_norm: str) -> Optional[str]:
    """Состояние креветок (с/м vs в/м)."""
    if any(x in name_norm for x in ['варён', 'варен', 'в/м', 'cooked']):
        return 'cooked_frozen'
    if any(x in name_norm for x in ['бланш', 'blanch']):
        return 'blanched'
    if any(x in name_norm for x in ['с/м', 'зам', 'сыромор', 'raw']):
        return 'raw_frozen'
    return 'raw_frozen'


def extract_shrimp_form(name_norm: str) -> Optional[str]:
    """Форма креветок (очищ/неочищ, б/г, с/г)."""
    forms = []
    
    # Peeled vs shell_on - проверяем сначала "неочищ"
    if any(x in name_norm for x in ['неочищ', 'в панцир', 'в скорлуп', 'unpeeled', 'shell on']):
        forms.append('shell_on')
    elif any(x in name_norm for x in ['очищ', 'peeled', 'о/м', 'чищен']):
        forms.append('peeled')
    else:
        forms.append('shell_on')  # default
    
    # Head: headless vs head_on
    if any(x in name_norm for x in ['б/г', 'без голов', 'headless']):
        forms.append('headless')
    elif any(x in name_norm for x in ['с/г', 'с голов', 'head on']):
        forms.append('head_on')
    else:
        forms.append('headless')  # default
    
    return '_'.join(forms) if forms else None


def extract_shrimp_tail_state(name_norm: str) -> Optional[str]:
    """v12: Состояние хвоста (tail_on / tail_off).
    
    Распознаёт варианты:
    - tail_on: с/хв, с хв, с хвостом, хвост, tail-on, t-on
    - tail_off: б/хв, без хв, без хвоста, tail-off, t-off
    """
    # Сначала проверяем "без хвоста" (должно быть ДО "с хвостом")
    tail_off_patterns = [
        r'\bб/хв\b', r'\bбез\s*хв', r'\bбез\s*хвост', r'\btail[\s\-]?off\b', r'\bt[\s\-]?off\b',
        r'\btailless\b',
    ]
    for pattern in tail_off_patterns:
        if re.search(pattern, name_norm, re.IGNORECASE):
            return 'tail_off'
    
    # Затем проверяем "с хвостом"
    tail_on_patterns = [
        r'\bс/хв\b', r'\bс\s+хв\b', r'\bс\s*хвост', r'\bхвостик', r'\btail[\s\-]?on\b', r'\bt[\s\-]?on\b',
    ]
    for pattern in tail_on_patterns:
        if re.search(pattern, name_norm, re.IGNORECASE):
            return 'tail_on'
    
    # По умолчанию не определено
    return None


def extract_shrimp_breaded(name_norm: str) -> bool:
    """v11: Флаг панировки/темпуры/кляра."""
    breaded_patterns = [
        'панир', 'темпур', 'кляр', 'breaded', 'tempura', 'batter',
        'в панир', 'в кляр', 'в темпур',
    ]
    return any(x in name_norm for x in breaded_patterns)


def extract_uom(name_norm: str, item: Dict) -> Tuple[Optional[str], Optional[float]]:
    """v11: Извлекает UOM (единицу измерения) и нормализованный вес."""
    # Сначала из item
    uom_from_item = item.get('uom') or item.get('unit')
    weight_from_item = item.get('net_weight_kg') or item.get('weight_kg')
    
    # Нормализация веса из текста
    weight_kg = None
    
    # Ищем вес в кг: 1кг, 1.5кг, 10 кг
    match_kg = re.search(r'(\d+(?:[.,]\d+)?)\s*кг\b', name_norm)
    if match_kg:
        weight_kg = float(match_kg.group(1).replace(',', '.'))
    
    # Ищем вес в граммах: 500г, 1000 г
    if not weight_kg:
        match_g = re.search(r'(\d+)\s*г(?:р)?\b', name_norm)
        if match_g:
            grams = int(match_g.group(1))
            if 50 <= grams <= 10000:  # разумный диапазон
                weight_kg = grams / 1000
    
    # Используем вес из item если не нашли в тексте
    if not weight_kg and weight_from_item:
        weight_kg = float(weight_from_item)
    
    # Определяем UOM
    uom = None
    if uom_from_item:
        uom_lower = str(uom_from_item).lower()
        if uom_lower in ('кг', 'kg', 'kilogram'):
            uom = 'kg'
        elif uom_lower in ('шт', 'pcs', 'piece', 'штука'):
            uom = 'pcs'
        elif uom_lower in ('уп', 'упак', 'pack', 'упаковка'):
            uom = 'pack'
    
    # Пытаемся определить из текста если не задано
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
    country_map = {
        'russia': ['росси', 'рф', 'мурманск', 'дальн', 'камчат', 'сахалин'],
        'chile': ['чили', 'chile'],
        'china': ['китай', 'china', 'кнр'],
        'vietnam': ['вьетнам', 'vietnam'],
        'india': ['инди', 'india'],
        'argentina': ['аргент', 'argentina'],
        'norway': ['норвег', 'norway'],
        'faroe': ['фарер', 'faroe'],
    }
    for country, tokens in country_map.items():
        for token in tokens:
            if token in name_norm:
                return country
    return None


def extract_brand_from_name(name_norm: str) -> Optional[str]:
    """Извлекает бренд из названия (если распознан)."""
    known_brands = [
        'heinz', 'knorr', 'bonduelle', 'horeca', 'metro', 'sango', 'agama',
        'vici', 'санта бремор', 'русское море', 'меридиан', 'dobroflot',
    ]
    for brand in known_brands:
        if brand in name_norm:
            return brand
    return None


# ============================================================================
# MAIN SIGNATURE EXTRACTION
# ============================================================================

def extract_npc_signature(item: Dict) -> NPCSignature:
    """Извлекает полную NPC сигнатуру v11 (SHRIMP Zero-Trash)."""
    sig = NPCSignature()
    
    name_raw = item.get('name_raw', item.get('name', ''))
    name_norm = name_raw.lower()
    
    sig.name_raw = name_raw
    sig.name_norm = name_norm
    sig.pack_qty = item.get('pack_qty') or item.get('net_weight_kg')
    
    # v11: Global NEVER blacklist check (FIRST!)
    is_blacklisted, blacklist_reason = check_blacklist(name_norm)
    if is_blacklisted:
        sig.is_blacklisted = True
        sig.blacklist_reason = blacklist_reason
        # Продолжаем извлечение для debug, но флаг is_blacklisted блокирует
    
    # v10: Brand & Country from item (только для ранжирования)
    sig.brand_id = item.get('brand_id')
    sig.brand_name = item.get('brand_name') or extract_brand_from_name(name_norm)
    sig.origin_country = item.get('origin_country') or extract_origin_country(name_norm)
    
    # v11: UOM и вес
    sig.uom, sig.weight_kg = extract_uom(name_norm, item)
    
    patterns = get_exclusion_patterns()
    
    # HARD EXCLUSIONS (legacy)
    for pattern_name, pattern in patterns.items():
        if pattern_name.startswith('oos_'):
            if pattern.search(name_norm):
                sig.is_excluded = True
                sig.exclude_reason = pattern_name
                return sig
    
    # PROCESSING FORM
    sig.processing_form = extract_processing_form(name_norm)
    
    # Exclude SAUCE_MIX_OTHER and READY_SEMIFINISHED
    if sig.processing_form == ProcessingForm.SAUCE_MIX_OTHER:
        sig.is_excluded = True
        sig.exclude_reason = 'SAUCE_MIX_OTHER'
        return sig
    
    if sig.processing_form == ProcessingForm.READY_SEMIFINISHED:
        sig.is_excluded = True
        sig.exclude_reason = 'READY_SEMIFINISHED'
        return sig
    
    # DOMAIN DETECTION
    sig.npc_domain = _detect_npc_domain(name_norm)
    
    if not sig.npc_domain:
        return sig
    
    # Attributes
    sig.is_box = extract_is_box(name_norm)
    sig.cut_type = extract_cut_type(name_norm, sig.npc_domain)
    sig.species = extract_species(name_norm, sig.npc_domain)
    
    # Domain-specific
    if sig.npc_domain == 'SHRIMP':
        sig.shrimp_species = sig.species
        sig.shrimp_caliber, sig.shrimp_caliber_min, sig.shrimp_caliber_max = extract_shrimp_caliber(name_norm)
        sig.shrimp_state = extract_shrimp_state(name_norm)
        sig.shrimp_form = extract_shrimp_form(name_norm)
        # v11: Новые атрибуты
        sig.shrimp_tail_state = extract_shrimp_tail_state(name_norm)
        sig.shrimp_breaded = extract_shrimp_breaded(name_norm)
    
    elif sig.npc_domain == 'FISH':
        sig.fish_species = sig.species
        sig.fish_cut = sig.cut_type
        if any(x in name_norm for x in ['без кож', 'б/к', 'skinless']):
            sig.fish_skin = 'skin_off'
        elif any(x in name_norm for x in ['на коже', 'с кож']):
            sig.fish_skin = 'skin_on'
        sig.size_gram_min, sig.size_gram_max = extract_size_grams(name_norm)
    
    elif sig.npc_domain == 'SEAFOOD':
        sig.seafood_type = sig.species
    
    elif sig.npc_domain == 'MEAT':
        sig.meat_animal = sig.species
        sig.meat_cut = sig.cut_type
    
    # Common
    sig.state_frozen = any(x in name_norm for x in ['с/м', 'зам', 'мороз', 'frozen'])
    sig.state_chilled = any(x in name_norm for x in ['охл', 'охлажд', 'chilled'])
    
    # v10: Semantic tokens for similarity
    sig.semantic_tokens = extract_semantic_tokens(name_raw)
    
    # NPC Node
    sig.npc_node_id = _lookup_npc_node_id(sig)
    
    return sig


def _detect_npc_domain(name_norm: str) -> Optional[str]:
    """Определяет NPC домен.
    
    P0 ZERO-TRASH: Расширенная логика для SHRIMP:
    1. Явные термины (креветк, shrimp, ваннам, etc.)
    2. Контекстное определение (калибр + атрибуты креветок)
    """
    # SHRIMP - Проверка исключений
    if any(exc in name_norm for exc in SHRIMP_EXCLUDES):
        pass  # Не SHRIMP если исключение
    # SHRIMP - Явные термины
    elif any(term in name_norm for term in SHRIMP_TERMS):
        return 'SHRIMP'
    # SHRIMP - Контекстное определение (калибр + атрибуты)
    elif detect_shrimp_by_context(name_norm):
        return 'SHRIMP'
    
    # SEAFOOD
    if any(x in name_norm for x in ['мидии', 'мидия', 'кальмар', 'осьминог', 
                                      'гребешок', 'краб', 'лобстер', 'омар']):
        if 'крабов' in name_norm and 'палоч' in name_norm:
            return None
        if 'сурими' in name_norm:
            return None
        return 'SEAFOOD'
    
    # FISH
    fish_tokens = ['лосось', 'лосос', 'сёмга', 'семга', 'форель', 'треска', 'трески',
                   'тунец', 'палтус', 'минтай', 'скумбри', 'сельд', 'окун', 'сибас',
                   'дорад', 'тилапи', 'пангасиус', 'горбуш', 'кижуч']
    if 'рибай' not in name_norm and 'ribeye' not in name_norm:
        for token in fish_tokens:
            if token in name_norm:
                return 'FISH'
    
    # MEAT
    meat_tokens = ['говядин', 'телятин', 'свинин', 'баранин', 'курин', 'курица',
                   'куриц', 'цыпл', 'индейк', 'утк', 'рибай', 'ribeye', 'колбас', 'сосиск']
    for token in meat_tokens:
        if token in name_norm:
            return 'MEAT'
    
    return None


def _lookup_npc_node_id(sig: NPCSignature) -> Optional[str]:
    """Ищет npc_node_id."""
    if not sig.npc_domain:
        return None
    schema = get_npc_schema(sig.npc_domain)
    if schema is None or schema.empty:
        return None
    try:
        if sig.npc_domain == 'SHRIMP':
            for _, row in schema.iterrows():
                if sig.shrimp_species and sig.shrimp_species in str(row.get('shrimp_variant', '')):
                    return row.get('node_id')
        elif sig.npc_domain == 'FISH':
            for _, row in schema.iterrows():
                if sig.fish_species and sig.fish_species == row.get('species'):
                    return row.get('node_id')
        elif sig.npc_domain == 'SEAFOOD':
            for _, row in schema.iterrows():
                if sig.seafood_type and sig.seafood_type == row.get('type'):
                    return row.get('node_id')
        elif sig.npc_domain == 'MEAT':
            for _, row in schema.iterrows():
                if sig.meat_animal and sig.meat_animal in str(row.get('meat_variant', '')):
                    return row.get('node_id')
    except Exception:
        pass
    return None


# ============================================================================
# NPC STRICT MATCHING v11 (SHRIMP Zero-Trash)
# ============================================================================

def check_npc_strict(source: NPCSignature, candidate: NPCSignature) -> NPCMatchResult:
    """
    Строгая проверка NPC v11 (SHRIMP Zero-Trash).
    
    ПОРЯДОК ПРОВЕРОК:
    0. Global NEVER blacklist (Strict + Similar)
    1. SHRIMP-only gate (если source = SHRIMP)
    2. Hard gates для SHRIMP:
       - species
       - shrimp_state (с/м vs в/м)
       - shrimp_form (очищ/неочищ)
       - tail_state (с хвостом vs без)
       - breaded_flag (панировка)
       - shrimp_caliber (НИКОГДА не ослабляется)
    3. UOM gate (шт vs кг)
    4. Box gate
    5. Processing form gate
    
    Brand/Country — только ранжирование, НЕ hard gates.
    """
    result = NPCMatchResult()
    
    # === 0. GLOBAL NEVER BLACKLIST (Strict + Similar) ===
    if candidate.is_blacklisted:
        result.block_reason = f"FORBIDDEN_CLASS:{candidate.blacklist_reason}"
        result.rejected_reason = result.block_reason
        return result
    
    # === LEGACY EXCLUSIONS ===
    if source.is_excluded:
        result.block_reason = f"SOURCE_EXCLUDED:{source.exclude_reason}"
        result.rejected_reason = result.block_reason
        return result
    if candidate.is_excluded:
        result.block_reason = f"CANDIDATE_EXCLUDED:{candidate.exclude_reason}"
        result.rejected_reason = result.block_reason
        return result
    
    # === 1. SHRIMP-ONLY GATE ===
    if source.npc_domain == 'SHRIMP':
        if candidate.npc_domain != 'SHRIMP':
            result.block_reason = f"NOT_SHRIMP:{candidate.npc_domain or 'UNKNOWN'}"
            result.rejected_reason = result.block_reason
            return result
        result.same_domain = True
        result.passed_gates.append('SHRIMP_DOMAIN')
        
        # === 2. SHRIMP HARD GATES (строго 1-в-1) ===
        
        # 2a. SPECIES
        if source.shrimp_species:
            if not candidate.shrimp_species:
                result.block_reason = f"SPECIES_MISSING:source={source.shrimp_species}"
                result.rejected_reason = result.block_reason
                return result
            if source.shrimp_species != candidate.shrimp_species:
                result.block_reason = f"SPECIES_MISMATCH:{source.shrimp_species}!={candidate.shrimp_species}"
                result.rejected_reason = result.block_reason
                return result
            result.same_species = True
            result.passed_gates.append('SPECIES')
        
        # 2b. SHRIMP_STATE (с/м vs в/м)
        if source.shrimp_state and candidate.shrimp_state:
            if source.shrimp_state != candidate.shrimp_state:
                result.block_reason = f"SHRIMP_STATE_MISMATCH:{source.shrimp_state}!={candidate.shrimp_state}"
                result.rejected_reason = result.block_reason
                return result
            result.same_shrimp_state = True
            result.passed_gates.append('SHRIMP_STATE')
        
        # 2c. SHRIMP_FORM (очищ/неочищ, б/г, с/г)
        if source.shrimp_form and candidate.shrimp_form:
            if source.shrimp_form != candidate.shrimp_form:
                result.block_reason = f"SHRIMP_FORM_MISMATCH:{source.shrimp_form}!={candidate.shrimp_form}"
                result.rejected_reason = result.block_reason
                return result
            result.same_shrimp_form = True
            result.passed_gates.append('SHRIMP_FORM')
        
        # 2d. TAIL_STATE (с хвостом vs без хвоста)
        if source.shrimp_tail_state and candidate.shrimp_tail_state:
            if source.shrimp_tail_state != candidate.shrimp_tail_state:
                result.block_reason = f"TAIL_STATE_MISMATCH:{source.shrimp_tail_state}!={candidate.shrimp_tail_state}"
                result.rejected_reason = result.block_reason
                return result
            result.same_tail_state = True
            result.passed_gates.append('TAIL_STATE')
        
        # 2e. BREADED_FLAG (панировка/темпура/кляр)
        if source.shrimp_breaded != candidate.shrimp_breaded:
            if source.shrimp_breaded:
                result.block_reason = "BREADED_MISMATCH:source_breaded_candidate_not"
            else:
                result.block_reason = "BREADED_MISMATCH:candidate_breaded"
            result.rejected_reason = result.block_reason
            return result
        result.same_breaded = True
        result.passed_gates.append('BREADED_FLAG')
        
        # 2f. CALIBER (НИКОГДА не ослабляется)
        if source.shrimp_caliber:
            if not candidate.shrimp_caliber:
                result.block_reason = f"CALIBER_MISSING:source={source.shrimp_caliber}"
                result.rejected_reason = result.block_reason
                return result
            if source.shrimp_caliber != candidate.shrimp_caliber:
                result.block_reason = f"CALIBER_MISMATCH:{source.shrimp_caliber}!={candidate.shrimp_caliber}"
                result.rejected_reason = result.block_reason
                return result
            result.same_caliber = True
            result.passed_gates.append('CALIBER')
    
    else:
        # === NON-SHRIMP DOMAIN LOGIC (legacy) ===
        if source.npc_domain != candidate.npc_domain:
            result.block_reason = f"DOMAIN_MISMATCH:{source.npc_domain}!={candidate.npc_domain}"
            result.rejected_reason = result.block_reason
            return result
        result.same_domain = True
        result.passed_gates.append('DOMAIN')
        
        # PROCESSING_FORM
        if source.processing_form and candidate.processing_form:
            if source.processing_form != candidate.processing_form:
                result.block_reason = f"PROCESSING_FORM_MISMATCH:{source.processing_form.value}!={candidate.processing_form.value}"
                result.rejected_reason = result.block_reason
                return result
            result.same_processing_form = True
            result.passed_gates.append('PROCESSING_FORM')
        
        # CUT_TYPE
        if source.cut_type:
            if candidate.cut_type and source.cut_type != candidate.cut_type:
                result.block_reason = f"CUT_TYPE_MISMATCH:{source.cut_type.value}!={candidate.cut_type.value}"
                result.rejected_reason = result.block_reason
                return result
            if not candidate.cut_type:
                result.block_reason = f"CUT_TYPE_MISSING:source={source.cut_type.value}"
                result.rejected_reason = result.block_reason
                return result
            result.same_cut_type = True
            result.passed_gates.append('CUT_TYPE')
        
        # SPECIES
        if source.species:
            if candidate.species and source.species != candidate.species:
                result.block_reason = f"SPECIES_MISMATCH:{source.species}!={candidate.species}"
                result.rejected_reason = result.block_reason
                return result
            if not candidate.species:
                result.block_reason = f"SPECIES_MISSING:source={source.species}"
                result.rejected_reason = result.block_reason
                return result
            result.same_species = True
            result.passed_gates.append('SPECIES')
        
        # FISH SIZE RANGE
        if source.npc_domain == 'FISH':
            if source.size_gram_min and source.size_gram_max:
                if source.size_gram_min != source.size_gram_max:
                    if candidate.size_gram_min and candidate.size_gram_max:
                        if candidate.size_gram_min != candidate.size_gram_max:
                            src_mid = (source.size_gram_min + source.size_gram_max) / 2
                            cand_mid = (candidate.size_gram_min + candidate.size_gram_max) / 2
                            diff_pct = abs(src_mid - cand_mid) / src_mid
                            if diff_pct > 0.20:
                                result.block_reason = f"SIZE_MISMATCH:{source.size_gram_min}-{source.size_gram_max}!={candidate.size_gram_min}-{candidate.size_gram_max}"
                                result.rejected_reason = result.block_reason
                                return result
                            result.same_size_range = True
                            result.passed_gates.append('SIZE_RANGE')
    
    # === 3. UOM GATE (шт vs кг) — жёсткий после нормализации ===
    if source.uom and candidate.uom:
        if source.uom != candidate.uom:
            result.block_reason = f"UOM_MISMATCH:{source.uom}!={candidate.uom}"
            result.rejected_reason = result.block_reason
            return result
        result.same_uom = True
        result.passed_gates.append('UOM')
    
    # === 4. BOX GATE (в обе стороны) ===
    if source.is_box != candidate.is_box:
        if source.is_box and not candidate.is_box:
            result.block_reason = "IS_BOX_MISMATCH:ref_is_box_but_candidate_not"
        else:
            result.block_reason = "IS_BOX_MISMATCH:candidate_is_box"
        result.rejected_reason = result.block_reason
        return result
    result.passed_gates.append('BOX')
    
    # === 5. 85% GUARD (для не-SHRIMP, если нет бренда) ===
    if source.npc_domain != 'SHRIMP' and not source.brand_id:
        similarity = calculate_similarity(source.semantic_tokens, candidate.semantic_tokens)
        result.similarity_score = similarity
        if similarity < SIMILARITY_THRESHOLD:
            result.block_reason = f"SIMILARITY_TOO_LOW:{similarity:.2f}<{SIMILARITY_THRESHOLD}"
            result.rejected_reason = result.block_reason
            return result
        result.passed_gates.append('SIMILARITY')
    
    # === PASSED STRICT ===
    result.passed_strict = True
    result.passed_similar = True
    
    # === RANKING (Brand/Country — только ранжирование, НЕ hard gates) ===
    
    # Brand match
    if source.brand_id and candidate.brand_id:
        result.same_brand = source.brand_id == candidate.brand_id
    elif source.brand_name and candidate.brand_name:
        result.same_brand = source.brand_name.lower() == candidate.brand_name.lower()
    
    # Country match
    if source.origin_country and candidate.origin_country:
        result.same_country = source.origin_country == candidate.origin_country
    
    # Text similarity
    if not result.similarity_score:
        result.similarity_score = calculate_similarity(source.semantic_tokens, candidate.semantic_tokens)
    
    # === SCORING (по новому ранжированию) ===
    # 1. brand_match → 2. country_match → 3. text_similarity → 4. ppu
    
    # Brand score (highest priority)
    if result.same_brand:
        result.brand_score = 100
    
    # Country score
    if result.same_country:
        result.country_score = 50
    
    # NPC score based on gates passed
    score = 100
    if result.same_species:
        score += 20
    if result.same_caliber:
        score += 20
    if result.same_shrimp_state:
        score += 15
    if result.same_shrimp_form:
        score += 15
    if result.same_tail_state:
        score += 10
    if result.same_breaded:
        score += 5
    if result.same_uom:
        score += 5
    
    # v12: Caliber score — TOP PRIORITY
    # Для SHRIMP калибр exact = 100, для FISH размерная близость
    if source.npc_domain == 'SHRIMP' and source.shrimp_caliber_min and candidate.shrimp_caliber_min:
        result.size_score = 100  # Exact match (калибр уже прошёл hard gate)
    elif source.npc_domain == 'FISH' and source.size_gram_min and candidate.size_gram_min:
        src_mid = (source.size_gram_min + source.size_gram_max) / 2
        cand_mid = (candidate.size_gram_min + candidate.size_gram_max) / 2
        diff_pct = abs(src_mid - cand_mid) / src_mid if src_mid else 0
        result.size_score = int(100 * (1 - diff_pct))
    
    # v12: Caliber exact flag (для ранжирования)
    result.caliber_exact = result.same_caliber
    
    result.npc_score = score + result.size_score + result.country_score + result.brand_score
    
    # === DEBUG: rank_features v12 ===
    result.rank_features = {
        # v12: Новый порядок ранжирования
        'caliber_exact': result.same_caliber,
        'caliber_score': result.size_score,
        'tail_match': result.same_tail_state,
        'breaded_match': result.same_breaded,
        'uom_match': result.same_uom,
        'text_similarity': round(result.similarity_score, 2),
        'brand_match': result.same_brand,
        'country_match': result.same_country,
        # Legacy
        'npc_score': result.npc_score,
        'brand_score': result.brand_score,
        'country_score': result.country_score,
        'size_score': result.size_score,
    }
    
    return result


def check_npc_similar(source: NPCSignature, candidate: NPCSignature) -> NPCMatchResult:
    """Мягкая проверка для Similar режима (v11).
    
    Blacklist действует и в Similar — FORBIDDEN_CLASS блокирует везде.
    """
    result = NPCMatchResult()
    
    # === GLOBAL NEVER BLACKLIST (Strict + Similar) ===
    if candidate.is_blacklisted:
        result.block_reason = f"FORBIDDEN_CLASS:{candidate.blacklist_reason}"
        result.rejected_reason = result.block_reason
        return result
    
    if source.is_excluded or candidate.is_excluded:
        result.block_reason = "EXCLUDED"
        result.rejected_reason = result.block_reason
        return result
    
    if source.npc_domain != candidate.npc_domain:
        result.block_reason = "DOMAIN_MISMATCH"
        result.rejected_reason = result.block_reason
        return result
    result.same_domain = True
    
    if source.npc_node_id and not candidate.npc_node_id:
        result.difference_labels.append("Не классифицирован в NPC")
        result.npc_score -= 30
    
    # Collect labels
    if source.processing_form and candidate.processing_form:
        if source.processing_form != candidate.processing_form:
            result.difference_labels.append(f"Другая форма обработки ({candidate.processing_form.value})")
    
    if source.cut_type and candidate.cut_type:
        if source.cut_type != candidate.cut_type:
            result.difference_labels.append(f"Другая разделка ({candidate.cut_type.value})")
    
    if source.species and candidate.species:
        if source.species != candidate.species:
            result.difference_labels.append(f"Другой вид ({candidate.species})")
    
    if source.brand_id and candidate.brand_id:
        if source.brand_id != candidate.brand_id:
            result.difference_labels.append("Другой бренд")
    
    if source.origin_country and candidate.origin_country:
        if source.origin_country != candidate.origin_country:
            result.difference_labels.append(f"Другая страна ({candidate.origin_country})")
    
    if candidate.is_box and not source.is_box:
        result.difference_labels.append("Короб/ящик")
    
    if source.npc_domain == 'SHRIMP':
        if source.shrimp_caliber and candidate.shrimp_caliber:
            if source.shrimp_caliber != candidate.shrimp_caliber:
                result.difference_labels.append(f"Другой калибр ({candidate.shrimp_caliber})")
        if source.shrimp_state and candidate.shrimp_state:
            if source.shrimp_state != candidate.shrimp_state:
                result.difference_labels.append(f"Другое состояние ({candidate.shrimp_state})")
        if source.shrimp_form and candidate.shrimp_form:
            if source.shrimp_form != candidate.shrimp_form:
                result.difference_labels.append(f"Другая форма ({candidate.shrimp_form})")
        if source.shrimp_tail_state and candidate.shrimp_tail_state:
            if source.shrimp_tail_state != candidate.shrimp_tail_state:
                result.difference_labels.append(f"Хвост: {candidate.shrimp_tail_state}")
        if source.shrimp_breaded != candidate.shrimp_breaded:
            if candidate.shrimp_breaded:
                result.difference_labels.append("В панировке")
    
    if source.npc_domain == 'FISH':
        if source.size_gram_min and candidate.size_gram_min:
            if source.size_gram_min != candidate.size_gram_min:
                result.difference_labels.append(f"Другой размер ({candidate.size_gram_min}-{candidate.size_gram_max}г)")
    
    result.passed_similar = True
    result.npc_score = 50 - len(result.difference_labels) * 10
    
    # Country and brand scores for ranking
    if source.origin_country and candidate.origin_country == source.origin_country:
        result.country_score = 30
        result.same_country = True
    if source.brand_id and candidate.brand_id == source.brand_id:
        result.brand_score = 30
        result.same_brand = True
    
    result.npc_score += result.country_score + result.brand_score
    
    # Debug rank_features
    result.rank_features = {
        'brand_match': result.same_brand,
        'country_match': result.same_country,
        'difference_labels': result.difference_labels,
        'npc_score': result.npc_score,
    }
    
    return result


# ============================================================================
# API FUNCTIONS
# ============================================================================

def is_npc_domain_item(item: Dict) -> bool:
    sig = extract_npc_signature(item)
    return sig.npc_domain is not None and not sig.is_excluded


def get_item_npc_domain(item: Dict) -> Optional[str]:
    sig = extract_npc_signature(item)
    if sig.is_excluded:
        return None
    return sig.npc_domain


def apply_npc_filter(
    source_item: Dict,
    candidates: List[Dict],
    limit: int = 10,
    mode: str = 'strict'
) -> Tuple[List[Dict], List[Dict], Dict[str, int]]:
    """
    Применяет NPC фильтрацию v12 (ZERO-TRASH).
    
    mode='strict': только точные аналоги, Similar=[]
    mode='similar': Strict + Similar с лейблами
    
    ZERO-TRASH ПРАВИЛА:
    1. Если REF похож на креветки (looks_like_shrimp) или имеет caliber pattern
       → ЗАПРЕЩЁН legacy_v3, используется только NPC
    2. Если REF shrimp-like но caliber не определён → пустой strict
    3. НИКОГДА не показывать 31/40 для REF 16/20
    
    РАНЖИРОВАНИЕ:
    1. caliber_exact (САМЫЙ ВАЖНЫЙ)
    2. brand_match
    3. country_match
    4. text_similarity
    """
    source_sig = extract_npc_signature(source_item)
    
    # Получаем name для ZERO-TRASH проверок
    name_raw = source_item.get('name_raw', source_item.get('name', ''))
    name_norm = name_raw.lower()
    
    # ZERO-TRASH: Проверяем выглядит ли REF как креветки
    is_shrimp_like = looks_like_shrimp(name_norm)
    has_caliber = has_caliber_pattern(name_norm)
    caliber_direct, _, _ = extract_shrimp_caliber(name_norm)
    
    # Blacklisted source
    if source_sig.is_blacklisted:
        return [], [], {'SOURCE_BLACKLISTED': 1}
    
    if source_sig.is_excluded:
        return [], [], {'SOURCE_EXCLUDED': 1}
    
    # ZERO-TRASH: Если REF shrimp-like но npc_domain=None → всё равно НЕ fallback на legacy
    if not source_sig.npc_domain:
        if is_shrimp_like or has_caliber:
            # REF выглядит как креветки, но не классифицирован → пустой strict (не legacy!)
            logger.warning(f"ZERO-TRASH: REF shrimp-like but not classified: {name_raw[:50]}")
            return [], [], {'REF_SHRIMP_LIKE_NOT_CLASSIFIED': 1}
        else:
            # REF не похож на креветки и не классифицирован → пустой strict
            logger.warning(f"REF item not classified to NPC domain: {name_raw[:50]}")
            return [], [], {'REF_NOT_CLASSIFIED': 1}
    
    # ZERO-TRASH: Для SHRIMP domain, если калибр в тексте есть но не распарсен → пустой strict
    if source_sig.npc_domain == 'SHRIMP':
        if has_caliber and not source_sig.shrimp_caliber:
            logger.warning(f"ZERO-TRASH: SHRIMP with caliber pattern but parse failed: {name_raw[:50]}")
            return [], [], {'REF_CALIBER_PARSE_FAILED': 1}
    
    strict_results = []
    similar_results = []
    rejected_reasons: Dict[str, int] = {}
    
    for cand in candidates:
        if cand.get('id') == source_item.get('id'):
            continue
        
        cand_sig = extract_npc_signature(cand)
        strict_result = check_npc_strict(source_sig, cand_sig)
        
        if strict_result.passed_strict:
            strict_results.append({
                'item': cand,
                'npc_result': strict_result,
                'npc_signature': cand_sig,
                # v11: Debug
                'passed_gates': strict_result.passed_gates,
                'rank_features': strict_result.rank_features,
            })
        else:
            reason = strict_result.block_reason or 'UNKNOWN'
            reason_key = reason.split(':')[0]
            rejected_reasons[reason_key] = rejected_reasons.get(reason_key, 0) + 1
            
            if mode == 'similar':
                similar_result = check_npc_similar(source_sig, cand_sig)
                if similar_result.passed_similar:
                    similar_results.append({
                        'item': cand,
                        'npc_result': similar_result,
                        'npc_signature': cand_sig,
                        'rejected_reason': strict_result.rejected_reason,
                    })
    
    # v12: RANKING (калибр > tail > breaded > similarity > brand > country > ppu)
    # Hard gates уже гарантируют точное совпадение калибра, но оставляем для будущего расширения
    def sort_key_strict(x):
        r = x['npc_result']
        # v12: caliber_exact TOP PRIORITY, затем tail, breaded, similarity, brand, country
        return (
            -int(r.caliber_exact),       # 1. Калибр (точный) — САМЫЙ ВАЖНЫЙ
            -r.size_score,               # 2. Близость размера (для будущего)
            -int(r.same_tail_state),     # 3. tail_state match
            -int(r.same_breaded),        # 4. breaded_flag match
            -r.similarity_score,         # 5. text_similarity
            -r.brand_score,              # 6. brand (НЕ выше калибра!)
            -r.country_score,            # 7. country (НЕ выше калибра!)
            -r.npc_score,                # 8. остальное
        )
    
    strict_results.sort(key=sort_key_strict)
    strict_results = strict_results[:limit]
    
    if mode == 'similar':
        # Аналогичная сортировка для similar
        similar_results.sort(key=lambda x: (
            -int(x['npc_result'].caliber_exact),
            -x['npc_result'].size_score,
            -x['npc_result'].similarity_score,
            -x['npc_result'].brand_score,
            -x['npc_result'].country_score,
            -x['npc_result'].npc_score
        ))
        similar_results = similar_results[:limit]
    else:
        similar_results = []
    
    return strict_results, similar_results, rejected_reasons


def build_ref_debug(item: Dict) -> Dict:
    """Строит расширенную debug информацию для REF item.
    
    Возвращает все детали парсинга для диагностики проблем с ref_caliber=null.
    """
    # Определяем source field
    if item.get('name_raw'):
        ref_text_source_field = 'name_raw'
        ref_text_used = item.get('name_raw', '')
    elif item.get('name'):
        ref_text_source_field = 'name'
        ref_text_used = item.get('name', '')
    else:
        ref_text_source_field = 'NONE'
        ref_text_used = ''
    
    ref_text_after_normalize = ref_text_used.lower()
    
    # Парсим сигнатуру
    sig = extract_npc_signature(item)
    
    # Прямой парсинг калибра (без проверки domain)
    caliber_direct, _, _ = extract_shrimp_caliber(ref_text_after_normalize)
    
    # Проверки для ZERO-TRASH
    is_shrimp_like = looks_like_shrimp(ref_text_after_normalize)
    has_caliber = has_caliber_pattern(ref_text_after_normalize)
    
    # Определяем ruleset и причину legacy
    if sig.npc_domain:
        ruleset_selected = 'npc_shrimp_v12'
        why_legacy = None
    else:
        ruleset_selected = 'legacy_v3'
        if sig.is_blacklisted:
            why_legacy = f'BLACKLISTED:{sig.blacklist_reason}'
        elif sig.is_excluded:
            why_legacy = f'EXCLUDED:{sig.exclude_reason}'
        elif not ref_text_used:
            why_legacy = 'name_raw_EMPTY'
        else:
            why_legacy = 'npc_domain_NOT_DETECTED'
    
    return {
        'ref_text_source_field': ref_text_source_field,
        'ref_text_used': ref_text_used[:100],  # Truncate for readability
        'ref_text_after_normalize': ref_text_after_normalize[:100],
        'looks_like_shrimp': is_shrimp_like,
        'has_caliber_pattern': has_caliber,
        'caliber_pattern_match': caliber_direct,
        'is_blacklisted': sig.is_blacklisted,
        'blacklist_reason': sig.blacklist_reason,
        'is_excluded': sig.is_excluded,
        'exclude_reason': sig.exclude_reason,
        'npc_domain': sig.npc_domain,
        'ref_caliber': sig.shrimp_caliber,
        'parse_method': 'npc_v12' if sig.npc_domain else 'none',
        'ruleset_selected': ruleset_selected,
        'why_legacy': why_legacy,
    }


def explain_npc_match(source_name: str, candidate_name: str) -> Dict:
    """Объясняет решение NPC matching v11."""
    source = extract_npc_signature({'name_raw': source_name})
    cand = extract_npc_signature({'name_raw': candidate_name})
    
    strict = check_npc_strict(source, cand)
    similar = check_npc_similar(source, cand)
    
    return {
        'source': {
            'name': source_name,
            'npc_domain': source.npc_domain,
            'processing_form': source.processing_form.value if source.processing_form else None,
            'cut_type': source.cut_type.value if source.cut_type else None,
            'species': source.species,
            'is_box': source.is_box,
            'brand_id': source.brand_id,
            'origin_country': source.origin_country,
            'is_excluded': source.is_excluded,
            'is_blacklisted': source.is_blacklisted,
            # v11: SHRIMP attrs
            'shrimp_caliber': source.shrimp_caliber,
            'shrimp_state': source.shrimp_state,
            'shrimp_form': source.shrimp_form,
            'shrimp_tail_state': source.shrimp_tail_state,
            'shrimp_breaded': source.shrimp_breaded,
            'uom': source.uom,
            'weight_kg': source.weight_kg,
        },
        'candidate': {
            'name': candidate_name,
            'npc_domain': cand.npc_domain,
            'processing_form': cand.processing_form.value if cand.processing_form else None,
            'cut_type': cand.cut_type.value if cand.cut_type else None,
            'species': cand.species,
            'is_box': cand.is_box,
            'brand_id': cand.brand_id,
            'origin_country': cand.origin_country,
            'is_excluded': cand.is_excluded,
            'is_blacklisted': cand.is_blacklisted,
            # v11: SHRIMP attrs
            'shrimp_caliber': cand.shrimp_caliber,
            'shrimp_state': cand.shrimp_state,
            'shrimp_form': cand.shrimp_form,
            'shrimp_tail_state': cand.shrimp_tail_state,
            'shrimp_breaded': cand.shrimp_breaded,
            'uom': cand.uom,
            'weight_kg': cand.weight_kg,
        },
        'strict_result': {
            'passed': strict.passed_strict,
            'block_reason': strict.block_reason,
            'rejected_reason': strict.rejected_reason,
            'npc_score': strict.npc_score,
            'similarity_score': strict.similarity_score,
            # v11: Debug output
            'passed_gates': strict.passed_gates,
            'rank_features': strict.rank_features,
        },
        'similar_result': {
            'passed': similar.passed_similar,
            'difference_labels': similar.difference_labels,
            'rank_features': similar.rank_features,
        }
    }
