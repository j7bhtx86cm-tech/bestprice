"""
Скрипт для создания lemma_tokens индекса для ускорения поиска.

lemma_tokens - это массив лемматизированных слов из названия товара,
который позволяет делать быстрый поиск по морфологии без regex.
"""

import os
import re
import logging
from pymongo import MongoClient
from typing import List

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Простой стеммер для русского языка
RUSSIAN_ENDINGS = [
    'ами', 'ями', 'ому', 'ему', 'ого', 'его', 'ими', 'ыми',
    'ах', 'ях', 'ов', 'ев', 'ий', 'ый', 'ой', 'ей', 'ию', 'ью',
    'ая', 'яя', 'ое', 'ее', 'ие', 'ые',
    'ом', 'ем', 'им', 'ым', 'ую', 'юю',
    'ам', 'ям', 'ой', 'ей', 'ов', 'ев',
    'а', 'я', 'о', 'е', 'и', 'ы', 'у', 'ю',
]


def simple_stem(word: str) -> str:
    """Простой стеммер - отрезает окончания"""
    word = word.lower()
    
    # Минимальная длина основы
    min_stem_len = 3
    
    for ending in RUSSIAN_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= min_stem_len:
            return word[:-len(ending)]
    
    return word


def tokenize(text: str) -> List[str]:
    """Токенизация текста"""
    if not text:
        return []
    
    # Приводим к нижнему регистру
    text = text.lower()
    
    # Удаляем спецсимволы, оставляем буквы и цифры
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Разбиваем на слова
    words = text.split()
    
    # Фильтруем короткие слова и стоп-слова
    stop_words = {'и', 'в', 'на', 'с', 'по', 'для', 'из', 'от', 'до', 'за', 'к', 'у', 'о', 'не'}
    
    tokens = []
    for word in words:
        if len(word) >= 2 and word not in stop_words:
            stem = simple_stem(word)
            if len(stem) >= 2:
                tokens.append(stem)
    
    return list(set(tokens))  # Уникальные токены


def create_lemma_tokens(db, batch_size=500, dry_run=True):
    """
    Создаёт lemma_tokens для всех товаров.
    
    Args:
        db: MongoDB database
        batch_size: Размер батча для обновления
        dry_run: Если True, только показывает примеры
    
    Returns:
        Количество обработанных документов
    """
    
    # Находим товары без lemma_tokens или с пустым
    query = {
        '$or': [
            {'lemma_tokens': {'$exists': False}},
            {'lemma_tokens': []},
            {'lemma_tokens': None}
        ]
    }
    
    total = db.supplier_items.count_documents(query)
    logger.info(f'Товаров без lemma_tokens: {total}')
    
    if dry_run:
        # Показываем примеры
        samples = list(db.supplier_items.find(
            {'name_raw': {'$exists': True}},
            {'_id': 0, 'name_raw': 1}
        ).limit(10))
        
        logger.info('\n=== Примеры токенизации ===')
        for s in samples:
            name = s.get('name_raw', '')
            tokens = tokenize(name)
            logger.info(f'"{name[:50]}"')
            logger.info(f'  → {tokens}')
        
        return 0
    
    # Обрабатываем батчами
    processed = 0
    cursor = db.supplier_items.find(
        {'name_raw': {'$exists': True}},
        {'_id': 1, 'name_raw': 1, 'name_norm': 1}
    )
    
    batch = []
    for doc in cursor:
        name = doc.get('name_raw') or doc.get('name_norm', '')
        tokens = tokenize(name)
        
        batch.append({
            '_id': doc['_id'],
            'lemma_tokens': tokens
        })
        
        if len(batch) >= batch_size:
            # Обновляем батч
            for item in batch:
                db.supplier_items.update_one(
                    {'_id': item['_id']},
                    {'$set': {'lemma_tokens': item['lemma_tokens']}}
                )
            processed += len(batch)
            logger.info(f'Обработано: {processed}/{total}')
            batch = []
    
    # Остаток
    if batch:
        for item in batch:
            db.supplier_items.update_one(
                {'_id': item['_id']},
                {'$set': {'lemma_tokens': item['lemma_tokens']}}
            )
        processed += len(batch)
    
    logger.info(f'\nВсего обработано: {processed}')
    
    # Создаём индекс
    logger.info('Создаём индекс на lemma_tokens...')
    db.supplier_items.create_index('lemma_tokens')
    logger.info('Индекс создан!')
    
    return processed


def search_with_lemma(db, query: str, limit: int = 20):
    """Поиск с использованием lemma_tokens"""
    tokens = tokenize(query)
    
    if not tokens:
        return []
    
    # Ищем документы содержащие все токены
    pipeline = [
        {'$match': {
            'active': True,
            'lemma_tokens': {'$all': tokens}
        }},
        {'$limit': limit},
        {'$project': {
            '_id': 0,
            'name_raw': 1,
            'price': 1,
            'product_core_id': 1
        }}
    ]
    
    return list(db.supplier_items.aggregate(pipeline))


if __name__ == '__main__':
    import sys
    
    mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
    db_name = os.environ.get('DB_NAME', 'test_database')
    
    client = MongoClient(mongo_url)
    db = client[db_name]
    
    if len(sys.argv) > 1 and sys.argv[1] == '--apply':
        logger.info('=== СОЗДАНИЕ LEMMA_TOKENS ===')
        processed = create_lemma_tokens(db, dry_run=False)
        logger.info(f'\nОбработано документов: {processed}')
        
        # Тестовый поиск
        logger.info('\n=== ТЕСТОВЫЙ ПОИСК ===')
        for query in ['икра лососевая', 'молоко', 'куриная грудка']:
            results = search_with_lemma(db, query, limit=3)
            logger.info(f'\nЗапрос: "{query}"')
            for r in results:
                logger.info(f'  - {r.get("name_raw", "")[:50]} | {r.get("price")}₽')
    else:
        logger.info('=== DRY RUN (добавьте --apply для создания) ===')
        create_lemma_tokens(db, dry_run=True)
