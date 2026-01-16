"""
BestPrice v12 - Cart Optimizer

Оптимизатор распределения заказа по поставщикам.

Ключевые правила:
1. Корзина = Intent (reference_id + qty)
2. Минималка по каждому поставщику отдельно
3. Matching: product_core_id, unit_type строго; pack ±20%; PPU fallback
4. В финале НЕТ поставщиков < минималки
"""

import logging
import math
from typing import List, Dict, Any, Optional, Tuple, Set
from dataclasses import dataclass, field
from enum import Enum
from datetime import datetime, timezone

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
    AUTO_TOPUP_10PCT = "AUTO_TOPUP_10PCT"          # Количество увеличено для минималки
    SUPPLIER_CHANGED = "SUPPLIER_CHANGED"          # Поставщик изменён системой
    NO_OFFER_FOUND = "NO_OFFER_FOUND"              # Нет подходящего оффера


# === DATA CLASSES ===

@dataclass
class CartIntent:
    """Намерение в корзине (что пользователь хочет)"""
    reference_id: str
    qty: float  # в единицах сайта (кг/л/шт)
    user_id: str = ""


@dataclass
class Reference:
    """Карточка каталога / избранного"""
    reference_id: str
    product_core_id: str
    unit_type: str  # WEIGHT, VOLUME, PIECE
    pack_value: Optional[float] = None
    pack_unit: Optional[str] = None
    brand_id: Optional[str] = None
    name: str = ""
    super_class: str = ""
    # Критические атрибуты (когда заполнены)
    fat_pct: Optional[float] = None  # для молочки
    cut: Optional[str] = None  # для рыбы/мяса


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
    price_per_base_unit: Optional[float] = None  # руб/кг или руб/л
    # Критические атрибуты
    fat_pct: Optional[float] = None
    cut: Optional[str] = None


@dataclass
class PlanLine:
    """Строка плана заказа"""
    reference_id: str
    reference_name: str
    offer: Offer
    user_qty: float       # что хотел пользователь
    final_qty: float      # после округления
    line_total: float     # final_qty * price
    flags: List[str] = field(default_factory=list)
    # Для UI бейджей
    original_brand: Optional[str] = None
    new_brand: Optional[str] = None
    original_pack: Optional[str] = None
    new_pack: Optional[str] = None


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
    total: float = 0.0
    unmatched_intents: List[str] = field(default_factory=list)
    blocked_reason: Optional[str] = None


# === CONSTANTS ===

DEFAULT_MIN_ORDER_AMOUNT = 10000.0
PACK_TOLERANCE = 0.20  # ±20%
MAX_TOPUP_PERCENT = 0.10  # +10%


# === HELPER FUNCTIONS ===

def get_supplier_min_order(db: Database, supplier_id: str) -> float:
    """Получает минималку поставщика из companies"""
    company = db.companies.find_one(
        {'id': supplier_id},
        {'min_order_amount': 1}
    )
    if company and company.get('min_order_amount'):
        return float(company['min_order_amount'])
    return DEFAULT_MIN_ORDER_AMOUNT


def load_all_supplier_minimums(db: Database, supplier_ids: Set[str]) -> Dict[str, float]:
    """Загружает минималки для списка поставщиков"""
    result = {}
    for sid in supplier_ids:
        result[sid] = get_supplier_min_order(db, sid)
    return result


def check_pack_tolerance(ref_pack: Optional[float], offer_pack: Optional[float], unit_type: str = None) -> bool:
    """
    Проверяет ±20% по фасовке.
    
    Для PIECE товаров: pack_value в reference может быть объём единицы (0.6л),
    а в offer - количество в упаковке (12шт). В этом случае пропускаем проверку.
    """
    # Если нет данных - пропускаем проверку
    if ref_pack is None or offer_pack is None:
        return True
    
    if ref_pack <= 0 or offer_pack <= 0:
        return True
    
    # Для PIECE: если значения сильно отличаются (>10x), скорее всего это разные единицы
    # (объём vs количество в упаковке) - пропускаем проверку
    if unit_type == 'PIECE':
        ratio = max(ref_pack, offer_pack) / min(ref_pack, offer_pack)
        if ratio > 10:
            # Скорее всего это разные единицы, пропускаем проверку
            return True
    
    lower = ref_pack * (1 - PACK_TOLERANCE)
    upper = ref_pack * (1 + PACK_TOLERANCE)
    return lower <= offer_pack <= upper


def check_critical_attrs(ref: Reference, offer: Offer) -> Tuple[bool, str]:
    """
    Проверяет критические атрибуты.
    Returns: (matches, reason)
    """
    # fat_pct для молочки
    if ref.super_class and ref.super_class.startswith('dairy'):
        if ref.fat_pct is not None and offer.fat_pct is not None:
            if ref.fat_pct != offer.fat_pct:
                return False, f"fat_pct mismatch: {ref.fat_pct}% vs {offer.fat_pct}%"
    
    # cut для рыбы/мяса
    if ref.super_class and (ref.super_class.startswith('seafood') or ref.super_class.startswith('meat')):
        if ref.cut is not None and offer.cut is not None:
            if ref.cut != offer.cut:
                return False, f"cut mismatch: {ref.cut} vs {offer.cut}"
    
    return True, ""


def apply_qty_constraints(qty: float, offer: Offer) -> Tuple[float, List[str]]:
    """
    Применяет min_order_qty и step_qty.
    Returns: (final_qty, flags)
    """
    flags = []
    final_qty = qty
    
    min_qty = offer.min_order_qty or 1
    step_qty = offer.step_qty or 1
    
    # Округление до min_order_qty
    if final_qty < min_qty:
        final_qty = float(min_qty)
        flags.append(OptFlag.MIN_QTY_ROUNDED.value)
    
    # Округление по step_qty
    if step_qty > 1:
        steps = math.ceil(final_qty / step_qty)
        new_qty = steps * step_qty
        if new_qty != final_qty:
            final_qty = float(new_qty)
            if OptFlag.STEP_QTY_APPLIED.value not in flags:
                flags.append(OptFlag.STEP_QTY_APPLIED.value)
    
    return final_qty, flags


def calculate_ppu_cost(offer: Offer, required_base: float) -> Optional[float]:
    """
    Рассчитывает стоимость по PPU для WEIGHT/VOLUME.
    required_base - сколько кг/л нужно
    Returns: total_cost или None если PPU недоступен
    """
    if offer.unit_type not in ('WEIGHT', 'VOLUME'):
        return None
    
    if not offer.price_per_base_unit or not offer.pack_value:
        # Пробуем вычислить price_per_base_unit
        if offer.pack_value and offer.pack_value > 0:
            offer.price_per_base_unit = offer.price / offer.pack_value
        else:
            return None
    
    pack_base = offer.pack_value or 1.0
    need_packs = math.ceil(required_base / pack_base)
    return need_packs * offer.price


# === OFFER MATCHING ===

def find_candidates(
    db: Database,
    ref: Reference,
    exclude_suppliers: Set[str] = None
) -> List[Offer]:
    """
    Находит кандидатов для reference по правилам matching.
    
    Жёсткие фильтры:
    - active = true
    - price > 0  
    - product_core_id == reference.product_core_id
    - unit_type == reference.unit_type
    """
    exclude_suppliers = exclude_suppliers or set()
    
    query = {
        'active': True,
        'price': {'$gt': 0},
        'product_core_id': ref.product_core_id,
        'unit_type': ref.unit_type,
    }
    
    if exclude_suppliers:
        query['supplier_company_id'] = {'$nin': list(exclude_suppliers)}
    
    items = list(db.supplier_items.find(query, {'_id': 0}))
    
    # Конвертируем в Offer
    offers = []
    for item in items:
        # Получаем название поставщика
        supplier_id = item.get('supplier_company_id', '')
        supplier_name = item.get('supplier_name', '')
        if not supplier_name:
            company = db.companies.find_one({'id': supplier_id}, {'companyName': 1, 'name': 1})
            supplier_name = company.get('companyName', company.get('name', 'Unknown')) if company else 'Unknown'
        
        # Определяем pack_value
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
        
        # Вычисляем price_per_base_unit для WEIGHT/VOLUME
        if offer.unit_type in ('WEIGHT', 'VOLUME') and pack_value and pack_value > 0:
            offer.price_per_base_unit = offer.price / pack_value
        
        offers.append(offer)
    
    return offers


def pick_best_offer(
    ref: Reference,
    qty: float,
    candidates: List[Offer],
    prefer_supplier_id: Optional[str] = None
) -> Tuple[Optional[Offer], List[str]]:
    """
    Выбирает лучший оффер из кандидатов.
    
    Tier 0: pack ±20%
    Tier 1: PPU fallback (только WEIGHT/VOLUME)
    
    Returns: (offer, flags)
    """
    if not candidates:
        return None, [OptFlag.NO_OFFER_FOUND.value]
    
    flags = []
    
    # Фильтруем по критическим атрибутам
    valid_candidates = []
    for offer in candidates:
        ok, reason = check_critical_attrs(ref, offer)
        if ok:
            valid_candidates.append(offer)
    
    if not valid_candidates:
        return None, [OptFlag.NO_OFFER_FOUND.value]
    
    # Tier 0: Ищем с pack ±20%
    tier0 = []
    for offer in valid_candidates:
        if check_pack_tolerance(ref.pack_value, offer.pack_value):
            tier0.append(offer)
    
    # Если есть brand preference - сначала ищем с нужным брендом
    if ref.brand_id and tier0:
        brand_matches = [o for o in tier0 if o.brand_id == ref.brand_id]
        if brand_matches:
            tier0_with_brand = brand_matches
        else:
            tier0_with_brand = tier0
            if tier0:
                flags.append(OptFlag.BRAND_REPLACED.value)
    else:
        tier0_with_brand = tier0
    
    # Выбираем лучший по цене из tier0
    if tier0_with_brand:
        # Если есть предпочтительный поставщик и он есть в списке
        if prefer_supplier_id:
            preferred = [o for o in tier0_with_brand if o.supplier_id == prefer_supplier_id]
            if preferred:
                best = min(preferred, key=lambda o: o.price)
                return best, flags
        
        # Иначе просто минимум по цене
        best = min(tier0_with_brand, key=lambda o: o.price)
        
        # Проверяем pack tolerance
        if ref.pack_value and best.pack_value:
            if abs(ref.pack_value - best.pack_value) / ref.pack_value > 0.01:
                flags.append(OptFlag.PACK_TOLERANCE_USED.value)
        
        return best, flags
    
    # Tier 1: PPU fallback (только WEIGHT/VOLUME)
    if ref.unit_type in ('WEIGHT', 'VOLUME'):
        ppu_candidates = []
        for offer in valid_candidates:
            cost = calculate_ppu_cost(offer, qty)
            if cost is not None:
                ppu_candidates.append((offer, cost))
        
        if ppu_candidates:
            # Сортируем по total_cost
            ppu_candidates.sort(key=lambda x: x[1])
            best_offer, _ = ppu_candidates[0]
            
            flags.append(OptFlag.PPU_FALLBACK_USED.value)
            
            # Проверяем бренд
            if ref.brand_id and best_offer.brand_id != ref.brand_id:
                if OptFlag.BRAND_REPLACED.value not in flags:
                    flags.append(OptFlag.BRAND_REPLACED.value)
            
            return best_offer, flags
    
    return None, [OptFlag.NO_OFFER_FOUND.value]


# === MAIN OPTIMIZER ===

def load_cart_intents(db: Database, user_id: str) -> List[CartIntent]:
    """Загружает интенты из корзины"""
    # Сначала пробуем новую коллекцию cart_intents
    intents_raw = list(db.cart_intents.find({'user_id': user_id}, {'_id': 0}))
    
    if intents_raw:
        return [
            CartIntent(
                reference_id=i['reference_id'],
                qty=i['qty'],
                user_id=user_id
            )
            for i in intents_raw
        ]
    
    # Fallback: старая корзина cart_items_v12
    old_cart = list(db.cart_items_v12.find({'user_id': user_id}, {'_id': 0}))
    return [
        CartIntent(
            reference_id=i.get('reference_id', ''),
            qty=i.get('user_qty', 1),
            user_id=user_id
        )
        for i in old_cart if i.get('reference_id')
    ]


def load_reference(db: Database, reference_id: str) -> Optional[Reference]:
    """Загружает reference по ID"""
    # Сначала catalog_references
    ref_data = db.catalog_references.find_one({'reference_id': reference_id}, {'_id': 0})
    
    if not ref_data:
        # Fallback: favorites_v12
        ref_data = db.favorites_v12.find_one({'reference_id': reference_id}, {'_id': 0})
    
    if not ref_data:
        # Еще fallback: по id
        ref_data = db.favorites_v12.find_one({'id': reference_id}, {'_id': 0})
        if ref_data:
            ref_data['reference_id'] = ref_data.get('id', reference_id)
    
    if not ref_data:
        return None
    
    return Reference(
        reference_id=ref_data.get('reference_id', reference_id),
        product_core_id=ref_data.get('product_core_id', ''),
        unit_type=ref_data.get('unit_type', 'PIECE'),
        pack_value=ref_data.get('pack_value'),
        pack_unit=ref_data.get('pack_unit'),
        brand_id=ref_data.get('brand_id'),
        name=ref_data.get('name', ref_data.get('product_name', '')),
        super_class=ref_data.get('super_class', ''),
        fat_pct=ref_data.get('fat_pct'),
        cut=ref_data.get('cut'),
    )


def build_initial_plan(
    db: Database,
    intents: List[CartIntent]
) -> Tuple[List[PlanLine], List[str]]:
    """
    Строит начальный план: для каждого intent подбирает лучший offer.
    
    Returns: (lines, unmatched_reference_ids)
    """
    lines = []
    unmatched = []
    
    for intent in intents:
        ref = load_reference(db, intent.reference_id)
        if not ref:
            logger.warning(f"Reference not found: {intent.reference_id}")
            unmatched.append(intent.reference_id)
            continue
        
        if not ref.product_core_id:
            logger.warning(f"Reference has no product_core_id: {intent.reference_id}")
            unmatched.append(intent.reference_id)
            continue
        
        # Ищем кандидатов
        candidates = find_candidates(db, ref)
        
        if not candidates:
            logger.warning(f"No candidates for reference: {intent.reference_id}")
            unmatched.append(intent.reference_id)
            continue
        
        # Выбираем лучший оффер
        offer, flags = pick_best_offer(ref, intent.qty, candidates)
        
        if not offer:
            unmatched.append(intent.reference_id)
            continue
        
        # Применяем qty constraints
        final_qty, qty_flags = apply_qty_constraints(intent.qty, offer)
        flags.extend(qty_flags)
        
        # Создаём строку плана
        line = PlanLine(
            reference_id=intent.reference_id,
            reference_name=ref.name,
            offer=offer,
            user_qty=intent.qty,
            final_qty=final_qty,
            line_total=final_qty * offer.price,
            flags=flags,
            original_brand=ref.brand_id,
            new_brand=offer.brand_id if OptFlag.BRAND_REPLACED.value in flags else None,
            original_pack=f"{ref.pack_value} {ref.pack_unit}" if ref.pack_value else None,
            new_pack=f"{offer.pack_value} {offer.pack_unit}" if offer.pack_value and OptFlag.PACK_TOLERANCE_USED.value in flags else None,
        )
        lines.append(line)
    
    return lines, unmatched


def group_by_supplier(
    lines: List[PlanLine],
    supplier_mins: Dict[str, float]
) -> Dict[str, SupplierPlan]:
    """Группирует строки по поставщикам"""
    groups: Dict[str, SupplierPlan] = {}
    
    for line in lines:
        sid = line.offer.supplier_id
        if sid not in groups:
            groups[sid] = SupplierPlan(
                supplier_id=sid,
                supplier_name=line.offer.supplier_name,
                min_order_amount=supplier_mins.get(sid, DEFAULT_MIN_ORDER_AMOUNT)
            )
        groups[sid].lines.append(line)
        groups[sid].subtotal += line.line_total
    
    # Вычисляем deficit и meets_minimum
    for plan in groups.values():
        plan.deficit = max(0, plan.min_order_amount - plan.subtotal)
        plan.meets_minimum = plan.deficit <= 0
    
    return groups


def try_move_line_to_other_supplier(
    db: Database,
    line: PlanLine,
    current_supplier_id: str,
    target_suppliers: Set[str],
    supplier_mins: Dict[str, float]
) -> Optional[Tuple[PlanLine, str]]:
    """
    Пытается перенести строку к другому поставщику.
    
    Returns: (new_line, target_supplier_id) или None
    """
    ref = load_reference(db, line.reference_id)
    if not ref:
        return None
    
    # Ищем кандидатов у других поставщиков
    exclude = {current_supplier_id}
    candidates = find_candidates(db, ref, exclude_suppliers=exclude)
    
    if not candidates:
        return None
    
    # Предпочитаем поставщиков из target_suppliers (где уже есть заказ)
    preferred_candidates = [c for c in candidates if c.supplier_id in target_suppliers]
    
    if preferred_candidates:
        offer, flags = pick_best_offer(ref, line.user_qty, preferred_candidates)
    else:
        offer, flags = pick_best_offer(ref, line.user_qty, candidates)
    
    if not offer:
        return None
    
    # Применяем qty constraints
    final_qty, qty_flags = apply_qty_constraints(line.user_qty, offer)
    flags.extend(qty_flags)
    
    # Добавляем флаг SUPPLIER_CHANGED
    flags.append(OptFlag.SUPPLIER_CHANGED.value)
    
    new_line = PlanLine(
        reference_id=line.reference_id,
        reference_name=line.reference_name,
        offer=offer,
        user_qty=line.user_qty,
        final_qty=final_qty,
        line_total=final_qty * offer.price,
        flags=flags,
        original_brand=ref.brand_id,
        new_brand=offer.brand_id if OptFlag.BRAND_REPLACED.value in flags else None,
    )
    
    return new_line, offer.supplier_id


def eliminate_under_min_suppliers(
    db: Database,
    groups: Dict[str, SupplierPlan],
    supplier_mins: Dict[str, float]
) -> Dict[str, SupplierPlan]:
    """
    Переносит позиции от поставщиков под минималкой к другим.
    """
    # Находим поставщиков под минималкой
    under_min = [sid for sid, plan in groups.items() if not plan.meets_minimum]
    
    if not under_min:
        return groups
    
    # Сортируем по deficit (сначала с меньшим deficit - легче решить)
    under_min.sort(key=lambda sid: groups[sid].deficit)
    
    for weak_sid in under_min:
        weak_plan = groups.get(weak_sid)
        if not weak_plan or weak_plan.meets_minimum:
            continue
        
        # Целевые поставщики - те кто над минималкой
        target_suppliers = {sid for sid, p in groups.items() if p.meets_minimum and sid != weak_sid}
        
        # Пробуем перенести каждую строку
        lines_to_move = list(weak_plan.lines)
        
        for line in lines_to_move:
            result = try_move_line_to_other_supplier(
                db, line, weak_sid, target_suppliers, supplier_mins
            )
            
            if result:
                new_line, target_sid = result
                
                # Удаляем из слабого поставщика
                weak_plan.lines.remove(line)
                weak_plan.subtotal -= line.line_total
                
                # Добавляем к целевому
                if target_sid not in groups:
                    groups[target_sid] = SupplierPlan(
                        supplier_id=target_sid,
                        supplier_name=new_line.offer.supplier_name,
                        min_order_amount=supplier_mins.get(target_sid, DEFAULT_MIN_ORDER_AMOUNT)
                    )
                
                groups[target_sid].lines.append(new_line)
                groups[target_sid].subtotal += new_line.line_total
                
                # Обновляем статусы
                weak_plan.deficit = max(0, weak_plan.min_order_amount - weak_plan.subtotal)
                weak_plan.meets_minimum = weak_plan.deficit <= 0
                
                groups[target_sid].deficit = max(0, groups[target_sid].min_order_amount - groups[target_sid].subtotal)
                groups[target_sid].meets_minimum = groups[target_sid].deficit <= 0
                
                target_suppliers.add(target_sid)
        
        # Удаляем пустых поставщиков
        if not weak_plan.lines:
            del groups[weak_sid]
    
    return groups


def apply_topup_10pct(
    groups: Dict[str, SupplierPlan],
    supplier_mins: Dict[str, float]
) -> Dict[str, SupplierPlan]:
    """
    Применяет +10% к qty для достижения минималки.
    ТОЛЬКО увеличение существующих позиций, НЕ добавление новых.
    """
    for sid, plan in groups.items():
        if plan.meets_minimum:
            continue
        
        deficit = plan.deficit
        
        # Сортируем строки по "шагу стоимости" (дешевле увеличивать)
        lines_by_cost = sorted(
            plan.lines,
            key=lambda l: l.offer.price * (l.offer.min_order_qty or 1)
        )
        
        for line in lines_by_cost:
            if deficit <= 0:
                break
            
            # Максимум +10% от текущего qty
            max_increase = line.final_qty * MAX_TOPUP_PERCENT
            
            # Округляем по min_order_qty/step_qty
            step = max(line.offer.min_order_qty or 1, line.offer.step_qty or 1)
            steps_to_add = min(
                math.ceil(max_increase / step),
                math.ceil(deficit / (step * line.offer.price))
            )
            
            if steps_to_add > 0:
                add_qty = steps_to_add * step
                add_cost = add_qty * line.offer.price
                
                line.final_qty += add_qty
                line.line_total = line.final_qty * line.offer.price
                
                if OptFlag.AUTO_TOPUP_10PCT.value not in line.flags:
                    line.flags.append(OptFlag.AUTO_TOPUP_10PCT.value)
                
                deficit -= add_cost
        
        # Обновляем subtotal
        plan.subtotal = sum(l.line_total for l in plan.lines)
        plan.deficit = max(0, plan.min_order_amount - plan.subtotal)
        plan.meets_minimum = plan.deficit <= 0
    
    return groups


def build_final_plan(db: Database, user_id: str) -> OptimizationResult:
    """
    Главная функция оптимизации.
    
    Алгоритм:
    1. Загрузить intents из корзины
    2. Подобрать offer для каждого intent
    3. Сгруппировать по поставщикам
    4. Перенести позиции от слабых поставщиков
    5. Применить +10% topup
    6. Проверить что нет поставщиков под минималкой
    """
    # 1. Load intents
    intents = load_cart_intents(db, user_id)
    
    if not intents:
        return OptimizationResult(
            success=True,
            suppliers=[],
            total=0.0,
            unmatched_intents=[]
        )
    
    # 2. Build initial plan
    lines, unmatched = build_initial_plan(db, intents)
    
    if not lines:
        return OptimizationResult(
            success=False,
            suppliers=[],
            total=0.0,
            unmatched_intents=unmatched,
            blocked_reason="Не найдено ни одного подходящего оффера"
        )
    
    # Get supplier IDs and load minimums
    supplier_ids = {line.offer.supplier_id for line in lines}
    supplier_mins = load_all_supplier_minimums(db, supplier_ids)
    
    # 3. Group by supplier
    groups = group_by_supplier(lines, supplier_mins)
    
    # 4. Eliminate under-min suppliers by moving lines
    groups = eliminate_under_min_suppliers(db, groups, supplier_mins)
    
    # 5. Apply +10% topup where needed
    groups = apply_topup_10pct(groups, supplier_mins)
    
    # 6. Second pass: try to eliminate again after topup
    groups = eliminate_under_min_suppliers(db, groups, supplier_mins)
    
    # 7. Check for remaining under-min suppliers
    still_under_min = [sid for sid, p in groups.items() if not p.meets_minimum]
    
    if still_under_min:
        # Блокируем checkout
        supplier_names = [groups[sid].supplier_name for sid in still_under_min]
        return OptimizationResult(
            success=False,
            suppliers=list(groups.values()),
            total=sum(p.subtotal for p in groups.values()),
            unmatched_intents=unmatched,
            blocked_reason=f"Невозможно достичь минималки для: {', '.join(supplier_names)}. "
                          f"Добавьте товары или удалите позиции этих поставщиков."
        )
    
    # Success!
    return OptimizationResult(
        success=True,
        suppliers=list(groups.values()),
        total=sum(p.subtotal for p in groups.values()),
        unmatched_intents=unmatched
    )


def get_plan_summary_for_ui(result: OptimizationResult) -> Dict[str, Any]:
    """Конвертирует результат оптимизации в формат для UI"""
    suppliers_data = []
    
    for plan in result.suppliers:
        items_data = []
        for line in plan.lines:
            items_data.append({
                'reference_id': line.reference_id,
                'product_name': line.reference_name or line.offer.name_raw,
                'supplier_item_id': line.offer.supplier_item_id,
                'user_qty': line.user_qty,
                'final_qty': line.final_qty,
                'price': line.offer.price,
                'line_total': line.line_total,
                'unit_type': line.offer.unit_type,
                'flags': line.flags,
                # Для бейджей
                'original_brand': line.original_brand,
                'new_brand': line.new_brand,
                'original_pack': line.original_pack,
                'new_pack': line.new_pack,
            })
        
        suppliers_data.append({
            'supplier_id': plan.supplier_id,
            'supplier_name': plan.supplier_name,
            'items': items_data,
            'subtotal': plan.subtotal,
            'min_order_amount': plan.min_order_amount,
            'deficit': plan.deficit,
            'meets_minimum': plan.meets_minimum,
        })
    
    return {
        'success': result.success,
        'suppliers': suppliers_data,
        'total': result.total,
        'unmatched_intents': result.unmatched_intents,
        'blocked_reason': result.blocked_reason,
    }
