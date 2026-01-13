"""
BestPrice v12 - Cart Logic

Логика корзины (п.8-10 ТЗ):
- Add-to-cart с выбором anchor vs best_candidate
- STRICT pack matching
- Минималка 10k по поставщику
- Автодобивка 10%
"""

import os
import uuid
import math
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple

from pymongo.database import Database

from .models import (
    CartItem, ReasonCode, UnitType,
    MIN_SUPPLIER_ORDER_RUB, TOPUP_THRESHOLD_RUB
)
from .catalog import (
    get_db, extract_pack_from_name, 
    calculate_effective_qty, calculate_line_total,
    check_strict_pack_match, get_best_price_for_reference
)

logger = logging.getLogger(__name__)


def get_anchor_offer(db: Database, anchor_id: str) -> Optional[Dict]:
    """Получает anchor оффер по ID"""
    return db.supplier_items.find_one(
        {'id': anchor_id, 'active': True, 'price': {'$gt': 0}},
        {'_id': 0}
    )


def get_candidates_for_reference(
    db: Database,
    product_core_id: str,
    unit_type: str,
    pack_value: Optional[float] = None,
    pack_unit: Optional[str] = None
) -> List[Dict]:
    """
    Получает кандидатов по правилам п.5 ТЗ
    
    Жёсткие фильтры:
    - active = true
    - price > 0
    - product_core_id == reference.product_core_id
    - unit_type == reference.unit_type
    - STRICT pack match
    """
    query = {
        'active': True,
        'price': {'$gt': 0},
        'product_core_id': product_core_id,
        'unit_type': unit_type,
    }
    
    candidates = list(db.supplier_items.find(query, {'_id': 0}))
    
    # Фильтруем по STRICT pack
    if pack_value is not None and pack_unit is not None:
        filtered = []
        for offer in candidates:
            offer_pack_value, offer_pack_unit = extract_pack_from_name(offer.get('name_raw', ''))
            
            # Используем pack_qty если есть
            if offer.get('pack_qty') and offer['pack_qty'] > 1:
                offer_pack_value = float(offer['pack_qty'])
                if unit_type == 'WEIGHT':
                    offer_pack_unit = 'кг'
                elif unit_type == 'VOLUME':
                    offer_pack_unit = 'л'
                else:
                    offer_pack_unit = 'шт'
            
            if check_strict_pack_match(offer_pack_value, offer_pack_unit, pack_value, pack_unit):
                filtered.append(offer)
        
        candidates = filtered
    
    return candidates


def find_best_candidate(
    candidates: List[Dict],
    user_qty: float
) -> Tuple[Optional[Dict], Optional[float]]:
    """
    Находит лучшего кандидата по line_total
    
    Returns:
        (best_candidate, best_line_total)
    """
    if not candidates:
        return None, None
    
    best_candidate = None
    best_line_total = None
    
    for candidate in candidates:
        min_order_qty = candidate.get('min_order_qty', 1)
        effective_qty = calculate_effective_qty(user_qty, min_order_qty)
        line_total = calculate_line_total(effective_qty, candidate['price'])
        
        if best_line_total is None or line_total < best_line_total:
            best_line_total = line_total
            best_candidate = candidate
    
    return best_candidate, best_line_total


def add_to_cart(
    db: Database,
    user_id: str,
    reference_id: str,
    user_qty: float
) -> Dict[str, Any]:
    """
    Добавление из избранного в корзину (п.8 ТЗ)
    
    Алгоритм:
    1. Загрузить reference
    2. Загрузить anchor
    3. Если anchor валиден → посчитать anchor_line_total
    4. Собрать кандидатов
    5. Найти best_candidate
    6. Правило выбора:
       - Если anchor доступен и best < anchor → substitution
       - Иначе → anchor
       - Если anchor недоступен → best_candidate или NOT_FOUND
    
    Returns:
        Response dict
    """
    # 1. Загрузить reference
    reference = db.catalog_references.find_one(
        {'reference_id': reference_id},
        {'_id': 0}
    )
    
    if not reference:
        # Пробуем найти в favorites (для обратной совместимости)
        favorite = db.favorites.find_one({'id': reference_id}, {'_id': 0})
        if favorite:
            # Конвертируем favorite в reference формат
            reference = convert_favorite_to_reference(db, favorite)
        
        if not reference:
            return {
                'status': 'not_found',
                'message': 'Reference не найден',
                'reason_code': ReasonCode.NO_VALID_CANDIDATES.value
            }
    
    product_core_id = reference['product_core_id']
    unit_type = reference['unit_type']
    pack_value = reference.get('pack_value')
    pack_unit = reference.get('pack_unit')
    anchor_id = reference.get('anchor_supplier_item_id')
    
    # 2. Загрузить anchor
    anchor = None
    anchor_line_total = None
    
    if anchor_id:
        anchor = get_anchor_offer(db, anchor_id)
        if anchor:
            anchor_min_order = anchor.get('min_order_qty', 1)
            anchor_effective_qty = calculate_effective_qty(user_qty, anchor_min_order)
            anchor_line_total = calculate_line_total(anchor_effective_qty, anchor['price'])
    
    # 4. Собрать кандидатов
    candidates = get_candidates_for_reference(
        db, product_core_id, unit_type, pack_value, pack_unit
    )
    
    # 5. Найти best_candidate
    best_candidate, best_line_total = find_best_candidate(candidates, user_qty)
    
    # 6. Правило выбора
    selected_offer = None
    reason_code = None
    substitution_applied = False
    savings = None
    
    if anchor and anchor.get('active') and anchor.get('price', 0) > 0:
        # Anchor доступен
        if best_candidate and best_line_total < anchor_line_total:
            # Best дешевле → замена
            selected_offer = best_candidate
            reason_code = ReasonCode.SUBSTITUTED_CHEAPER
            substitution_applied = True
            savings = anchor_line_total - best_line_total
        else:
            # Anchor дешевле или равен → оставляем anchor
            selected_offer = anchor
            reason_code = ReasonCode.ANCHOR_USED_NO_CHEAPER
    else:
        # Anchor недоступен
        if best_candidate:
            selected_offer = best_candidate
            reason_code = ReasonCode.ANCHOR_INACTIVE_USED_BEST
        else:
            # NOT FOUND
            return {
                'status': 'not_found',
                'message': 'Этого товара сейчас нет у поставщиков. Давайте подберём замену — покажем самые похожие варианты в каталоге 🙂',
                'reason_code': ReasonCode.NO_VALID_CANDIDATES.value if not candidates else ReasonCode.NO_SAME_PACK_FOUND.value
            }
    
    # Расчёт финальных значений
    min_order_qty = selected_offer.get('min_order_qty', 1)
    effective_qty = calculate_effective_qty(user_qty, min_order_qty)
    line_total = calculate_line_total(effective_qty, selected_offer['price'])
    
    # Получаем название поставщика
    supplier_id = selected_offer.get('supplier_company_id')
    company = db.companies.find_one({'id': supplier_id}, {'_id': 0, 'companyName': 1, 'name': 1})
    supplier_name = company.get('companyName', company.get('name', 'Unknown')) if company else 'Unknown'
    
    # Создаём cart_item
    cart_item_id = f"cart_{uuid.uuid4().hex[:12]}"
    
    cart_item = {
        'cart_item_id': cart_item_id,
        'user_id': user_id,
        'reference_id': reference_id,
        'anchor_supplier_item_id': anchor_id or selected_offer['id'],
        'selected_supplier_item_id': selected_offer['id'],
        'supplier_id': supplier_id,
        'user_qty': user_qty,
        'effective_qty': effective_qty,
        'unit_type': unit_type,
        'price': selected_offer['price'],
        'line_total': line_total,
        'substitution_applied': substitution_applied,
        'topup_applied': False,
        'reason_code': reason_code.value if reason_code else None,
        'product_name': selected_offer.get('name_raw', reference.get('name', '')),
        'supplier_name': supplier_name,
        'min_order_qty': min_order_qty,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    
    # Добавляем информацию о замене
    if substitution_applied and anchor:
        anchor_company = db.companies.find_one({'id': anchor.get('supplier_company_id')}, {'_id': 0, 'companyName': 1, 'name': 1})
        cart_item['original_price'] = anchor['price']
        cart_item['original_supplier_name'] = anchor_company.get('companyName', anchor_company.get('name', 'Unknown')) if anchor_company else 'Unknown'
        cart_item['savings'] = savings
    
    # Сохраняем в корзину
    db.cart_items_v12.update_one(
        {'user_id': user_id, 'reference_id': reference_id},
        {'$set': cart_item},
        upsert=True
    )
    
    return {
        'status': 'ok',
        'cart_item': cart_item,
        'substituted': substitution_applied,
        'original_item_name': anchor.get('name_raw') if anchor and substitution_applied else None,
        'new_item_name': selected_offer.get('name_raw') if substitution_applied else None,
        'savings': savings,
        'reason_code': reason_code.value if reason_code else None,
    }


def convert_favorite_to_reference(db: Database, favorite: Dict) -> Optional[Dict]:
    """
    Конвертирует старый формат favorite в reference формат
    """
    from universal_super_class_mapper import detect_super_class
    from product_core_classifier import detect_product_core
    
    name = favorite.get('reference_name') or favorite.get('productName', '')
    
    if not name:
        return None
    
    # Определяем super_class и product_core
    super_class, _ = detect_super_class(name)
    product_core_id, _ = detect_product_core(name, super_class) if super_class else (None, 0)
    
    if not product_core_id:
        return None
    
    # Определяем unit_type
    unit_norm = favorite.get('unit_norm', 'kg')
    unit_type = 'WEIGHT'
    if unit_norm in ['pcs', 'шт']:
        unit_type = 'PIECE'
    elif unit_norm in ['l', 'л']:
        unit_type = 'VOLUME'
    
    # Извлекаем pack
    pack_value, pack_unit = extract_pack_from_name(name)
    if favorite.get('pack_size'):
        pack_value = favorite['pack_size']
    
    # Ищем anchor в supplier_items
    candidates = get_candidates_for_reference(db, product_core_id, unit_type, pack_value, pack_unit)
    
    anchor_id = None
    if candidates:
        best = min(candidates, key=lambda x: x.get('price', float('inf')))
        anchor_id = best['id']
    
    return {
        'reference_id': favorite['id'],
        'product_core_id': product_core_id,
        'unit_type': unit_type,
        'pack_value': pack_value,
        'pack_unit': pack_unit,
        'brand_id': favorite.get('brand_id'),
        'origin_country_id': favorite.get('origin_country'),
        'anchor_supplier_item_id': anchor_id,
        'name': name,
        'super_class': super_class,
    }


def get_cart_summary(db: Database, user_id: str) -> Dict[str, Any]:
    """
    Получает сводку по корзине (п.9 ТЗ)
    
    Returns:
        Cart summary with supplier grouping
    """
    items = list(db.cart_items_v12.find({'user_id': user_id}, {'_id': 0}))
    
    if not items:
        return {
            'items': [],
            'total': 0,
            'suppliers': [],
            'has_minimum_issues': False,
            'minimum_issues': []
        }
    
    # Группируем по поставщикам
    supplier_groups = {}
    for item in items:
        supplier_id = item['supplier_id']
        if supplier_id not in supplier_groups:
            supplier_groups[supplier_id] = {
                'supplier_id': supplier_id,
                'supplier_name': item.get('supplier_name', 'Unknown'),
                'items': [],
                'subtotal': 0
            }
        supplier_groups[supplier_id]['items'].append(item)
        supplier_groups[supplier_id]['subtotal'] += item['line_total']
    
    # Проверяем минималки
    suppliers = []
    minimum_issues = []
    
    for supplier_id, group in supplier_groups.items():
        subtotal = group['subtotal']
        deficit = MIN_SUPPLIER_ORDER_RUB - subtotal
        can_topup = 0 < deficit <= TOPUP_THRESHOLD_RUB
        
        supplier_info = {
            'supplier_id': supplier_id,
            'supplier_name': group['supplier_name'],
            'subtotal': subtotal,
            'deficit': max(0, deficit),
            'can_topup': can_topup,
            'items_count': len(group['items']),
            'meets_minimum': deficit <= 0
        }
        suppliers.append(supplier_info)
        
        if deficit > 0:
            minimum_issues.append(supplier_info)
    
    total = sum(item['line_total'] for item in items)
    
    return {
        'items': items,
        'total': total,
        'suppliers': suppliers,
        'has_minimum_issues': len(minimum_issues) > 0,
        'minimum_issues': minimum_issues
    }


def apply_topup(db: Database, user_id: str, supplier_id: str) -> Dict[str, Any]:
    """
    Применяет автодобивку для достижения минималки (п.10 ТЗ)
    
    Правила:
    - Применяется только если deficit <= 1000 (10%)
    - Увеличивает количество уже выбранных товаров
    - Минимизирует перерасход
    
    Returns:
        Result dict with applied topups
    """
    # Получаем позиции поставщика
    items = list(db.cart_items_v12.find(
        {'user_id': user_id, 'supplier_id': supplier_id},
        {'_id': 0}
    ))
    
    if not items:
        return {'status': 'error', 'message': 'Нет позиций для этого поставщика'}
    
    # Считаем текущую сумму
    current_subtotal = sum(item['line_total'] for item in items)
    deficit = MIN_SUPPLIER_ORDER_RUB - current_subtotal
    
    if deficit <= 0:
        return {'status': 'ok', 'message': 'Минималка уже достигнута', 'applied': []}
    
    if deficit > TOPUP_THRESHOLD_RUB:
        return {
            'status': 'error',
            'message': f'Дефицит {deficit:.0f}₽ превышает порог автодобивки ({TOPUP_THRESHOLD_RUB}₽)',
            'reason_code': ReasonCode.SUPPLIER_MIN_NOT_MET.value
        }
    
    # Сортируем по step_cost (шаг увеличения)
    items_with_step = []
    for item in items:
        min_order = item.get('min_order_qty', 1)
        step_qty = min_order if min_order > 0 else 1
        step_cost = step_qty * item['price']
        items_with_step.append({
            **item,
            'step_qty': step_qty,
            'step_cost': step_cost
        })
    
    # Сортируем по step_cost (сначала дешёвые шаги)
    items_with_step.sort(key=lambda x: x['step_cost'])
    
    # Жадно добавляем шаги пока не покроем deficit
    applied = []
    remaining_deficit = deficit
    
    for item in items_with_step:
        if remaining_deficit <= 0:
            break
        
        steps_needed = math.ceil(remaining_deficit / item['step_cost'])
        
        # Добавляем минимум 1 шаг
        steps_to_add = max(1, min(steps_needed, 3))  # Не более 3 шагов за раз
        added_qty = steps_to_add * item['step_qty']
        added_cost = steps_to_add * item['step_cost']
        
        new_effective_qty = item['effective_qty'] + added_qty
        new_line_total = new_effective_qty * item['price']
        
        # Обновляем в БД
        db.cart_items_v12.update_one(
            {'cart_item_id': item['cart_item_id']},
            {'$set': {
                'effective_qty': new_effective_qty,
                'line_total': new_line_total,
                'topup_applied': True,
                'reason_code': ReasonCode.TOPUP_APPLIED_QTY.value,
                'qty_increased_reason': f'Увеличено на {added_qty} для достижения минималки',
                'updated_at': datetime.now(timezone.utc).isoformat()
            }}
        )
        
        applied.append({
            'cart_item_id': item['cart_item_id'],
            'product_name': item['product_name'],
            'old_qty': item['effective_qty'],
            'new_qty': new_effective_qty,
            'added_cost': added_cost
        })
        
        remaining_deficit -= added_cost
    
    return {
        'status': 'ok',
        'message': f'Добавлено {len(applied)} позиций для достижения минималки',
        'applied': applied,
        'new_subtotal': current_subtotal + sum(a['added_cost'] for a in applied)
    }


def clear_cart(db: Database, user_id: str) -> Dict[str, Any]:
    """Очищает корзину пользователя"""
    result = db.cart_items_v12.delete_many({'user_id': user_id})
    return {'status': 'ok', 'deleted_count': result.deleted_count}


def remove_from_cart(db: Database, user_id: str, cart_item_id: str) -> Dict[str, Any]:
    """Удаляет позицию из корзины"""
    result = db.cart_items_v12.delete_one({'user_id': user_id, 'cart_item_id': cart_item_id})
    if result.deleted_count > 0:
        return {'status': 'ok'}
    return {'status': 'not_found', 'message': 'Позиция не найдена'}
