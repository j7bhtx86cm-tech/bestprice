"""
Unit Normalizer for BestPrice v12
Нормализация единиц измерения и расчёт количества упаковок
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
    
    # Паттерны для парсинга
    # Weight patterns (в граммы)
    weight_patterns = [
        # Килограммы
        (r'(\d+[\.,]?\d*)\s*кг', 1000.0, UnitType.WEIGHT, 1.0),
        (r'(\d+[\.,]?\d*)\s*kg', 1000.0, UnitType.WEIGHT, 1.0),
        # Граммы (с пробелом или без)
        (r'(\d+[\.,]?\d*)\s*гр?\.?\b', 1.0, UnitType.WEIGHT, 1.0),
        (r'(\d+[\.,]?\d*)\s*gr?\.?\b', 1.0, UnitType.WEIGHT, 1.0),
        (r'(\d+[\.,]?\d*)\s*г\b', 1.0, UnitType.WEIGHT, 1.0),
        # Приблизительный вес: ~5кг
        (r'~\s*(\d+[\.,]?\d*)\s*кг', 1000.0, UnitType.WEIGHT, 0.9),
        (r'~\s*(\d+[\.,]?\d*)\s*г', 1.0, UnitType.WEIGHT, 0.9),
        # Диапазон: 300-400г, 4-5кг
        (r'(\d+)[-–]\d+\s*кг', 1000.0, UnitType.WEIGHT, 0.8),
        (r'(\d+)[-–]\d+\s*г', 1.0, UnitType.WEIGHT, 0.8),
        # Дробь: 4/5 кг
        (r'(\d+)/\d+\s*кг', 1000.0, UnitType.WEIGHT, 0.8),
    ]
    
    # Volume patterns (в миллилитры)
    volume_patterns = [
        # Литры
        (r'(\d+[\.,]?\d*)\s*л\b', 1000.0, UnitType.VOLUME, 1.0),
        (r'(\d+[\.,]?\d*)\s*l\b', 1000.0, UnitType.VOLUME, 1.0),
        # Миллилитры
        (r'(\d+[\.,]?\d*)\s*мл', 1.0, UnitType.VOLUME, 1.0),
        (r'(\d+[\.,]?\d*)\s*ml', 1.0, UnitType.VOLUME, 1.0),
    ]
    
    # Piece patterns
    piece_patterns = [
        (r'(\d+)\s*шт', 1.0, UnitType.PIECE, 1.0),
        (r'(\d+)\s*pcs', 1.0, UnitType.PIECE, 1.0),
        (r'(\d+)\s*штук', 1.0, UnitType.PIECE, 1.0),
        # Листы (бумага, полотенца)
        (r'(\d+)\s*лист', 1.0, UnitType.PIECE, 0.9),
        # Рулоны
        (r'(\d+)\s*рул', 1.0, UnitType.PIECE, 0.9),
        # Упаковки
        (r'(\d+)\s*уп', 1.0, UnitType.PIECE, 0.8),
        (r'(\d+)\s*пач', 1.0, UnitType.PIECE, 0.8),  # пачек
        # Порции
        (r'(\d+)\s*порц', 1.0, UnitType.PIECE, 0.8),
    ]
    
    # Проверяем сложные форматы: 10x200г, 200 шт x 5 г
    complex_match = re.search(r'(\d+)\s*x\s*(\d+[\.,]?\d*)\s*(кг|г|л|мл)', text_lower)
    if complex_match:
        count = float(complex_match.group(1))
        value = float(complex_match.group(2).replace(',', '.'))
        unit = complex_match.group(3)
        
        if unit in ['кг', 'kg']:
            base_qty = count * value * 1000  # В граммы
            return PackInfo(UnitType.WEIGHT, base_qty, text, 0.9)
        elif unit in ['г', 'g', 'gr']:
            base_qty = count * value
            return PackInfo(UnitType.WEIGHT, base_qty, text, 0.9)
        elif unit in ['л', 'l']:
            base_qty = count * value * 1000  # В мл
            return PackInfo(UnitType.VOLUME, base_qty, text, 0.9)
        elif unit in ['мл', 'ml']:
            base_qty = count * value
            return PackInfo(UnitType.VOLUME, base_qty, text, 0.9)
    
    # Пробуем все паттерны по порядку приоритета
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
    
    # Специальные форматы:
    # 1. Весовой товар ("вес" в конце) - устанавливаем 1кг по умолчанию
    if re.search(r'\bвес\s*$', text_lower) or re.search(r'\sвес\b', text_lower):
        return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.5)  # 1кг default
    
    # 2. "с/м вес" - замороженные весовые
    if 'с/м вес' in text_lower or 'см вес' in text_lower:
        return PackInfo(UnitType.WEIGHT, 1000.0, text, 0.5)  # 1кг default
    
    # 3. Банки с указанием объёма в мл через запятую: "2,650" = 2650мл
    bank_match = re.search(r'(\d+)[,.](\d{3})\s*$', text)
    if bank_match:
        liters = int(bank_match.group(1))
        ml = int(bank_match.group(2))
        total_ml = liters * 1000 + ml
        return PackInfo(UnitType.VOLUME, float(total_ml), text, 0.7)
    
    # 4. Размер в см для бумаги: "22 см" - считаем как штуки
    cm_match = re.search(r'(\d+)\s*см\b', text_lower)
    if cm_match and ('бумаг' in text_lower or 'рисов' in text_lower):
        return PackInfo(UnitType.PIECE, 1.0, text, 0.6)  # 1 упаковка
    
    # 5. Метры для рулонов: "11м", "15м"  
    meter_match = re.search(r'(\d+)\s*м\b', text_lower)
    if meter_match and ('рулон' in text_lower or 'рул' in text_lower):
        meters = float(meter_match.group(1))
        return PackInfo(UnitType.PIECE, meters, text, 0.7)
    
    # Ничего не найдено
    return PackInfo(UnitType.UNKNOWN, None, text, 0.0)


def calculate_packs_needed(
    required_pack: PackInfo,
    offer_pack: PackInfo
) -> Tuple[Optional[int], Optional[float], str]:
    """
    Рассчитывает количество упаковок для закрытия потребности
    
    Args:
        required_pack: Требуемая фасовка (reference)
        offer_pack: Фасовка предложения (candidate)
    
    Returns:
        (packs_needed, total_cost_multiplier, reason_code)
        - packs_needed: количество упаковок (ceil)
        - total_cost_multiplier: множитель для цены
        - reason_code: код причины если не удалось
    """
    # Проверка 1: оба неизвестны
    if required_pack.unit_type == UnitType.UNKNOWN and offer_pack.unit_type == UnitType.UNKNOWN:
        return (1, 1.0, "BOTH_UNITS_UNKNOWN")
    
    # Проверка 2: reference неизвестен, но offer известен
    if required_pack.unit_type == UnitType.UNKNOWN and offer_pack.unit_type != UnitType.UNKNOWN:
        # Предполагаем 1 упаковку
        return (1, 1.0, "REFERENCE_UNIT_UNKNOWN")
    
    # Проверка 3: offer неизвестен
    if offer_pack.unit_type == UnitType.UNKNOWN:
        # Не можем рассчитать, предполагаем 1
        return (1, 1.0, "OFFER_UNIT_UNKNOWN")
    
    # Проверка 4: количество не определено
    if required_pack.base_qty is None or offer_pack.base_qty is None:
        return (1, 1.0, "QTY_MISSING")
    
    # Проверка 5: UNIT_MISMATCH (несовместимые типы)
    if required_pack.unit_type != offer_pack.unit_type:
        # КРИТИЧНО: разные типы единиц
        return (None, None, f"UNIT_MISMATCH_{required_pack.unit_type}_vs_{offer_pack.unit_type}")
    
    # Проверка 6: деление на ноль
    if offer_pack.base_qty <= 0:
        return (None, None, "OFFER_PACK_ZERO")
    
    # Рассчитываем количество упаковок
    packs_needed = math.ceil(required_pack.base_qty / offer_pack.base_qty)
    
    # Множитель для total_cost
    total_cost_multiplier = float(packs_needed)
    
    return (packs_needed, total_cost_multiplier, "OK")


def format_pack_explanation(
    required_pack: PackInfo,
    offer_pack: PackInfo,
    packs_needed: int
) -> str:
    """
    Форматирует пояснение для пользователя
    
    Returns:
        Строка типа "200 × 5 г = 1000 г (1 кг)"
    """
    if not packs_needed or not required_pack.base_qty or not offer_pack.base_qty:
        return ""
    
    # Определяем единицу для отображения
    if required_pack.unit_type == UnitType.WEIGHT:
        if offer_pack.base_qty >= 1000:
            offer_str = f"{offer_pack.base_qty / 1000:.1f} кг"
        else:
            offer_str = f"{offer_pack.base_qty:.0f} г"
        
        if required_pack.base_qty >= 1000:
            required_str = f"{required_pack.base_qty / 1000:.1f} кг"
        else:
            required_str = f"{required_pack.base_qty:.0f} г"
    
    elif required_pack.unit_type == UnitType.VOLUME:
        if offer_pack.base_qty >= 1000:
            offer_str = f"{offer_pack.base_qty / 1000:.1f} л"
        else:
            offer_str = f"{offer_pack.base_qty:.0f} мл"
        
        if required_pack.base_qty >= 1000:
            required_str = f"{required_pack.base_qty / 1000:.1f} л"
        else:
            required_str = f"{required_pack.base_qty:.0f} мл"
    
    elif required_pack.unit_type == UnitType.PIECE:
        offer_str = f"{offer_pack.base_qty:.0f} шт"
        required_str = f"{required_pack.base_qty:.0f} шт"
    
    else:
        return ""
    
    if packs_needed == 1:
        return f"1 × {offer_str} = {required_str}"
    else:
        return f"{packs_needed} × {offer_str} = {required_str}"


def calculate_pack_penalty(packs_needed: Optional[int], unit_type: UnitType) -> int:
    """
    Рассчитывает штраф к match_percent за большое количество упаковок
    
    Args:
        packs_needed: количество упаковок
        unit_type: тип единицы
    
    Returns:
        Штраф в процентах (0-40)
    """
    if not packs_needed:
        return 20  # Неизвестное количество
    
    if packs_needed == 1:
        return 0  # Идеальное совпадение
    
    # Шкала штрафов в зависимости от количества упаковок
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
    else:
        return 40  # Очень большое количество (200 упаковок и т.п.)


# Тесты для проверки
if __name__ == "__main__":
    test_cases = [
        ("ВАСАБИ 1кг", "ВАСАБИ порционный 5 г"),
        ("МУКА пшеничная 1кг", "МУКА пшеничная 10 кг"),
        ("Кетчуп 1л", "Кетчуп 500 мл"),
        ("Соль 1 кг", "Соль нитритная 5 шт"),  # UNIT_MISMATCH
    ]
    
    print("=" * 80)
    print("UNIT NORMALIZER TESTS")
    print("=" * 80)
    
    for ref_text, offer_text in test_cases:
        print(f"\n📋 Reference: {ref_text}")
        print(f"🎯 Offer: {offer_text}")
        
        ref_pack = parse_pack_from_text(ref_text)
        offer_pack = parse_pack_from_text(offer_text)
        
        print(f"   Ref pack: {ref_pack}")
        print(f"   Offer pack: {offer_pack}")
        
        packs, multiplier, reason = calculate_packs_needed(ref_pack, offer_pack)
        
        if reason == "OK":
            explanation = format_pack_explanation(ref_pack, offer_pack, packs)
            penalty = calculate_pack_penalty(packs, ref_pack.unit_type)
            print(f"   ✅ Packs needed: {packs}")
            print(f"   💰 Total cost multiplier: {multiplier}")
            print(f"   📝 Explanation: {explanation}")
            print(f"   ⚠️ Pack penalty: -{penalty}%")
        else:
            print(f"   ❌ Reason: {reason}")
