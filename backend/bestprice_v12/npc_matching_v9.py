"""
BestPrice v12 - NPC Matching Module v9.1
========================================

"Нулевой мусор" в matching для SHRIMP/FISH/SEAFOOD/MEAT/CANNED

АРХИТЕКТУРА:
1. NPC-layer применяется поверх matching_engine_v3 (topK=200)
2. Strict по умолчанию — только точные аналоги
3. Similar — только по явному запросу (mode=similar)
4. Если Strict пуст → возвращаем пустой список

HARD-ПРАВИЛА (Strict 1-в-1):
- PROCESSING_FORM: CANNED, SMOKED, FROZEN_RAW, CHILLED_RAW, READY_SEMIFINISHED
- CUT_TYPE: WHOLE_TUSHKA, FILLET, STEAK, MINCED (рыба/мясо)
- SPECIES: строгое совпадение вида
- SHRIMP: species/state/form/caliber строго 1-в-1
- IS_BOX: короб исключается если REF не короб

РАНЖИРОВАНИЕ:
1. Близость размера/калибра
2. Совпадение бренда
3. ppu_value
4. min_line_total

Version: 9.1 ("Нулевой мусор")
Date: January 2026
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from pathlib import Path
from enum import Enum

import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# ENUMS FOR PROCESSING & CUT TYPES
# ============================================================================

class ProcessingForm(str, Enum):
    """Тип обработки продукта"""
    CANNED = "CANNED"                    # ж/б, ст/б, консервы, в масле
    SMOKED = "SMOKED"                    # х/к, г/к, копчёное
    FROZEN_RAW = "FROZEN_RAW"            # с/м, замороженное сырьё
    CHILLED_RAW = "CHILLED_RAW"          # охл, охлаждённое
    READY_SEMIFINISHED = "READY_SEMIFINISHED"  # п/ф, гёдза, котлеты, панировка
    SALTED_CURED = "SALTED_CURED"        # солёное, пресервы, малосол
    SAUCE_MIX_OTHER = "SAUCE_MIX_OTHER"  # соусы, пасты, специи (не NPC)
    RAW_UNSPECIFIED = "RAW_UNSPECIFIED"  # сырьё без указания состояния


class CutType(str, Enum):
    """Тип разделки"""
    # Рыба
    WHOLE_TUSHKA = "WHOLE_TUSHKA"    # тушка, целая, н/р, потрошёная
    FILLET = "FILLET"                # филе
    STEAK_PORTION = "STEAK_PORTION"  # стейк, кусок, порция
    MINCED = "MINCED"                # фарш
    LIVER = "LIVER"                  # печень (трески и т.д.)
    
    # Мясо/птица
    BREAST = "BREAST"       # грудка
    THIGH = "THIGH"         # бедро, окорочок
    WING = "WING"           # крыло
    DRUMSTICK = "DRUMSTICK" # голень
    TENDERLOIN = "TENDERLOIN"  # вырезка
    RIB = "RIB"             # рёбра
    SAUSAGE = "SAUSAGE"     # колбаса, сосиски


# ============================================================================
# NPC DATA LOADING (Singleton)
# ============================================================================

_NPC_SCHEMA: Dict[str, pd.DataFrame] = {}
_NPC_LEXICON: Dict = {}
_NPC_SAMPLES: Dict[str, pd.DataFrame] = {}
_NPC_OUT_OF_SCOPE: pd.DataFrame = None
_NPC_LOADED = False

NPC_SCHEMA_PATH = Path(__file__).parent / "npc_schema_v9.xlsx"
NPC_LEXICON_PATH = Path(__file__).parent / "lexicon_npc_v9.json"


def load_npc_data():
    """Загружает NPC схему и лексикон один раз."""
    global _NPC_SCHEMA, _NPC_LEXICON, _NPC_SAMPLES, _NPC_OUT_OF_SCOPE, _NPC_LOADED
    
    if _NPC_LOADED:
        return
    
    try:
        if NPC_SCHEMA_PATH.exists():
            xls = pd.ExcelFile(NPC_SCHEMA_PATH)
            for sheet in xls.sheet_names:
                if sheet.startswith('NPC_nodes_'):
                    domain = sheet.replace('NPC_nodes_', '').replace('_top50', '').replace('_top80', '')
                    _NPC_SCHEMA[domain] = pd.read_excel(xls, sheet)
                elif sheet.startswith('Samples_'):
                    domain = sheet.replace('Samples_', '').replace('_200', '')
                    _NPC_SAMPLES[domain] = pd.read_excel(xls, sheet)
                elif sheet == 'OUT_OF_SCOPE':
                    _NPC_OUT_OF_SCOPE = pd.read_excel(xls, sheet)
        
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

NPC_DOMAINS = {'SHRIMP', 'FISH', 'SEAFOOD', 'MEAT', 'CANNED'}

# Size tolerance for ranking (not filtering)
SIZE_TOLERANCE_PCT = 0.15  # 15% for size ranking bonus


# ============================================================================
# EXCLUSION PATTERNS
# ============================================================================

_EXCLUSION_PATTERNS: Dict[str, re.Pattern] = {}


def compile_exclusion_patterns() -> Dict[str, re.Pattern]:
    """Компилирует regex паттерны исключений."""
    lexicon = get_npc_lexicon()
    patterns = {}
    
    oos = lexicon.get('out_of_scope_patterns', {})
    for category, pattern_list in oos.items():
        combined = '|'.join(f'({p})' for p in pattern_list)
        try:
            patterns[f'oos_{category}'] = re.compile(combined, re.IGNORECASE)
        except re.error:
            pass
    
    rules = lexicon.get('npc', {}).get('rules', {})
    for rule_name, pattern in rules.items():
        if pattern and isinstance(pattern, str) and not pattern.startswith('token'):
            try:
                patterns[rule_name] = re.compile(pattern, re.IGNORECASE)
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
    """NPC сигнатура товара v9.1"""
    name_raw: str = ""
    name_norm: str = ""
    
    # NPC классификация
    npc_domain: Optional[str] = None
    npc_node_id: Optional[str] = None
    
    # === НОВЫЕ ГЛОБАЛЬНЫЕ АТРИБУТЫ ===
    processing_form: Optional[ProcessingForm] = None  # CANNED, SMOKED, FROZEN_RAW, etc.
    cut_type: Optional[CutType] = None               # FILLET, WHOLE_TUSHKA, etc.
    species: Optional[str] = None                    # окунь, скумбрия, говядина, etc.
    is_box: bool = False                             # короб/ящик/кор.
    
    # Размер/граммовка (для рыбы)
    size_gram_min: Optional[int] = None   # 255г → 255
    size_gram_max: Optional[int] = None   # 311г → 311
    size_oz_min: Optional[float] = None   # 9oz
    size_oz_max: Optional[float] = None   # 11oz
    
    # === КРЕВЕТКИ ===
    shrimp_species: Optional[str] = None
    shrimp_caliber: Optional[str] = None       # "16/20", "31/40"
    shrimp_caliber_min: Optional[int] = None   # 16
    shrimp_caliber_max: Optional[int] = None   # 20
    shrimp_state: Optional[str] = None         # raw_frozen, cooked_frozen, blanched
    shrimp_form: Optional[str] = None          # peeled, shell_on, headless, head_on, tail_on
    
    # === РЫБА ===
    fish_species: Optional[str] = None
    fish_cut: Optional[CutType] = None
    fish_skin: Optional[str] = None  # skin_on, skin_off
    
    # === МОРЕПРОДУКТЫ ===
    seafood_type: Optional[str] = None
    
    # === МЯСО ===
    meat_animal: Optional[str] = None
    meat_cut: Optional[CutType] = None
    
    # === ОБЩИЕ ===
    state_frozen: bool = False
    state_chilled: bool = False
    is_smoked: bool = False
    is_salted: bool = False
    
    # Исключения
    is_excluded: bool = False
    exclude_reason: Optional[str] = None
    
    # Фасовка
    pack_qty: Optional[float] = None
    pack_unit: Optional[str] = None  # kg, g, pcs


@dataclass
class NPCMatchResult:
    """Результат NPC matching"""
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
    
    # Scoring
    npc_score: int = 0
    size_score: int = 0
    
    # Лейблы
    difference_labels: List[str] = field(default_factory=list)


# ============================================================================
# ATTRIBUTE EXTRACTION
# ============================================================================

def extract_processing_form(name_norm: str) -> Optional[ProcessingForm]:
    """Определяет тип обработки продукта."""
    
    # CANNED - приоритет высший (консервы)
    if any(x in name_norm for x in ['ж/б', 'ст/б', 'консерв', 'в масле', 'в собств', 
                                      'в томат', 'банка', 'ключ', 'жб ', ' жб']):
        return ProcessingForm.CANNED
    
    # SMOKED - используем regex для более точного match
    # Исключаем ложные срабатывания типа "кг/кор" → "г/к"
    smoked_patterns = [
        r'\bх/к\b', r'\bг/к\b', r'копч', r'холодн\.?коп', r'горяч\.?коп',
        r'холодного\s+копчен', r'горячего\s+копчен'
    ]
    for pattern in smoked_patterns:
        if re.search(pattern, name_norm, re.IGNORECASE):
            return ProcessingForm.SMOKED
    
    # SALTED/CURED
    if any(x in name_norm for x in ['пресерв', 'солён', 'солен', 'посол', 'малосол', 
                                      'слабосол', 'с/с', 'сол.']):
        return ProcessingForm.SALTED_CURED
    
    # READY_SEMIFINISHED (полуфабрикаты)
    if any(x in name_norm for x in ['п/ф', 'гёдза', 'гедза', 'пельмен', 'котлет', 
                                      'наггетс', 'панир', 'темпур', 'кляр', 'фрикадел',
                                      'шницел', 'бургер', 'стрипс']):
        return ProcessingForm.READY_SEMIFINISHED
    
    # SAUCE_MIX_OTHER
    if any(x in name_norm for x in ['соус', 'паста', 'маринад', 'специ', 'приправ',
                                      'чука', 'нори', 'водоросл', 'лапша']):
        return ProcessingForm.SAUCE_MIX_OTHER
    
    # CHILLED_RAW
    if any(x in name_norm for x in ['охл', 'охлажд', 'свеж', 'с/г']):
        return ProcessingForm.CHILLED_RAW
    
    # FROZEN_RAW
    if any(x in name_norm for x in ['с/м', 'зам', 'замор', 'мороз', 'frozen', 'свежеморож']):
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
                                          'непотрош', 'б/г', 'с/г']):
            return CutType.WHOLE_TUSHKA
        if any(x in name_norm for x in ['стейк', 'steak', 'кусок', 'порц']):
            return CutType.STEAK_PORTION
        if any(x in name_norm for x in ['печень']):
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
        if any(x in name_norm for x in ['колбас', 'сосиск', 'сардельк', 'sausage']):
            return CutType.SAUSAGE
        if any(x in name_norm for x in ['стейк', 'steak']):
            return CutType.STEAK_PORTION
    
    return None


def extract_species(name_norm: str, domain: str) -> Optional[str]:
    """Извлекает вид продукта."""
    
    if domain == 'FISH':
        species_map = {
            'salmon': ['лосось', 'лосос', 'salmon', 'сёмга', 'семга', 'сёмги', 'семги'],
            'trout': ['форель', 'форели', 'trout'],
            'cod': ['треска', 'трески', 'трескова', 'cod'],
            'tuna': ['тунец', 'тунца', 'tuna'],
            'halibut': ['палтус', 'палтуса', 'halibut'],
            'pollock': ['минтай', 'минтая', 'pollock'],
            'mackerel': ['скумбри', 'mackerel'],
            'herring': ['сельд', 'сельди', 'herring'],
            'seabass': ['сибас', 'seabass'],
            'dorado': ['дорад', 'dorado'],
            'tilapia': ['тилапи', 'tilapia'],
            'perch': ['окун', 'окуня', 'perch'],
            'pike': ['щук', 'pike'],
            'pangasius': ['пангасиус', 'pangasius'],
            'sturgeon': ['осетр', 'осетра', 'sturgeon'],
        }
        for species, tokens in species_map.items():
            for token in tokens:
                if token in name_norm:
                    return species
    
    elif domain == 'MEAT':
        animal_map = {
            'beef': ['говядин', 'beef', 'телятин', 'veal', 'рибай', 'ribeye'],
            'pork': ['свинин', 'pork', 'свиной', 'свиная'],
            'chicken': ['курин', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер'],
            'turkey': ['индейк', 'turkey', 'индюш'],
            'lamb': ['баранин', 'lamb', 'ягнят', 'ягненок'],
            'duck': ['утк', 'duck', 'утин'],
        }
        for animal, tokens in animal_map.items():
            for token in tokens:
                if token in name_norm:
                    return animal
    
    elif domain == 'SHRIMP':
        shrimp_map = {
            'vannamei': ['ваннам', 'vannamei', 'белоног'],
            'tiger': ['тигр', 'tiger'],
            'argentine': ['аргент'],
            'north': ['северн', 'ботан'],
            'king': ['королев', 'king'],
        }
        for species, tokens in shrimp_map.items():
            for token in tokens:
                if token in name_norm:
                    return species
        return 'unspecified'
    
    elif domain == 'SEAFOOD':
        seafood_map = {
            'mussels': ['мидии', 'мидия', 'mussel'],
            'squid': ['кальмар', 'squid'],
            'octopus': ['осьминог', 'octopus'],
            'scallop': ['гребешок', 'scallop'],
            'crab': ['краб', 'crab'],
            'lobster': ['лобстер', 'омар', 'lobster'],
        }
        for seafood_type, tokens in seafood_map.items():
            for token in tokens:
                if token in name_norm:
                    return seafood_type
    
    return None


def extract_is_box(name_norm: str) -> bool:
    """Определяет, является ли товар коробом/ящиком."""
    box_patterns = [
        r'\bкор\.?\b', r'\bкороб', r'\bящик', r'\bbox\b',
        r'\b10\s*кг\b', r'\b20\s*кг\b', r'\b5\s*кг\b.*кор',
        r'кг/кор', r'кг\s*/\s*кор',
    ]
    for pattern in box_patterns:
        if re.search(pattern, name_norm, re.IGNORECASE):
            return True
    return False


def extract_size_grams(name_norm: str) -> Tuple[Optional[int], Optional[int]]:
    """Извлекает диапазон размера в граммах (для рыбы)."""
    
    # Паттерн: 255-311г, 150-300г
    match = re.search(r'(\d{2,4})\s*[-–]\s*(\d{2,4})\s*г', name_norm)
    if match:
        return int(match.group(1)), int(match.group(2))
    
    # Паттерн: 9-11oz
    match = re.search(r'(\d+)\s*[-–]\s*(\d+)\s*oz', name_norm, re.IGNORECASE)
    if match:
        # Конвертируем oz в граммы (1 oz ≈ 28.35г)
        return int(float(match.group(1)) * 28.35), int(float(match.group(2)) * 28.35)
    
    # Единичный размер: 150г
    match = re.search(r'(\d{2,4})\s*г(?!р)', name_norm)
    if match:
        size = int(match.group(1))
        if 50 <= size <= 2000:  # Разумный диапазон для рыбы
            return size, size
    
    return None, None


def extract_shrimp_caliber(name_norm: str) -> Tuple[Optional[str], Optional[int], Optional[int]]:
    """Извлекает калибр креветок."""
    
    # Паттерн: 16/20, 21/25, 31/40, 200/300
    match = re.search(r'(\d{1,3})\s*[/\-]\s*(\d{1,3})', name_norm)
    if match:
        min_cal = int(match.group(1))
        max_cal = int(match.group(2))
        caliber_str = f"{min_cal}/{max_cal}"
        return caliber_str, min_cal, max_cal
    
    return None, None, None


def extract_shrimp_state(name_norm: str) -> Optional[str]:
    """Определяет состояние креветок."""
    
    if any(x in name_norm for x in ['варён', 'варен', 'в/м', 'cooked']):
        return 'cooked_frozen'
    if any(x in name_norm for x in ['бланш', 'blanch']):
        return 'blanched'
    if any(x in name_norm for x in ['с/м', 'зам', 'сыромор', 'raw']):
        return 'raw_frozen'
    
    return 'raw_frozen'  # По умолчанию для с/м


def extract_shrimp_form(name_norm: str) -> Optional[str]:
    """Определяет форму креветок."""
    
    forms = []
    
    # Очищенные vs неочищенные
    if any(x in name_norm for x in ['очищ', 'peeled', 'о/м']):
        forms.append('peeled')
    else:
        forms.append('shell_on')
    
    # Голова
    if any(x in name_norm for x in ['б/г', 'без голов', 'headless']):
        forms.append('headless')
    elif any(x in name_norm for x in ['с/г', 'с голов', 'head-on']):
        forms.append('head_on')
    else:
        forms.append('headless')  # По умолчанию б/г
    
    # Хвост
    if any(x in name_norm for x in ['с хвост', 'хвостик', 'tail']):
        forms.append('tail_on')
    
    return '_'.join(forms) if forms else None


# ============================================================================
# MAIN SIGNATURE EXTRACTION
# ============================================================================

def extract_npc_signature(item: Dict) -> NPCSignature:
    """Извлекает полную NPC сигнатуру товара."""
    sig = NPCSignature()
    
    name_raw = item.get('name_raw', item.get('name', ''))
    name_norm = name_raw.lower()
    
    sig.name_raw = name_raw
    sig.name_norm = name_norm
    sig.pack_qty = item.get('pack_qty') or item.get('net_weight_kg')
    
    patterns = get_exclusion_patterns()
    
    # === HARD EXCLUSIONS ===
    for pattern_name, pattern in patterns.items():
        if pattern_name.startswith('oos_'):
            if pattern.search(name_norm):
                sig.is_excluded = True
                sig.exclude_reason = pattern_name
                return sig
    
    # === PROCESSING FORM ===
    sig.processing_form = extract_processing_form(name_norm)
    
    # Исключаем SAUCE_MIX_OTHER и READY_SEMIFINISHED из NPC matching
    if sig.processing_form == ProcessingForm.SAUCE_MIX_OTHER:
        sig.is_excluded = True
        sig.exclude_reason = 'SAUCE_MIX_OTHER'
        return sig
    
    if sig.processing_form == ProcessingForm.READY_SEMIFINISHED:
        sig.is_excluded = True
        sig.exclude_reason = 'READY_SEMIFINISHED'
        return sig
    
    # === DOMAIN DETECTION ===
    sig.npc_domain = _detect_npc_domain(name_norm, patterns)
    
    if not sig.npc_domain:
        return sig
    
    # === IS_BOX ===
    sig.is_box = extract_is_box(name_norm)
    
    # === CUT TYPE ===
    sig.cut_type = extract_cut_type(name_norm, sig.npc_domain)
    
    # === SPECIES ===
    sig.species = extract_species(name_norm, sig.npc_domain)
    
    # === DOMAIN-SPECIFIC ATTRIBUTES ===
    if sig.npc_domain == 'SHRIMP':
        sig.shrimp_species = sig.species
        sig.shrimp_caliber, sig.shrimp_caliber_min, sig.shrimp_caliber_max = extract_shrimp_caliber(name_norm)
        sig.shrimp_state = extract_shrimp_state(name_norm)
        sig.shrimp_form = extract_shrimp_form(name_norm)
    
    elif sig.npc_domain == 'FISH':
        sig.fish_species = sig.species
        sig.fish_cut = sig.cut_type
        # Skin
        if any(x in name_norm for x in ['без кож', 'б/к', 'skinless', 'н/к']):
            sig.fish_skin = 'skin_off'
        elif any(x in name_norm for x in ['на коже', 'с кож', 'skin on']):
            sig.fish_skin = 'skin_on'
        # Size
        sig.size_gram_min, sig.size_gram_max = extract_size_grams(name_norm)
    
    elif sig.npc_domain == 'SEAFOOD':
        sig.seafood_type = sig.species
    
    elif sig.npc_domain == 'MEAT':
        sig.meat_animal = sig.species
        sig.meat_cut = sig.cut_type
    
    # === COMMON ATTRIBUTES ===
    sig.state_frozen = any(x in name_norm for x in ['с/м', 'зам', 'мороз', 'frozen'])
    sig.state_chilled = any(x in name_norm for x in ['охл', 'охлажд', 'chilled', 'свеж'])
    sig.is_smoked = any(x in name_norm for x in ['копч', 'х/к', 'г/к', 'smoked'])
    sig.is_salted = any(x in name_norm for x in ['солен', 'солён', 'посол', 'пресерв'])
    
    # === NPC NODE ID ===
    sig.npc_node_id = _lookup_npc_node_id(sig)
    
    return sig


def _detect_npc_domain(name_norm: str, patterns: Dict) -> Optional[str]:
    """Определяет NPC домен."""
    
    # SHRIMP
    shrimp_tokens = ['кревет', 'shrimp', 'prawn', 'ваннам', 'лангустин']
    for token in shrimp_tokens:
        if token in name_norm:
            if 'со вкусом' in name_norm or 'вкус кревет' in name_norm:
                return None
            return 'SHRIMP'
    
    # SEAFOOD (не рыба)
    seafood_tokens = ['мидии', 'мидия', 'mussel', 'кальмар', 'squid', 'осьминог', 
                      'octopus', 'гребешок', 'scallop', 'краб', 'crab', 'лобстер', 'омар']
    for token in seafood_tokens:
        if token in name_norm:
            if 'крабов' in name_norm and 'палоч' in name_norm:
                return None  # Крабовые палочки
            if 'сурими' in name_norm:
                return None
            return 'SEAFOOD'
    
    # FISH
    fish_tokens = ['лосось', 'лосос', 'salmon', 'сёмга', 'семга', 'форель', 'trout',
                   'треска', 'трески', 'cod', 'тунец', 'tuna', 'палтус', 'halibut',
                   'минтай', 'pollock', 'скумбри', 'mackerel', 'сельд', 'herring',
                   'окун', 'perch', 'сибас', 'seabass', 'дорад', 'dorado',
                   'тилапи', 'tilapia', 'пангасиус', 'горбуш', 'кижуч', 'нерк']
    
    # Исключаем ribeye как рыбу
    if 'рибай' in name_norm or 'ribeye' in name_norm:
        pass  # Это мясо
    else:
        for token in fish_tokens:
            if token in name_norm:
                return 'FISH'
    
    # MEAT
    meat_tokens = ['говядин', 'beef', 'телятин', 'свинин', 'pork', 'баранин', 'lamb',
                   'курин', 'курица', 'куриц', 'chicken', 'цыпл', 'индейк', 'turkey',
                   'утк', 'duck', 'рибай', 'ribeye', 'колбас', 'сосиск', 'ветчин']
    for token in meat_tokens:
        if token in name_norm:
            return 'MEAT'
    
    return None


def _lookup_npc_node_id(sig: NPCSignature) -> Optional[str]:
    """Ищет npc_node_id по атрибутам."""
    if not sig.npc_domain:
        return None
    
    schema = get_npc_schema(sig.npc_domain)
    if schema is None or schema.empty:
        return None
    
    try:
        if sig.npc_domain == 'SHRIMP':
            for _, row in schema.iterrows():
                schema_variant = str(row.get('shrimp_variant', ''))
                if sig.shrimp_species and sig.shrimp_species in schema_variant:
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
                meat_variant = str(row.get('meat_variant', ''))
                if sig.meat_animal and sig.meat_animal in meat_variant:
                    return row.get('node_id')
    
    except Exception as e:
        logger.warning(f"Error looking up NPC node: {e}")
    
    return None


# ============================================================================
# NPC STRICT MATCHING (v9.1 - "Нулевой мусор")
# ============================================================================

def check_npc_strict(source: NPCSignature, candidate: NPCSignature) -> NPCMatchResult:
    """
    Строгая проверка NPC v9.1 — "Нулевой мусор"
    
    HARD-правила (все должны совпадать 1-в-1):
    1. processing_form
    2. cut_type (если распознано)
    3. species (если распознано)
    4. is_box (короб при некоробе исключается)
    5. Креветки: state/form/caliber
    """
    result = NPCMatchResult()
    
    # === HARD EXCLUSIONS ===
    if source.is_excluded:
        result.block_reason = f"SOURCE_EXCLUDED:{source.exclude_reason}"
        return result
    
    if candidate.is_excluded:
        result.block_reason = f"CANDIDATE_EXCLUDED:{candidate.exclude_reason}"
        return result
    
    # === DOMAIN CHECK ===
    if source.npc_domain != candidate.npc_domain:
        result.block_reason = f"DOMAIN_MISMATCH:{source.npc_domain}!={candidate.npc_domain}"
        return result
    result.same_domain = True
    
    # === NPC NODE CHECK ===
    if source.npc_node_id:
        if not candidate.npc_node_id:
            result.block_reason = "CANDIDATE_NO_NPC_NODE"
            return result
    
    # === 1. PROCESSING_FORM (STRICT 1-в-1) ===
    if source.processing_form and candidate.processing_form:
        if source.processing_form != candidate.processing_form:
            result.block_reason = f"PROCESSING_FORM_MISMATCH:{source.processing_form.value}!={candidate.processing_form.value}"
            return result
        result.same_processing_form = True
    
    # === 2. CUT_TYPE (STRICT 1-в-1 если распознано) ===
    if source.cut_type:
        if candidate.cut_type and source.cut_type != candidate.cut_type:
            result.block_reason = f"CUT_TYPE_MISMATCH:{source.cut_type.value}!={candidate.cut_type.value}"
            return result
        if not candidate.cut_type:
            # Кандидат без cut_type когда у source есть — блокируем
            result.block_reason = f"CUT_TYPE_MISSING:source={source.cut_type.value}"
            return result
        result.same_cut_type = True
    
    # === 3. SPECIES (STRICT 1-в-1 если распознано) ===
    if source.species:
        if candidate.species and source.species != candidate.species:
            result.block_reason = f"SPECIES_MISMATCH:{source.species}!={candidate.species}"
            return result
        if not candidate.species:
            result.block_reason = f"SPECIES_MISSING:source={source.species}"
            return result
        result.same_species = True
    
    # === 4. IS_BOX (короб при некоробе исключается) ===
    if not source.is_box and candidate.is_box:
        result.block_reason = "IS_BOX_MISMATCH:candidate_is_box"
        return result
    
    # === 5. SHRIMP-SPECIFIC RULES ===
    if source.npc_domain == 'SHRIMP':
        # STATE (сырые ≠ варёные)
        if source.shrimp_state and candidate.shrimp_state:
            if source.shrimp_state != candidate.shrimp_state:
                result.block_reason = f"SHRIMP_STATE_MISMATCH:{source.shrimp_state}!={candidate.shrimp_state}"
                return result
        
        # FORM (очищ ≠ неочищ, headless ≠ head_on)
        if source.shrimp_form and candidate.shrimp_form:
            if source.shrimp_form != candidate.shrimp_form:
                result.block_reason = f"SHRIMP_FORM_MISMATCH:{source.shrimp_form}!={candidate.shrimp_form}"
                return result
        
        # CALIBER (STRICT 1-в-1)
        if source.shrimp_caliber:
            if not candidate.shrimp_caliber:
                result.block_reason = f"SHRIMP_CALIBER_MISSING:source={source.shrimp_caliber}"
                return result
            if source.shrimp_caliber != candidate.shrimp_caliber:
                result.block_reason = f"SHRIMP_CALIBER_MISMATCH:{source.shrimp_caliber}!={candidate.shrimp_caliber}"
                return result
            result.same_caliber = True
    
    # === 6. FISH SIZE RANGE ===
    # Size check применяется только для диапазонов (255-311г), а не для единичных размеров
    if source.npc_domain == 'FISH':
        if source.size_gram_min and source.size_gram_max:
            # Только для реальных диапазонов (min != max)
            if source.size_gram_min != source.size_gram_max:
                if candidate.size_gram_min and candidate.size_gram_max:
                    if candidate.size_gram_min != candidate.size_gram_max:
                        # Оба диапазоны — проверяем пересечение
                        src_mid = (source.size_gram_min + source.size_gram_max) / 2
                        cand_mid = (candidate.size_gram_min + candidate.size_gram_max) / 2
                        diff_pct = abs(src_mid - cand_mid) / src_mid
                        
                        if diff_pct > 0.35:  # Больше 35% разницы — блок
                            result.block_reason = f"SIZE_MISMATCH:{source.size_gram_min}-{source.size_gram_max}!={candidate.size_gram_min}-{candidate.size_gram_max}"
                            return result
                        result.same_size_range = True
    
    # === PASSED STRICT ===
    result.passed_strict = True
    result.passed_similar = True
    
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
    
    # Size/caliber proximity bonus
    if source.npc_domain == 'SHRIMP' and source.shrimp_caliber_min and candidate.shrimp_caliber_min:
        # Exact caliber match already checked above
        result.size_score = 100
    elif source.npc_domain == 'FISH' and source.size_gram_min and candidate.size_gram_min:
        src_mid = (source.size_gram_min + source.size_gram_max) / 2
        cand_mid = (candidate.size_gram_min + candidate.size_gram_max) / 2
        diff_pct = abs(src_mid - cand_mid) / src_mid
        result.size_score = int(100 * (1 - diff_pct))
    
    result.npc_score = score + result.size_score
    
    return result


def check_npc_similar(source: NPCSignature, candidate: NPCSignature) -> NPCMatchResult:
    """
    Мягкая проверка NPC для Similar режима (только по кнопке).
    
    Допускает:
    - Соседний калибр (с лейблом)
    - Разную разделку (с лейблом)
    - Разную обработку внутри группы (с лейблом)
    """
    result = NPCMatchResult()
    
    # === HARD EXCLUSIONS ===
    if source.is_excluded or candidate.is_excluded:
        result.block_reason = "EXCLUDED"
        return result
    
    # === DOMAIN CHECK ===
    if source.npc_domain != candidate.npc_domain:
        result.block_reason = "DOMAIN_MISMATCH"
        return result
    result.same_domain = True
    
    # === NPC NODE CHECK ===
    if source.npc_node_id and not candidate.npc_node_id:
        result.block_reason = "CANDIDATE_NO_NPC_NODE"
        return result
    
    # === COLLECT DIFFERENCE LABELS ===
    
    # Processing form
    if source.processing_form and candidate.processing_form:
        if source.processing_form != candidate.processing_form:
            result.difference_labels.append(f"Тип обработки: {candidate.processing_form.value}")
    
    # Cut type
    if source.cut_type and candidate.cut_type:
        if source.cut_type != candidate.cut_type:
            result.difference_labels.append(f"Разделка: {candidate.cut_type.value}")
    
    # Species
    if source.species and candidate.species:
        if source.species != candidate.species:
            result.difference_labels.append(f"Вид: {candidate.species}")
    
    # Caliber (shrimp)
    if source.npc_domain == 'SHRIMP':
        if source.shrimp_caliber and candidate.shrimp_caliber:
            if source.shrimp_caliber != candidate.shrimp_caliber:
                result.difference_labels.append(f"Калибр: {candidate.shrimp_caliber}")
    
    # Size (fish)
    if source.npc_domain == 'FISH':
        if source.size_gram_min and candidate.size_gram_min:
            if source.size_gram_min != candidate.size_gram_min:
                result.difference_labels.append(f"Размер: {candidate.size_gram_min}-{candidate.size_gram_max}г")
    
    # Box
    if candidate.is_box and not source.is_box:
        result.difference_labels.append("Короб/ящик")
    
    result.passed_similar = True
    result.npc_score = 50 - len(result.difference_labels) * 10
    
    return result


# ============================================================================
# MAIN API FUNCTIONS
# ============================================================================

def is_npc_domain_item(item: Dict) -> bool:
    """Проверяет, относится ли товар к NPC домену."""
    sig = extract_npc_signature(item)
    return sig.npc_domain is not None and not sig.is_excluded


def get_item_npc_domain(item: Dict) -> Optional[str]:
    """Возвращает NPC домен товара."""
    sig = extract_npc_signature(item)
    if sig.is_excluded:
        return None
    return sig.npc_domain


def apply_npc_filter(
    source_item: Dict,
    candidates: List[Dict],
    limit: int = 10,
    mode: str = 'strict'  # 'strict' или 'similar'
) -> Tuple[List[Dict], List[Dict], Dict[str, int]]:
    """
    Применяет NPC фильтрацию v9.1 ("Нулевой мусор").
    
    Args:
        source_item: Исходный товар
        candidates: Кандидаты из matching_engine_v3
        limit: Максимум результатов
        mode: 'strict' (по умолчанию) или 'similar' (по кнопке)
    
    Returns:
        (strict_results, similar_results, rejected_reasons)
        
    При mode='strict': similar_results всегда пустой
    При mode='similar': similar_results заполняется
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
        
        # Strict check
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
            
            # Similar только если mode='similar'
            if mode == 'similar':
                similar_result = check_npc_similar(source_sig, cand_sig)
                if similar_result.passed_similar:
                    similar_results.append({
                        'item': cand,
                        'npc_result': similar_result,
                        'npc_signature': cand_sig,
                    })
    
    # РАНЖИРОВАНИЕ: size/caliber first, потом score (который включает ppu)
    def sort_key(x):
        npc_result = x['npc_result']
        return (-npc_result.size_score, -npc_result.npc_score)
    
    strict_results.sort(key=sort_key)
    strict_results = strict_results[:limit]
    
    if mode == 'similar':
        similar_results.sort(key=lambda x: -x['npc_result'].npc_score)
        similar_results = similar_results[:limit]
    else:
        similar_results = []  # Strict mode — без Similar
    
    return strict_results, similar_results, rejected_reasons


def format_npc_result(item: Dict, npc_result: NPCMatchResult, npc_sig: NPCSignature, mode: str) -> Dict:
    """Форматирует результат для API."""
    return {
        'id': item.get('id'),
        'name': item.get('name_raw', ''),
        'name_raw': item.get('name_raw', ''),
        'price': item.get('price', 0),
        'pack_qty': item.get('pack_qty'),
        'unit_type': item.get('unit_type', 'PIECE'),
        'brand_id': item.get('brand_id'),
        'supplier_company_id': item.get('supplier_company_id'),
        'min_order_qty': item.get('min_order_qty', 1),
        
        'npc_domain': npc_sig.npc_domain,
        'npc_node_id': npc_sig.npc_node_id,
        'processing_form': npc_sig.processing_form.value if npc_sig.processing_form else None,
        'cut_type': npc_sig.cut_type.value if npc_sig.cut_type else None,
        'species': npc_sig.species,
        'is_box': npc_sig.is_box,
        
        'npc_score': npc_result.npc_score,
        'size_score': npc_result.size_score,
        'match_mode': mode,
        'difference_labels': npc_result.difference_labels,
    }


def explain_npc_match(source_name: str, candidate_name: str) -> Dict:
    """Объясняет решение NPC matching."""
    source_item = {'name_raw': source_name}
    cand_item = {'name_raw': candidate_name}
    
    source_sig = extract_npc_signature(source_item)
    cand_sig = extract_npc_signature(cand_item)
    
    strict_result = check_npc_strict(source_sig, cand_sig)
    similar_result = check_npc_similar(source_sig, cand_sig)
    
    return {
        'source': {
            'name': source_name,
            'npc_domain': source_sig.npc_domain,
            'processing_form': source_sig.processing_form.value if source_sig.processing_form else None,
            'cut_type': source_sig.cut_type.value if source_sig.cut_type else None,
            'species': source_sig.species,
            'is_box': source_sig.is_box,
            'is_excluded': source_sig.is_excluded,
        },
        'candidate': {
            'name': candidate_name,
            'npc_domain': cand_sig.npc_domain,
            'processing_form': cand_sig.processing_form.value if cand_sig.processing_form else None,
            'cut_type': cand_sig.cut_type.value if cand_sig.cut_type else None,
            'species': cand_sig.species,
            'is_box': cand_sig.is_box,
            'is_excluded': cand_sig.is_excluded,
        },
        'strict_result': {
            'passed': strict_result.passed_strict,
            'block_reason': strict_result.block_reason,
            'npc_score': strict_result.npc_score,
        },
        'similar_result': {
            'passed': similar_result.passed_similar,
            'difference_labels': similar_result.difference_labels,
        }
    }
