"""
Скрипт для назначения product_core_id на основе super_class

ПРОБЛЕМА:
- 77% активных товаров (5998 из 7790) не имеют product_core_id
- Без product_core_id оптимизатор не может найти замену для товара
- Товары с пустым product_core_id получают статус "Нет доступных предложений"

РЕШЕНИЕ:
- Назначить product_core_id = super_class для всех товаров где:
  - product_core_id пустой или отсутствует
  - super_class заполнен
"""

import os
import logging
from pymongo import MongoClient

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def fix_product_core_ids(db, dry_run=True):
    """
    Назначает product_core_id для товаров на основе super_class.
    
    Args:
        db: MongoDB database instance
        dry_run: Если True, только показывает что будет изменено
    
    Returns:
        dict с результатами операции
    """
    
    # Находим товары без product_core_id но с super_class
    query = {
        'active': True,
        'super_class': {'$exists': True, '$ne': None, '$ne': ''},
        '$or': [
            {'product_core_id': None},
            {'product_core_id': ''},
            {'product_core_id': {'$exists': False}}
        ]
    }
    
    items_to_fix = list(db.supplier_items.find(query, {'_id': 1, 'id': 1, 'name_raw': 1, 'super_class': 1}))
    
    logger.info(f"Найдено {len(items_to_fix)} товаров для исправления")
    
    if dry_run:
        # Показываем примеры
        logger.info("=== DRY RUN - Примеры исправлений ===")
        for item in items_to_fix[:20]:
            logger.info(f"  [{item.get('super_class')}] {item.get('name_raw', 'N/A')[:50]}")
        
        return {
            'status': 'dry_run',
            'to_fix': len(items_to_fix),
            'fixed': 0,
            'errors': 0
        }
    
    # Выполняем исправления
    fixed = 0
    errors = 0
    
    for item in items_to_fix:
        try:
            new_core_id = item['super_class']
            
            result = db.supplier_items.update_one(
                {'_id': item['_id']},
                {'$set': {'product_core_id': new_core_id}}
            )
            
            if result.modified_count > 0:
                fixed += 1
            
        except Exception as e:
            logger.error(f"Ошибка при обновлении {item.get('id')}: {e}")
            errors += 1
    
    logger.info(f"=== РЕЗУЛЬТАТ ===")
    logger.info(f"Исправлено: {fixed}")
    logger.info(f"Ошибок: {errors}")
    
    return {
        'status': 'completed',
        'to_fix': len(items_to_fix),
        'fixed': fixed,
        'errors': errors
    }


def get_stats(db):
    """Возвращает статистику по product_core_id"""
    
    total_active = db.supplier_items.count_documents({'active': True})
    
    no_core_id = db.supplier_items.count_documents({
        'active': True,
        '$or': [
            {'product_core_id': None},
            {'product_core_id': ''},
            {'product_core_id': {'$exists': False}}
        ]
    })
    
    no_super_class = db.supplier_items.count_documents({
        'active': True,
        '$or': [
            {'super_class': None},
            {'super_class': ''},
            {'super_class': {'$exists': False}}
        ]
    })
    
    fixable = db.supplier_items.count_documents({
        'active': True,
        'super_class': {'$exists': True, '$ne': None, '$ne': ''},
        '$or': [
            {'product_core_id': None},
            {'product_core_id': ''},
            {'product_core_id': {'$exists': False}}
        ]
    })
    
    return {
        'total_active': total_active,
        'no_product_core_id': no_core_id,
        'no_super_class': no_super_class,
        'fixable': fixable,
        'pct_no_core': round(no_core_id * 100 / total_active, 1) if total_active > 0 else 0,
        'pct_fixable': round(fixable * 100 / total_active, 1) if total_active > 0 else 0
    }


if __name__ == '__main__':
    import sys
    
    # Подключение к БД
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    
    client = MongoClient(mongo_url)
    db = client[db_name]
    
    # Статистика до
    logger.info("=== СТАТИСТИКА ДО ИСПРАВЛЕНИЯ ===")
    stats_before = get_stats(db)
    for k, v in stats_before.items():
        logger.info(f"  {k}: {v}")
    
    # Проверяем аргументы
    if len(sys.argv) > 1 and sys.argv[1] == '--apply':
        logger.info("\n=== ПРИМЕНЕНИЕ ИСПРАВЛЕНИЙ ===")
        result = fix_product_core_ids(db, dry_run=False)
    else:
        logger.info("\n=== DRY RUN (добавьте --apply для применения) ===")
        result = fix_product_core_ids(db, dry_run=True)
    
    logger.info(f"\nРезультат: {result}")
    
    # Статистика после (только если применили)
    if result['status'] == 'completed':
        logger.info("\n=== СТАТИСТИКА ПОСЛЕ ИСПРАВЛЕНИЯ ===")
        stats_after = get_stats(db)
        for k, v in stats_after.items():
            logger.info(f"  {k}: {v}")
