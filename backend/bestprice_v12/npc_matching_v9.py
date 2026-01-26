"""
BestPrice v12 - NPC Matching Module v9
======================================

NPC-matching как дополнительный слой для сложных категорий:
- SHRIMP (креветки)
- FISH + SEAFOOD (рыба и морепродукты)
- MEAT (мясо и птица)

Для остальных категорий система работает как раньше.

ЖЁСТКИЕ ЗАПРЕТЫ (никогда не попадают в креветки/рыбу/мясо):
- гёдза / пельмени / вареники
- бульоны (Knorr и аналоги)
- лапша, вермишель, удон
- нори, чука, водоросли
- чипсы, снеки
- соусы
- крабовые палочки (имитация)

Version: 9.0
"""

import re
import json
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from pathlib import Path

logger = logging.getLogger(__name__)


# ============================================================================
# NPC DOMAINS
# ============================================================================

NPC_DOMAINS = {'SHRIMP', 'FISH', 'SEAFOOD', 'MEAT', 'POULTRY', 'BEEF', 'PORK', 'LAMB'}


# ============================================================================
# ЖЁСТКИЕ ЗАПРЕТЫ (HARD EXCLUDES)
# ============================================================================

# Эти товары НИКОГДА не должны попадать в креветки/рыбу/мясо
HARD_EXCLUDE_PATTERNS = {
    # Пельмени и полуфабрикаты
    'dumplings': r'\b(г[её]дз[аы]|пельмен[ьи]?|вареник[и]?|манты|хинкал[ьи]?|равиол[ьи]|дамплинг[и]?|dumpling[s]?|gyoza)\b',
    
    # Бульоны
    'bouillon': r'\b(бульон[ыа]?|knorr|кнорр|arikon|арикон|profi|бульонн(ый|ая|ые))\b',
    
    # Лапша и вермишель
    'noodles': r'\b(лапша|вермишел[ьи]?|фунчоз[аы]?|удон|соба|рамен|батат|стеклянн(ая|ые))\b',
    
    # Водоросли
    'seaweed': r'\b(нори|чука|водоросл[ьиь]|ламинар|морск(ая|ие)\s+капуст[аы])\b',
    
    # Чипсы и снеки
    'snacks': r'\b(чипс[ыа]?|снек[и]?|сухарик[и]?|крекер[ыа]?)\b',
    
    # Соусы
    'sauce': r'\b(соус[ыа]?|кетчуп|майонез|горчиц|заправк[аи])\b',
    
    # Имитация краба
    'imitation': r'(крабов(ые|ая)?\s+палоч|сурими|краб\.?\s+палоч)',
    
    # Овощная икра
    'veg_spread': r'\bикра\b.*(кабач|баклаж|грибн|овощн)',
}

# Паттерны для "ложных друзей" (false friends)
FALSE_FRIENDS_PATTERNS = {
    # "рибай" - это говядина, не рыба
    'ribeye_as_meat': r'\b(рибай|ribeye)\b',
    
    # "со вкусом креветки" - это не креветка
    'shrimp_flavor': r'(со вкус|аромат|вкусом)\s+\w*\s*кревет',
    
    # "груша форель" - это фрукт, не рыба
    'pear_trout': r'\bгруша\b.*\bфорел',
}


# ============================================================================
# NPC FAMILY DETECTION
# ============================================================================

# Токены для определения семейства
FAMILY_TOKENS = {
    'SHRIMP': [
        'кревет', 'креветк', 'shrimp', 'prawn', 'ваннамей', 'vannamei', 
        'тигров', 'tiger', 'лангустин', 'langoustine', 'северн кревет',
    ],
    'FISH': [
        'рыб', 'fish', 'лосось', 'salmon', 'форель', 'trout', 'семга', 
        'треск', 'cod', 'сельд', 'herring', 'скумбри', 'mackerel',
        'тунец', 'tuna', 'палтус', 'halibut', 'камбал', 'flounder',
        'минтай', 'pollock', 'хек', 'hake', 'окун', 'perch', 'bass',
        'карп', 'carp', 'сом', 'catfish', 'щук', 'pike', 'судак',
        'дорад', 'dorado', 'сибас', 'seabass', 'тилапи', 'tilapia',
        'пангасиус', 'pangasius', 'горбуш', 'кет', 'нерк', 'кижуч',
        'чавыч', 'анчоус', 'килька', 'мойва', 'сайра', 'сайда',
        'угорь', 'eel', 'стерлядь', 'осетр',
    ],
    'SEAFOOD_OTHER': [
        'мидии', 'мидия', 'mussel', 'вонголи', 'vongole', 'clam',
        'устриц', 'oyster', 'кальмар', 'squid', 'осьминог', 'octopus',
        'октопус', 'сепия', 'cuttlefish', 'краб', 'crab', 'лобстер',
        'омар', 'lobster', 'каракатиц', 'гребешок', 'scallop',
    ],
    'MEAT': [
        'говяд', 'beef', 'телятин', 'veal', 'свинин', 'pork',
        'баранин', 'lamb', 'mutton', 'кролик', 'rabbit', 'оленин',
        'утка', 'duck', 'гус', 'goose', 'индейк', 'turkey',
        'курин', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер',
    ],
}

# Подсемейства для мяса
MEAT_SUBFAMILIES = {
    'POULTRY': ['курин', 'курица', 'куриц', 'chicken', 'цыпл', 'бройлер', 
                'утка', 'duck', 'гус', 'goose', 'индейк', 'turkey', 'перепел'],
    'BEEF': ['говяд', 'beef', 'телятин', 'veal', 'рибай', 'ribeye'],
    'PORK': ['свинин', 'pork'],
    'LAMB': ['баранин', 'lamb', 'mutton'],
}

# Форма продукта
PRODUCT_FORM_PATTERNS = {
    'frozen': r'\b(с/м|зам|замор|свежеморож|мороз)\b',
    'chilled': r'\b(охл|охлажд)\b',
    'canned': r'\b(ж/б|консерв|банка)\b',
    'breaded': r'\b(панир|кляр|темпур|в паниров)\b',
    'smoked': r'\b(копч)\b',
    'salted': r'\b(солен|солё)\b',
    'dried': r'\b(вялен|сушен|сушё)\b',
    'marinated': r'\b(марин)\b',
    'raw': r'\b(сыр(ой|ая|ое)?|свеж(ий|ая|ее)?)\b',
}

# Части туши
CUT_PATTERNS = {
    'fillet': r'\b(филе|fillet|filet)\b',
    'breast': r'\b(грудк|breast)\b',
    'thigh': r'\b(бедр|thigh)\b',
    'wing': r'\b(крыл|wing)\b',
    'drumstick': r'\b(голень|drumstick)\b',
    'carcass': r'\b(тушк|тушка|carcass|whole)\b',
    'mince': r'\b(фарш|mince|ground)\b',
    'steak': r'\b(стейк|steak)\b',
    'loin': r'\b(вырезк|карбонад|loin)\b',
    'rib': r'\b(ребр|rib)\b',
    'liver': r'\b(печен|liver)\b',
    'roe': r'\b(икра|roe|caviar)\b',
}

# Атрибуты для рыбы
FISH_SKIN_PATTERNS = {
    'skin_off': r'\b(без кож|б/к|skinless)\b',
    'skin_on': r'\b(на коже|с кож|skin[- ]?on)\b',
}

# Атрибуты для креветок
SHRIMP_PATTERNS = {
    'peeled': r'\b(очищ|peeled)\b',
    'headless': r'\b(без голов|б/г|headless)\b',
    'tail_on': r'\b(с хвост|tail[- ]?on)\b',
    'tail_off': r'\b(без хвост|б/хв|tail[- ]?off)\b',
    'shell_on': r'\b(в панцир|shell[- ]?on)\b',
}

# Калибр креветок
SHRIMP_CALIBER_PATTERN = r'(\d{1,3})\s*[/\-]\s*(\d{1,3})'

# Виды креветок
SHRIMP_SPECIES_PATTERNS = {
    'vannamei': r'\b(ваннам|vannamei|белоног)\b',
    'tiger': r'\b(тигр|tiger)\b',
    'north': r'\b(северн|ботан)\b',
    'argentine': r'\b(аргент)\b',
}


# ============================================================================
# DATACLASSES
# ============================================================================

@dataclass
class NPCSignature:
    """NPC сигнатура товара"""
    # Идентификация
    name_raw: str = ""
    name_norm: str = ""
    
    # NPC классификация
    npc_family: Optional[str] = None  # SHRIMP, FISH, SEAFOOD_OTHER, MEAT
    npc_subfamily: Optional[str] = None  # POULTRY, BEEF, PORK, etc.
    npc_node_id: Optional[str] = None  # Если присвоен узел
    
    # Форма продукта
    product_form: Optional[str] = None  # frozen, chilled, canned, breaded, etc.
    is_breaded: bool = False
    is_canned: bool = False
    is_semifinished: bool = False  # Полуфабрикат
    
    # Часть туши / вид
    cut_type: Optional[str] = None  # fillet, breast, thigh, etc.
    fish_species: Optional[str] = None  # salmon, cod, etc.
    
    # Рыба специфичные
    skin: Optional[str] = None  # skin_on, skin_off
    
    # Креветки специфичные
    shrimp_species: Optional[str] = None  # vannamei, tiger, etc.
    shrimp_caliber: Optional[str] = None  # 16/20, 31/40, etc.
    shrimp_caliber_band: Optional[str] = None  # small, medium, large, xlarge
    shrimp_state: Set[str] = field(default_factory=set)  # peeled, headless, etc.
    
    # Жёсткие исключения
    is_excluded: bool = False  # Если товар попадает под HARD_EXCLUDE
    exclude_reason: Optional[str] = None
    is_false_friend: bool = False
    false_friend_reason: Optional[str] = None


@dataclass
class NPCMatchResult:
    """Результат NPC matching"""
    passed_strict: bool = False
    passed_similar: bool = False
    block_reason: Optional[str] = None
    
    # NPC совместимость
    same_family: bool = False
    same_subfamily: bool = False
    same_node: bool = False
    same_species: bool = False
    same_form: bool = False
    same_caliber_band: bool = False
    
    # Для ранжирования
    npc_score: int = 0
    
    # Лейблы
    difference_labels: List[str] = field(default_factory=list)


# ============================================================================
# SIGNATURE EXTRACTION
# ============================================================================

def extract_npc_signature(item: Dict) -> NPCSignature:
    """
    Извлекает NPC сигнатуру из товара.
    """
    sig = NPCSignature()
    
    name_raw = item.get('name_raw', '')
    name_norm = item.get('name_norm', name_raw.lower())
    
    sig.name_raw = name_raw
    sig.name_norm = name_norm
    
    # === ПРОВЕРКА ЖЁСТКИХ ИСКЛЮЧЕНИЙ ===
    for exclude_type, pattern in HARD_EXCLUDE_PATTERNS.items():
        if re.search(pattern, name_norm, re.IGNORECASE):
            sig.is_excluded = True
            sig.exclude_reason = exclude_type
            return sig  # Сразу возвращаем - это не NPC товар
    
    # === ПРОВЕРКА FALSE FRIENDS ===
    for ff_type, pattern in FALSE_FRIENDS_PATTERNS.items():
        if re.search(pattern, name_norm, re.IGNORECASE):
            sig.is_false_friend = True
            sig.false_friend_reason = ff_type
            
            # Специальная обработка рибая
            if ff_type == 'ribeye_as_meat':
                sig.npc_family = 'MEAT'
                sig.npc_subfamily = 'BEEF'
                return sig
            
            # Остальные false friends исключаются из NPC
            sig.is_excluded = True
            sig.exclude_reason = f'false_friend:{ff_type}'
            return sig
    
    # === ОПРЕДЕЛЕНИЕ СЕМЕЙСТВА ===
    sig.npc_family = _detect_family(name_norm)
    
    if not sig.npc_family:
        return sig  # Не NPC товар
    
    # === ОПРЕДЕЛЕНИЕ ПОДСЕМЕЙСТВА (для MEAT) ===
    if sig.npc_family == 'MEAT':
        sig.npc_subfamily = _detect_meat_subfamily(name_norm)
    
    # === ФОРМА ПРОДУКТА ===
    sig.product_form = _detect_product_form(name_norm)
    sig.is_breaded = bool(re.search(PRODUCT_FORM_PATTERNS.get('breaded', ''), name_norm, re.IGNORECASE))
    sig.is_canned = bool(re.search(PRODUCT_FORM_PATTERNS.get('canned', ''), name_norm, re.IGNORECASE))
    
    # === ЧАСТЬ ТУШИ ===
    sig.cut_type = _detect_cut_type(name_norm)
    
    # === РЫБА СПЕЦИФИЧНЫЕ ===
    if sig.npc_family == 'FISH':
        sig.fish_species = _detect_fish_species(name_norm)
        sig.skin = _detect_fish_skin(name_norm)
    
    # === КРЕВЕТКИ СПЕЦИФИЧНЫЕ ===
    if sig.npc_family == 'SHRIMP':
        sig.shrimp_species = _detect_shrimp_species(name_norm)
        sig.shrimp_caliber = _detect_shrimp_caliber(name_norm)
        sig.shrimp_caliber_band = _caliber_to_band(sig.shrimp_caliber)
        sig.shrimp_state = _detect_shrimp_state(name_norm)
    
    # === ПРОВЕРКА НА ПОЛУФАБРИКАТ ===
    # Если breaded но не явно "сырьё" - это полуфабрикат
    if sig.is_breaded:
        sig.is_semifinished = True
    
    return sig


def _detect_family(name_norm: str) -> Optional[str]:
    """Определяет NPC семейство"""
    # Приоритет: SHRIMP > SEAFOOD_OTHER > FISH > MEAT
    
    for token in FAMILY_TOKENS['SHRIMP']:
        if token in name_norm:
            return 'SHRIMP'
    
    for token in FAMILY_TOKENS['SEAFOOD_OTHER']:
        if token in name_norm:
            return 'SEAFOOD_OTHER'
    
    for token in FAMILY_TOKENS['FISH']:
        if token in name_norm:
            return 'FISH'
    
    for token in FAMILY_TOKENS['MEAT']:
        if token in name_norm:
            return 'MEAT'
    
    return None


def _detect_meat_subfamily(name_norm: str) -> Optional[str]:
    """Определяет подсемейство мяса"""
    for subfamily, tokens in MEAT_SUBFAMILIES.items():
        for token in tokens:
            if token in name_norm:
                return subfamily
    return None


def _detect_product_form(name_norm: str) -> Optional[str]:
    """Определяет форму продукта"""
    for form, pattern in PRODUCT_FORM_PATTERNS.items():
        if re.search(pattern, name_norm, re.IGNORECASE):
            return form
    return None


def _detect_cut_type(name_norm: str) -> Optional[str]:
    """Определяет часть туши"""
    for cut, pattern in CUT_PATTERNS.items():
        if re.search(pattern, name_norm, re.IGNORECASE):
            return cut
    return None


def _detect_fish_species(name_norm: str) -> Optional[str]:
    """Определяет вид рыбы"""
    species_map = {
        'salmon': ['лосось', 'salmon', 'семга', 'сёмга'],
        'trout': ['форель', 'trout'],
        'cod': ['треск', 'cod'],
        'herring': ['сельд', 'herring'],
        'mackerel': ['скумбри', 'mackerel'],
        'tuna': ['тунец', 'tuna'],
        'halibut': ['палтус', 'halibut'],
        'pollock': ['минтай', 'pollock'],
        'pike': ['щук', 'pike'],
        'perch': ['окун', 'perch'],
        'carp': ['карп', 'carp'],
        'eel': ['угорь', 'eel'],
        'anchovy': ['анчоус', 'anchovy'],
        'tilapia': ['тилапи', 'tilapia'],
        'pangasius': ['пангасиус', 'pangasius'],
        'seabass': ['сибас', 'seabass'],
        'dorado': ['дорад', 'dorado'],
    }
    
    for species, tokens in species_map.items():
        for token in tokens:
            if token in name_norm:
                return species
    return None


def _detect_fish_skin(name_norm: str) -> Optional[str]:
    """Определяет наличие кожи"""
    for skin_type, pattern in FISH_SKIN_PATTERNS.items():
        if re.search(pattern, name_norm, re.IGNORECASE):
            return skin_type
    return None


def _detect_shrimp_species(name_norm: str) -> Optional[str]:
    """Определяет вид креветок"""
    for species, pattern in SHRIMP_SPECIES_PATTERNS.items():
        if re.search(pattern, name_norm, re.IGNORECASE):
            return species
    return None


def _detect_shrimp_caliber(name_norm: str) -> Optional[str]:
    """Извлекает калибр креветок (например 16/20)"""
    match = re.search(SHRIMP_CALIBER_PATTERN, name_norm)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None


def _caliber_to_band(caliber: Optional[str]) -> Optional[str]:
    """Преобразует калибр в диапазон (small, medium, large, xlarge)"""
    if not caliber:
        return None
    
    try:
        parts = caliber.split('/')
        avg = (int(parts[0]) + int(parts[1])) / 2
        
        if avg <= 20:
            return 'small'  # 16/20, 8/12, etc.
        elif avg <= 45:
            return 'medium'  # 21/25, 26/30, 31/40, 41/50
        elif avg <= 80:
            return 'large'  # 51/60, 61/70, 71/80
        else:
            return 'xlarge'  # 100/200, 200/300, etc.
    except:
        return None


def _detect_shrimp_state(name_norm: str) -> Set[str]:
    """Определяет состояние креветок (очищ, б/г, etc.)"""
    states = set()
    for state, pattern in SHRIMP_PATTERNS.items():
        if re.search(pattern, name_norm, re.IGNORECASE):
            states.add(state)
    return states


# ============================================================================
# NPC MATCHING
# ============================================================================

def check_npc_compatibility(
    source: NPCSignature,
    candidate: NPCSignature
) -> NPCMatchResult:
    """
    Проверяет NPC совместимость между source и candidate.
    
    Returns:
        NPCMatchResult с результатами проверки
    """
    result = NPCMatchResult()
    
    # === ИСКЛЮЧЁННЫЕ ТОВАРЫ ===
    if source.is_excluded:
        result.block_reason = f"SOURCE_EXCLUDED:{source.exclude_reason}"
        return result
    
    if candidate.is_excluded:
        result.block_reason = f"CANDIDATE_EXCLUDED:{candidate.exclude_reason}"
        return result
    
    # === НЕ-NPC ТОВАРЫ ===
    if not source.npc_family:
        result.block_reason = "SOURCE_NOT_NPC"
        return result
    
    if not candidate.npc_family:
        result.block_reason = "CANDIDATE_NOT_NPC"
        return result
    
    # === СЕМЕЙСТВО ДОЛЖНО СОВПАДАТЬ ===
    if source.npc_family != candidate.npc_family:
        result.block_reason = f"FAMILY_MISMATCH:{source.npc_family}!={candidate.npc_family}"
        return result
    
    result.same_family = True
    
    # === ПОДСЕМЕЙСТВО (для MEAT) ===
    if source.npc_family == 'MEAT':
        if source.npc_subfamily and candidate.npc_subfamily:
            if source.npc_subfamily != candidate.npc_subfamily:
                result.block_reason = f"SUBFAMILY_MISMATCH:{source.npc_subfamily}!={candidate.npc_subfamily}"
                return result
            result.same_subfamily = True
    
    # === ФОРМА ПРОДУКТА ===
    # Сырьё ≠ полуфабрикат
    if source.is_semifinished != candidate.is_semifinished:
        result.block_reason = "FORM_MISMATCH:semifinished"
        return result
    
    # Панировка запрещена в Strict (если source без панировки)
    if candidate.is_breaded and not source.is_breaded:
        result.block_reason = "BREADED_IN_STRICT"
        return result
    
    # Консервы ≠ замороженное сырьё
    if source.is_canned != candidate.is_canned:
        result.block_reason = f"FORM_MISMATCH:canned={source.is_canned}!={candidate.is_canned}"
        return result
    
    # Frozen ≠ Chilled
    if source.product_form and candidate.product_form:
        if source.product_form in ('frozen', 'chilled') and candidate.product_form in ('frozen', 'chilled'):
            if source.product_form != candidate.product_form:
                result.block_reason = f"TEMP_MISMATCH:{source.product_form}!={candidate.product_form}"
                return result
    
    result.same_form = True
    
    # === РЫБА СПЕЦИФИЧНЫЕ ===
    if source.npc_family == 'FISH':
        # Вид рыбы должен совпадать (если указан)
        if source.fish_species and candidate.fish_species:
            if source.fish_species != candidate.fish_species:
                result.block_reason = f"FISH_SPECIES_MISMATCH:{source.fish_species}!={candidate.fish_species}"
                return result
            result.same_species = True
        
        # Кожа (если указана)
        if source.skin and candidate.skin:
            if source.skin != candidate.skin:
                result.block_reason = f"SKIN_MISMATCH:{source.skin}!={candidate.skin}"
                return result
    
    # === КРЕВЕТКИ СПЕЦИФИЧНЫЕ ===
    if source.npc_family == 'SHRIMP':
        # Вид креветок
        if source.shrimp_species and candidate.shrimp_species:
            if source.shrimp_species != candidate.shrimp_species:
                result.block_reason = f"SHRIMP_SPECIES_MISMATCH:{source.shrimp_species}!={candidate.shrimp_species}"
                return result
            result.same_species = True
        
        # Калибр (диапазон)
        if source.shrimp_caliber_band and candidate.shrimp_caliber_band:
            if source.shrimp_caliber_band != candidate.shrimp_caliber_band:
                result.block_reason = f"CALIBER_BAND_MISMATCH:{source.shrimp_caliber_band}!={candidate.shrimp_caliber_band}"
                return result
            result.same_caliber_band = True
    
    # === ЧАСТЬ ТУШИ ===
    if source.cut_type and candidate.cut_type:
        if source.cut_type != candidate.cut_type:
            result.block_reason = f"CUT_MISMATCH:{source.cut_type}!={candidate.cut_type}"
            return result
    
    # === PASSED STRICT ===
    result.passed_strict = True
    result.passed_similar = True
    
    # === NPC SCORING ===
    score = 100
    
    if result.same_family:
        score += 20
    if result.same_subfamily:
        score += 15
    if result.same_species:
        score += 25
    if result.same_form:
        score += 10
    if result.same_caliber_band:
        score += 20
    
    result.npc_score = score
    
    # === ЛЕЙБЛЫ ===
    if source.shrimp_caliber != candidate.shrimp_caliber:
        if source.shrimp_caliber and candidate.shrimp_caliber:
            result.difference_labels.append(f"Калибр: {candidate.shrimp_caliber} vs {source.shrimp_caliber}")
    
    if source.product_form != candidate.product_form:
        if candidate.product_form:
            result.difference_labels.append(f"Форма: {candidate.product_form}")
    
    return result


def check_npc_for_similar(
    source: NPCSignature,
    candidate: NPCSignature
) -> NPCMatchResult:
    """
    Более мягкая проверка для Similar режима.
    Позволяет соседние калибры, разные формы с лейблами.
    """
    result = NPCMatchResult()
    
    # Исключённые товары всегда блокируются
    if source.is_excluded or candidate.is_excluded:
        result.block_reason = "EXCLUDED"
        return result
    
    # Семейство должно совпадать даже в Similar
    if source.npc_family != candidate.npc_family:
        result.block_reason = "FAMILY_MISMATCH"
        return result
    
    result.same_family = True
    
    # Подсемейство (MEAT) - мягче в Similar
    if source.npc_family == 'MEAT':
        if source.npc_subfamily != candidate.npc_subfamily:
            result.difference_labels.append(f"Другое мясо: {candidate.npc_subfamily or 'не указано'}")
    
    # Панировка допускается в Similar с лейблом
    if candidate.is_breaded and not source.is_breaded:
        result.difference_labels.append("В панировке")
    
    # Форма продукта - с лейблом
    if source.product_form != candidate.product_form:
        if candidate.product_form:
            result.difference_labels.append(f"Форма: {candidate.product_form}")
    
    # Вид - с лейблом если разный
    if source.npc_family == 'FISH' and source.fish_species != candidate.fish_species:
        if candidate.fish_species:
            result.difference_labels.append(f"Вид: {candidate.fish_species}")
    
    if source.npc_family == 'SHRIMP' and source.shrimp_species != candidate.shrimp_species:
        if candidate.shrimp_species:
            result.difference_labels.append(f"Вид: {candidate.shrimp_species}")
    
    result.passed_similar = True
    result.npc_score = 50  # Базовый score для Similar
    
    return result


# ============================================================================
# HELPERS
# ============================================================================

def is_npc_domain(item: Dict) -> bool:
    """
    Проверяет, относится ли товар к NPC домену.
    """
    name_norm = item.get('name_norm', item.get('name_raw', '')).lower()
    
    # Сначала проверяем исключения
    for pattern in HARD_EXCLUDE_PATTERNS.values():
        if re.search(pattern, name_norm, re.IGNORECASE):
            return False
    
    # Проверяем false friends
    for pattern in FALSE_FRIENDS_PATTERNS.values():
        if re.search(pattern, name_norm, re.IGNORECASE):
            # Рибай - это MEAT, поэтому True
            if 'ribeye_as_meat' in str(pattern):
                return True
            return False
    
    # Проверяем принадлежность к семейству
    sig = extract_npc_signature(item)
    return sig.npc_family is not None


def get_npc_family(item: Dict) -> Optional[str]:
    """
    Возвращает NPC семейство товара.
    """
    sig = extract_npc_signature(item)
    return sig.npc_family
