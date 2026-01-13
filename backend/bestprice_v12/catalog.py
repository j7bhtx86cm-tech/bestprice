"""
BestPrice v12 - Catalog Logic

Логика каталога:
- Генерация catalog_references из supplier_items
- Best Price расчёт для каталога
- STRICT pack matching
"""

import os
import uuid
import math
import logging
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional, Tuple
from collections import defaultdict

from pymongo import MongoClient
from pymongo.database import Database

logger = logging.getLogger(__name__)


# === GLOBAL PARAMETERS (п.3 ТЗ) ===
PACK_MATCH_MODE = "STRICT"


def get_db() -> Database:
    """Get MongoDB connection"""
    from dotenv import load_dotenv
    load_dotenv('/app/backend/.env')
    
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    client = MongoClient(mongo_url)
    return client[db_name]


def extract_pack_from_name(name: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Извлекает pack_value и pack_unit из названия товара.
    
    Примеры:
    - "БУЛГУР 3 кг" → (3.0, "кг")
    - "Креветки 16/20 1кг" → (1.0, "кг")
    - "Томаты консерв. 800г" → (0.8, "кг")
    - "Сок 1л" → (1.0, "л")
    
    Returns:
        (pack_value, pack_unit) или (None, None)
    """
    import re
    
    if not name:
        return None, None
    
    name_lower = name.lower()
    
    # Паттерны для веса
    weight_patterns = [
        r'(\d+(?:[.,]\d+)?)\s*кг\.?(?:\s|$|[^а-яa-z])',  # 3 кг, 1.5кг
        r'(\d+(?:[.,]\d+)?)\s*г\.?(?:\s|$|[^а-яa-z])',   # 800г, 500 г
        r'(\d+(?:[.,]\d+)?)\s*kg\.?(?:\s|$|[^а-яa-z])',  # 2kg
        r'(\d+(?:[.,]\d+)?)\s*g\.?(?:\s|$|[^а-яa-z])',   # 500g
    ]
    
    # Паттерны для объёма
    volume_patterns = [
        r'(\d+(?:[.,]\d+)?)\s*л\.?(?:\s|$|[^а-яa-z])',   # 1 л, 0.5л
        r'(\d+(?:[.,]\d+)?)\s*мл\.?(?:\s|$|[^а-яa-z])',  # 750мл
        r'(\d+(?:[.,]\d+)?)\s*l\.?(?:\s|$|[^а-яa-z])',   # 1l
        r'(\d+(?:[.,]\d+)?)\s*ml\.?(?:\s|$|[^а-яa-z])',  # 500ml
    ]
    
    # Паттерны для штук
    piece_patterns = [
        r'(\d+)\s*шт\.?(?:\s|$|[^а-яa-z])',  # 10 шт
        r'(\d+)\s*pcs\.?(?:\s|$|[^а-яa-z])', # 10pcs
    ]
    
    # Проверяем вес
    for pattern in weight_patterns:
        match = re.search(pattern, name_lower)
        if match:
            value_str = match.group(1).replace(',', '.')
            value = float(value_str)
            
            # Конвертируем граммы в кг
            if 'г' in pattern or 'g' in pattern:
                value = value / 1000
            
            return value, 'кг'
    
    # Проверяем объём
    for pattern in volume_patterns:
        match = re.search(pattern, name_lower)
        if match:
            value_str = match.group(1).replace(',', '.')
            value = float(value_str)
            
            # Конвертируем мл в л
            if 'мл' in pattern or 'ml' in pattern:
                value = value / 1000
            
            return value, 'л'
    
    # Проверяем штуки
    for pattern in piece_patterns:
        match = re.search(pattern, name_lower)
        if match:
            value = int(match.group(1))
            return float(value), 'шт'
    
    return None, None


def calculate_effective_qty(user_qty: float, min_order_qty: int) -> float:
    """
    Округление количества по минимальному заказу (п.4.1 ТЗ)
    
    effective_qty = ceil(user_qty / min_order_qty) * min_order_qty
    """
    if min_order_qty <= 1:
        return user_qty
    
    return math.ceil(user_qty / min_order_qty) * min_order_qty


def calculate_line_total(effective_qty: float, price: float) -> float:
    """
    Итоговая стоимость строки (п.4.2 ТЗ)
    
    line_total = effective_qty * price
    """
    return effective_qty * price


def check_strict_pack_match(
    offer_pack_value: Optional[float],
    offer_pack_unit: Optional[str],
    ref_pack_value: Optional[float],
    ref_pack_unit: Optional[str]
) -> bool:
    """
    STRICT фасовка (п.5.2 ТЗ)
    
    Оффер допускается только если:
    - offer.pack_unit == ref.pack_unit
    - offer.pack_value == ref.pack_value
    
    Если у reference нет pack → допускаем всех
    """
    # Если у reference нет pack, допускаем всех
    if ref_pack_value is None or ref_pack_unit is None:
        return True
    
    # Если у offer нет pack, не допускаем
    if offer_pack_value is None or offer_pack_unit is None:
        return False
    
    # Нормализуем единицы
    ref_unit_norm = ref_pack_unit.lower().strip()
    offer_unit_norm = offer_pack_unit.lower().strip()
    
    # Синонимы единиц
    unit_aliases = {
        'кг': ['кг', 'kg', 'кг.'],
        'г': ['г', 'g', 'гр', 'гр.', 'г.'],
        'л': ['л', 'l', 'л.'],
        'мл': ['мл', 'ml', 'мл.'],
        'шт': ['шт', 'шт.', 'pcs', 'штук', 'штука'],
    }
    
    # Находим канонические единицы
    def get_canonical(unit):
        for canonical, aliases in unit_aliases.items():
            if unit in aliases:
                return canonical
        return unit
    
    ref_canonical = get_canonical(ref_unit_norm)
    offer_canonical = get_canonical(offer_unit_norm)
    
    # Проверяем совпадение
    if ref_canonical != offer_canonical:
        return False
    
    # Проверяем значение (с погрешностью 1%)
    tolerance = 0.01
    if abs(ref_pack_value - offer_pack_value) / max(ref_pack_value, 0.001) > tolerance:
        return False
    
    return True


def get_best_price_for_reference(
    db: Database,
    product_core_id: str,
    unit_type: str,
    pack_value: Optional[float] = None,
    pack_unit: Optional[str] = None,
    user_qty: float = 1.0
) -> Tuple[Optional[float], Optional[str], Optional[Dict]]:
    """
    Находит Best Price для карточки каталога (п.6 ТЗ)
    
    Returns:
        (best_line_total, best_supplier_id, best_offer)
    """
    # Получаем кандидатов по правилам п.5.1
    query = {
        'active': True,
        'price': {'$gt': 0},
        'product_core_id': product_core_id,
        'unit_type': unit_type,
    }
    
    candidates = list(db.supplier_items.find(query, {'_id': 0}))
    
    if not candidates:
        return None, None, None
    
    best_line_total = None
    best_supplier_id = None
    best_offer = None
    
    for offer in candidates:
        # STRICT pack matching (п.5.2)
        offer_pack_value, offer_pack_unit = extract_pack_from_name(offer.get('name_raw', ''))
        
        # Если в supplier_item есть pack_qty, используем его
        if offer.get('pack_qty') and offer['pack_qty'] > 1:
            offer_pack_value = float(offer['pack_qty'])
            # Определяем unit по unit_type
            if unit_type == 'WEIGHT':
                offer_pack_unit = 'кг'
            elif unit_type == 'VOLUME':
                offer_pack_unit = 'л'
            else:
                offer_pack_unit = 'шт'
        
        if not check_strict_pack_match(offer_pack_value, offer_pack_unit, pack_value, pack_unit):
            continue
        
        # Расчёт line_total
        min_order_qty = offer.get('min_order_qty', 1)
        effective_qty = calculate_effective_qty(user_qty, min_order_qty)
        line_total = calculate_line_total(effective_qty, offer['price'])
        
        if best_line_total is None or line_total < best_line_total:
            best_line_total = line_total
            best_supplier_id = offer.get('supplier_company_id')
            best_offer = offer
    
    return best_line_total, best_supplier_id, best_offer


def generate_catalog_references(db: Database, limit: Optional[int] = None) -> Dict[str, Any]:
    """
    Генерирует catalog_references из supplier_items (п.2.1 ТЗ)
    
    Логика:
    - Группируем supplier_items по (product_core_id, unit_type)
    - Для каждой группы создаём одну reference карточку
    - anchor = оффер с лучшей ценой
    
    Returns:
        Statistics dict
    """
    logger.info("🔄 Generating catalog_references from supplier_items...")
    
    # Агрегация: группируем по product_core_id + unit_type
    pipeline = [
        {'$match': {'active': True, 'price': {'$gt': 0}, 'product_core_id': {'$ne': None}}},
        {'$group': {
            '_id': {
                'product_core_id': '$product_core_id',
                'unit_type': '$unit_type'
            },
            'items': {'$push': {
                'id': '$id',
                'name_raw': '$name_raw',
                'price': '$price',
                'supplier_company_id': '$supplier_company_id',
                'brand_id': '$brand_id',
                'origin_country': '$origin_country',
                'super_class': '$super_class',
                'min_order_qty': '$min_order_qty',
                'pack_qty': '$pack_qty',
            }},
            'count': {'$sum': 1}
        }},
        {'$sort': {'count': -1}}
    ]
    
    if limit:
        pipeline.append({'$limit': limit})
    
    groups = list(db.supplier_items.aggregate(pipeline))
    logger.info(f"   Found {len(groups)} unique product_core + unit_type combinations")
    
    # Создаём коллекцию catalog_references
    created = 0
    skipped = 0
    
    for group in groups:
        product_core_id = group['_id']['product_core_id']
        unit_type = group['_id']['unit_type']
        items = group['items']
        
        if not items:
            skipped += 1
            continue
        
        # Находим anchor (лучшая цена)
        best_item = min(items, key=lambda x: x.get('price', float('inf')))
        
        # Извлекаем pack из названия anchor
        pack_value, pack_unit = extract_pack_from_name(best_item.get('name_raw', ''))
        
        # Генерируем reference_id
        reference_id = f"ref_{product_core_id}_{unit_type}_{uuid.uuid4().hex[:8]}"
        
        # Создаём reference
        reference = {
            'reference_id': reference_id,
            'product_core_id': product_core_id,
            'unit_type': unit_type,
            'pack_value': pack_value,
            'pack_unit': pack_unit,
            'brand_id': best_item.get('brand_id'),
            'origin_country_id': best_item.get('origin_country'),
            'critical_attrs': None,
            'anchor_supplier_item_id': best_item['id'],
            'name': best_item.get('name_raw', product_core_id),
            'super_class': best_item.get('super_class'),
            'best_price': best_item.get('price'),
            'best_supplier_id': best_item.get('supplier_company_id'),
            'created_at': datetime.now(timezone.utc).isoformat(),
            'updated_at': datetime.now(timezone.utc).isoformat(),
        }
        
        # Upsert в коллекцию
        db.catalog_references.update_one(
            {'product_core_id': product_core_id, 'unit_type': unit_type},
            {'$set': reference},
            upsert=True
        )
        created += 1
    
    # Создаём индексы
    db.catalog_references.create_index('reference_id', unique=True)
    db.catalog_references.create_index([('product_core_id', 1), ('unit_type', 1)])
    db.catalog_references.create_index('super_class')
    
    stats = {
        'total_groups': len(groups),
        'created': created,
        'skipped': skipped,
    }
    
    logger.info(f"✅ Catalog references generated: {created} created, {skipped} skipped")
    return stats


def get_catalog_items(
    db: Database,
    filters: Optional[Dict[str, Any]] = None,
    skip: int = 0,
    limit: int = 50
) -> List[Dict]:
    """
    Получает список карточек каталога с Best Price
    
    Returns:
        List of catalog items with best_price info
    """
    query = {}
    
    if filters:
        if 'super_class' in filters:
            query['super_class'] = {'$regex': f"^{filters['super_class']}", '$options': 'i'}
        if 'product_core_id' in filters:
            query['product_core_id'] = filters['product_core_id']
        if 'search' in filters:
            query['name'] = {'$regex': filters['search'], '$options': 'i'}
    
    cursor = db.catalog_references.find(query, {'_id': 0}).skip(skip).limit(limit)
    items = list(cursor)
    
    # Получаем названия поставщиков
    supplier_ids = [item.get('best_supplier_id') for item in items if item.get('best_supplier_id')]
    companies = {c['id']: c.get('companyName', c.get('name', 'Unknown')) 
                 for c in db.companies.find({'id': {'$in': supplier_ids}}, {'_id': 0, 'id': 1, 'companyName': 1, 'name': 1})}
    
    # Добавляем информацию о поставщике
    for item in items:
        supplier_id = item.get('best_supplier_id')
        if supplier_id:
            item['best_supplier_name'] = companies.get(supplier_id, 'Unknown')
    
    return items


def update_best_prices(db: Database) -> Dict[str, Any]:
    """
    Обновляет best_price для всех catalog_references
    
    Вызывать периодически или после импорта прайсов
    """
    logger.info("🔄 Updating best prices for catalog references...")
    
    references = list(db.catalog_references.find({}, {'_id': 0}))
    updated = 0
    
    for ref in references:
        best_price, best_supplier_id, best_offer = get_best_price_for_reference(
            db,
            ref['product_core_id'],
            ref['unit_type'],
            ref.get('pack_value'),
            ref.get('pack_unit'),
            user_qty=1.0
        )
        
        if best_price is not None:
            db.catalog_references.update_one(
                {'reference_id': ref['reference_id']},
                {'$set': {
                    'best_price': best_price,
                    'best_supplier_id': best_supplier_id,
                    'anchor_supplier_item_id': best_offer['id'] if best_offer else ref.get('anchor_supplier_item_id'),
                    'updated_at': datetime.now(timezone.utc).isoformat()
                }}
            )
            updated += 1
    
    logger.info(f"✅ Updated {updated} catalog references")
    return {'updated': updated, 'total': len(references)}


# === CLI ===

if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='BestPrice v12 Catalog Manager')
    parser.add_argument('--generate', action='store_true', help='Generate catalog references')
    parser.add_argument('--update-prices', action='store_true', help='Update best prices')
    parser.add_argument('--limit', type=int, help='Limit number of references to generate')
    
    args = parser.parse_args()
    
    db = get_db()
    
    if args.generate:
        stats = generate_catalog_references(db, limit=args.limit)
        print(f"Generated: {stats}")
    
    if args.update_prices:
        stats = update_best_prices(db)
        print(f"Updated: {stats}")
