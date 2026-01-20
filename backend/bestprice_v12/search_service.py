"""
Search service for BestPrice v12

Модуль поиска с поддержкой:
- Морфологический поиск через lemma_tokens
- Синонимы (search_synonyms.py)
- Prefix search для typeahead
- Multi-word order-insensitive search
"""

import re
import logging
from typing import List, Dict, Optional, Tuple
from pymongo.database import Database

logger = logging.getLogger(__name__)

# Русские окончания для стемминга
RUSSIAN_ENDINGS = [
    'ами', 'ями', 'ому', 'ему', 'ого', 'его', 'ими', 'ыми',
    'ах', 'ях', 'ов', 'ев', 'ий', 'ый', 'ой', 'ей', 'ию', 'ью',
    'ая', 'яя', 'ое', 'ее', 'ие', 'ые',
    'ом', 'ем', 'им', 'ым', 'ую', 'юю',
    'ам', 'ям', 'ой', 'ей', 'ов', 'ев',
    'а', 'я', 'о', 'е', 'и', 'ы', 'у', 'ю',
]


def stem_russian(word: str) -> str:
    """Простой русский стеммер - отрезает окончания"""
    word = word.lower()
    min_stem_len = 3
    
    for ending in RUSSIAN_ENDINGS:
        if word.endswith(ending) and len(word) - len(ending) >= min_stem_len:
            return word[:-len(ending)]
    
    return word


def generate_lemma_tokens(words: List[str]) -> List[str]:
    """Генерирует леммы для списка слов"""
    lemmas = []
    for word in words:
        if len(word) >= 2:
            lemma = stem_russian(word)
            if len(lemma) >= 2:
                lemmas.append(lemma)
    return list(set(lemmas))


def tokenize_query(query: str) -> Tuple[List[str], List[str]]:
    """
    Токенизирует поисковый запрос.
    
    Returns:
        (tokens, lemmas) - исходные токены и их леммы
    """
    if not query:
        return [], []
    
    # Нормализация
    query = query.lower().strip()
    
    # Сохраняем калибры (напр. 31/40) как единый токен
    caliber_pattern = r'(\d+/\d+)'
    calibers = re.findall(caliber_pattern, query)
    query_without_calibers = re.sub(caliber_pattern, ' ', query)
    
    # Токенизация
    tokens = re.findall(r'[а-яёa-z0-9]+', query_without_calibers)
    tokens.extend(calibers)
    
    # Фильтруем стоп-слова
    stop_words = {'и', 'в', 'на', 'с', 'по', 'для', 'из', 'от', 'до', 'за', 'к', 'у', 'о', 'не'}
    tokens = [t for t in tokens if t not in stop_words and len(t) >= 2]
    
    # Генерируем леммы
    lemmas = generate_lemma_tokens(tokens)
    
    return tokens, lemmas


def is_token_complete(token: str, lemma: str) -> bool:
    """
    Определяет завершён ли токен (полное слово) или пользователь ещё печатает.
    
    Правила:
    - len >= 6: полное слово
    - stem != original И len >= 5: вероятно полное
    - иначе: пользователь печатает (prefix search)
    """
    return len(token) >= 6 or (token != lemma and len(token) >= 5)


def build_search_query(
    query_str: str,
    base_query: Dict,
    use_synonyms: bool = True
) -> Dict:
    """
    Строит MongoDB query для поиска.
    
    Args:
        query_str: Поисковая строка
        base_query: Базовый фильтр (active, price>0 и т.д.)
        use_synonyms: Использовать ли синонимы
    
    Returns:
        MongoDB query dict
    """
    from search_synonyms import build_synonym_regex
    
    tokens, lemmas = tokenize_query(query_str)
    
    if not tokens:
        return base_query
    
    query = base_query.copy()
    
    # Определяем полноту последнего токена
    last_token = tokens[-1]
    last_lemma = lemmas[-1] if lemmas else last_token
    is_complete = is_token_complete(last_token, last_lemma)
    
    if len(tokens) == 1:
        # Одиночный токен
        escaped = re.escape(last_token)
        
        if is_complete and lemmas:
            # Полное слово: lemma search + prefix fallback
            query['$or'] = [
                {'lemma_tokens': {'$all': lemmas}},
                {'name_norm': {'$regex': f'(^|\\s){escaped}', '$options': 'i'}}
            ]
        else:
            # Typeahead: prefix search
            query['name_norm'] = {'$regex': f'(^|\\s){escaped}', '$options': 'i'}
    else:
        # Многословный запрос
        or_conditions = []
        
        # 1. Lemma search (основной)
        if lemmas:
            or_conditions.append({'lemma_tokens': {'$all': lemmas}})
        
        # 2. Synonym regex
        if use_synonyms:
            try:
                synonym_regex = build_synonym_regex(tokens)
                or_conditions.append({
                    'name_norm': {'$regex': synonym_regex, '$options': 'i'}
                })
            except Exception as e:
                logger.warning(f"Synonym regex error: {e}")
        
        # 3. Exact tokens (any order)
        lookahead = [f'(?=.*{re.escape(t)})' for t in tokens]
        exact_regex = ''.join(lookahead) + '.*'
        or_conditions.append({
            'name_norm': {'$regex': exact_regex, '$options': 'i'}
        })
        
        # 4. Short tokens fallback (fuzzy)
        short_tokens = [t[:4] if len(t) >= 4 else t for t in tokens if len(t) >= 3]
        if short_tokens:
            short_lookahead = [f'(?=.*{re.escape(t)})' for t in short_tokens]
            short_regex = ''.join(short_lookahead) + '.*'
            or_conditions.append({
                'name_norm': {'$regex': short_regex, '$options': 'i'}
            })
        
        # 5. Если последний токен неполный - добавить prefix
        if not is_complete:
            escaped_last = re.escape(last_token)
            full_lemmas = generate_lemma_tokens(tokens[:-1])
            if full_lemmas:
                or_conditions.insert(0, {
                    'lemma_tokens': {'$all': full_lemmas},
                    'name_norm': {'$regex': f'(^|\\s){escaped_last}', '$options': 'i'}
                })
        
        query['$or'] = or_conditions
    
    return query


def search_items(
    db: Database,
    query_str: str,
    collection: str = 'supplier_items',
    limit: int = 50,
    skip: int = 0,
    super_class: Optional[str] = None,
    supplier_id: Optional[str] = None,
    projection: Optional[Dict] = None
) -> Tuple[List[Dict], int]:
    """
    Выполняет поиск товаров.
    
    Returns:
        (items, total_count)
    """
    # Базовый фильтр
    base_query = {
        'active': True,
        'price': {'$gt': 0},
        'unit_type': {'$exists': True, '$ne': None},
        'id': {'$exists': True, '$ne': None}
    }
    
    if super_class:
        base_query['super_class'] = {'$regex': f'^{re.escape(super_class)}', '$options': 'i'}
    
    if supplier_id:
        base_query['supplier_company_id'] = supplier_id
    
    # Строим поисковый query
    if query_str and query_str.strip():
        query = build_search_query(query_str, base_query)
    else:
        query = base_query
    
    # Projection
    if projection is None:
        projection = {'_id': 0}
    
    # Выполняем поиск
    cursor = db[collection].find(query, projection)
    
    # Сортировка: сначала по цене, потом по релевантности
    cursor = cursor.sort([('price', 1)])
    
    # Pagination
    total = db[collection].count_documents(query)
    items = list(cursor.skip(skip).limit(limit))
    
    return items, total


def search_with_lemma_only(
    db: Database,
    query_str: str,
    limit: int = 20
) -> List[Dict]:
    """
    Быстрый поиск только по lemma_tokens индексу.
    Используется для автодополнения и быстрых подсказок.
    """
    _, lemmas = tokenize_query(query_str)
    
    if not lemmas:
        return []
    
    pipeline = [
        {'$match': {
            'active': True,
            'lemma_tokens': {'$all': lemmas}
        }},
        {'$sort': {'price': 1}},
        {'$limit': limit},
        {'$project': {
            '_id': 0,
            'id': 1,
            'name_raw': 1,
            'price': 1,
            'unit_type': 1,
            'super_class': 1
        }}
    ]
    
    return list(db.supplier_items.aggregate(pipeline))
