"""
BestPrice - Offer Validation Module

Hard gate для качества данных офферов.
Оффер НЕ публикуется, если не проходит валидацию.

Обязательные поля:
1. unit_type - единица измерения (WEIGHT/VOLUME/PIECE)
2. pack_qty/pack_value - фасовка/вес/объём (число > 0)
3. price - цена (число > 0)
4. supplier_company_id - поставщик
5. id - уникальный идентификатор оффера

Категорийные правила:
- Продукты питания: требуется pack_qty > 0 для WEIGHT/VOLUME
- Непищевые товары: допускается PIECE без pack_qty
"""

import logging
from typing import Dict, Any, List, Tuple, Optional
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ValidationError(str, Enum):
    """Типы ошибок валидации"""
    MISSING_PRICE = "MISSING_PRICE"
    INVALID_PRICE = "INVALID_PRICE"
    MISSING_UNIT_TYPE = "MISSING_UNIT_TYPE"
    MISSING_PACK_SIZE = "MISSING_PACK_SIZE"
    MISSING_SUPPLIER = "MISSING_SUPPLIER"
    MISSING_ID = "MISSING_ID"
    FOOD_WITHOUT_WEIGHT = "FOOD_WITHOUT_WEIGHT"


@dataclass
class ValidationResult:
    """Результат валидации оффера"""
    is_valid: bool
    errors: List[str]
    warnings: List[str]
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            'is_valid': self.is_valid,
            'errors': self.errors,
            'warnings': self.warnings
        }


# Категории продуктов питания, требующие вес/объём
FOOD_CATEGORIES = [
    'seafood', 'meat', 'dairy', 'vegetables', 'fruits', 
    'bakery', 'beverages', 'condiments', 'grains', 'canned', 
    'frozen', 'oils', 'pasta', 'spices', 'sauces', 'snacks',
    'confectionery', 'nuts', 'dried', 'alcohol'
]

# Непищевые категории, где PIECE допустим
NON_FOOD_CATEGORIES = [
    'packaging', 'supplies', 'equipment', 'cleaning', 
    'tableware', 'uniforms', 'other'
]


def is_food_category(super_class: str) -> bool:
    """Проверяет, является ли категория пищевой"""
    if not super_class:
        return False
    
    super_class_lower = super_class.lower()
    for cat in FOOD_CATEGORIES:
        if super_class_lower.startswith(cat):
            return True
    return False


def validate_offer(offer: Dict[str, Any]) -> ValidationResult:
    """
    Валидирует оффер по правилам публикации.
    
    Returns:
        ValidationResult с is_valid=True если оффер можно публиковать
    """
    errors = []
    warnings = []
    
    # 1. Проверка ID
    offer_id = offer.get('id') or offer.get('unique_key')
    if not offer_id:
        errors.append(ValidationError.MISSING_ID.value)
    
    # 2. Проверка поставщика
    supplier_id = offer.get('supplier_company_id')
    if not supplier_id:
        errors.append(ValidationError.MISSING_SUPPLIER.value)
    
    # 3. Проверка цены
    price = offer.get('price')
    if price is None:
        errors.append(ValidationError.MISSING_PRICE.value)
    elif not isinstance(price, (int, float)) or price <= 0:
        errors.append(ValidationError.INVALID_PRICE.value)
    
    # 4. Проверка единицы измерения
    unit_type = offer.get('unit_type')
    if not unit_type:
        errors.append(ValidationError.MISSING_UNIT_TYPE.value)
    
    # 5. Проверка фасовки
    pack_qty = offer.get('pack_qty') or offer.get('pack_value')
    super_class = offer.get('super_class', '')
    
    if is_food_category(super_class):
        # Для продуктов питания требуется фасовка
        if unit_type in ('WEIGHT', 'VOLUME'):
            if not pack_qty or pack_qty <= 0:
                errors.append(ValidationError.MISSING_PACK_SIZE.value)
        elif unit_type == 'PIECE':
            # PIECE для еды должен иметь pack_qty (вес единицы)
            if not pack_qty or pack_qty <= 0:
                # Это warning, не error - допускаем штучные товары
                warnings.append(f"PIECE food item without pack size: {offer.get('name_raw', '')[:50]}")
    else:
        # Непищевые - PIECE без фасовки допустим
        if unit_type in ('WEIGHT', 'VOLUME') and (not pack_qty or pack_qty <= 0):
            errors.append(ValidationError.MISSING_PACK_SIZE.value)
    
    is_valid = len(errors) == 0
    
    return ValidationResult(
        is_valid=is_valid,
        errors=errors,
        warnings=warnings
    )


def validate_offers_batch(offers: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Валидирует пакет офферов.
    
    Returns:
        {
            'total': int,
            'valid': int,
            'invalid': int,
            'invalid_items': List[{id, name, errors}],
            'warnings_count': int
        }
    """
    results = {
        'total': len(offers),
        'valid': 0,
        'invalid': 0,
        'invalid_items': [],
        'warnings_count': 0
    }
    
    for offer in offers:
        validation = validate_offer(offer)
        
        if validation.is_valid:
            results['valid'] += 1
        else:
            results['invalid'] += 1
            results['invalid_items'].append({
                'id': offer.get('id', offer.get('unique_key', 'N/A')),
                'name': offer.get('name_raw', '')[:50],
                'errors': validation.errors
            })
        
        results['warnings_count'] += len(validation.warnings)
    
    return results


def get_publishable_query() -> Dict[str, Any]:
    """
    Возвращает MongoDB query для фильтрации только публикуемых офферов.
    
    Использовать в каталоге, поиске, избранном.
    """
    return {
        'active': True,
        'price': {'$gt': 0},
        'unit_type': {'$exists': True, '$ne': None, '$ne': ''},
        'supplier_company_id': {'$exists': True, '$ne': None, '$ne': ''},
        'id': {'$exists': True, '$ne': None, '$ne': ''},
        # pack_qty проверяется для WEIGHT/VOLUME, для PIECE опционально
        '$or': [
            {'unit_type': {'$in': ['WEIGHT', 'VOLUME']}, 'pack_qty': {'$gt': 0}},
            {'unit_type': 'PIECE'}
        ]
    }


def mark_invalid_offers(db, dry_run: bool = True) -> Dict[str, Any]:
    """
    Помечает невалидные офферы как inactive.
    
    Args:
        db: MongoDB database
        dry_run: если True, только возвращает что будет помечено
    
    Returns:
        Статистика по операции
    """
    # Найти все невалидные офферы
    invalid_query = {
        'active': True,
        '$or': [
            {'price': {'$lte': 0}},
            {'price': {'$exists': False}},
            {'price': None},
            {'unit_type': {'$exists': False}},
            {'unit_type': None},
            {'unit_type': ''},
            {'supplier_company_id': {'$exists': False}},
            {'supplier_company_id': None},
            # WEIGHT/VOLUME без pack_qty
            {'unit_type': {'$in': ['WEIGHT', 'VOLUME']}, '$or': [
                {'pack_qty': {'$exists': False}},
                {'pack_qty': None},
                {'pack_qty': {'$lte': 0}}
            ]}
        ]
    }
    
    invalid_count = db.supplier_items.count_documents(invalid_query)
    
    if dry_run:
        # Показать примеры
        samples = list(db.supplier_items.find(
            invalid_query,
            {'_id': 0, 'name_raw': 1, 'price': 1, 'unit_type': 1, 'pack_qty': 1}
        ).limit(10))
        
        return {
            'dry_run': True,
            'would_mark_inactive': invalid_count,
            'samples': samples
        }
    
    # Пометить как inactive
    result = db.supplier_items.update_many(
        invalid_query,
        {'$set': {'active': False, 'inactive_reason': 'validation_failed'}}
    )
    
    return {
        'dry_run': False,
        'marked_inactive': result.modified_count
    }


def cleanup_favorites_invalid(db, user_id: str = None) -> Dict[str, Any]:
    """
    Удаляет невалидные позиции из избранного.
    
    Args:
        db: MongoDB database
        user_id: опционально, для конкретного пользователя
    
    Returns:
        Статистика по очистке
    """
    # Получить все reference_id из избранного
    fav_query = {'user_id': user_id} if user_id else {}
    favorites = list(db.favorites_v12.find(fav_query, {'_id': 0, 'reference_id': 1, 'user_id': 1}))
    
    if not favorites:
        return {'checked': 0, 'removed': 0}
    
    removed = 0
    
    for fav in favorites:
        ref_id = fav.get('reference_id')
        if not ref_id:
            continue
        
        # Проверить есть ли валидный оффер для этого reference
        # Ищем в catalog_references
        ref = db.catalog_references.find_one({'reference_id': ref_id}, {'product_core_id': 1, 'unit_type': 1})
        if not ref:
            # Reference не найден - удаляем из избранного
            db.favorites_v12.delete_one({'reference_id': ref_id, 'user_id': fav['user_id']})
            removed += 1
            continue
        
        # Проверить есть ли хотя бы один валидный оффер
        valid_offer_query = {
            **get_publishable_query(),
            'product_core_id': ref.get('product_core_id'),
            'unit_type': ref.get('unit_type')
        }
        
        has_valid_offer = db.supplier_items.count_documents(valid_offer_query) > 0
        
        if not has_valid_offer:
            db.favorites_v12.delete_one({'reference_id': ref_id, 'user_id': fav['user_id']})
            removed += 1
    
    return {
        'checked': len(favorites),
        'removed': removed
    }


def validate_cart_before_checkout(db, user_id: str) -> Tuple[bool, List[Dict], List[str]]:
    """
    Валидирует корзину перед оформлением заказа.
    
    Returns:
        (is_valid, removed_items, messages)
    """
    intents = list(db.cart_intents.find({'user_id': user_id}, {'_id': 0}))
    
    if not intents:
        return True, [], []
    
    removed_items = []
    messages = []
    
    for intent in intents:
        ref_id = intent.get('reference_id')
        
        # Получить reference
        ref = db.catalog_references.find_one({'reference_id': ref_id})
        if not ref:
            ref = db.favorites_v12.find_one({'reference_id': ref_id})
        
        if not ref:
            # Reference не найден
            db.cart_intents.delete_one({'user_id': user_id, 'reference_id': ref_id})
            removed_items.append({'reference_id': ref_id, 'reason': 'reference_not_found'})
            messages.append(f"Позиция удалена: товар не найден")
            continue
        
        # Проверить есть ли валидные офферы
        valid_query = {
            **get_publishable_query(),
            'product_core_id': ref.get('product_core_id'),
            'unit_type': ref.get('unit_type')
        }
        
        if db.supplier_items.count_documents(valid_query) == 0:
            db.cart_intents.delete_one({'user_id': user_id, 'reference_id': ref_id})
            removed_items.append({
                'reference_id': ref_id, 
                'name': ref.get('product_name', ref.get('name', '')),
                'reason': 'no_valid_offers'
            })
            messages.append(f"Позиция снята: некорректные данные поставщика ({ref.get('product_name', '')[:30]})")
    
    is_valid = len(removed_items) == 0
    
    return is_valid, removed_items, messages
