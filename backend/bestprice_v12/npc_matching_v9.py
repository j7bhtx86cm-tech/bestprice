"""
BestPrice v12 - NPC Matching Module v9
======================================

NPC-matching как дополнительный слой для сложных категорий:
- SHRIMP (креветки)
- FISH + SEAFOOD (рыба и морепродукты)
- MEAT (мясо и птица)

Для остальных категорий система работает как раньше (legacy через matching_engine_v3).

АРХИТЕКТУРА:
1. Загрузка npc_schema_v9.xlsx → lookup по npc_node_id
2. Загрузка lexicon_npc_v9.json → hard exclusions (гёдза, бульоны, соусы и пр.)
3. В /api/v12/item/{item_id}/alternatives:
   - Получаем candidates из matching_engine_v3 (topK=200)
   - Применяем NPC ТОЛЬКО для категорий MEAT/FISH/SEAFOOD/SHRIMP
   - Split Strict/Similar, фильтры, ранжирование, лейблы

ПРАВИЛА FALLBACK:
- Если REF без npc_node_id → возвращаем legacy результат (NPC skip)
- Если candidate без npc_node_id → запрещаем в Strict, разрешаем в Similar при прохождении guards

Version: 9.0
Date: January 2026
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


# ============================================================================
# NPC DATA LOADING (Singleton pattern)
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
        # Load Excel schema
        if NPC_SCHEMA_PATH.exists():
            xls = pd.ExcelFile(NPC_SCHEMA_PATH)
            
            # Load NPC nodes (lookup tables)
            for sheet in xls.sheet_names:
                if sheet.startswith('NPC_nodes_'):
                    domain = sheet.replace('NPC_nodes_', '').replace('_top50', '').replace('_top80', '')
                    _NPC_SCHEMA[domain] = pd.read_excel(xls, sheet)
                    logger.info(f"Loaded NPC nodes for {domain}: {len(_NPC_SCHEMA[domain])} nodes")
                
                elif sheet.startswith('Samples_'):
                    domain = sheet.replace('Samples_', '').replace('_200', '')
                    _NPC_SAMPLES[domain] = pd.read_excel(xls, sheet)
                    logger.info(f"Loaded NPC samples for {domain}: {len(_NPC_SAMPLES[domain])} samples")
                
                elif sheet == 'OUT_OF_SCOPE':
                    _NPC_OUT_OF_SCOPE = pd.read_excel(xls, sheet)
                    logger.info(f"Loaded OUT_OF_SCOPE: {len(_NPC_OUT_OF_SCOPE)} items")
        else:
            logger.warning(f"NPC schema file not found: {NPC_SCHEMA_PATH}")
        
        # Load lexicon
        if NPC_LEXICON_PATH.exists():
            with open(NPC_LEXICON_PATH, 'r', encoding='utf-8') as f:
                _NPC_LEXICON = json.load(f)
            logger.info(f"Loaded NPC lexicon v{_NPC_LEXICON.get('version', 'unknown')}")
        else:
            logger.warning(f"NPC lexicon file not found: {NPC_LEXICON_PATH}")
        
        _NPC_LOADED = True
        
    except Exception as e:
        logger.error(f"Failed to load NPC data: {e}")
        _NPC_LOADED = True  # Prevent repeated loading attempts


def get_npc_schema(domain: str) -> Optional[pd.DataFrame]:
    """Возвращает NPC nodes для домена."""
    load_npc_data()
    return _NPC_SCHEMA.get(domain)


def get_npc_lexicon() -> Dict:
    """Возвращает NPC лексикон."""
    load_npc_data()
    return _NPC_LEXICON


def get_npc_samples(domain: str) -> Optional[pd.DataFrame]:
    """Возвращает samples для домена (для отладки)."""
    load_npc_data()
    return _NPC_SAMPLES.get(domain)


# ============================================================================
# NPC DOMAINS & CONSTANTS
# ============================================================================

NPC_DOMAINS = {'SHRIMP', 'FISH', 'SEAFOOD', 'MEAT'}

# Минимальное количество Strict для показа Similar
STRICT_MIN_THRESHOLD = 4

# Допуски по фасовке
PACK_TOLERANCE = {
    'SHRIMP': 0.20,
    'FISH': 0.20,
    'SEAFOOD': 0.20,
    'MEAT': 0.20,
    'default': 0.20,
}


# ============================================================================
# HARD EXCLUSION PATTERNS (from lexicon)
# ============================================================================

def compile_exclusion_patterns() -> Dict[str, re.Pattern]:
    """Компилирует regex паттерны исключений из лексикона."""
    lexicon = get_npc_lexicon()
    patterns = {}
    
    # Out of scope patterns
    oos = lexicon.get('out_of_scope_patterns', {})
    for category, pattern_list in oos.items():
        combined = '|'.join(f'({p})' for p in pattern_list)
        try:
            patterns[f'oos_{category}'] = re.compile(combined, re.IGNORECASE)
        except re.error as e:
            logger.warning(f"Invalid regex in {category}: {e}")
    
    # NPC rules
    rules = lexicon.get('npc', {}).get('rules', {})
    for rule_name, pattern in rules.items():
        if pattern and isinstance(pattern, str) and not pattern.startswith('token'):
            try:
                patterns[rule_name] = re.compile(pattern, re.IGNORECASE)
            except re.error as e:
                logger.warning(f"Invalid regex in {rule_name}: {e}")
    
    # Regex section
    regex_section = lexicon.get('regex', {})
    for section_name, section_data in regex_section.items():
        if isinstance(section_data, dict):
            for key, pattern in section_data.items():
                if isinstance(pattern, str):
                    try:
                        patterns[f'{section_name}_{key}'] = re.compile(pattern, re.IGNORECASE)
                    except re.error:
                        pass
                elif isinstance(pattern, dict):  # nested dict (e.g., shrimp.species)
                    for subkey, subpattern in pattern.items():
                        try:
                            patterns[f'{section_name}_{key}_{subkey}'] = re.compile(subpattern, re.IGNORECASE)
                        except re.error:
                            pass
        elif isinstance(section_data, str):
            try:
                patterns[section_name] = re.compile(section_data, re.IGNORECASE)
            except re.error:
                pass
    
    return patterns


_EXCLUSION_PATTERNS: Dict[str, re.Pattern] = {}


def get_exclusion_patterns() -> Dict[str, re.Pattern]:
    """Возвращает скомпилированные паттерны исключений (singleton)."""
    global _EXCLUSION_PATTERNS
    if not _EXCLUSION_PATTERNS:
        _EXCLUSION_PATTERNS = compile_exclusion_patterns()
    return _EXCLUSION_PATTERNS


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class NPCSignature:
    """NPC сигнатура товара"""
    # Базовая информация
    name_raw: str = ""
    name_norm: str = ""
    
    # NPC классификация
    npc_domain: Optional[str] = None  # SHRIMP, FISH, SEAFOOD, MEAT
    npc_node_id: Optional[str] = None  # ID узла из схемы
    
    # Креветки специфичные
    shrimp_species: Optional[str] = None  # vannamei, tiger, argentine, north, king, unspecified
    shrimp_caliber: Optional[str] = None  # 16/20, 31/40, etc.
    shrimp_caliber_band: Optional[str] = None  # small_<=20, medium_21_40, xlarge_>70
    shrimp_peeled: bool = False
    shrimp_headless: bool = False
    shrimp_cooked: bool = False
    
    # Рыба специфичные
    fish_species: Optional[str] = None  # salmon, tuna, trout, cod, etc.
    fish_cut: Optional[str] = None  # fillet, whole, steak
    fish_skin: Optional[str] = None  # skin_on, skin_off
    fish_canned: bool = False
    
    # Морепродукты специфичные
    seafood_type: Optional[str] = None  # mussels, crab, scallop, squid, octopus
    
    # Мясо специфичные
    meat_animal: Optional[str] = None  # beef, pork, chicken, turkey, lamb, duck, processed
    meat_cut: Optional[str] = None  # fillet, breast, thigh, wing, tenderloin, mince, sausage
    
    # Общие атрибуты
    state_frozen: bool = False
    state_chilled: bool = False
    is_breaded: bool = False
    is_smoked: bool = False
    is_salted: bool = False
    is_marinated: bool = False
    
    # Исключения
    is_excluded: bool = False  # Hard exclude (гёдза, бульон, etc.)
    exclude_reason: Optional[str] = None
    
    # Фасовка
    pack_qty: Optional[float] = None


@dataclass
class NPCMatchResult:
    """Результат NPC matching"""
    passed_strict: bool = False
    passed_similar: bool = False
    block_reason: Optional[str] = None
    
    # Совпадения
    same_domain: bool = False
    same_node: bool = False
    same_species: bool = False
    same_caliber_band: bool = False
    same_state: bool = False
    same_form: bool = False
    
    # Для ранжирования
    npc_score: int = 0
    
    # Лейблы отличий
    difference_labels: List[str] = field(default_factory=list)


# ============================================================================
# SIGNATURE EXTRACTION
# ============================================================================

def extract_npc_signature(item: Dict) -> NPCSignature:
    """
    Извлекает NPC сигнатуру из товара.
    
    Используется:
    1. Паттерны из лексикона
    2. Готовые атрибуты из БД (если есть)
    """
    sig = NPCSignature()
    
    name_raw = item.get('name_raw', item.get('name', ''))
    name_norm = name_raw.lower()
    
    sig.name_raw = name_raw
    sig.name_norm = name_norm
    sig.pack_qty = item.get('pack_qty') or item.get('net_weight_kg')
    
    patterns = get_exclusion_patterns()
    
    # === HARD EXCLUSIONS ===
    # Проверяем out_of_scope паттерны
    for pattern_name, pattern in patterns.items():
        if pattern_name.startswith('oos_'):
            if pattern.search(name_norm):
                sig.is_excluded = True
                sig.exclude_reason = pattern_name
                return sig
    
    # Проверяем правила исключения из npc.rules
    if 'shrimp_exclude_dumplings_regex' in patterns:
        if patterns['shrimp_exclude_dumplings_regex'].search(name_norm):
            sig.is_excluded = True
            sig.exclude_reason = 'dumplings'
            return sig
    
    if 'meat_exclude_bouillon_regex' in patterns:
        if patterns['meat_exclude_bouillon_regex'].search(name_norm):
            sig.is_excluded = True
            sig.exclude_reason = 'bouillon'
            return sig
    
    if 'meat_exclude_dumplings_regex' in patterns:
        if patterns['meat_exclude_dumplings_regex'].search(name_norm):
            sig.is_excluded = True
            sig.exclude_reason = 'dumplings_meat'
            return sig
    
    if 'seafood_exclude_seaweed_noodles_regex' in patterns:
        if patterns['seafood_exclude_seaweed_noodles_regex'].search(name_norm):
            sig.is_excluded = True
            sig.exclude_reason = 'seaweed_noodles'
            return sig
    
    # === ОПРЕДЕЛЕНИЕ ДОМЕНА ===
    sig.npc_domain = _detect_npc_domain(name_norm, patterns)
    
    if not sig.npc_domain:
        return sig
    
    # === ИЗВЛЕЧЕНИЕ АТРИБУТОВ ПО ДОМЕНУ ===
    if sig.npc_domain == 'SHRIMP':
        _extract_shrimp_attributes(sig, name_norm, patterns)
    elif sig.npc_domain == 'FISH':
        _extract_fish_attributes(sig, name_norm, patterns)
    elif sig.npc_domain == 'SEAFOOD':
        _extract_seafood_attributes(sig, name_norm, patterns)
    elif sig.npc_domain == 'MEAT':
        _extract_meat_attributes(sig, name_norm, patterns)
    
    # === ОБЩИЕ АТРИБУТЫ ===
    _extract_common_attributes(sig, name_norm, patterns)
    
    # === NPC NODE ID (lookup by attributes) ===
    sig.npc_node_id = _lookup_npc_node_id(sig)
    
    return sig


def _detect_npc_domain(name_norm: str, patterns: Dict[str, re.Pattern]) -> Optional[str]:
    """Определяет NPC домен товара."""
    
    # Приоритет: SHRIMP > SEAFOOD > FISH > MEAT
    # (креветки - подмножество seafood, но обрабатываются отдельно)
    
    # SHRIMP tokens
    shrimp_tokens = ['кревет', 'креветк', 'shrimp', 'prawn', 'ваннам', 'vannamei', 
                     'лангустин', 'langoustine']
    for token in shrimp_tokens:
        if token in name_norm:
            # Проверяем что это не "со вкусом креветки"
            if 'shrimp_exclude_flavor_regex' in patterns:
                if patterns['shrimp_exclude_flavor_regex'].search(name_norm):
                    return None
            return 'SHRIMP'
    
    # SEAFOOD tokens (non-fish)
    seafood_tokens = ['мидии', 'мидия', 'mussel', 'устриц', 'oyster', 'кальмар', 
                      'squid', 'осьминог', 'octopus', 'гребешок', 'scallop',
                      'краб', 'crab', 'лобстер', 'омар', 'lobster']
    for token in seafood_tokens:
        if token in name_norm:
            # Исключаем крабовые палочки (имитация)
            if 'крабов' in name_norm and 'палоч' in name_norm:
                return None
            if 'сурими' in name_norm:
                return None
            return 'SEAFOOD'
    
    # FISH tokens (with declensions for Russian morphology)
    fish_tokens = ['лосось', 'лосос', 'salmon', 'сёмга', 'семга', 'сёмги', 'семги',
                   'форель', 'форели', 'trout',
                   'треска', 'трески', 'трескова', 'cod', 'тунец', 'тунца', 'tuna',
                   'палтус', 'палтуса', 'halibut',
                   'минтай', 'минтая', 'pollock', 'скумбри', 'mackerel',
                   'сельд', 'сельди', 'herring',
                   'анчоус', 'анчоусов', 'anchovy', 'килька', 'мойва', 'сайра', 'хек',
                   'окун', 'окуня', 'perch', 'судак', 'судака', 'щук', 'pike',
                   'карп', 'карпа', 'carp', 'угорь', 'угря', 'eel',
                   'осетр', 'осетра', 'осетрин', 'дорад', 'сибас', 'тилапи',
                   'пангасиус', 'горбуш', 'кижуч', 'нерк', 'чавыч',
                   'печень трески', 'печен трески']  # compound term for cod liver
    
    # Сначала проверяем false friends
    if 'fish_exclude_regex' in patterns:
        if patterns['fish_exclude_regex'].search(name_norm):
            # рибай/ribeye - это мясо, не рыба
            pass
        else:
            for token in fish_tokens:
                if token in name_norm:
                    # Исключаем "груша форель" (фрукт)
                    if 'fruit_forel_exclude_regex' in patterns:
                        if patterns['fruit_forel_exclude_regex'].search(name_norm):
                            return None
                    return 'FISH'
    else:
        for token in fish_tokens:
            if token in name_norm:
                return 'FISH'
    
    # MEAT tokens
    meat_tokens = ['говядин', 'beef', 'телятин', 'veal', 'свинин', 'pork',
                   'баранин', 'lamb', 'курин', 'курица', 'куриц', 'chicken',
                   'цыпл', 'бройлер', 'индейк', 'turkey', 'утк', 'duck',
                   'гус', 'goose', 'кролик', 'rabbit', 'ягнят', 'ягненок']
    
    # Рибай - это мясо
    if 'meat_force_regex' in patterns:
        if patterns['meat_force_regex'].search(name_norm):
            return 'MEAT'
    
    for token in meat_tokens:
        if token in name_norm:
            return 'MEAT'
    
    # Processed meat
    processed_tokens = ['колбас', 'сосиск', 'сардельк', 'ветчин', 'бекон',
                        'шпик', 'буженин', 'корейк', 'грудинк', 'шницел',
                        'котлет', 'фрикадел', 'наггет']
    for token in processed_tokens:
        if token in name_norm:
            return 'MEAT'
    
    return None


def _extract_shrimp_attributes(sig: NPCSignature, name_norm: str, patterns: Dict):
    """Извлекает атрибуты креветок."""
    
    # Species
    species_map = {
        'vannamei': ['ваннам', 'vannamei', 'белоног'],
        'tiger': ['тигр', 'tiger'],
        'argentine': ['аргент'],
        'north': ['северн', 'ботан'],
        'king': ['королев', 'king'],
    }
    
    for species, tokens in species_map.items():
        for token in tokens:
            if token in name_norm:
                sig.shrimp_species = species
                break
        if sig.shrimp_species:
            break
    
    if not sig.shrimp_species:
        sig.shrimp_species = 'unspecified'
    
    # Caliber
    caliber_match = re.search(r'(\d{1,3})\s*[/\-]\s*(\d{1,3})', name_norm)
    if caliber_match:
        sig.shrimp_caliber = f"{caliber_match.group(1)}/{caliber_match.group(2)}"
        # Caliber band
        try:
            low, high = int(caliber_match.group(1)), int(caliber_match.group(2))
            avg = (low + high) / 2
            if avg <= 20:
                sig.shrimp_caliber_band = 'small_<=20'
            elif avg <= 70:
                sig.shrimp_caliber_band = 'medium_21_40'  # объединяем 21-40 и 41-70
            else:
                sig.shrimp_caliber_band = 'xlarge_>70'
        except:
            pass
    
    # Peeled
    if 'shrimp_peeled' in patterns:
        sig.shrimp_peeled = bool(patterns['shrimp_peeled'].search(name_norm))
    elif any(x in name_norm for x in ['очищ', 'peeled']):
        sig.shrimp_peeled = True
    
    # Headless
    if 'shrimp_headless' in patterns:
        sig.shrimp_headless = bool(patterns['shrimp_headless'].search(name_norm))
    elif any(x in name_norm for x in ['б/г', 'без голов', 'headless']):
        sig.shrimp_headless = True
    
    # Cooked
    if any(x in name_norm for x in ['в/м', 'варен', 'cooked']):
        sig.shrimp_cooked = True


def _extract_fish_attributes(sig: NPCSignature, name_norm: str, patterns: Dict):
    """Извлекает атрибуты рыбы."""
    
    # Species
    species_map = {
        'salmon': ['лосось', 'salmon', 'сёмга', 'семга'],
        'trout': ['форель', 'trout'],
        'cod': ['треска', 'cod'],
        'tuna': ['тунец', 'tuna'],
        'halibut': ['палтус', 'halibut'],
        'pollock': ['минтай', 'pollock'],
        'mackerel': ['скумбри', 'mackerel'],
        'herring': ['сельд', 'herring'],
        'anchovy': ['анчоус', 'anchovy'],
        'pike': ['щук', 'pike'],
        'perch': ['окун', 'perch'],
        'carp': ['карп', 'carp'],
        'eel': ['угорь', 'eel'],
        'sturgeon': ['осетр', 'sturgeon'],
        'dorado': ['дорад', 'dorado'],
        'seabass': ['сибас', 'seabass'],
        'tilapia': ['тилапи', 'tilapia'],
        'pangasius': ['пангасиус', 'pangasius'],
    }
    
    for species, tokens in species_map.items():
        for token in tokens:
            if token in name_norm:
                sig.fish_species = species
                break
        if sig.fish_species:
            break
    
    # Cut
    if any(x in name_norm for x in ['филе', 'fillet', 'filet']):
        sig.fish_cut = 'fillet'
    elif any(x in name_norm for x in ['тушка', 'целая', 'whole']):
        sig.fish_cut = 'whole'
    elif any(x in name_norm for x in ['стейк', 'steak']):
        sig.fish_cut = 'steak'
    
    # Skin
    if any(x in name_norm for x in ['без кож', 'б/к', 'skinless', 'н/к']):
        sig.fish_skin = 'skin_off'
    elif any(x in name_norm for x in ['на коже', 'с кож', 'skin on']):
        sig.fish_skin = 'skin_on'
    
    # Canned
    if any(x in name_norm for x in ['ж/б', 'консерв', 'банка', 'canned', 'в масле', 'в собств']):
        sig.fish_canned = True


def _extract_seafood_attributes(sig: NPCSignature, name_norm: str, patterns: Dict):
    """Извлекает атрибуты морепродуктов (кроме креветок и рыбы)."""
    
    type_map = {
        'mussels': ['мидии', 'мидия', 'mussel'],
        'crab': ['краб', 'crab'],
        'scallop': ['гребешок', 'scallop'],
        'squid': ['кальмар', 'squid'],
        'octopus': ['осьминог', 'octopus', 'октопус'],
        'lobster': ['лобстер', 'омар', 'lobster'],
        'oyster': ['устриц', 'oyster'],
        'clam': ['вонгол', 'clam', 'венер'],
    }
    
    for seafood_type, tokens in type_map.items():
        for token in tokens:
            if token in name_norm:
                sig.seafood_type = seafood_type
                break
        if sig.seafood_type:
            break


def _extract_meat_attributes(sig: NPCSignature, name_norm: str, patterns: Dict):
    """Извлекает атрибуты мяса."""
    
    # Animal
    animal_map = {
        'beef': ['говядин', 'beef', 'телятин', 'veal', 'рибай', 'ribeye'],
        'pork': ['свинин', 'pork', 'свиной', 'свиная'],
        'chicken': ['курин', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер'],
        'turkey': ['индейк', 'turkey', 'индюш'],
        'lamb': ['баранин', 'lamb', 'ягнят', 'ягненок'],
        'duck': ['утк', 'duck', 'утин'],
        'goose': ['гус', 'goose'],
        'rabbit': ['кролик', 'rabbit'],
        'processed': ['колбас', 'сосиск', 'сардельк', 'ветчин', 'бекон',
                      'шпик', 'буженин', 'мортадел', 'салями'],
    }
    
    for animal, tokens in animal_map.items():
        for token in tokens:
            if token in name_norm:
                sig.meat_animal = animal
                break
        if sig.meat_animal:
            break
    
    # Cut
    cut_map = {
        'fillet': ['филе', 'fillet'],
        'breast': ['грудк', 'breast'],
        'thigh': ['бедр', 'thigh', 'окорочок', 'окорочк'],
        'wing': ['крыл', 'wing'],
        'drumstick': ['голень', 'drumstick'],
        'tenderloin': ['вырезк', 'tenderloin'],
        'loin': ['карбонад', 'loin', 'корейк'],
        'rib': ['ребр', 'rib'],
        'mince': ['фарш', 'mince', 'ground'],
        'sausage': ['сосиск', 'колбас', 'сардельк', 'sausage'],
        'brisket': ['грудинк', 'brisket'],
    }
    
    for cut, tokens in cut_map.items():
        for token in tokens:
            if token in name_norm:
                sig.meat_cut = cut
                break
        if sig.meat_cut:
            break


def _extract_common_attributes(sig: NPCSignature, name_norm: str, patterns: Dict):
    """Извлекает общие атрибуты."""
    
    # Temperature state
    if any(x in name_norm for x in ['с/м', 'зам', 'замор', 'свежеморож', 'мороз', 'frozen']):
        sig.state_frozen = True
    if any(x in name_norm for x in ['охл', 'охлажд', 'chilled', 'свеж']):
        sig.state_chilled = True
    
    # Processing
    if any(x in name_norm for x in ['панир', 'кляр', 'темпур', 'breaded']):
        sig.is_breaded = True
    if any(x in name_norm for x in ['копч', 'х/к', 'г/к', 'smoked']):
        sig.is_smoked = True
    if any(x in name_norm for x in ['солен', 'солё', 'посол', 'слабосол', 'малосол', 'пресерв']):
        sig.is_salted = True
    if any(x in name_norm for x in ['марин', 'marinated']):
        sig.is_marinated = True


def _lookup_npc_node_id(sig: NPCSignature) -> Optional[str]:
    """
    Ищет npc_node_id по атрибутам сигнатуры.
    
    Логика:
    - Для SHRIMP: species + caliber_band + состояние (очищ, б/г)
    - Для FISH: species + cut
    - Для SEAFOOD: type
    - Для MEAT: animal + cut
    """
    if not sig.npc_domain:
        return None
    
    schema = get_npc_schema(sig.npc_domain)
    if schema is None or schema.empty:
        return None
    
    try:
        if sig.npc_domain == 'SHRIMP':
            # Формируем variant string: species | caliber_band | состояние
            variant_parts = []
            variant_parts.append(sig.shrimp_species or 'unspecified')
            variant_parts.append(sig.shrimp_caliber_band or 'medium_21_40')
            
            state_parts = []
            if sig.shrimp_peeled:
                state_parts.append('очищ')
            if sig.shrimp_headless:
                state_parts.append('б/г')
            if sig.shrimp_cooked:
                state_parts.append('вар')
            
            if state_parts:
                variant_parts.append(','.join(state_parts))
            
            variant_str = ' | '.join(variant_parts)
            
            # Ищем в схеме
            for _, row in schema.iterrows():
                schema_variant = str(row.get('shrimp_variant', ''))
                # Нечёткое сравнение: проверяем что все части variant_str есть в schema_variant
                if all(part in schema_variant for part in variant_parts[:2]):  # species + caliber
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
# NPC MATCHING
# ============================================================================

def check_npc_strict(source: NPCSignature, candidate: NPCSignature) -> NPCMatchResult:
    """
    Строгая проверка NPC совместимости для Strict режима.
    
    Правила:
    - Домен должен совпадать
    - Если у source есть npc_node_id, candidate должен иметь такой же
    - Если у candidate нет npc_node_id → блокируем в Strict
    - Hard exclusions блокируют всё
    - Атрибуты состояния должны совпадать (frozen/chilled, breaded)
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
    # Если у source есть node_id, требуем совпадение
    if source.npc_node_id:
        if not candidate.npc_node_id:
            result.block_reason = "CANDIDATE_NO_NPC_NODE"
            return result
        
        if source.npc_node_id != candidate.npc_node_id:
            result.block_reason = f"NODE_MISMATCH:{source.npc_node_id}!={candidate.npc_node_id}"
            return result
        
        result.same_node = True
    else:
        # Source без node_id - используем атрибутное сравнение
        pass
    
    # === STATE CHECK (frozen vs chilled) ===
    if source.state_frozen and candidate.state_chilled:
        result.block_reason = "STATE_MISMATCH:frozen!=chilled"
        return result
    if source.state_chilled and candidate.state_frozen:
        result.block_reason = "STATE_MISMATCH:chilled!=frozen"
        return result
    
    result.same_state = (source.state_frozen == candidate.state_frozen and 
                         source.state_chilled == candidate.state_chilled)
    
    # === BREADED CHECK ===
    # Панировка в Strict запрещена если source без панировки
    if candidate.is_breaded and not source.is_breaded:
        result.block_reason = "BREADED_IN_STRICT"
        return result
    
    # === DOMAIN-SPECIFIC CHECKS ===
    if source.npc_domain == 'SHRIMP':
        # Species check
        if source.shrimp_species and candidate.shrimp_species:
            if source.shrimp_species != 'unspecified' and candidate.shrimp_species != 'unspecified':
                if source.shrimp_species != candidate.shrimp_species:
                    result.block_reason = f"SHRIMP_SPECIES_MISMATCH:{source.shrimp_species}!={candidate.shrimp_species}"
                    return result
                result.same_species = True
        
        # Caliber band check
        if source.shrimp_caliber_band and candidate.shrimp_caliber_band:
            if source.shrimp_caliber_band != candidate.shrimp_caliber_band:
                result.block_reason = f"CALIBER_MISMATCH:{source.shrimp_caliber_band}!={candidate.shrimp_caliber_band}"
                return result
            result.same_caliber_band = True
    
    elif source.npc_domain == 'FISH':
        # Species check
        if source.fish_species and candidate.fish_species:
            if source.fish_species != candidate.fish_species:
                result.block_reason = f"FISH_SPECIES_MISMATCH:{source.fish_species}!={candidate.fish_species}"
                return result
            result.same_species = True
        
        # Cut check
        if source.fish_cut and candidate.fish_cut:
            if source.fish_cut != candidate.fish_cut:
                result.block_reason = f"FISH_CUT_MISMATCH:{source.fish_cut}!={candidate.fish_cut}"
                return result
            result.same_form = True
        
        # Canned check
        if source.fish_canned != candidate.fish_canned:
            result.block_reason = "FISH_CANNED_MISMATCH"
            return result
    
    elif source.npc_domain == 'SEAFOOD':
        # Type check
        if source.seafood_type and candidate.seafood_type:
            if source.seafood_type != candidate.seafood_type:
                result.block_reason = f"SEAFOOD_TYPE_MISMATCH:{source.seafood_type}!={candidate.seafood_type}"
                return result
            result.same_species = True
    
    elif source.npc_domain == 'MEAT':
        # Animal check
        if source.meat_animal and candidate.meat_animal:
            if source.meat_animal != candidate.meat_animal:
                result.block_reason = f"MEAT_ANIMAL_MISMATCH:{source.meat_animal}!={candidate.meat_animal}"
                return result
            result.same_species = True
        
        # Cut check (strict for meat)
        if source.meat_cut and candidate.meat_cut:
            if source.meat_cut != candidate.meat_cut:
                result.block_reason = f"MEAT_CUT_MISMATCH:{source.meat_cut}!={candidate.meat_cut}"
                return result
            result.same_form = True
    
    # === PASSED STRICT ===
    result.passed_strict = True
    result.passed_similar = True
    
    # === SCORING ===
    score = 100
    if result.same_node:
        score += 50
    if result.same_species:
        score += 30
    if result.same_caliber_band:
        score += 20
    if result.same_state:
        score += 10
    if result.same_form:
        score += 15
    
    result.npc_score = score
    
    return result


def check_npc_similar(source: NPCSignature, candidate: NPCSignature) -> NPCMatchResult:
    """
    Мягкая проверка NPC для Similar режима.
    
    Правила:
    - Домен должен совпадать
    - Candidate без npc_node_id → ИСКЛЮЧАЕМ ПОЛНОСТЬЮ (не показываем)
    - Разные species/caliber разрешены (с лейблами)
    - Панировка разрешена (с лейблом)
    """
    result = NPCMatchResult()
    
    # === HARD EXCLUSIONS (всегда блокируют) ===
    if source.is_excluded or candidate.is_excluded:
        result.block_reason = "EXCLUDED"
        return result
    
    # === DOMAIN CHECK (обязателен даже для Similar) ===
    if source.npc_domain != candidate.npc_domain:
        result.block_reason = f"DOMAIN_MISMATCH"
        return result
    
    result.same_domain = True
    
    # === NPC NODE CHECK ===
    # Candidate без npc_node_id → исключаем ПОЛНОСТЬЮ (даже из Similar)
    if source.npc_node_id and not candidate.npc_node_id:
        result.block_reason = "CANDIDATE_NO_NPC_NODE"
        return result
    
    # === COLLECT DIFFERENCE LABELS ===
    
    # NPC node difference (both have node_id but different)
    if source.npc_node_id and candidate.npc_node_id and source.npc_node_id != candidate.npc_node_id:
        result.difference_labels.append("Другая подкатегория")
    
    # State difference
    if source.state_frozen and candidate.state_chilled:
        result.difference_labels.append("Охлаждённый (не замороженный)")
    elif source.state_chilled and candidate.state_frozen:
        result.difference_labels.append("Замороженный (не охлаждённый)")
    
    # Breaded
    if candidate.is_breaded and not source.is_breaded:
        result.difference_labels.append("В панировке")
    
    # Domain-specific labels
    if source.npc_domain == 'SHRIMP':
        if source.shrimp_species != candidate.shrimp_species:
            if candidate.shrimp_species:
                result.difference_labels.append(f"Вид: {candidate.shrimp_species}")
        if source.shrimp_caliber_band != candidate.shrimp_caliber_band:
            if candidate.shrimp_caliber:
                result.difference_labels.append(f"Калибр: {candidate.shrimp_caliber}")
    
    elif source.npc_domain == 'FISH':
        if source.fish_species != candidate.fish_species:
            if candidate.fish_species:
                result.difference_labels.append(f"Рыба: {candidate.fish_species}")
        if source.fish_cut != candidate.fish_cut:
            if candidate.fish_cut:
                result.difference_labels.append(f"Часть: {candidate.fish_cut}")
        if source.fish_canned != candidate.fish_canned:
            if candidate.fish_canned:
                result.difference_labels.append("Консервы")
    
    elif source.npc_domain == 'SEAFOOD':
        if source.seafood_type != candidate.seafood_type:
            if candidate.seafood_type:
                result.difference_labels.append(f"Тип: {candidate.seafood_type}")
    
    elif source.npc_domain == 'MEAT':
        if source.meat_animal != candidate.meat_animal:
            if candidate.meat_animal:
                result.difference_labels.append(f"Мясо: {candidate.meat_animal}")
        if source.meat_cut != candidate.meat_cut:
            if candidate.meat_cut:
                result.difference_labels.append(f"Часть: {candidate.meat_cut}")
    
    # === PASSED SIMILAR ===
    result.passed_similar = True
    
    # Scoring for Similar (lower than Strict)
    # Base score for Similar is lower
    result.npc_score = 50
    if result.same_domain:
        result.npc_score += 20
    if not result.difference_labels:
        result.npc_score += 10
    
    # PENALTY: candidate without npc_node_id goes to the bottom
    if source.npc_node_id and not candidate.npc_node_id:
        result.npc_score -= 30  # Significant penalty to push to bottom
    
    return result


# ============================================================================
# MAIN API FUNCTIONS
# ============================================================================

def is_npc_domain_item(item: Dict) -> bool:
    """
    Проверяет, относится ли товар к NPC домену (SHRIMP/FISH/SEAFOOD/MEAT).
    """
    sig = extract_npc_signature(item)
    return sig.npc_domain is not None and not sig.is_excluded


def get_item_npc_domain(item: Dict) -> Optional[str]:
    """
    Возвращает NPC домен товара или None.
    """
    sig = extract_npc_signature(item)
    if sig.is_excluded:
        return None
    return sig.npc_domain


def apply_npc_filter(
    source_item: Dict,
    candidates: List[Dict],
    limit: int = 10,
    strict_threshold: int = STRICT_MIN_THRESHOLD
) -> Tuple[List[Dict], List[Dict], Dict[str, int]]:
    """
    Применяет NPC фильтрацию к кандидатам.
    
    Args:
        source_item: Исходный товар
        candidates: Список кандидатов (уже отфильтрованных matching_engine_v3)
        limit: Максимум результатов на режим
        strict_threshold: Порог для включения Similar
    
    Returns:
        (strict_results, similar_results, rejected_reasons)
        
    Если source не имеет npc_node_id → возвращаем None (используйте legacy)
    """
    source_sig = extract_npc_signature(source_item)
    
    # Если source excluded → пустой результат
    if source_sig.is_excluded:
        return [], [], {'SOURCE_EXCLUDED': 1}
    
    # Если source не NPC домен → None (сигнал для legacy fallback)
    if not source_sig.npc_domain:
        return None, None, None
    
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
            # Record rejection reason
            reason = strict_result.block_reason or 'UNKNOWN'
            reason_key = reason.split(':')[0]
            rejected_reasons[reason_key] = rejected_reasons.get(reason_key, 0) + 1
            
            # Try Similar
            similar_result = check_npc_similar(source_sig, cand_sig)
            if similar_result.passed_similar:
                similar_results.append({
                    'item': cand,
                    'npc_result': similar_result,
                    'npc_signature': cand_sig,
                })
    
    # Sort by NPC score
    strict_results.sort(key=lambda x: -x['npc_result'].npc_score)
    similar_results.sort(key=lambda x: (-x['npc_result'].npc_score, len(x['npc_result'].difference_labels)))
    
    # Apply limits
    strict_results = strict_results[:limit]
    
    # Similar только если Strict < threshold
    if len(strict_results) >= strict_threshold:
        similar_results = []
    else:
        similar_results = similar_results[:limit]
    
    return strict_results, similar_results, rejected_reasons


def format_npc_result(
    item: Dict,
    npc_result: NPCMatchResult,
    npc_sig: NPCSignature,
    mode: str
) -> Dict:
    """
    Форматирует результат NPC matching для API ответа.
    """
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
        
        # NPC specific
        'npc_domain': npc_sig.npc_domain,
        'npc_node_id': npc_sig.npc_node_id,
        'npc_score': npc_result.npc_score,
        'match_mode': mode,
        'difference_labels': npc_result.difference_labels,
        
        # NPC attributes (for debugging)
        'npc_attributes': {
            'shrimp_species': npc_sig.shrimp_species,
            'shrimp_caliber': npc_sig.shrimp_caliber,
            'fish_species': npc_sig.fish_species,
            'fish_cut': npc_sig.fish_cut,
            'seafood_type': npc_sig.seafood_type,
            'meat_animal': npc_sig.meat_animal,
            'meat_cut': npc_sig.meat_cut,
            'state_frozen': npc_sig.state_frozen,
            'state_chilled': npc_sig.state_chilled,
            'is_breaded': npc_sig.is_breaded,
        }
    }


# ============================================================================
# UTILITY / DEBUG
# ============================================================================

def explain_npc_match(source_name: str, candidate_name: str) -> Dict:
    """
    Объясняет решение NPC matching между двумя товарами.
    Для отладки и UI.
    """
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
            'npc_node_id': source_sig.npc_node_id,
            'is_excluded': source_sig.is_excluded,
            'exclude_reason': source_sig.exclude_reason,
        },
        'candidate': {
            'name': candidate_name,
            'npc_domain': cand_sig.npc_domain,
            'npc_node_id': cand_sig.npc_node_id,
            'is_excluded': cand_sig.is_excluded,
            'exclude_reason': cand_sig.exclude_reason,
        },
        'strict_result': {
            'passed': strict_result.passed_strict,
            'block_reason': strict_result.block_reason,
            'npc_score': strict_result.npc_score,
        },
        'similar_result': {
            'passed': similar_result.passed_similar,
            'difference_labels': similar_result.difference_labels,
            'npc_score': similar_result.npc_score,
        }
    }
