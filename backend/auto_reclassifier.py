"""
Автоматическая переклассификация товаров при запуске сервера.

Этот скрипт исправляет неверно классифицированные товары:
- meat → seafood (треска, тунец и т.д.)
- Товары без классификации

Запускается автоматически при старте backend.
"""

import logging
from typing import Tuple

logger = logging.getLogger(__name__)


def reclassify_items(db, limit: int = None) -> Tuple[int, int]:
    """
    Переклассификация товаров с использованием обновлённых правил.
    
    Args:
        db: MongoDB database instance
        limit: Максимальное количество товаров для обработки (None = все)
    
    Returns:
        (updated_count, error_count)
    """
    from universal_super_class_mapper import detect_super_class
    from product_core_classifier import detect_product_core
    
    logger.info("🔄 Starting automatic reclassification...")
    
    # Получаем товары которые могут быть неверно классифицированы
    # 1. Товары с meat где название содержит seafood keywords
    # 2. Товары без классификации
    
    seafood_keywords = [
        'треск', 'cod', 'тунец', 'tuna', 'лосос', 'salmon', 'семг', 'форел',
        'trout', 'сибас', 'seabass', 'дорад', 'dorado', 'минтай', 'pollock',
        'камбал', 'flounder', 'палтус', 'halibut', 'тюрбо', 'turbot',
        'сельд', 'herring', 'скумбри', 'mackerel', 'сардин', 'sardine',
        'шпрот', 'sprat', 'килька', 'угорь', 'eel', 'икра', 'caviar',
        'креветк', 'shrimp', 'кальмар', 'squid', 'осьминог', 'octopus',
        'мидии', 'mussel', 'устриц', 'oyster', 'краб', 'crab', 'лангустин',
        'навага', 'корюшк', 'мойва', 'анчоус', 'печень треск', 'морепродукт'
    ]
    
    # Создаём regex для seafood keywords
    seafood_regex = '|'.join(seafood_keywords)
    
    query = {
        'active': True,
        '$or': [
            # Товары с meat которые могут быть seafood
            {
                'super_class': {'$regex': '^meat', '$options': 'i'},
                'name_raw': {'$regex': seafood_regex, '$options': 'i'}
            },
            # Товары без классификации
            {'super_class': {'$exists': False}},
            {'super_class': None},
            {'super_class': ''}
        ]
    }
    
    projection = {'name_raw': 1, 'super_class': 1, 'product_core_id': 1, '_id': 1}
    
    cursor = db.supplier_items.find(query, projection)
    if limit:
        cursor = cursor.limit(limit)
    
    items = list(cursor)
    logger.info(f"   Found {len(items)} items to check")
    
    updated = 0
    errors = 0
    
    for item in items:
        try:
            name = item.get('name_raw', '')
            if not name:
                continue
            
            current_sc = item.get('super_class', '')
            
            # Переклассифицируем
            new_sc, sc_conf = detect_super_class(name)
            new_pc, pc_conf = detect_product_core(name, new_sc)
            
            # Обновляем только если:
            # 1. Новая классификация отличается
            # 2. Уверенность >= 80%
            # 3. Новая классификация - seafood (для meat→seafood)
            if new_sc and new_sc != current_sc and sc_conf >= 0.80:
                # Для meat→seafood - строго проверяем
                if current_sc and current_sc.startswith('meat') and not new_sc.startswith('seafood'):
                    continue
                
                db.supplier_items.update_one(
                    {'_id': item['_id']},
                    {'$set': {
                        'super_class': new_sc,
                        'product_core_id': new_pc or new_sc,
                        'classification_auto_updated': True
                    }}
                )
                updated += 1
                
                if updated <= 5:
                    logger.info(f"   ✅ {name[:40]} | {current_sc or 'None'} → {new_sc}")
                    
        except Exception as e:
            errors += 1
            logger.error(f"   Error processing item: {e}")
    
    if updated > 5:
        logger.info(f"   ... and {updated - 5} more items")
    
    logger.info(f"✅ Reclassification complete: {updated} updated, {errors} errors")
    
    return updated, errors


def run_startup_reclassification(db):
    """
    Запуск переклассификации при старте сервера.
    """
    try:
        updated, errors = reclassify_items(db)
        if updated > 0:
            logger.info(f"🔄 Startup reclassification: {updated} items updated")
    except Exception as e:
        logger.error(f"❌ Startup reclassification failed: {e}")


if __name__ == '__main__':
    # Для ручного запуска
    from pymongo import MongoClient
    import os
    
    logging.basicConfig(level=logging.INFO)
    
    client = MongoClient(os.environ.get('MONGO_URL', 'mongodb://localhost:27017'))
    db = client[os.environ.get('DB_NAME', 'test_database')]
    
    updated, errors = reclassify_items(db)
    print(f"\nResult: {updated} updated, {errors} errors")
