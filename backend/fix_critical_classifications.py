"""
Скрипт для безопасного исправления классификации товаров.

ПРИНЦИП: НЕ менять существующие правильные категории!
Исправляем только явные ошибки где категория верхнего уровня явно неправильная.
"""

import os
import re
import logging
from pymongo import MongoClient
from typing import Optional, Dict, List, Tuple

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Явные исправления для критических ошибок
# Формат: (regex_pattern, wrong_category_prefix, correct_category)
EXPLICIT_FIXES = [
    # === МОРЕПРОДУКТЫ / МЯСО ===
    # Икра лососевая должна быть seafood.caviar
    (r'икр.*лосос|лосос.*икр', 'seafood.salmon', 'seafood.caviar'),
    (r'икр.*горбуш|горбуш.*икр', 'seafood.salmon', 'seafood.caviar'),
    
    # Масло оливковое - это oils, не vegetables
    (r'масл.*оливк|оливк.*масл', 'vegetables', 'oils.olive'),
    
    # Куриное/говядина/свинина - это meat, не seafood
    (r'курин|куриц|курица|цыпл|бройлер', 'seafood', 'meat.chicken'),
    (r'говядин|говяж', 'seafood', 'meat.beef'),
    (r'свинин|свин', 'seafood', 'meat.pork'),
    (r'баранин|бараний', 'seafood', 'meat.lamb'),
    
    # Мясо креветки/мидий - это seafood (правильно), НЕ менять
    
    # === УПАКОВКА / ПОСУДА ===
    # Упаковка "для салата" - это packaging, не vegetables
    (r'контейнер.*салат|для.*салат.*контейнер', 'vegetables', 'packaging.container'),
    
    # Стаканы - disposables, не bakery/desserts
    (r'стакан.*waffle|waffle.*стакан', 'bakery', 'disposables.cups'),
    (r'стакан.*бумаж|бумаж.*стакан', 'desserts', 'disposables.cups'),
    
    # Салфетки с рисунком - disposables, не vegetables
    (r'салфетк.*гриб|гриб.*салфетк', 'vegetables', 'disposables.napkins'),
    (r'салфетк.*100|салфетк.*белы', 'vegetables', 'disposables.napkins'),
    
    # === ХЛЕБ / ВЫПЕЧКА ===
    # Хлеб кукурузный - bakery, не vegetables
    (r'хлеб.*кукуруз|кукуруз.*хлеб', 'vegetables', 'bakery.bread'),
    # Хлебные палочки - bakery, не vegetables
    (r'палочк.*хлебн|хлебн.*палочк|гриссини', 'vegetables', 'bakery.breadsticks'),
    
    # === САХАР ===
    # Сахар порционный (стики) - это staples, не desserts
    (r'сахар.*порцион|сахар.*стик|сахар.*5г|сахар.*пакет', 'desserts', 'staples.sugar'),
    # Сахар-песок большой фасовки - staples
    (r'сахар.*песок.*кг|сахар.*1000', 'desserts', 'staples.sugar'),
    # Сахарная пудра - оставляем в desserts (правильно для выпечки)
    
    # === ЧАЙ ===
    # Чай с добавками - beverages, не fruits/vegetables
    (r'чай.*лайм|лайм.*чай', 'fruits', 'beverages.tea'),
    (r'чай.*малин|малин.*чай', 'fruits', 'beverages.tea'),
    (r'чай.*мят|мят.*чай', 'vegetables', 'beverages.tea'),
    (r'чай.*лимон|лимон.*чай', 'fruits', 'beverages.tea'),
    (r'чай.*зелен|зелен.*чай', 'fruits', 'beverages.tea'),
    (r'чай.*черн|черн.*чай', 'fruits', 'beverages.tea'),
    
    # === ПАКЕТЫ С ОВОЩАМИ ===
    # "в пакете" - это описание упаковки, товар остаётся овощем
    # НЕ ИСПРАВЛЯЕМ: "огурцы пакет" правильно vegetables
]


def should_fix(name: str, current_class: str, fix_pattern: str, wrong_prefix: str, correct_class: str) -> bool:
    """Проверяет нужно ли исправлять классификацию"""
    if not current_class:
        return False
    
    # Проверяем что название матчит паттерн
    if not re.search(fix_pattern, name.lower()):
        return False
    
    # Проверяем что текущая категория неправильная
    if not current_class.startswith(wrong_prefix):
        return False
    
    return True


def fix_critical_classifications(db, dry_run=True):
    """Исправляет только критически неправильные классификации"""
    
    total_fixed = 0
    
    for pattern, wrong_prefix, correct_class in EXPLICIT_FIXES:
        # Находим товары с неправильной классификацией
        query = {
            'active': True,
            'name_norm': {'$regex': pattern, '$options': 'i'},
            'product_core_id': {'$regex': f'^{wrong_prefix}', '$options': 'i'}
        }
        
        items = list(db.supplier_items.find(query, {
            '_id': 1, 'id': 1, 'name_raw': 1, 'product_core_id': 1
        }))
        
        if items:
            logger.info(f'\nПаттерн: {pattern}')
            logger.info(f'  {wrong_prefix} → {correct_class}: {len(items)} товаров')
            
            if not dry_run:
                for item in items:
                    db.supplier_items.update_one(
                        {'_id': item['_id']},
                        {'$set': {
                            'product_core_id': correct_class,
                            'super_class': correct_class
                        }}
                    )
                    total_fixed += 1
            else:
                for item in items[:3]:
                    logger.info(f'    - {item.get("name_raw", "")[:50]}')
                total_fixed += len(items)
    
    return total_fixed


def analyze_problems(db) -> Dict:
    """Анализирует проблемы классификации"""
    
    problems = {
        'total_active': db.supplier_items.count_documents({'active': True}),
        'no_class': db.supplier_items.count_documents({
            'active': True,
            '$or': [
                {'product_core_id': None},
                {'product_core_id': ''},
                {'product_core_id': {'$exists': False}}
            ]
        }),
        'categories': {}
    }
    
    # Статистика по категориям верхнего уровня
    pipeline = [
        {'$match': {'active': True, 'product_core_id': {'$exists': True, '$ne': None}}},
        {'$project': {
            'top_category': {'$arrayElemAt': [{'$split': ['$product_core_id', '.']}, 0]}
        }},
        {'$group': {'_id': '$top_category', 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]
    
    for cat in db.supplier_items.aggregate(pipeline):
        problems['categories'][cat['_id']] = cat['count']
    
    return problems


if __name__ == '__main__':
    import sys
    
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    
    client = MongoClient(mongo_url)
    db = client[db_name]
    
    # Анализ
    logger.info('=== АНАЛИЗ КЛАССИФИКАЦИИ ===')
    problems = analyze_problems(db)
    logger.info(f'Всего активных: {problems["total_active"]}')
    logger.info(f'Без классификации: {problems["no_class"]}')
    logger.info('\nКатегории верхнего уровня:')
    for cat, count in sorted(problems['categories'].items(), key=lambda x: -x[1])[:15]:
        logger.info(f'  {cat}: {count}')
    
    # Исправление
    if len(sys.argv) > 1 and sys.argv[1] == '--apply':
        logger.info('\n=== ПРИМЕНЕНИЕ ИСПРАВЛЕНИЙ ===')
        fixed = fix_critical_classifications(db, dry_run=False)
        logger.info(f'\nИсправлено: {fixed} товаров')
    else:
        logger.info('\n=== DRY RUN (добавьте --apply для применения) ===')
        fixed = fix_critical_classifications(db, dry_run=True)
        logger.info(f'\nБудет исправлено: {fixed} товаров')
