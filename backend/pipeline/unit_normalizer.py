"""
Unit Normalizer for BestPrice v12 (pack parsing: weight/volume/piece).
Нормализация единиц измерения и расчёт количества упаковок.
Canonical implementation; re-exported by backend.unit_normalizer for compat.
"""
import re
from typing import Tuple, Optional
from enum import Enum
import math


class UnitType(str, Enum):
    WEIGHT = "WEIGHT"
    VOLUME = "VOLUME"
    PIECE = "PIECE"
    UNKNOWN = "UNKNOWN"


class PackInfo:
    """Информация о фасовке товара"""
    def __init__(
        self,
        unit_type: UnitType,
        base_qty: Optional[float] = None,
        original_str: str = "",
        confidence: float = 1.0
    ):
        self.unit_type = unit_type
        self.base_qty = base_qty  # В базовых единицах: g, ml, pieces
        self.original_str = original_str
        self.confidence = confidence
    
    def __repr__(self):
        return f"PackInfo(type={self.unit_type}, qty={self.base_qty}, conf={self.confidence})"


def parse_pack_from_text(text: str) -> PackInfo:
    """
    Парсит фасовку из текста товара
    
    Поддерживаемые форматы:
    - Вес: 1кг, 500г, 0.5 кг, 1,5кг, ~5кг, 300-400г
    - Объём: 1л, 500мл, 0.5 л
    - Количество: 10шт, 5 pcs, 200 шт
    - Сложные: 10x200г, 200 шт x 5 г, 4/5кг, 4-5кг
    
    Returns:
        PackInfo с unit_type, base_qty, confidence
    """
    if not text:
        return PackInfo(UnitType.UNKNOWN, None, "", 0.0)
    
    text_lower = text.lower()
    
    weight_patterns = [
        (r'(\d+[\.,]?\d*)\s*кг', 1000.0, UnitType.WEIGHT, 1.0),
        (r'(\d+[\.,]?\d*)\s*kg', 1000.0, UnitType.WEIGHT, 1.0),
        (r'(\d+[\.,]?\d*)\s*гр?\.?\b', 1.0, UnitType.WEIGHT, 1.0),
        (r'(\d+[\.,]?\d*)\s*gr?\.?\b', 1.0, UnitType.WEIGHT, 1.0),
        (r'(\d+[\.,]?\d*)\s*г\b', 1.0, UnitType.WEIGHT, 1.0),
        (r'~\s*(\d+[\.,]?\d*)\s*кг', 1000.0, UnitType.WEIGHT, 0.9),
        (r'~\s*(\d+[\.,]?\d*)\s*г', 1.0, UnitType.WEIGHT, 0.9),
        (r'(\d+)[-–]\d+\s*кг', 1000.0, UnitType.WEIGHT, 0.8),
        (r'(\d+)[-–]\d+\s*г', 1.0, UnitType.WEIGHT, 0.8),
        (r'(\d+)/\d+\s*кг', 1000.0, UnitType.WEIGHT, 0.8),
    ]
    
    volume_patterns = [
        (r'(\d+[\.,]?\d*)\s*л\b', 1000.0, UnitType.VOLUME, 1.0),
        (r'(\d+[\.,]?\d*)\s*l\b', 1000.0, UnitType.VOLUME, 1.0),
        (r'(\d+[\.,]?\d*)\s*мл', 1.0, UnitType.VOLUME, 1.0),
        (r'(\d+[\.,]?\d*)\s*ml', 1.0, UnitType.VOLUME, 1.0),
        (r'\b(0[,\.]\d+)\s*$', 1000.0, UnitType.VOLUME, 0.7),
    ]
    
    piece_patterns = [
        (r'(\d+)\s*шт', 1.0, UnitType.PIECE, 1.0),
        (r'(\d+)\s*pcs', 1.0, UnitType.PIECE, 1.0),
        (r'(\d+)\s*штук', 1.0, UnitType.PIECE, 1.0),
        (r'(\d+)\s*лист', 1.0, UnitType.PIECE, 0.9),
        (r'(\d+)\s*рул', 1.0, UnitType.PIECE, 0.9),
        (r'(\d+)\s*уп', 1.0, UnitType.PIECE, 0.8),
        (r'(\d+)\s*пач', 1.0, UnitType.PIECE, 0.8),
        (r'(\d+)\s*порц', 1.0, UnitType.PIECE, 0.8),
        (r'(\d+)\s*п\b', 1.0, UnitType.PIECE, 0.7),
    ]
    
    complex_match = re.search(r'(\d+)\s*x\s*(\d+[\.,]?\d*)\s*(кг|г|л|мл)', text_lower)
    if complex_match:
        count = float(complex_match.group(1))
        value = float(complex_match.group(2).replace(',', '.'))
        unit = complex_match.group(3)
        if unit in ['кг', 'kg']:
            return PackInfo(UnitType.WEIGHT, count * value * 1000, text, 0.9)
        elif unit in ['г', 'g', 'gr']:
            return PackInfo(UnitType.WEIGHT, count * value, text, 0.9)
        elif unit in ['л', 'l']:
            return PackInfo(UnitType.VOLUME, count * value * 1000, text, 0.9)
        elif unit in ['мл', 'ml']:
            return PackInfo(UnitType.VOLUME, count * value, text, 0.9)
    
    all_patterns = weight_patterns + volume_patterns + piece_patterns
    for pattern, multiplier, unit_type, confidence in all_patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                base_qty = value * multiplier
                return PackInfo(unit_type, base_qty, text, confidence)
            except (ValueError, IndexError):
                continue
    
    if re.search(r'\bвес\s*$', text_lower) or re.search(r'\sвес\b', text_lower):
        return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.5)
    if 'с/м вес' in text_lower or 'см вес' in text_lower:
        return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.5)
    if re.search(r'\bс/м\s*$', text_lower) or re.search(r'\bсм\s*$', text_lower):
        return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.4)
    if re.search(r'\bзам\.?\s*$', text_lower) or re.search(r'\bзам,', text_lower):
        return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.4)
    
    bank_match = re.search(r'(\d+)[,.](\d{3})\s*$', text)
    if bank_match:
        total_ml = int(bank_match.group(1)) * 1000 + int(bank_match.group(2))
        return PackInfo(UnitType.VOLUME, float(total_ml), text, 0.7)
    
    cm_match = re.search(r'(\d+)\s*см\b', text_lower)
    if cm_match and ('бумаг' in text_lower or 'рисов' in text_lower):
        return PackInfo(UnitType.PIECE, 1.0, text, 0.6)
    
    meter_match = re.search(r'(\d+)\s*м\b', text_lower)
    if meter_match and ('рулон' in text_lower or 'рул' in text_lower):
        return PackInfo(UnitType.PIECE, float(meter_match.group(1)), text, 0.7)
    
    meat_fish_keywords = ['говядин', 'свинин', 'курин', 'индейк', 'утк', 'гуся', 'кролик', 'баранин', 'телятин', 'окорок', 'филе', 'вырезк', 'голень', 'бедр', 'грудк', 'печень', 'сердц', 'язык', 'шея', 'шейк']
    for kw in meat_fish_keywords:
        if kw in text_lower and not any(x in text_lower for x in ['кг', 'г ', 'гр', 'шт']):
            return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.3)
    
    dairy_keywords = ['сыр ', 'сливки', 'сметан', 'творог', 'масло ', 'молоко']
    for kw in dairy_keywords:
        if kw in text_lower and not any(x in text_lower for x in ['кг', 'г ', 'гр', 'л ', 'мл', 'шт']):
            return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.3)
    
    spice_keywords = ['базилик', 'ваниль', 'кориандр', 'корица', 'паприка', 'перец', 'орех', 'изюм', 'арахис', 'кешью', 'фисташ', 'миндал', 'груша суш']
    for kw in spice_keywords:
        if kw in text_lower and not any(x in text_lower for x in ['кг', 'г ', 'гр', 'шт']):
            return PackInfo(UnitType.WEIGHT, 100.0, text, 0.3)
    
    if text_lower.strip().endswith(' кг') or text_lower.strip().endswith(' кг.'):
        return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.4)
    
    sausage_keywords = ['сосиск', 'колбас', 'сардельк', 'ветчин']
    for kw in sausage_keywords:
        if kw in text_lower and not any(x in text_lower for x in ['кг', 'г ', 'гр', 'шт']):
            return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.3)
    
    if re.search(r'\b(\d+)/(\d+)\s*$', text):
        return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.4)
    
    bread_keywords = ['батон', 'хлеб', 'булк', 'багет']
    for kw in bread_keywords:
        if kw in text_lower and not any(x in text_lower for x in ['кг', 'г ', 'гр']):
            return PackInfo(UnitType.WEIGHT, 400.0, text, 0.3)
    
    dried_keywords = ['груша суш', 'компотн', 'смесь', 'сухар', 'пудр']
    for kw in dried_keywords:
        if kw in text_lower and not any(x in text_lower for x in ['кг', 'г ', 'гр']):
            return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.3)
    
    fish_keywords = ['копчен', 'охл', 'мидии', 'гребешок', 'палтус', 'скумбрия', 'лосось тушк']
    for kw in fish_keywords:
        if kw in text_lower and not any(x in text_lower for x in ['кг', 'г ', 'гр']):
            return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.3)
    
    grain_keywords = ['рис ', 'рис,', 'гречк', 'пшен', 'овсян', 'манк', 'перлов']
    for kw in grain_keywords:
        if kw in text_lower and not any(x in text_lower for x in ['кг', 'г ', 'гр']):
            return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.3)
    
    return PackInfo(UnitType.UNKNOWN, None, text, 0.0)


def calculate_packs_needed(
    required_pack: PackInfo,
    offer_pack: PackInfo
) -> Tuple[Optional[int], Optional[float], str]:
    if required_pack.unit_type == UnitType.UNKNOWN and offer_pack.unit_type == UnitType.UNKNOWN:
        return (1, 1.0, "BOTH_UNITS_UNKNOWN")
    if required_pack.unit_type == UnitType.UNKNOWN and offer_pack.unit_type != UnitType.UNKNOWN:
        return (1, 1.0, "REFERENCE_UNIT_UNKNOWN")
    if offer_pack.unit_type == UnitType.UNKNOWN:
        return (1, 1.0, "OFFER_UNIT_UNKNOWN")
    if required_pack.base_qty is None or offer_pack.base_qty is None:
        return (1, 1.0, "QTY_MISSING")
    if required_pack.unit_type != offer_pack.unit_type:
        return (None, None, f"UNIT_MISMATCH_{required_pack.unit_type}_vs_{offer_pack.unit_type}")
    if offer_pack.base_qty <= 0:
        return (None, None, "OFFER_PACK_ZERO")
    packs_needed = math.ceil(required_pack.base_qty / offer_pack.base_qty)
    return (packs_needed, float(packs_needed), "OK")


def format_pack_explanation(
    required_pack: PackInfo,
    offer_pack: PackInfo,
    packs_needed: int
) -> str:
    if not packs_needed or not required_pack.base_qty or not offer_pack.base_qty:
        return ""
    if required_pack.unit_type == UnitType.WEIGHT:
        offer_str = f"{offer_pack.base_qty / 1000:.1f} кг" if offer_pack.base_qty >= 1000 else f"{offer_pack.base_qty:.0f} г"
        required_str = f"{required_pack.base_qty / 1000:.1f} кг" if required_pack.base_qty >= 1000 else f"{required_pack.base_qty:.0f} г"
    elif required_pack.unit_type == UnitType.VOLUME:
        offer_str = f"{offer_pack.base_qty / 1000:.1f} л" if offer_pack.base_qty >= 1000 else f"{offer_pack.base_qty:.0f} мл"
        required_str = f"{required_pack.base_qty / 1000:.1f} л" if required_pack.base_qty >= 1000 else f"{required_pack.base_qty:.0f} мл"
    elif required_pack.unit_type == UnitType.PIECE:
        offer_str = f"{offer_pack.base_qty:.0f} шт"
        required_str = f"{required_pack.base_qty:.0f} шт"
    else:
        return ""
    return f"1 × {offer_str} = {required_str}" if packs_needed == 1 else f"{packs_needed} × {offer_str} = {required_str}"


def calculate_pack_penalty(packs_needed: Optional[int], unit_type: UnitType) -> int:
    if not packs_needed:
        return 20
    if packs_needed == 1:
        return 0
    if packs_needed <= 2:
        return 5
    elif packs_needed <= 5:
        return 10
    elif packs_needed <= 10:
        return 15
    elif packs_needed <= 20:
        return 25
    elif packs_needed <= 50:
        return 30
    return 40
