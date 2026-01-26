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
    """NPC сигнатура товара v10"""
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
    
    # v10: Brand & Country
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
    
    # Фасовка
    pack_qty: Optional[float] = None
    
    # v10: Similarity tokens
    semantic_tokens: List[str] = field(default_factory=list)


@dataclass
class NPCMatchResult:
    """Результат NPC matching v10"""
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
    
    # v10: Similarity score
    similarity_score: float = 0.0
    
    # Scoring
    npc_score: int = 0
    size_score: int = 0
    country_score: int = 0
    brand_score: int = 0
    
    # Лейблы
    difference_labels: List[str] = field(default_factory=list)


# ============================================================================
# SIMILARITY CALCULATION (85% guard)
# ============================================================================

# Служебные слова для исключения из similarity
STOPWORDS = {
    'с/м', 'в/у', 'б/г', 'с/г', 'н/р', 'н/п', 'х/к', 'г/к', 'ж/б', 'ст/б',
    'кг', 'г', 'гр', 'шт', 'уп', 'упак', 'короб', 'кор', 'ящик', 'box',
    'гост', 'ту', 'россия', 'чили', 'china', 'russia',
    'замор', 'охл', 'охлажд', 'свеж', 'frozen', 'chilled',
    '1', '2', '3', '4', '5', '6', '7', '8', '9', '0',
}


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
    """Извлекает калибр креветок."""
    match = re.search(r'(\d{1,3})\s*[/\-]\s*(\d{1,3})', name_norm)
    if match:
        min_cal = int(match.group(1))
        max_cal = int(match.group(2))
        return f"{min_cal}/{max_cal}", min_cal, max_cal
    return None, None, None


def extract_shrimp_state(name_norm: str) -> Optional[str]:
    """Состояние креветок."""
    if any(x in name_norm for x in ['варён', 'варен', 'в/м', 'cooked']):
        return 'cooked_frozen'
    if any(x in name_norm for x in ['бланш', 'blanch']):
        return 'blanched'
    if any(x in name_norm for x in ['с/м', 'зам', 'сыромор', 'raw']):
        return 'raw_frozen'
    return 'raw_frozen'


def extract_shrimp_form(name_norm: str) -> Optional[str]:
    """Форма креветок."""
    forms = []
    if any(x in name_norm for x in ['очищ', 'peeled', 'о/м']):
        forms.append('peeled')
    else:
        forms.append('shell_on')
    if any(x in name_norm for x in ['б/г', 'без голов', 'headless']):
        forms.append('headless')
    elif any(x in name_norm for x in ['с/г', 'с голов']):
        forms.append('head_on')
    else:
        forms.append('headless')
    if any(x in name_norm for x in ['с хвост', 'хвостик', 'tail']):
        forms.append('tail_on')
    return '_'.join(forms) if forms else None


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
    """Извлекает полную NPC сигнатуру v10."""
    sig = NPCSignature()
    
    name_raw = item.get('name_raw', item.get('name', ''))
    name_norm = name_raw.lower()
    
    sig.name_raw = name_raw
    sig.name_norm = name_norm
    sig.pack_qty = item.get('pack_qty') or item.get('net_weight_kg')
    
    # v10: Brand & Country from item
    sig.brand_id = item.get('brand_id')
    sig.brand_name = item.get('brand_name') or extract_brand_from_name(name_norm)
    sig.origin_country = item.get('origin_country') or extract_origin_country(name_norm)
    
    patterns = get_exclusion_patterns()
    
    # HARD EXCLUSIONS
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
    """Определяет NPC домен."""
    # SHRIMP
    if any(x in name_norm for x in ['кревет', 'shrimp', 'prawn', 'ваннам', 'лангустин']):
        if 'со вкусом' in name_norm or 'вкус кревет' in name_norm:
            return None
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
# NPC STRICT MATCHING v10
# ============================================================================

def check_npc_strict(source: NPCSignature, candidate: NPCSignature) -> NPCMatchResult:
    """
    Строгая проверка NPC v10.
    
    HARD GATES (все должны совпадать):
    1. processing_form
    2. cut_type
    3. species
    4. is_box (в обе стороны)
    5. brand (если у source есть)
    6. 85% similarity (если бренда нет)
    7. SHRIMP: state/form/caliber
    """
    result = NPCMatchResult()
    
    # === EXCLUSIONS ===
    if source.is_excluded:
        result.block_reason = f"SOURCE_EXCLUDED:{source.exclude_reason}"
        return result
    if candidate.is_excluded:
        result.block_reason = f"CANDIDATE_EXCLUDED:{candidate.exclude_reason}"
        return result
    
    # === DOMAIN ===
    if source.npc_domain != candidate.npc_domain:
        result.block_reason = f"DOMAIN_MISMATCH:{source.npc_domain}!={candidate.npc_domain}"
        return result
    result.same_domain = True
    
    # === NPC NODE ===
    if source.npc_node_id and not candidate.npc_node_id:
        result.block_reason = "CANDIDATE_NO_NPC_NODE"
        return result
    
    # === 1. PROCESSING_FORM (1-в-1) ===
    if source.processing_form and candidate.processing_form:
        if source.processing_form != candidate.processing_form:
            result.block_reason = f"PROCESSING_FORM_MISMATCH:{source.processing_form.value}!={candidate.processing_form.value}"
            return result
        result.same_processing_form = True
    
    # === 2. CUT_TYPE (1-в-1) ===
    if source.cut_type:
        if candidate.cut_type and source.cut_type != candidate.cut_type:
            result.block_reason = f"CUT_TYPE_MISMATCH:{source.cut_type.value}!={candidate.cut_type.value}"
            return result
        if not candidate.cut_type:
            result.block_reason = f"CUT_TYPE_MISSING:source={source.cut_type.value}"
            return result
        result.same_cut_type = True
    
    # === 3. SPECIES (1-в-1) ===
    if source.species:
        if candidate.species and source.species != candidate.species:
            result.block_reason = f"SPECIES_MISMATCH:{source.species}!={candidate.species}"
            return result
        if not candidate.species:
            result.block_reason = f"SPECIES_MISSING:source={source.species}"
            return result
        result.same_species = True
    
    # === 4. IS_BOX (в обе стороны) ===
    if source.is_box != candidate.is_box:
        if source.is_box and not candidate.is_box:
            result.block_reason = "IS_BOX_MISMATCH:ref_is_box_but_candidate_not"
        else:
            result.block_reason = "IS_BOX_MISMATCH:candidate_is_box"
        return result
    
    # === 5. BRAND GATE ===
    if source.brand_id:
        # Если у REF есть brand → только тот же бренд
        if candidate.brand_id and source.brand_id != candidate.brand_id:
            result.block_reason = f"BRAND_MISMATCH:{source.brand_id}!={candidate.brand_id}"
            return result
        if not candidate.brand_id and source.brand_name:
            # Пробуем сравнить по brand_name
            if candidate.brand_name and source.brand_name.lower() != candidate.brand_name.lower():
                result.block_reason = f"BRAND_NAME_MISMATCH:{source.brand_name}!={candidate.brand_name}"
                return result
        result.same_brand = True
    
    # === 6. SHRIMP RULES (перед 85% guard) ===
    if source.npc_domain == 'SHRIMP':
        # STATE
        if source.shrimp_state and candidate.shrimp_state:
            if source.shrimp_state != candidate.shrimp_state:
                result.block_reason = f"SHRIMP_STATE_MISMATCH:{source.shrimp_state}!={candidate.shrimp_state}"
                return result
        # FORM
        if source.shrimp_form and candidate.shrimp_form:
            if source.shrimp_form != candidate.shrimp_form:
                result.block_reason = f"SHRIMP_FORM_MISMATCH:{source.shrimp_form}!={candidate.shrimp_form}"
                return result
        # CALIBER
        if source.shrimp_caliber:
            if not candidate.shrimp_caliber:
                result.block_reason = f"SHRIMP_CALIBER_MISSING:source={source.shrimp_caliber}"
                return result
            if source.shrimp_caliber != candidate.shrimp_caliber:
                result.block_reason = f"SHRIMP_CALIBER_MISMATCH:{source.shrimp_caliber}!={candidate.shrimp_caliber}"
                return result
            result.same_caliber = True
    
    # === 7. FISH SIZE RANGE (±20% tolerance, перед 85% guard) ===
    if source.npc_domain == 'FISH':
        if source.size_gram_min and source.size_gram_max:
            if source.size_gram_min != source.size_gram_max:  # Real range
                if candidate.size_gram_min and candidate.size_gram_max:
                    if candidate.size_gram_min != candidate.size_gram_max:
                        src_mid = (source.size_gram_min + source.size_gram_max) / 2
                        cand_mid = (candidate.size_gram_min + candidate.size_gram_max) / 2
                        diff_pct = abs(src_mid - cand_mid) / src_mid
                        if diff_pct > 0.20:  # ±20% tolerance
                            result.block_reason = f"SIZE_MISMATCH:{source.size_gram_min}-{source.size_gram_max}!={candidate.size_gram_min}-{candidate.size_gram_max}"
                            return result
                        result.same_size_range = True
    
    # === 8. 85% GUARD (только если нет бренда и hard-gates пройдены) ===
    if not source.brand_id:
        similarity = calculate_similarity(source.semantic_tokens, candidate.semantic_tokens)
        result.similarity_score = similarity
        if similarity < SIMILARITY_THRESHOLD:
            result.block_reason = f"SIMILARITY_TOO_LOW:{similarity:.2f}<{SIMILARITY_THRESHOLD}"
            return result
    
    # === PASSED STRICT ===
    result.passed_strict = True
    result.passed_similar = True
    
    # === COUNTRY CHECK (for ranking) ===
    if source.origin_country and candidate.origin_country:
        result.same_country = source.origin_country == candidate.origin_country
    
    # === SCORING ===
    score = 100
    if result.same_processing_form:
        score += 30
    if result.same_cut_type:
        score += 25
    if result.same_species:
        score += 20
    if result.same_caliber:
        score += 20
    if result.same_size_range:
        score += 15
    if result.same_brand:
        score += 50  # Brand bonus
    
    # Size/caliber proximity
    if source.npc_domain == 'SHRIMP' and source.shrimp_caliber_min and candidate.shrimp_caliber_min:
        result.size_score = 100
    elif source.npc_domain == 'FISH' and source.size_gram_min and candidate.size_gram_min:
        src_mid = (source.size_gram_min + source.size_gram_max) / 2
        cand_mid = (candidate.size_gram_min + candidate.size_gram_max) / 2
        diff_pct = abs(src_mid - cand_mid) / src_mid if src_mid else 0
        result.size_score = int(100 * (1 - diff_pct))
    
    # Country score
    if result.same_country:
        result.country_score = 50
    
    # Brand score
    if result.same_brand:
        result.brand_score = 50
    
    result.npc_score = score + result.size_score + result.country_score + result.brand_score
    
    return result


def check_npc_similar(source: NPCSignature, candidate: NPCSignature) -> NPCMatchResult:
    """Мягкая проверка для Similar режима."""
    result = NPCMatchResult()
    
    if source.is_excluded or candidate.is_excluded:
        result.block_reason = "EXCLUDED"
        return result
    
    if source.npc_domain != candidate.npc_domain:
        result.block_reason = "DOMAIN_MISMATCH"
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
    Применяет NPC фильтрацию v10.
    
    mode='strict': только точные аналоги, Similar=[]
    mode='similar': Strict + Similar с лейблами
    """
    source_sig = extract_npc_signature(source_item)
    
    if source_sig.is_excluded:
        return [], [], {'SOURCE_EXCLUDED': 1}
    
    if not source_sig.npc_domain:
        return None, None, None  # Fallback to legacy
    
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
                    })
    
    # RANKING: size_score → country_score → brand_score → npc_score
    def sort_key(x):
        r = x['npc_result']
        return (-r.size_score, -r.country_score, -r.brand_score, -r.npc_score)
    
    strict_results.sort(key=sort_key)
    strict_results = strict_results[:limit]
    
    if mode == 'similar':
        similar_results.sort(key=lambda x: (-x['npc_result'].country_score, -x['npc_result'].npc_score))
        similar_results = similar_results[:limit]
    else:
        similar_results = []
    
    return strict_results, similar_results, rejected_reasons


def explain_npc_match(source_name: str, candidate_name: str) -> Dict:
    """Объясняет решение NPC matching."""
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
        },
        'strict_result': {
            'passed': strict.passed_strict,
            'block_reason': strict.block_reason,
            'npc_score': strict.npc_score,
            'similarity_score': strict.similarity_score,
        },
        'similar_result': {
            'passed': similar.passed_similar,
            'difference_labels': similar.difference_labels,
        }
    }
