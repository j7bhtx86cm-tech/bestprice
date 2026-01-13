"""
BestPrice v12 - Test Favorites Seeder

Эндпоинт для тестирования (п.14 ТЗ):
- Добавить 100 случайных карточек в избранное
"""

import os
import uuid
import random
import logging
from datetime import datetime, timezone
from typing import Dict, Any, Optional, List

from pymongo.database import Database

from .catalog import get_db, generate_catalog_references

logger = logging.getLogger(__name__)


def seed_random_favorites(
    db: Database,
    user_id: str,
    count: int = 100,
    filters: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Добавляет случайные карточки каталога в избранное (п.14 ТЗ)
    
    Args:
        db: MongoDB database
        user_id: ID пользователя
        count: Количество карточек (default=100)
        filters: Опциональные фильтры
    
    Returns:
        Statistics dict
    """
    logger.info(f"🎲 Seeding {count} random favorites for user {user_id}")
    
    # Проверяем есть ли catalog_references
    total_refs = db.catalog_references.count_documents({})
    
    if total_refs == 0:
        logger.info("   No catalog_references found, generating...")
        generate_catalog_references(db)
        total_refs = db.catalog_references.count_documents({})
    
    logger.info(f"   Total catalog references available: {total_refs}")
    
    # Строим query для фильтрации
    query = {}
    
    if filters:
        if filters.get('only_active'):
            query['best_price'] = {'$gt': 0}
        if filters.get('with_pack'):
            query['pack_value'] = {'$ne': None}
        if filters.get('super_class'):
            query['super_class'] = {'$regex': f"^{filters['super_class']}", '$options': 'i'}
    
    # Получаем все подходящие references
    all_refs = list(db.catalog_references.find(query, {'_id': 0, 'reference_id': 1, 'name': 1, 'product_core_id': 1, 'unit_type': 1, 'pack_value': 1, 'pack_unit': 1, 'brand_id': 1, 'origin_country_id': 1, 'anchor_supplier_item_id': 1, 'super_class': 1, 'best_price': 1, 'best_supplier_id': 1}))
    
    if not all_refs:
        return {
            'status': 'error',
            'message': 'Нет подходящих карточек каталога',
            'added_count': 0,
            'skipped_duplicates': 0
        }
    
    logger.info(f"   Found {len(all_refs)} matching references")
    
    # Получаем существующие избранные
    existing_favorites = set(
        f['reference_id'] 
        for f in db.favorites_v12.find({'user_id': user_id}, {'_id': 0, 'reference_id': 1})
    )
    
    logger.info(f"   User already has {len(existing_favorites)} favorites")
    
    # Выбираем случайные, исключая дубликаты
    available_refs = [r for r in all_refs if r['reference_id'] not in existing_favorites]
    
    if not available_refs:
        return {
            'status': 'ok',
            'message': 'Все карточки уже в избранном',
            'added_count': 0,
            'skipped_duplicates': len(existing_favorites)
        }
    
    # Случайная выборка
    to_add = random.sample(available_refs, min(count, len(available_refs)))
    
    # Добавляем в избранное
    added = 0
    skipped = 0
    
    for ref in to_add:
        favorite = {
            'id': f"fav_{ref['reference_id']}_{uuid.uuid4().hex[:8]}",
            'user_id': user_id,
            'reference_id': ref['reference_id'],
            'product_name': ref.get('name', ''),
            'product_core_id': ref.get('product_core_id'),
            'unit_type': ref.get('unit_type'),
            'pack_value': ref.get('pack_value'),
            'pack_unit': ref.get('pack_unit'),
            'brand_id': ref.get('brand_id'),
            'origin_country': ref.get('origin_country_id'),
            'anchor_supplier_item_id': ref.get('anchor_supplier_item_id'),
            'super_class': ref.get('super_class'),
            'best_price': ref.get('best_price'),
            'best_supplier_id': ref.get('best_supplier_id'),
            'brand_critical': True,  # По умолчанию True по ТЗ
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        
        try:
            db.favorites_v12.insert_one(favorite)
            added += 1
        except Exception as e:
            logger.error(f"   Error adding favorite: {e}")
            skipped += 1
    
    # Создаём индексы
    db.favorites_v12.create_index([('user_id', 1), ('reference_id', 1)], unique=True)
    db.favorites_v12.create_index('user_id')
    
    logger.info(f"✅ Seeded {added} favorites, skipped {skipped}")
    
    return {
        'status': 'ok',
        'message': f'Добавлено {added} карточек в избранное',
        'added_count': added,
        'skipped_duplicates': skipped,
        'total_favorites': len(existing_favorites) + added
    }


def get_user_favorites(db: Database, user_id: str, skip: int = 0, limit: int = 50) -> List[Dict]:
    """Получает избранное пользователя"""
    return list(db.favorites_v12.find(
        {'user_id': user_id},
        {'_id': 0}
    ).skip(skip).limit(limit))


def add_to_favorites(
    db: Database,
    user_id: str,
    reference_id: str
) -> Dict[str, Any]:
    """Добавляет карточку в избранное"""
    # Проверяем существование reference
    reference = db.catalog_references.find_one({'reference_id': reference_id}, {'_id': 0})
    
    if not reference:
        return {'status': 'not_found', 'message': 'Карточка не найдена'}
    
    # Проверяем дубликат
    existing = db.favorites_v12.find_one(
        {'user_id': user_id, 'reference_id': reference_id},
        {'_id': 0}
    )
    
    if existing:
        return {'status': 'duplicate', 'message': 'Уже в избранном', 'favorite_id': existing['id']}
    
    # Создаём favorite
    favorite = {
        'id': f"fav_{reference_id}_{uuid.uuid4().hex[:8]}",
        'user_id': user_id,
        'reference_id': reference_id,
        'product_name': reference.get('name', ''),
        'product_core_id': reference.get('product_core_id'),
        'unit_type': reference.get('unit_type'),
        'pack_value': reference.get('pack_value'),
        'pack_unit': reference.get('pack_unit'),
        'brand_id': reference.get('brand_id'),
        'origin_country': reference.get('origin_country_id'),
        'anchor_supplier_item_id': reference.get('anchor_supplier_item_id'),
        'super_class': reference.get('super_class'),
        'best_price': reference.get('best_price'),
        'best_supplier_id': reference.get('best_supplier_id'),
        'brand_critical': True,
        'created_at': datetime.now(timezone.utc).isoformat(),
    }
    
    db.favorites_v12.insert_one(favorite)
    
    return {'status': 'ok', 'favorite_id': favorite['id']}


def remove_from_favorites(db: Database, user_id: str, favorite_id: str) -> Dict[str, Any]:
    """Удаляет из избранного"""
    result = db.favorites_v12.delete_one({'user_id': user_id, 'id': favorite_id})
    if result.deleted_count > 0:
        return {'status': 'ok'}
    return {'status': 'not_found', 'message': 'Не найдено в избранном'}


# === CLI ===

if __name__ == '__main__':
    import argparse
    
    logging.basicConfig(level=logging.INFO)
    
    parser = argparse.ArgumentParser(description='BestPrice v12 Favorites Seeder')
    parser.add_argument('--user-id', required=True, help='User ID')
    parser.add_argument('--count', type=int, default=100, help='Number of favorites to add')
    parser.add_argument('--with-pack', action='store_true', help='Only items with pack info')
    
    args = parser.parse_args()
    
    db = get_db()
    
    filters = {}
    if args.with_pack:
        filters['with_pack'] = True
    
    result = seed_random_favorites(db, args.user_id, args.count, filters)
    print(f"Result: {result}")
