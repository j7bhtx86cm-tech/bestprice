"""
BestPrice v12 - Cart Optimizer (Phase 3)

Оптимизатор распределения заказа по поставщикам.

КЛЮЧЕВЫЕ ПРАВИЛА:
1. Draft корзина - только намерения, БЕЗ оптимизации
2. Plan (после "Оформить заказ") - оптимизированное распределение
3. Минималка по каждому поставщику отдельно
4. +10% topup - ТОЛЬКО увеличение qty существующих позиций
5. Если минималка не достигнута - ПЕРЕРАСПРЕДЕЛЕНИЕ на других поставщиков
6. В финале НЕТ поставщиков с суммой < минималки
"""

import logging
import math
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone
from copy import deepcopy

from pymongo.database import Database

logger = logging.getLogger(__name__)


# === FLAGS / REASON CODES ===

class OptFlag(str, Enum):
    """Флаги оптимизации для UI"""
    BRAND_REPLACED = "BRAND_REPLACED"              # Бренд заменён
    PACK_TOLERANCE_USED = "PACK_TOLERANCE_USED"    # Фасовка ±20%
    PPU_FALLBACK_USED = "PPU_FALLBACK_USED"        # Другая фасовка по PPU
    MIN_QTY_ROUNDED = "MIN_QTY_ROUNDED"            # Округлено до min_order_qty
    STEP_QTY_APPLIED = "STEP_QTY_APPLIED"          # Округлено по step_qty
    AUTO_TOPUP_10PCT = "AUTO_TOPUP_10PCT"          # Количество увеличено для минималки (+10%)
    SUPPLIER_CHANGED = "SUPPLIER_CHANGED"          # Поставщик изменён системой
    NO_OFFER_FOUND = "NO_OFFER_FOUND"              # Нет подходящего оффера
    PRICE_TOLERANCE_EXCEEDED = "PRICE_TOLERANCE_EXCEEDED"  # Цена замены вне допуска ±50%


class UnavailableReason(str, Enum):
    """P0.2: Коды причин недоступности товара"""
    OFFER_INACTIVE = "OFFER_INACTIVE"              # Оффер стал неактивным
    PRICE_INVALID = "PRICE_INVALID"                # Цена <= 0
    MIN_QTY_NOT_MET = "MIN_QTY_NOT_MET"            # Не выполнен min_order_qty
    PACK_TOLERANCE_FAILED = "PACK_TOLERANCE_FAILED"  # Фасовка вне ±20%
    STRICT_ATTR_MISMATCH = "STRICT_ATTR_MISMATCH"  # Жёсткие атрибуты не совпали (филе/тушка, охл/зам, жирность)
    CLASSIFICATION_MISSING = "CLASSIFICATION_MISSING"  # Нет product_core_id
    NO_SUPPLIER_OFFERS = "NO_SUPPLIER_OFFERS"      # У поставщиков нет подходящих офферов
    OTHER = "OTHER"                                # Другая причина


# Человекочитаемые описания причин
UNAVAILABLE_REASON_TEXTS = {
    UnavailableReason.OFFER_INACTIVE: "Товар снят с продажи поставщиком",
    UnavailableReason.PRICE_INVALID: "Некорректная цена товара",
    UnavailableReason.MIN_QTY_NOT_MET: "Минимальный заказ не достигнут",
    UnavailableReason.PACK_TOLERANCE_FAILED: "Фасовка не соответствует (±20%)",
    UnavailableReason.STRICT_ATTR_MISMATCH: "Не совпадают критические атрибуты (тип обработки, жирность и т.д.)",
    UnavailableReason.CLASSIFICATION_MISSING: "Товар не классифицирован в системе",
    UnavailableReason.NO_SUPPLIER_OFFERS: "Нет подходящих предложений у поставщиков",
    UnavailableReason.OTHER: "Товар временно недоступен",
}


# === DATA CLASSES ===

@dataclass
class CartIntent:
    """Намерение в корзине (что пользователь хочет)"""
    reference_id: str
    qty: float  # requested qty
    user_id: str = ""
    supplier_item_id: Optional[str] = None  # Конкретный оффер если выбран
    product_name: str = ""
    price: float = 0
    unit_type: str = "PIECE"
    supplier_id: Optional[str] = None
    supplier_name: str = ""
    product_core_id: Optional[str] = None
    brand_id: Optional[str] = None
    pack_value: Optional[float] = None
    fat_pct: Optional[float] = None
    cut: Optional[str] = None
    super_class: str = ""


@dataclass
class Offer:
    """Оффер поставщика"""
    supplier_item_id: str
    supplier_id: str
    supplier_name: str
    product_core_id: str
    unit_type: str
    price: float
    pack_value: Optional[float] = None
    pack_unit: Optional[str] = None
    brand_id: Optional[str] = None
    name_raw: str = ""
    min_order_qty: int = 1
    step_qty: int = 1
    price_per_base_unit: Optional[float] = None
    fat_pct: Optional[float] = None
    cut: Optional[str] = None


@dataclass
class PlanLine:
    """Строка плана заказа"""
    reference_id: str
    intent: CartIntent  # Что хотел клиент
    offer: Optional[Offer]  # Что назначено (None = unfulfilled)
    requested_qty: float
    final_qty: float
    line_total: float
    flags: List[str] = field(default_factory=list)
    # Флаги изменений
    supplier_changed: bool = False
    brand_changed: bool = False
    pack_changed: bool = False
    qty_changed_by_topup: bool = False
    # P0.2: Reason code для недоступных товаров
    unavailable_reason_code: Optional[str] = None
    unavailable_reason_text: Optional[str] = None
    # Дополнительная информация о locked offer
    locked: bool = False


@dataclass
class SupplierPlan:
    """План по одному поставщику"""
    supplier_id: str
    supplier_name: str
    lines: List[PlanLine] = field(default_factory=list)
    subtotal: float = 0.0
    min_order_amount: float = 10000.0
    deficit: float = 0.0
    meets_minimum: bool = False


@dataclass 
class OptimizationResult:
    """Результат оптимизации"""
    success: bool
    suppliers: List[SupplierPlan] = field(default_factory=list)
    unfulfilled: List[PlanLine] = field(default_factory=list)
    total: float = 0.0
    blocked_reason: Optional[str] = None


# === CONSTANTS ===

DEFAULT_MIN_ORDER_AMOUNT = 10000.0
PACK_TOLERANCE_PCT = 0.20  # ±20%
TOPUP_MAX_PCT = 0.10  # +10% максимум


# === HELPER FUNCTIONS ===

def get_supplier_minimums(db: Database) -> Dict[str, float]:
    """Загружает минималки поставщиков из БД"""
    mins = {}
    for comp in db.companies.find({'type': 'supplier'}, {'_id': 0, 'id': 1, 'min_order_amount': 1}):
        mins[comp['id']] = comp.get('min_order_amount', DEFAULT_MIN_ORDER_AMOUNT)
    return mins


def check_pack_tolerance(ref_pack: Optional[float], offer_pack: Optional[float], unit_type: str) -> bool:
    """Проверяет pack tolerance ±20%"""
    if unit_type == 'PIECE':
        return True
    if not ref_pack or not offer_pack:
        return True
    ratio = offer_pack / ref_pack
    return (1 - PACK_TOLERANCE_PCT) <= ratio <= (1 + PACK_TOLERANCE_PCT)


def check_critical_attrs(intent: CartIntent, offer: Offer) -> Tuple[bool, Optional[str]]:
    """Проверяет критические атрибуты (strict if задано в намерении)"""
    # Жирность
    if intent.fat_pct is not None and offer.fat_pct is not None:
        if abs(intent.fat_pct - offer.fat_pct) > 1.0:
            return False, "fat_pct mismatch"
    
    # Cut (филе vs тушка)
    if intent.cut and offer.cut:
        if intent.cut.lower() != offer.cut.lower():
            return False, "cut mismatch"
    
    return True, None


def apply_qty_constraints(qty: float, offer: Offer) -> Tuple[float, List[str]]:
    """Применяет ограничения min_order_qty и step_qty"""
    flags = []
    final_qty = qty
    
    min_qty = offer.min_order_qty or 1
    step_qty = offer.step_qty or 1
    
    if final_qty < min_qty:
        final_qty = min_qty
        flags.append(OptFlag.MIN_QTY_ROUNDED.value)
    
    if step_qty > 1:
        remainder = final_qty % step_qty
        if remainder > 0:
            final_qty = final_qty + (step_qty - remainder)
            flags.append(OptFlag.STEP_QTY_APPLIED.value)
    
    return final_qty, flags


# === OFFER MATCHING ===

def find_candidates(
    db: Database,
    intent: CartIntent,
    exclude_suppliers: Set[str] = None
) -> List[Offer]:
    """
    Находит кандидатов для intent.
    
    Жёсткие фильтры:
    - active = true
    - price > 0
    - product_core_id совпадает
    - unit_type совпадает
    """
    exclude_suppliers = exclude_suppliers or set()
    
    # Если нет product_core_id - не можем матчить
    if not intent.product_core_id:
        return []
    
    query = {
        'active': True,
        'price': {'$gt': 0},
        'product_core_id': intent.product_core_id,
        'unit_type': intent.unit_type,
    }
    
    if exclude_suppliers:
        query['supplier_company_id'] = {'$nin': list(exclude_suppliers)}
    
    items = list(db.supplier_items.find(query, {'_id': 0}))
    
    # Конвертируем в Offer
    offers = []
    for item in items:
        supplier_id = item.get('supplier_company_id', '')
        supplier_name = item.get('supplier_name', '')
        if not supplier_name:
            company = db.companies.find_one({'id': supplier_id}, {'companyName': 1, 'name': 1})
            supplier_name = company.get('companyName', company.get('name', 'Unknown')) if company else 'Unknown'
        
        pack_value = item.get('pack_qty') or item.get('pack_value')
        
        offer = Offer(
            supplier_item_id=item['id'],
            supplier_id=supplier_id,
            supplier_name=supplier_name,
            product_core_id=item['product_core_id'],
            unit_type=item['unit_type'],
            price=item['price'],
            pack_value=pack_value,
            pack_unit=item.get('pack_unit'),
            brand_id=item.get('brand_id'),
            name_raw=item.get('name_raw', ''),
            min_order_qty=item.get('min_order_qty', 1),
            step_qty=item.get('step_qty', 1),
            fat_pct=item.get('fat_pct'),
            cut=item.get('cut'),
        )
        
        if offer.unit_type in ('WEIGHT', 'VOLUME') and pack_value and pack_value > 0:
            offer.price_per_base_unit = offer.price / pack_value
        
        offers.append(offer)
    
    return offers


def pick_best_offer(
    intent: CartIntent,
    candidates: List[Offer],
    prefer_supplier_id: Optional[str] = None
) -> Tuple[Optional[Offer], List[str]]:
    """
    Выбирает лучший оффер из кандидатов.
    
    1. Фильтр по критическим атрибутам
    2. Фильтр по pack tolerance ±20%
    3. Фильтр по адекватности цены (±50% от исходной)
    4. Brand preference (если задан)
    5. Минимальная цена среди валидных
    
    Returns: (offer, flags)
    """
    if not candidates:
        return None, [OptFlag.NO_OFFER_FOUND.value]
    
    flags = []
    
    # Фильтр 1: критические атрибуты
    valid_candidates = []
    for offer in candidates:
        ok, reason = check_critical_attrs(intent, offer)
        if ok:
            valid_candidates.append(offer)
    
    if not valid_candidates:
        return None, [OptFlag.NO_OFFER_FOUND.value]
    
    # Фильтр 2: pack tolerance ±20%
    pack_ok = [o for o in valid_candidates 
               if check_pack_tolerance(intent.pack_value, o.pack_value, intent.unit_type)]
    
    if pack_ok:
        valid_candidates = pack_ok
    else:
        flags.append(OptFlag.PACK_TOLERANCE_USED.value)
    
    # Фильтр 3: адекватность цены (КРИТИЧЕСКИ ВАЖНО!)
    # Если есть исходная цена, фильтруем замены с разницей более 50%
    if intent.price and intent.price > 0:
        price_min = intent.price * 0.5  # -50%
        price_max = intent.price * 2.0  # +100%
        
        price_ok = [o for o in valid_candidates 
                    if price_min <= o.price <= price_max]
        
        if price_ok:
            valid_candidates = price_ok
        else:
            # Нет адекватных по цене - ищем ближайшую по цене
            flags.append(OptFlag.PRICE_TOLERANCE_EXCEEDED.value)
            # Сортируем по близости к исходной цене
            valid_candidates = sorted(valid_candidates, 
                                     key=lambda o: abs(o.price - intent.price))
            # Берём только те, что ближе всего (топ-3)
            valid_candidates = valid_candidates[:3]
    
    # Фильтр 4: brand preference
    brand_matched = False
    if intent.brand_id:
        brand_matches = [o for o in valid_candidates if o.brand_id == intent.brand_id]
        if brand_matches:
            valid_candidates = brand_matches
            brand_matched = True
        else:
            flags.append(OptFlag.BRAND_REPLACED.value)
    
    # Фильтр 5: prefer_supplier_id (если задан)
    if prefer_supplier_id:
        preferred = [o for o in valid_candidates if o.supplier_id == prefer_supplier_id]
        if preferred:
            valid_candidates = preferred
    
    if not valid_candidates:
        return None, [OptFlag.NO_OFFER_FOUND.value]
    
    # Выбираем минимум по цене среди валидных кандидатов
    best = min(valid_candidates, key=lambda o: o.price)
    
    return best, flags


# === PLAN BUILDING ===

def load_cart_intents(db: Database, user_id: str) -> List[CartIntent]:
    """Загружает намерения из корзины"""
    intents_raw = list(db.cart_intents.find({'user_id': user_id}, {'_id': 0}))
    
    intents = []
    for i in intents_raw:
        # Загружаем данные о товаре если есть supplier_item_id
        supplier_item_id = i.get('supplier_item_id')
        product_core_id = None
        brand_id = None
        pack_value = None
        fat_pct = None
        cut = None
        
        if supplier_item_id:
            item = db.supplier_items.find_one({'id': supplier_item_id}, {'_id': 0})
            if item:
                product_core_id = item.get('product_core_id')
                brand_id = item.get('brand_id')
                pack_value = item.get('pack_qty') or item.get('pack_value')
                fat_pct = item.get('fat_pct')
                cut = item.get('cut')
        
        intent = CartIntent(
            reference_id=i.get('reference_id', ''),
            qty=i['qty'],
            user_id=user_id,
            supplier_item_id=supplier_item_id,
            product_name=i.get('product_name', ''),
            price=i.get('price', 0),
            unit_type=i.get('unit_type', 'PIECE'),
            supplier_id=i.get('supplier_id'),
            supplier_name=i.get('supplier_name', ''),
            product_core_id=product_core_id,
            brand_id=brand_id,
            pack_value=pack_value,
            fat_pct=fat_pct,
            cut=cut,
            super_class=i.get('super_class', ''),
        )
        intents.append(intent)
    
    return intents


def build_initial_plan(
    db: Database,
    intents: List[CartIntent]
) -> Tuple[List[PlanLine], List[PlanLine]]:
    """
    Строит начальный план: для каждого intent подбирает лучший offer.
    
    P0.2: При недоступности товара устанавливает unavailable_reason_code.
    
    Returns: (assigned_lines, unfulfilled_lines)
    """
    assigned = []
    unfulfilled = []
    
    for intent in intents:
        locked = False  # Флаг что пользователь выбрал конкретный оффер
        
        # Если есть конкретный supplier_item_id - используем его напрямую (locked offer)
        if intent.supplier_item_id:
            locked = True
            item = db.supplier_items.find_one(
                {'id': intent.supplier_item_id},
                {'_id': 0}
            )
            
            # P0.2: Детальная проверка причин недоступности locked offer
            if not item:
                # Товар вообще не найден в БД
                line = PlanLine(
                    reference_id=intent.reference_id,
                    intent=intent,
                    offer=None,
                    requested_qty=intent.qty,
                    final_qty=0,
                    line_total=0,
                    flags=[OptFlag.NO_OFFER_FOUND.value],
                    unavailable_reason_code=UnavailableReason.OFFER_INACTIVE.value,
                    unavailable_reason_text=UNAVAILABLE_REASON_TEXTS[UnavailableReason.OFFER_INACTIVE],
                    locked=locked,
                )
                unfulfilled.append(line)
                continue
            
            if not item.get('active', False):
                # Товар неактивен
                line = PlanLine(
                    reference_id=intent.reference_id,
                    intent=intent,
                    offer=None,
                    requested_qty=intent.qty,
                    final_qty=0,
                    line_total=0,
                    flags=[OptFlag.NO_OFFER_FOUND.value],
                    unavailable_reason_code=UnavailableReason.OFFER_INACTIVE.value,
                    unavailable_reason_text=UNAVAILABLE_REASON_TEXTS[UnavailableReason.OFFER_INACTIVE],
                    locked=locked,
                )
                unfulfilled.append(line)
                continue
            
            if item.get('price', 0) <= 0:
                # Некорректная цена
                line = PlanLine(
                    reference_id=intent.reference_id,
                    intent=intent,
                    offer=None,
                    requested_qty=intent.qty,
                    final_qty=0,
                    line_total=0,
                    flags=[OptFlag.NO_OFFER_FOUND.value],
                    unavailable_reason_code=UnavailableReason.PRICE_INVALID.value,
                    unavailable_reason_text=UNAVAILABLE_REASON_TEXTS[UnavailableReason.PRICE_INVALID],
                    locked=locked,
                )
                unfulfilled.append(line)
                continue
            
            # Товар валиден - создаём offer
            supplier_id = item.get('supplier_company_id', '')
            supplier_name = ''
            if supplier_id:
                company = db.companies.find_one({'id': supplier_id}, {'companyName': 1, 'name': 1})
                supplier_name = company.get('companyName', company.get('name', 'Unknown')) if company else 'Unknown'
            
            offer = Offer(
                supplier_item_id=item['id'],
                supplier_id=supplier_id,
                supplier_name=supplier_name,
                product_core_id=item.get('product_core_id', ''),
                unit_type=item.get('unit_type', 'PIECE'),
                price=item['price'],
                pack_value=item.get('pack_qty') or item.get('pack_value'),
                pack_unit=item.get('pack_unit'),
                brand_id=item.get('brand_id'),
                name_raw=item.get('name_raw', ''),
                min_order_qty=item.get('min_order_qty', 1),
                step_qty=item.get('step_qty', 1),
                fat_pct=item.get('fat_pct'),
                cut=item.get('cut'),
            )
            
            final_qty, qty_flags = apply_qty_constraints(intent.qty, offer)
            
            line = PlanLine(
                reference_id=intent.reference_id,
                intent=intent,
                offer=offer,
                requested_qty=intent.qty,
                final_qty=final_qty,
                line_total=final_qty * offer.price,
                flags=qty_flags,
                supplier_changed=False,
                brand_changed=False,
                pack_changed=False,
                qty_changed_by_topup=False,
                locked=locked,
            )
            assigned.append(line)
            continue
        
        # Ищем кандидатов по product_core_id
        if not intent.product_core_id:
            # Нет product_core_id - CLASSIFICATION_MISSING
            line = PlanLine(
                reference_id=intent.reference_id,
                intent=intent,
                offer=None,
                requested_qty=intent.qty,
                final_qty=0,
                line_total=0,
                flags=[OptFlag.NO_OFFER_FOUND.value],
                unavailable_reason_code=UnavailableReason.CLASSIFICATION_MISSING.value,
                unavailable_reason_text=UNAVAILABLE_REASON_TEXTS[UnavailableReason.CLASSIFICATION_MISSING],
                locked=locked,
            )
            unfulfilled.append(line)
            continue
        
        candidates = find_candidates(db, intent)
        
        if not candidates:
            # Нет подходящих офферов у поставщиков
            line = PlanLine(
                reference_id=intent.reference_id,
                intent=intent,
                offer=None,
                requested_qty=intent.qty,
                final_qty=0,
                line_total=0,
                flags=[OptFlag.NO_OFFER_FOUND.value],
                unavailable_reason_code=UnavailableReason.NO_SUPPLIER_OFFERS.value,
                unavailable_reason_text=UNAVAILABLE_REASON_TEXTS[UnavailableReason.NO_SUPPLIER_OFFERS],
                locked=locked,
            )
            unfulfilled.append(line)
            continue
        
        offer, flags = pick_best_offer(intent, candidates)
        
        if not offer:
            # Фильтры отсеяли всех кандидатов - определяем причину
            reason_code = UnavailableReason.OTHER.value
            reason_text = UNAVAILABLE_REASON_TEXTS[UnavailableReason.OTHER]
            
            # Анализируем почему отсеялись
            if intent.fat_pct is not None or intent.cut:
                reason_code = UnavailableReason.STRICT_ATTR_MISMATCH.value
                reason_text = UNAVAILABLE_REASON_TEXTS[UnavailableReason.STRICT_ATTR_MISMATCH]
            elif intent.pack_value:
                # Проверяем есть ли проблема с фасовкой
                pack_mismatch = all(
                    not check_pack_tolerance(intent.pack_value, c.pack_value, intent.unit_type)
                    for c in candidates
                )
                if pack_mismatch:
                    reason_code = UnavailableReason.PACK_TOLERANCE_FAILED.value
                    reason_text = UNAVAILABLE_REASON_TEXTS[UnavailableReason.PACK_TOLERANCE_FAILED]
            
            line = PlanLine(
                reference_id=intent.reference_id,
                intent=intent,
                offer=None,
                requested_qty=intent.qty,
                final_qty=0,
                line_total=0,
                flags=flags,
                unavailable_reason_code=reason_code,
                unavailable_reason_text=reason_text,
                locked=locked,
            )
            unfulfilled.append(line)
            continue
        
        final_qty, qty_flags = apply_qty_constraints(intent.qty, offer)
        flags.extend(qty_flags)
        
        # Определяем флаги изменений
        supplier_changed = (intent.supplier_id and offer.supplier_id != intent.supplier_id)
        brand_changed = OptFlag.BRAND_REPLACED.value in flags
        pack_changed = OptFlag.PACK_TOLERANCE_USED.value in flags
        
        if supplier_changed and OptFlag.SUPPLIER_CHANGED.value not in flags:
            flags.append(OptFlag.SUPPLIER_CHANGED.value)
        
        line = PlanLine(
            reference_id=intent.reference_id,
            intent=intent,
            offer=offer,
            requested_qty=intent.qty,
            final_qty=final_qty,
            line_total=final_qty * offer.price,
            flags=flags,
            supplier_changed=supplier_changed,
            brand_changed=brand_changed,
            pack_changed=pack_changed,
            qty_changed_by_topup=False,
        )
        assigned.append(line)
    
    return assigned, unfulfilled


def group_by_supplier(
    lines: List[PlanLine],
    supplier_mins: Dict[str, float]
) -> Dict[str, SupplierPlan]:
    """Группирует строки по поставщикам"""
    groups: Dict[str, SupplierPlan] = {}
    
    for line in lines:
        if not line.offer:
            continue
            
        sid = line.offer.supplier_id
        if sid not in groups:
            groups[sid] = SupplierPlan(
                supplier_id=sid,
                supplier_name=line.offer.supplier_name,
                min_order_amount=supplier_mins.get(sid, DEFAULT_MIN_ORDER_AMOUNT)
            )
        
        groups[sid].lines.append(line)
        groups[sid].subtotal += line.line_total
    
    # Вычисляем статусы
    for plan in groups.values():
        plan.deficit = max(0, plan.min_order_amount - plan.subtotal)
        plan.meets_minimum = plan.deficit <= 0
    
    return groups


# === OPTIMIZATION: +10% TOPUP ===

def apply_topup_10pct(groups: Dict[str, SupplierPlan]) -> Dict[str, SupplierPlan]:
    """
    Применяет +10% к qty для достижения минималки.
    ТОЛЬКО увеличение существующих позиций, НЕ добавление новых.
    """
    for plan in groups.values():
        if plan.meets_minimum:
            continue
        
        # Пробуем добить минималку увеличением qty
        deficit = plan.deficit
        
        for line in plan.lines:
            if deficit <= 0:
                break
            
            if not line.offer:
                continue
            
            # Максимум +10% от requested_qty
            max_increase = line.requested_qty * TOPUP_MAX_PCT
            current_qty = line.final_qty
            max_new_qty = current_qty + max_increase
            
            # Сколько можем добавить в деньгах
            price = line.offer.price
            max_add_value = max_increase * price
            
            # Сколько нужно добавить
            needed_add_qty = min(max_increase, deficit / price) if price > 0 else 0
            
            if needed_add_qty > 0:
                new_qty = current_qty + needed_add_qty
                
                # Округляем по step_qty
                step = line.offer.step_qty or 1
                if step > 1:
                    new_qty = math.ceil(new_qty / step) * step
                
                # Не превышаем максимум
                new_qty = min(new_qty, max_new_qty)
                
                if new_qty > current_qty:
                    added_value = (new_qty - current_qty) * price
                    
                    line.final_qty = new_qty
                    line.line_total = new_qty * price
                    line.qty_changed_by_topup = True
                    
                    if OptFlag.AUTO_TOPUP_10PCT.value not in line.flags:
                        line.flags.append(OptFlag.AUTO_TOPUP_10PCT.value)
                    
                    plan.subtotal += added_value
                    deficit -= added_value
        
        # Пересчитываем статус
        plan.deficit = max(0, plan.min_order_amount - plan.subtotal)
        plan.meets_minimum = plan.deficit <= 0
    
    return groups


# === OPTIMIZATION: REDISTRIBUTION ===

def redistribute_under_minimum(
    db: Database,
    groups: Dict[str, SupplierPlan],
    supplier_mins: Dict[str, float],
    max_iterations: int = 10
) -> Tuple[Dict[str, SupplierPlan], List[PlanLine]]:
    """
    Перераспределяет позиции от поставщиков < минималки к другим.
    
    Алгоритм:
    1. Найти поставщиков под минималкой
    2. Для каждой их позиции искать альтернативу у других поставщиков
    3. Перенести если найдена
    4. Повторять до стабилизации
    
    Returns: (updated_groups, unfulfilled_lines)
    """
    unfulfilled = []
    
    for iteration in range(max_iterations):
        # Находим поставщиков под минималкой
        under_min = [sid for sid, plan in groups.items() if not plan.meets_minimum]
        
        if not under_min:
            break  # Все ок
        
        made_changes = False
        
        for weak_sid in under_min:
            weak_plan = groups.get(weak_sid)
            if not weak_plan:
                continue
            
            # Пробуем перенести каждую позицию
            lines_to_redistribute = list(weak_plan.lines)
            
            for line in lines_to_redistribute:
                if not line.offer:
                    continue
                
                intent = line.intent
                
                # Ищем альтернативы у ДРУГИХ поставщиков (не weak_sid)
                candidates = find_candidates(db, intent, exclude_suppliers={weak_sid})
                
                # Предпочитаем поставщиков которые уже в плане и над минималкой
                good_suppliers = {sid for sid, p in groups.items() if p.meets_minimum and sid != weak_sid}
                
                preferred_candidates = [c for c in candidates if c.supplier_id in good_suppliers]
                
                if preferred_candidates:
                    new_offer, flags = pick_best_offer(intent, preferred_candidates)
                elif candidates:
                    new_offer, flags = pick_best_offer(intent, candidates)
                else:
                    new_offer = None
                    flags = [OptFlag.NO_OFFER_FOUND.value]
                
                if new_offer:
                    # Удаляем из старого поставщика
                    weak_plan.lines.remove(line)
                    weak_plan.subtotal -= line.line_total
                    
                    # Создаём новую строку
                    final_qty, qty_flags = apply_qty_constraints(intent.qty, new_offer)
                    flags.extend(qty_flags)
                    
                    if OptFlag.SUPPLIER_CHANGED.value not in flags:
                        flags.append(OptFlag.SUPPLIER_CHANGED.value)
                    
                    new_line = PlanLine(
                        reference_id=line.reference_id,
                        intent=intent,
                        offer=new_offer,
                        requested_qty=intent.qty,
                        final_qty=final_qty,
                        line_total=final_qty * new_offer.price,
                        flags=flags,
                        supplier_changed=True,
                        brand_changed=OptFlag.BRAND_REPLACED.value in flags,
                        pack_changed=OptFlag.PACK_TOLERANCE_USED.value in flags,
                        qty_changed_by_topup=False,
                    )
                    
                    # Добавляем к новому поставщику
                    target_sid = new_offer.supplier_id
                    if target_sid not in groups:
                        groups[target_sid] = SupplierPlan(
                            supplier_id=target_sid,
                            supplier_name=new_offer.supplier_name,
                            min_order_amount=supplier_mins.get(target_sid, DEFAULT_MIN_ORDER_AMOUNT)
                        )
                    
                    groups[target_sid].lines.append(new_line)
                    groups[target_sid].subtotal += new_line.line_total
                    
                    made_changes = True
            
            # Обновляем статусы
            for plan in groups.values():
                plan.deficit = max(0, plan.min_order_amount - plan.subtotal)
                plan.meets_minimum = plan.deficit <= 0
            
            # Удаляем пустых поставщиков
            if weak_plan.lines == []:
                del groups[weak_sid]
        
        if not made_changes:
            break
    
    # Собираем unfulfilled из оставшихся под-минималкой поставщиков
    # НО НЕ УДАЛЯЕМ ИХ! Показываем пользователю с blocked_reason
    under_min_final = [sid for sid, plan in groups.items() if not plan.meets_minimum]
    
    # Проверяем есть ли хоть один поставщик над минималкой
    has_good_supplier = any(plan.meets_minimum for plan in groups.values())
    
    if not has_good_supplier:
        # Все под минималкой - возвращаем как есть (не удаляем)
        # Пользователь увидит blocked_reason
        pass
    else:
        # Есть хорошие поставщики - удаляем плохих и перемещаем их позиции в unfulfilled
        for sid in under_min_final:
            plan = groups[sid]
            for line in plan.lines:
                unfulfilled.append(line)
            del groups[sid]
    
    return groups, unfulfilled


# === MAIN OPTIMIZATION FUNCTION ===

def optimize_cart(db: Database, user_id: str) -> OptimizationResult:
    """
    Главная функция оптимизации корзины.
    
    1. Загружает intents
    2. Строит начальный план (best offer per item)
    3. Группирует по поставщикам
    4. Применяет +10% topup
    5. Перераспределяет от поставщиков < минималки
    6. Формирует результат
    """
    # 1. Загружаем данные
    intents = load_cart_intents(db, user_id)
    
    if not intents:
        return OptimizationResult(
            success=True,
            suppliers=[],
            total=0.0
        )
    
    supplier_mins = get_supplier_minimums(db)
    
    # 2. Строим начальный план
    assigned_lines, unfulfilled_lines = build_initial_plan(db, intents)
    
    if not assigned_lines:
        return OptimizationResult(
            success=False,
            unfulfilled=[],
            blocked_reason="Нет доступных товаров у поставщиков"
        )
    
    # 3. Группируем по поставщикам
    groups = group_by_supplier(assigned_lines, supplier_mins)
    
    # 4. Применяем +10% topup
    groups = apply_topup_10pct(groups)
    
    # 5. Перераспределяем от поставщиков < минималки
    groups, extra_unfulfilled = redistribute_under_minimum(db, groups, supplier_mins)
    unfulfilled_lines.extend(extra_unfulfilled)
    
    # 6. Финальная проверка и применение +10% ещё раз
    groups = apply_topup_10pct(groups)
    
    # 7. Проверяем успех
    under_min = [sid for sid, plan in groups.items() if not plan.meets_minimum]
    
    if under_min:
        supplier_names = [groups[sid].supplier_name for sid in under_min]
        blocked_reason = f"Невозможно достичь минималки для: {', '.join(supplier_names)}. Добавьте товары или удалите позиции этих поставщиков."
        success = False
    else:
        blocked_reason = None
        success = True
    
    # 8. Формируем результат
    total = sum(plan.subtotal for plan in groups.values())
    
    return OptimizationResult(
        success=success,
        suppliers=list(groups.values()),
        unfulfilled=unfulfilled_lines,
        total=total,
        blocked_reason=blocked_reason
    )


# === API HELPERS ===

def plan_to_dict(result: OptimizationResult) -> Dict[str, Any]:
    """Конвертирует результат оптимизации в dict для API"""
    suppliers_data = []
    
    for plan in result.suppliers:
        items_data = []
        for line in plan.lines:
            # Цена из оффера (что будет заказано)
            offer_price = line.offer.price if line.offer else 0
            # Исходная цена из intent (что хотел клиент)
            original_price = line.intent.price if line.intent else 0
            
            item_dict = {
                'reference_id': line.reference_id,
                'product_name': line.intent.product_name if line.intent else '',
                'requested_qty': line.requested_qty,
                'final_qty': line.final_qty,
                'price': offer_price,
                'original_price': original_price,  # Для UI-индикатора изменения цены
                'line_total': line.line_total,
                'unit_type': line.offer.unit_type if line.offer else line.intent.unit_type,
                'supplier_item_id': line.offer.supplier_item_id if line.offer else None,
                'flags': line.flags,
                'supplier_changed': line.supplier_changed,
                'brand_changed': line.brand_changed,
                'pack_changed': line.pack_changed,
                'qty_changed_by_topup': line.qty_changed_by_topup,
                'locked': line.locked,
            }
            items_data.append(item_dict)
        
        supplier_dict = {
            'supplier_id': plan.supplier_id,
            'supplier_name': plan.supplier_name,
            'items': items_data,
            'subtotal': plan.subtotal,
            'min_order_amount': plan.min_order_amount,
            'deficit': plan.deficit,
            'meets_minimum': plan.meets_minimum,
        }
        suppliers_data.append(supplier_dict)
    
    # P0.2: Добавляем reason codes в unfulfilled items
    unfulfilled_data = []
    for line in result.unfulfilled:
        unfulfilled_item = {
            'reference_id': line.reference_id,
            'product_name': line.intent.product_name if line.intent else '',
            'requested_qty': line.requested_qty,
            'original_price': line.intent.price if line.intent else 0,  # Добавляем для консистентности
            'locked': line.locked,
        }
        
        # Используем детальный reason если есть, иначе generic
        if line.unavailable_reason_code:
            unfulfilled_item['unavailable_reason_code'] = line.unavailable_reason_code
            unfulfilled_item['reason'] = line.unavailable_reason_text or UNAVAILABLE_REASON_TEXTS.get(
                UnavailableReason(line.unavailable_reason_code),
                'Товар временно недоступен'
            )
        else:
            unfulfilled_item['unavailable_reason_code'] = UnavailableReason.OTHER.value
            unfulfilled_item['reason'] = 'Нет доступных предложений у поставщиков'
        
        unfulfilled_data.append(unfulfilled_item)
    
    return {
        'success': result.success,
        'suppliers': suppliers_data,
        'unfulfilled': unfulfilled_data,
        'total': result.total,
        'blocked_reason': result.blocked_reason,
    }
