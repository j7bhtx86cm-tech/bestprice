"""
BestPrice v12 - API Routes

FastAPI роутер для v12 функционала

Модульная структура (в процессе рефакторинга):
- search_service.py: Поиск с lemma_tokens
- optimizer.py: Оптимизация корзины
- plan_snapshot.py: Снепшоты планов
"""

import logging
import re
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from .models import (
    AddToCartRequest, AddToCartResponse,
    CatalogItemResponse, CartSummary,
    SeedFavoritesRequest, SeedFavoritesResponse,
    MIN_SUPPLIER_ORDER_RUB, TOPUP_THRESHOLD_RUB
)
from .catalog import (
    get_db, generate_catalog_references, 
    get_catalog_items, update_best_prices
)
from .cart import (
    add_to_cart, get_cart_summary, 
    apply_topup, clear_cart, remove_from_cart
)
from .favorites import (
    seed_random_favorites, get_user_favorites,
    add_to_favorites, remove_from_favorites
)

# Import search utilities
import sys

# Logger
logger = logging.getLogger(__name__)
sys.path.insert(0, '/app/backend')
from search_utils import (
    tokenize, tokenize_with_lemmas, detect_brand_from_query,
    detect_brands_enhanced, BrandDetectionResult,
    calculate_ppu_value, calculate_min_line_total, normalize_text,
    STOP_WORDS
)
from russian_stemmer import stem_token_safe, generate_lemma_tokens
from search_synonyms import get_synonyms, build_synonym_regex, expand_query_with_synonyms

# Import search service (новый модуль)
from .search_service import search_items, search_with_lemma_only, tokenize_query

# Import matching engine v3.0 (ТЗ v12 - Strict + Similar)
from .matching_engine_v3 import (
    find_alternatives_v3, extract_signature, explain_match_v3,
    AlternativesResult
)

# Import NPC matching v9.1 (для SHRIMP/FISH/SEAFOOD/MEAT - "Нулевой мусор")
from .npc_matching_v9 import (
    is_npc_domain_item, get_item_npc_domain,
    apply_npc_filter, format_npc_result,
    extract_npc_signature, explain_npc_match
)

# Import modular routers
from .routes_modules import (
    cart_router, orders_router, favorites_router,
    init_all_routers
)

router = APIRouter(prefix="/v12", tags=["BestPrice v12"])


# === INITIALIZE MODULAR ROUTERS ===
# Note: DB initialization happens in get_db() on first call
# The modular routers will be included after main router setup

def _init_modules():
    """Lazy initialization of modular routers"""
    try:
        db = get_db()
        init_all_routers(db)
    except Exception as e:
        logger.warning(f"Could not init modular routers: {e}")

# Include modular routers (they use their own DB connection)
# router.include_router(cart_router)  # TODO: Enable after testing
# router.include_router(orders_router)  # TODO: Enable after testing
# router.include_router(favorites_router)  # TODO: Enable after testing


# === CATALOG ENDPOINTS ===

@router.get("/catalog", summary="Получить каталог с Best Price")
async def get_catalog(
    super_class: Optional[str] = Query(None, description="Фильтр по категории"),
    search: Optional[str] = Query(None, description="Поиск по названию"),
    category: Optional[str] = Query(None, description="Альтернативный фильтр по категории"),
    q: Optional[str] = Query(None, description="Альтернативный поиск"),
    supplier_id: Optional[str] = Query(None, description="Фильтр по поставщику"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: dict = None  # TODO: Add auth dependency
):
    """
    Получает список всех товаров из supplier_items.
    
    Search features (v12 FINAL):
    - Order-insensitive token search
    - Prefix-friendly: last token as prefix (enables typeahead)
    - RU morphology: lemma_tokens for singular/plural matching
    - Caliber preservation: tokens like 31/40 kept intact
    - Safe fallback: empty tokens → default catalog
    - BestPrice ranking: price first, then relevance
    """
    db = get_db()
    
    # Merge alternative params
    search_term = search or q
    super_class_filter = super_class or category
    
    # Базовый фильтр - только валидные офферы (publishable)
    # Правила: active=true, price>0, unit_type exists, id exists
    # Для WEIGHT/VOLUME требуется pack_qty > 0
    query = {
        'active': True,
        'price': {'$gt': 0},
        'unit_type': {'$exists': True, '$ne': None, '$ne': ''},
        'id': {'$exists': True, '$ne': None},
        '$or': [
            {'unit_type': {'$in': ['WEIGHT', 'VOLUME']}, 'pack_qty': {'$gt': 0}},
            {'unit_type': 'PIECE'}
        ]
    }
    
    # Фильтр по категории
    if super_class_filter:
        query['super_class'] = {'$regex': f'^{super_class_filter}', '$options': 'i'}
    
    # Фильтр по поставщику
    if supplier_id:
        query['supplier_company_id'] = supplier_id
    
    # === SEARCH LOGIC (v12 FINAL with Brand RU/EN support) ===
    q_tokens = []
    q_lemmas = []
    brand_detection: BrandDetectionResult = BrandDetectionResult()
    is_search_mode = False
    last_token_raw = ''
    use_brand_filter = False  # Whether to apply brand_id filter in query
    
    if search_term and search_term.strip():
        # Tokenize query with lemmas
        q_tokens, q_lemmas = tokenize_with_lemmas(search_term)
        
        if q_tokens:
            is_search_mode = True
            last_token_raw = q_tokens[-1]
            last_token_lemma = stem_token_safe(last_token_raw)
            
            # === BRAND DETECTION (RU/EN with prefix support) ===
            brand_detection = detect_brands_enhanced(db, q_tokens)
            if not brand_detection.brand_ids:
                brand_detection = detect_brands_enhanced(db, q_lemmas)
            
            # Decide: brand_filter_mode vs brand_boost_mode
            # Filter mode: exact match OR prefix >= 3 chars with high confidence
            # Boost mode: prefix 2 chars or lower confidence
            if brand_detection.brand_ids:
                if brand_detection.match_type == 'exact':
                    use_brand_filter = True
                elif brand_detection.match_type == 'prefix' and brand_detection.confidence >= 0.7:
                    use_brand_filter = True
                # else: brand_boost_mode (applied in ranking)
            
            # Check if last token looks like a complete word
            # ВАЖНО: is_complete определяет используем ли lemma_tokens (морфология)
            # или prefix search (typeahead)
            # 
            # Проблема: "лосо" → stem="лос" → is_complete=True → lemma_tokens поиск
            # Но пользователь ещё печатает! Нужен prefix.
            #
            # Новая логика:
            # - len >= 6: полное слово → lemma search
            # - stem != original И len >= 5: возможно полное → lemma search
            # - иначе: пользователь печатает → prefix search
            is_last_token_complete = (
                len(last_token_raw) >= 6 or
                (last_token_raw != last_token_lemma and len(last_token_raw) >= 5)
            )
            
            # Build text search query
            # Используем комбинированный подход: prefix search всегда + lemma boost
            if len(q_tokens) == 1:
                if is_last_token_complete and q_lemmas:
                    # Полное слово: ищем по lemma ИЛИ prefix (для обратной совместимости)
                    escaped_last = re.escape(last_token_raw)
                    query['$or'] = [
                        {'lemma_tokens': {'$all': q_lemmas}},
                        {'name_norm': {'$regex': f'(^|\\s){escaped_last}'}}
                    ]
                else:
                    # Typeahead: только prefix search
                    escaped_last = re.escape(last_token_raw)
                    query['name_norm'] = {'$regex': f'(^|\\s){escaped_last}'}
            else:
                # Многословный запрос - СТРОГИЙ поиск
                # Приоритет:
                # 1. lemma_tokens (морфологический поиск) - ГЛАВНЫЙ
                # 2. synonym regex
                # 3. exact tokens (точные слова)
                
                # Полные токены lookahead (без \b - не работает с кириллицей в MongoDB)
                lookahead_parts = [f'(?=.*{re.escape(t)})' for t in q_tokens]
                any_order_regex = ''.join(lookahead_parts) + '.*'
                
                # Regex с синонимами
                synonym_regex = build_synonym_regex(q_tokens)
                
                # УБРАН fuzzy short_tokens - слишком много ложных срабатываний
                
                if is_last_token_complete:
                    # Все токены полные: lemma search ИЛИ synonym regex ИЛИ exact regex
                    or_conditions = [
                        {'lemma_tokens': {'$all': q_lemmas}},
                        {'name_norm': {'$regex': synonym_regex, '$options': 'i'}},
                        {'name_norm': {'$regex': any_order_regex, '$options': 'i'}}
                    ]
                    query['$or'] = or_conditions
                else:
                    # Последний токен неполный: prefix для него + lemma для остальных
                    full_lemmas = generate_lemma_tokens(q_tokens[:-1])
                    escaped_last = re.escape(last_token_raw)
                    
                    or_conditions = [
                        {'name_norm': {'$regex': synonym_regex, '$options': 'i'}},
                        {'name_norm': {'$regex': any_order_regex, '$options': 'i'}}
                    ]
                    
                    if full_lemmas:
                        # Комбинированный: lemma для полных + prefix для последнего
                        or_conditions.insert(0, {'lemma_tokens': {'$all': full_lemmas}, 'name_norm': {'$regex': f'(^|\\s){escaped_last}'}})
                    
                    query['$or'] = or_conditions
            
            # === APPLY BRAND FILTER if confident ===
            if use_brand_filter and brand_detection.brand_ids:
                # Build brand-filtered query
                brand_query = {'active': True, 'price': {'$gt': 0}}
                if super_class_filter:
                    brand_query['super_class'] = query.get('super_class')
                if supplier_id:
                    brand_query['supplier_company_id'] = supplier_id
                brand_query['brand_id'] = {'$in': brand_detection.brand_ids}
                
                # Filter out brand-related tokens from lemmas
                matched_token = brand_detection.matched_token.lower()
                matched_lemma = stem_token_safe(matched_token)
                
                # Find which original token was the brand match
                # The brand token is the one that equals or is a prefix of the matched alias
                brand_token_idx = None
                for i, t in enumerate(q_tokens):
                    t_lower = t.lower()
                    # Exact match
                    if t_lower == matched_token:
                        brand_token_idx = i
                        break
                    # Token is prefix of alias (user typing "мак" → alias "макфа")
                    if matched_token.startswith(t_lower) and len(t_lower) >= 2 and t_lower not in ['мак', 'ма']:
                        # Avoid common words like "мак" (poppy) being treated as brand
                        brand_token_idx = i
                        break
                    # Alias is prefix of token (shouldn't happen normally)
                    if t_lower.startswith(matched_token) and len(matched_token) >= 4:
                        brand_token_idx = i
                        break
                
                # Non-brand lemmas = all lemmas except the one from brand token
                if brand_token_idx is not None and brand_token_idx < len(q_tokens):
                    brand_token = q_tokens[brand_token_idx]
                    brand_lemma = stem_token_safe(brand_token)
                    non_brand_lemmas = [l for l in q_lemmas if l != brand_lemma and l != matched_lemma]
                else:
                    # Couldn't identify brand token - just exclude matched_lemma
                    non_brand_lemmas = [l for l in q_lemmas if l != matched_lemma]
                
                if non_brand_lemmas:
                    brand_query['lemma_tokens'] = {'$all': non_brand_lemmas}
                
                query = brand_query
        else:
            is_search_mode = False
    
    # Count total before pagination
    total = db.supplier_items.count_documents(query)
    
    # Get items (fetch more for in-memory ranking when searching)
    fetch_limit = limit * 4 if is_search_mode else limit
    
    items = list(db.supplier_items.find(
        query,
        {'_id': 0}
    ).limit(fetch_limit + skip))
    
    # === RANKING (v12 FINAL: BestPrice ordering) ===
    if is_search_mode and q_lemmas:
        for item in items:
            # Calculate match_score using lemmas for RU morphology
            item_lemmas = item.get('lemma_tokens', [])
            item_tokens = item.get('search_tokens', [])
            
            if item_lemmas:
                # Count full lemma matches
                matched_lemmas = len(set(q_lemmas) & set(item_lemmas))
                
                # Check prefix match for last token
                last_token_lemma = stem_token_safe(q_tokens[-1]) if q_tokens else ''
                prefix_match = any(
                    t.startswith(q_tokens[-1]) or t.startswith(last_token_lemma) 
                    for t in item_tokens + item_lemmas
                )
                
                if prefix_match:
                    matched_lemmas = max(matched_lemmas, len(q_lemmas) - 0.3)
                
                item['_match_score'] = matched_lemmas / len(q_lemmas) if q_lemmas else 0
            else:
                # Fallback to simple token match
                item['_match_score'] = 0.5 if any(
                    t.startswith(q_tokens[-1]) for t in item_tokens
                ) else 0
            
            # Brand boost (1 if brand matches detected brand, 0 otherwise)
            # Now uses brand_detection result with multiple brand_ids support
            if brand_detection.brand_ids and item.get('brand_id') in brand_detection.brand_ids:
                item['_brand_boost'] = 1
            else:
                item['_brand_boost'] = 0
            
            # PPU value (lower is better)
            item['_ppu_value'] = calculate_ppu_value(
                item.get('price', 0),
                item.get('unit_type', 'PIECE'),
                item.get('pack_qty', 1)
            )
            
            # Price (for PIECE items where ppu is None)
            item['_price'] = item.get('price', 0)
            
            # Min line total (lower is better) - now just tie-breaker
            item['_min_line_total'] = calculate_min_line_total(
                item.get('price', 0),
                item.get('min_order_qty', 1)
            )
        
        # BestPrice sorting:
        # 1) Price ASC (main criterion - lowest price first)
        # 2) ppu_value ASC (for same price, prefer better per-unit value)
        # 3) min_line_total ASC (tie-breaker)
        # 4) match_score DESC (relevance as final tie-breaker)
        # 5) name_norm ASC
        def sort_key(item):
            ppu = item.get('_ppu_value')
            price = item.get('_price', 0) or 0
            
            # PPU for tie-breaking (nulls last)
            if ppu is not None:
                ppu_sort = ppu
            else:
                ppu_sort = float('inf')
            
            return (
                price,                              # 1) price ASC (MAIN)
                ppu_sort,                           # 2) ppu ASC (tie-breaker)
                item.get('_min_line_total', 0),     # 3) min_line_total ASC
                -item.get('_match_score', 0),       # 4) match_score DESC
                item.get('name_norm', '')           # 5) name_norm ASC
            )
        
        items.sort(key=sort_key)
        
        # Apply pagination after sorting
        items = items[skip:skip + limit]
        
        # Remove internal scoring fields from response
        for item in items:
            item.pop('_match_score', None)
            item.pop('_brand_boost', None)
            item.pop('_ppu_value', None)
            item.pop('_price', None)
            item.pop('_min_line_total', None)
    else:
        # No search: simple sort by super_class, name_norm
        items.sort(key=lambda x: (x.get('super_class', ''), x.get('name_norm', '')))
        items = items[skip:skip + limit]
    
    # Получаем названия поставщиков
    supplier_ids = list(set(i.get('supplier_company_id') for i in items if i.get('supplier_company_id')))
    companies = {}
    if supplier_ids:
        for comp in db.companies.find({'id': {'$in': supplier_ids}}, {'_id': 0, 'id': 1, 'companyName': 1, 'name': 1}):
            companies[comp['id']] = comp.get('companyName') or comp.get('name', 'Unknown')
    
    # Добавляем имена поставщиков к товарам
    for item in items:
        sid = item.get('supplier_company_id')
        item['supplier_name'] = companies.get(sid, sid[:8] + '...' if sid else 'Unknown')
    
    return {
        'items': items,
        'total': total,
        'skip': skip,
        'limit': limit,
        'has_more': skip + len(items) < total
    }


@router.get("/search/quick", summary="Быстрый поиск по lemma_tokens")
async def quick_search(
    q: str = Query(..., min_length=2, description="Поисковый запрос"),
    limit: int = Query(10, ge=1, le=50)
):
    """
    Быстрый поиск только по lemma_tokens индексу.
    Используется для autocomplete/typeahead.
    
    Преимущества:
    - Использует индекс lemma_tokens (быстрее regex)
    - Поддержка морфологии (молоко/молока/молочный)
    """
    db = get_db()
    
    results = search_with_lemma_only(db, q, limit=limit)
    
    # Добавляем supplier names
    supplier_ids = list(set(r.get('supplier_company_id') for r in results if r.get('supplier_company_id')))
    if supplier_ids:
        companies = {c['id']: c.get('companyName', c.get('name', 'Unknown')) 
                     for c in db.companies.find({'id': {'$in': supplier_ids}}, {'_id': 0})}
        for item in results:
            sid = item.get('supplier_company_id')
            if sid:
                item['supplier_name'] = companies.get(sid, 'Unknown')
    
    return {
        'query': q,
        'results': results,
        'count': len(results)
    }


@router.get("/catalog/{reference_id}", summary="Получить карточку каталога")
async def get_catalog_item(reference_id: str):
    """Получает детали карточки каталога"""
    db = get_db()
    
    ref = db.catalog_references.find_one({'reference_id': reference_id}, {'_id': 0})
    
    if not ref:
        raise HTTPException(status_code=404, detail="Карточка не найдена")
    
    # Получаем все предложения для этой карточки
    from .cart import get_candidates_for_reference
    
    candidates = get_candidates_for_reference(
        db,
        ref['product_core_id'],
        ref['unit_type'],
        ref.get('pack_value'),
        ref.get('pack_unit')
    )
    
    # Получаем названия поставщиков
    supplier_ids = list(set(c.get('supplier_company_id') for c in candidates))
    companies = {c['id']: c.get('companyName', c.get('name', 'Unknown')) 
                 for c in db.companies.find({'id': {'$in': supplier_ids}}, {'_id': 0})}
    
    offers = []
    for c in sorted(candidates, key=lambda x: x.get('price', float('inf'))):
        offers.append({
            'supplier_item_id': c['id'],
            'supplier_name': companies.get(c.get('supplier_company_id'), 'Unknown'),
            'price': c['price'],
            'min_order_qty': c.get('min_order_qty', 1),
            'name': c.get('name_raw', '')
        })
    
    ref['offers'] = offers
    ref['offers_count'] = len(offers)
    
    return ref


# === FAVORITES ENDPOINTS ===

@router.get("/favorites", summary="Получить избранное")
async def get_favorites(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=1000),
    user_id: str = Query(..., description="ID пользователя")  # TODO: Get from auth
):
    """Получает список избранного пользователя"""
    db = get_db()
    
    favorites = get_user_favorites(db, user_id, skip, limit)
    total = db.favorites_v12.count_documents({'user_id': user_id})
    
    return {
        'items': favorites,
        'total': total,
        'skip': skip,
        'limit': limit
    }


@router.post("/favorites", summary="Добавить в избранное")
async def add_favorite(
    reference_id: str,
    user_id: str = Query(..., description="ID пользователя")
):
    """Добавляет карточку каталога в избранное (п.7 ТЗ)"""
    db = get_db()
    
    result = add_to_favorites(db, user_id, reference_id)
    
    if result['status'] == 'not_found':
        raise HTTPException(status_code=404, detail=result['message'])
    
    return result


@router.delete("/favorites/{favorite_id}", summary="Удалить из избранного")
async def delete_favorite(
    favorite_id: str,
    user_id: str = Query(..., description="ID пользователя")
):
    """Удаляет из избранного"""
    db = get_db()
    
    result = remove_from_favorites(db, user_id, favorite_id)
    
    if result['status'] == 'not_found':
        raise HTTPException(status_code=404, detail=result['message'])
    
    return result


@router.post("/favorites/clear", summary="Очистить всё избранное пользователя")
async def clear_all_favorites(user_id: str = Query(..., description="ID пользователя")):
    """
    Удаляет ВСЕ записи избранного для пользователя.
    
    Возвращает:
    - deleted_count: сколько записей удалено
    - remaining_count: сколько осталось (должно быть 0)
    """
    db = get_db()
    
    # Считаем сколько было
    before_count = db.favorites_v12.count_documents({'user_id': user_id})
    
    # Удаляем все
    result = db.favorites_v12.delete_many({'user_id': user_id})
    
    # Проверяем что всё удалено
    remaining_count = db.favorites_v12.count_documents({'user_id': user_id})
    
    logger.info(f"Cleared favorites for user {user_id}: deleted={result.deleted_count}, remaining={remaining_count}")
    
    return {
        'status': 'ok',
        'deleted_count': result.deleted_count,
        'remaining_count': remaining_count,
        'message': f'Удалено {result.deleted_count} записей из избранного'
    }


# === CART ENDPOINTS ===

class AddToCartRequestV12(BaseModel):
    supplier_item_id: Optional[str] = Field(None, description="ID supplier_item")
    reference_id: Optional[str] = Field(None, description="ID reference карточки или favorite")
    product_name: Optional[str] = Field(None, description="Название товара")
    supplier_id: Optional[str] = Field(None, description="ID поставщика")
    price: Optional[float] = Field(None, description="Цена")
    qty: float = Field(gt=0, description="Количество", default=1)
    user_id: str = Field(..., description="ID пользователя")


@router.post("/cart/add", summary="Добавить в корзину")
async def add_to_cart_endpoint(request: AddToCartRequestV12):
    """
    Добавляет товар в корзину.
    
    Поддерживает два режима:
    1. По supplier_item_id - напрямую из каталога
    2. По reference_id - из избранного (старая логика)
    """
    db = get_db()
    
    # Режим 1: Напрямую из каталога
    if request.supplier_item_id:
        # Получаем товар из supplier_items
        item = db.supplier_items.find_one({'id': request.supplier_item_id}, {'_id': 0})
        
        if not item:
            raise HTTPException(status_code=404, detail="Товар не найден")
        
        # Получаем имя поставщика
        company = db.companies.find_one({'id': item.get('supplier_company_id')}, {'_id': 0})
        supplier_name = company.get('companyName') or company.get('name', 'Unknown') if company else 'Unknown'
        
        # Рассчитываем effective_qty и line_total
        min_order_qty = item.get('min_order_qty', 1)
        effective_qty = max(request.qty, min_order_qty)
        price = item.get('price', 0)
        line_total = effective_qty * price
        
        # Создаём запись в корзине
        cart_item = {
            'cart_item_id': f"cart_{request.user_id}_{item['id']}",
            'user_id': request.user_id,
            'supplier_item_id': item['id'],
            'product_name': item.get('name_raw', ''),
            'supplier_id': item.get('supplier_company_id'),
            'supplier_name': supplier_name,
            'price': price,
            'user_qty': request.qty,
            'effective_qty': effective_qty,
            'line_total': line_total,
            'min_order_qty': min_order_qty,
            'unit_type': item.get('unit_type', 'PIECE'),
            'super_class': item.get('super_class'),
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        
        # Upsert в корзину
        db.cart_items_v12.update_one(
            {'user_id': request.user_id, 'supplier_item_id': item['id']},
            {'$set': cart_item},
            upsert=True
        )
        
        return {
            'status': 'ok',
            'message': 'Товар добавлен в корзину',
            'item': cart_item
        }
    
    # Режим 2: Из избранного (старая логика)
    elif request.reference_id:
        result = add_to_cart(db, request.user_id, request.reference_id, request.qty)
        
        if result['status'] == 'not_found':
            raise HTTPException(status_code=404, detail=result['message'])
        
        return result
    
    else:
        raise HTTPException(status_code=400, detail="Нужен supplier_item_id или reference_id")


@router.get("/cart", summary="Получить корзину")
async def get_cart(user_id: str = Query(..., description="ID пользователя")):
    """
    Получает корзину с группировкой по поставщикам (п.9 ТЗ)
    
    Возвращает:
    - Список позиций
    - Сумму по каждому поставщику
    - Информацию о минималках
    """
    db = get_db()
    
    summary = get_cart_summary(db, user_id)
    
    return {
        **summary,
        'minimum_order_rub': MIN_SUPPLIER_ORDER_RUB,
        'topup_threshold_rub': TOPUP_THRESHOLD_RUB
    }


# === CART INTENTS ROUTES (must be before /cart/{cart_item_id}) ===

@router.get("/cart/intents", summary="Получить intents")
async def get_cart_intents(user_id: str = Query(..., description="ID пользователя")):
    """Получает все intents пользователя с информацией о товаре"""
    db = get_db()
    
    intents = list(db.cart_intents.find({'user_id': user_id}, {'_id': 0}))
    
    # Проверяем актуальность каждого intent
    enriched = []
    for intent in intents:
        supplier_item_id = intent.get('supplier_item_id')
        
        # Проверяем что supplier_item ещё активен
        if supplier_item_id:
            item = db.supplier_items.find_one(
                {'id': supplier_item_id, 'active': True},
                {'_id': 0}
            )
            if item:
                # Актуальная информация
                enriched.append({
                    **intent,
                    'product_name': item.get('name_raw', intent.get('product_name', '')),
                    'price': item.get('price', intent.get('price', 0)),
                    'unit_type': item.get('unit_type', intent.get('unit_type', 'PIECE')),
                    'super_class': item.get('super_class', intent.get('super_class', '')),
                    'is_available': True,
                })
            else:
                # Товар стал неактивен
                enriched.append({
                    **intent,
                    'is_available': False,
                    'unavailable_reason': 'Товар временно недоступен'
                })
        else:
            enriched.append({
                **intent,
                'is_available': False,
                'unavailable_reason': 'Нет привязки к товару'
            })
    
    return {
        'intents': enriched,
        'count': len(enriched)
    }


@router.delete("/cart/intents", summary="Очистить все intents")
async def clear_cart_intents(user_id: str = Query(..., description="ID пользователя")):
    """Очищает все intents пользователя"""
    db = get_db()
    
    result = db.cart_intents.delete_many({'user_id': user_id})
    
    return {'status': 'ok', 'deleted_count': result.deleted_count}


# === END CART INTENTS ROUTES ===


@router.post("/cart/topup/{supplier_id}", summary="Применить автодобивку")
async def apply_topup_endpoint(
    supplier_id: str,
    user_id: str = Query(..., description="ID пользователя")
):
    """
    Применяет автодобивку для достижения минималки (п.10 ТЗ)
    
    - Работает только если deficit <= 1000₽ (10%)
    - Увеличивает количество существующих товаров
    """
    db = get_db()
    
    result = apply_topup(db, user_id, supplier_id)
    
    if result['status'] == 'error':
        raise HTTPException(status_code=400, detail=result['message'])
    
    return result


@router.delete("/cart", summary="Очистить корзину")
async def clear_cart_endpoint(user_id: str = Query(..., description="ID пользователя")):
    """Очищает корзину"""
    db = get_db()
    return clear_cart(db, user_id)


@router.put("/cart/{cart_item_id}", summary="Обновить количество")
async def update_cart_item(
    cart_item_id: str,
    qty: float = Query(..., gt=0, description="Новое количество"),
    user_id: str = Query(..., description="ID пользователя")
):
    """Обновляет количество товара в корзине"""
    db = get_db()
    
    # Находим позицию
    item = db.cart_items_v12.find_one({'cart_item_id': cart_item_id, 'user_id': user_id})
    
    if not item:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    
    # Обновляем
    price = item.get('price', 0)
    min_order_qty = item.get('min_order_qty', 1)
    effective_qty = max(qty, min_order_qty)
    line_total = effective_qty * price
    
    db.cart_items_v12.update_one(
        {'cart_item_id': cart_item_id, 'user_id': user_id},
        {'$set': {
            'user_qty': qty,
            'effective_qty': effective_qty,
            'line_total': line_total,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }}
    )
    
    return {
        'status': 'ok',
        'message': 'Количество обновлено',
        'qty': qty,
        'effective_qty': effective_qty,
        'line_total': line_total
    }


@router.delete("/cart/{cart_item_id}", summary="Удалить из корзины")
async def remove_cart_item(
    cart_item_id: str,
    user_id: str = Query(..., description="ID пользователя")
):
    """Удаляет позицию из корзины"""
    db = get_db()
    
    result = remove_from_cart(db, user_id, cart_item_id)
    
    if result['status'] == 'not_found':
        raise HTTPException(status_code=404, detail=result['message'])
    
    return result


# === ADMIN ENDPOINTS ===

@router.post("/admin/catalog/generate", summary="Сгенерировать каталог")
async def generate_catalog(limit: Optional[int] = None):
    """
    Генерирует catalog_references из supplier_items
    
    Вызывать после импорта новых прайсов
    """
    db = get_db()
    
    stats = generate_catalog_references(db, limit)
    
    return {
        'status': 'ok',
        'stats': stats
    }


@router.post("/admin/catalog/update-prices", summary="Обновить Best Prices")
async def update_prices():
    """
    Обновляет best_price для всех карточек
    
    Вызывать периодически или после изменения прайсов
    """
    db = get_db()
    
    stats = update_best_prices(db)
    
    return {
        'status': 'ok',
        'stats': stats
    }


@router.post("/admin/test/favorites/random", summary="Добавить случайные карточки в избранное")
async def seed_favorites_endpoint(request: SeedFavoritesRequest):
    """
    Добавляет случайные карточки каталога в избранное (п.14 ТЗ)
    
    Для тестирования:
    - Add-to-cart логики
    - Замены
    - Минималок
    - Автодобивки
    """
    db = get_db()
    
    result = seed_random_favorites(db, request.user_id, request.count, request.filters)
    
    return SeedFavoritesResponse(**result)


# === DIAGNOSTICS ===

@router.get("/diagnostics", summary="Диагностика v12")
async def get_diagnostics():
    """Возвращает статистику по v12"""
    db = get_db()
    
    return {
        'catalog_references': db.catalog_references.count_documents({}),
        'favorites_v12': db.favorites_v12.count_documents({}),
        'cart_items_v12': db.cart_items_v12.count_documents({}),
        'supplier_items_active': db.supplier_items.count_documents({'active': True}),
        'config': {
            'MIN_SUPPLIER_ORDER_RUB': MIN_SUPPLIER_ORDER_RUB,
            'TOPUP_THRESHOLD_RUB': TOPUP_THRESHOLD_RUB,
            'PACK_MATCH_MODE': 'STRICT'
        }
    }


# === NEW: INTENT-BASED CART + OPTIMIZER ===

from .optimizer import (
    optimize_cart, plan_to_dict,
    load_cart_intents, CartIntent, OptFlag
)


class CartIntentRequest(BaseModel):
    """Запрос добавления intent в корзину"""
    reference_id: Optional[str] = None  # Для избранного/catalog_references
    supplier_item_id: Optional[str] = None  # Для добавления напрямую из каталога
    qty: float = Field(gt=0, description="Количество в единицах (шт/кг/л)")
    user_id: str
    # NEW: Закрепить конкретный оффер (без авто-замены)
    lock_offer: bool = Field(default=True, description="Закрепить выбранный оффер без замены")


class CartIntentUpdateRequest(BaseModel):
    """Запрос обновления qty в корзине"""
    qty: float = Field(gt=0, description="Новое количество")


@router.post("/cart/intent", summary="Добавить intent в корзину (новая модель)")
async def add_cart_intent(request: CartIntentRequest):
    """
    Добавляет намерение (intent) в корзину.
    
    ВАЖНО: При добавлении сохраняется КОНКРЕТНЫЙ supplier_item_id.
    Оптимизация (замены) происходит ТОЛЬКО при checkout, а не при добавлении.
    
    Принимает либо reference_id, либо supplier_item_id.
    """
    db = get_db()
    
    supplier_item = None
    supplier_item_id = None
    product_name = ""
    unit_type = "PIECE"
    price = 0
    supplier_id = None
    super_class = ""
    pack_qty = None
    brand_id = None
    
    # Режим 1: Напрямую по supplier_item_id (из каталога)
    if request.supplier_item_id:
        supplier_item = db.supplier_items.find_one(
            {'id': request.supplier_item_id, 'active': True},
            {'_id': 0}
        )
        if not supplier_item:
            # Fallback: по unique_key
            supplier_item = db.supplier_items.find_one(
                {'unique_key': request.supplier_item_id, 'active': True},
                {'_id': 0}
            )
        
        if not supplier_item:
            raise HTTPException(status_code=404, detail="Товар не найден или неактивен")
        
        if supplier_item.get('price', 0) <= 0:
            raise HTTPException(status_code=400, detail="Товар недоступен (некорректная цена)")
        
        supplier_item_id = supplier_item['id']
        product_name = supplier_item.get('name_raw', '')
        unit_type = supplier_item.get('unit_type', 'PIECE')
        price = supplier_item.get('price', 0)
        supplier_id = supplier_item.get('supplier_company_id')
        super_class = supplier_item.get('super_class', '')
        pack_qty = supplier_item.get('pack_qty')
        brand_id = supplier_item.get('brand_id')
    
    # Режим 2: По reference_id (из избранного)
    elif request.reference_id:
        # Ищем в favorites_v12
        fav = db.favorites_v12.find_one({'reference_id': request.reference_id}, {'_id': 0})
        if not fav:
            fav = db.favorites_v12.find_one({'id': request.reference_id}, {'_id': 0})
        
        # Или в catalog_references
        if not fav:
            fav = db.catalog_references.find_one({'reference_id': request.reference_id}, {'_id': 0})
        
        if not fav:
            raise HTTPException(status_code=404, detail="Reference не найден")
        
        product_name = fav.get('product_name', fav.get('name', ''))
        unit_type = fav.get('unit_type', 'PIECE')
        super_class = fav.get('super_class', '')
        pack_qty = fav.get('pack_value')
        brand_id = fav.get('brand_id')
        
        # Получаем закреплённый supplier_item_id из избранного
        anchor_id = fav.get('anchor_supplier_item_id') or fav.get('best_supplier_id')
        
        # Проверяем что anchor ещё активен
        if anchor_id:
            anchor_item = db.supplier_items.find_one(
                {'id': anchor_id, 'active': True},
                {'_id': 0}
            )
            if anchor_item:
                supplier_item_id = anchor_item['id']
                price = anchor_item.get('price', 0)
                supplier_id = anchor_item.get('supplier_company_id')
                product_name = anchor_item.get('name_raw', product_name)
                supplier_item = anchor_item
        
        # Если anchor неактивен - ищем замену по product_core_id + unit_type
        if not supplier_item_id and fav.get('product_core_id'):
            replacement = db.supplier_items.find_one(
                {
                    'active': True,
                    'price': {'$gt': 0},
                    'product_core_id': fav['product_core_id'],
                    'unit_type': fav.get('unit_type', 'PIECE')
                },
                {'_id': 0},
                sort=[('price', 1)]  # Самый дешёвый
            )
            if replacement:
                supplier_item_id = replacement['id']
                price = replacement.get('price', 0)
                supplier_id = replacement.get('supplier_company_id')
                product_name = replacement.get('name_raw', product_name)
                supplier_item = replacement
                # Обновляем избранное с новым anchor
                db.favorites_v12.update_one(
                    {'reference_id': request.reference_id},
                    {'$set': {
                        'anchor_supplier_item_id': supplier_item_id,
                        'best_price': price,
                        'best_supplier_id': supplier_id,
                        'updated_at': datetime.now(timezone.utc).isoformat()
                    }}
                )
        
        if not supplier_item_id:
            raise HTTPException(
                status_code=400, 
                detail="Товар временно недоступен (нет активных офферов)"
            )
    
    else:
        raise HTTPException(status_code=400, detail="Укажите reference_id или supplier_item_id")
    
    # Получаем имя поставщика
    supplier_name = ""
    if supplier_id:
        company = db.companies.find_one({'id': supplier_id}, {'companyName': 1, 'name': 1})
        supplier_name = company.get('companyName', company.get('name', 'Unknown')) if company else 'Unknown'
    
    # Сохраняем intent с КОНКРЕТНЫМ supplier_item_id
    intent_data = {
        'user_id': request.user_id,
        'reference_id': request.reference_id or f"direct_{supplier_item_id}",
        'supplier_item_id': supplier_item_id,  # КЛЮЧЕВОЕ: сохраняем конкретный оффер
        'qty': request.qty,
        'product_name': product_name,
        'price': price,
        'unit_type': unit_type,
        'supplier_id': supplier_id,
        'supplier_name': supplier_name,
        'super_class': super_class,
        'pack_qty': pack_qty,
        'brand_id': brand_id,
        'locked': request.lock_offer,  # Флаг блокировки замены
        'created_at': datetime.now(timezone.utc).isoformat(),
        'updated_at': datetime.now(timezone.utc).isoformat(),
    }
    
    # Upsert - обновляем если уже есть такой товар
    db.cart_intents.update_one(
        {'user_id': request.user_id, 'supplier_item_id': supplier_item_id},
        {'$set': intent_data},
        upsert=True
    )
    
    return {
        'status': 'ok',
        'intent': {
            'product_name': product_name,
            'price': price,
            'qty': request.qty,
            'supplier_name': supplier_name,
            'supplier_item_id': supplier_item_id,
        },
        'message': 'Добавлено в корзину'
    }


@router.put("/cart/intent/{item_id}", summary="Обновить qty intent")
async def update_cart_intent(
    item_id: str,
    request: CartIntentUpdateRequest,
    user_id: str = Query(..., description="ID пользователя")
):
    """Обновляет количество для intent. item_id = supplier_item_id или reference_id"""
    db = get_db()
    
    # Try by supplier_item_id first
    result = db.cart_intents.update_one(
        {'user_id': user_id, 'supplier_item_id': item_id},
        {'$set': {
            'qty': request.qty,
            'updated_at': datetime.now(timezone.utc).isoformat()
        }}
    )
    
    # Fallback: try by reference_id
    if result.matched_count == 0:
        result = db.cart_intents.update_one(
            {'user_id': user_id, 'reference_id': item_id},
            {'$set': {
                'qty': request.qty,
                'updated_at': datetime.now(timezone.utc).isoformat()
            }}
        )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Intent не найден")
    
    return {'status': 'ok', 'qty': request.qty}


@router.delete("/cart/intent/{item_id}", summary="Удалить intent")
async def remove_cart_intent(
    item_id: str,
    user_id: str = Query(..., description="ID пользователя")
):
    """Удаляет intent из корзины. item_id = supplier_item_id или reference_id"""
    db = get_db()
    
    # Try by supplier_item_id first
    result = db.cart_intents.delete_one({'user_id': user_id, 'supplier_item_id': item_id})
    
    # Fallback: try by reference_id
    if result.deleted_count == 0:
        result = db.cart_intents.delete_one({'user_id': user_id, 'reference_id': item_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Intent не найден")
    
    return {'status': 'ok'}


@router.get("/cart/plan", summary="Получить оптимизированный план")
async def get_cart_plan(user_id: str = Query(..., description="ID пользователя")):
    """
    Запускает оптимизатор и возвращает план распределения по поставщикам.
    
    НОВОЕ (P0.1): Сохраняет snapshot плана в БД и возвращает plan_id.
    Checkout должен использовать этот plan_id, а не пересчитывать план.
    
    Вызывать ТОЛЬКО при нажатии "Оформить заказ".
    До этого корзина отображается как есть (без оптимизации).
    """
    db = get_db()
    
    from .optimizer import optimize_cart, plan_to_dict
    from .plan_snapshot import (
        compute_cart_hash, get_min_order_map, save_plan_snapshot
    )
    
    # 1. Запускаем оптимизацию
    result = optimize_cart(db, user_id)
    plan_payload = plan_to_dict(result)
    
    # 2. Вычисляем хэш корзины и получаем минималки
    cart_hash = compute_cart_hash(db, user_id)
    min_order_map = get_min_order_map(db)
    
    # 3. Сохраняем snapshot
    plan_id = save_plan_snapshot(db, user_id, plan_payload, cart_hash, min_order_map)
    
    # 4. Добавляем plan_id в ответ
    plan_payload['plan_id'] = plan_id
    
    return plan_payload


class CheckoutRequest(BaseModel):
    """Запрос checkout с plan_id"""
    plan_id: str = Field(..., description="ID сохранённого плана из /cart/plan")
    delivery_address_id: Optional[str] = Field(None, description="ID адреса доставки")


@router.post("/cart/checkout", summary="Подтвердить и создать заказы")
async def checkout_cart(
    request: CheckoutRequest,
    user_id: str = Query(..., description="ID пользователя")
):
    """
    Финализирует корзину и создаёт заказы.
    
    НОВОЕ (P0.1): Использует сохранённый plan_id, а НЕ пересчитывает план.
    
    1. Загружает plan snapshot по plan_id
    2. Проверяет что корзина не изменилась (cart_hash)
    3. Если изменилась → возвращает PLAN_CHANGED (409)
    4. Создаёт заказы из сохранённого плана
    5. Очищает корзину ТОЛЬКО после успешной записи заказов
    """
    import uuid as uuid_module
    
    db = get_db()
    
    logger.info(f"=== CHECKOUT START for user {user_id}, plan_id={request.plan_id} ===")
    
    from .plan_snapshot import (
        load_plan_snapshot, validate_cart_unchanged, 
        delete_plan_snapshot, compute_cart_hash
    )
    
    # 1. Загружаем snapshot плана
    plan_data, error = load_plan_snapshot(db, request.plan_id, user_id)
    
    if error:
        logger.warning(f"Plan snapshot load failed: {error}")
        return {
            'status': 'error',
            'code': 'PLAN_NOT_FOUND',
            'message': error
        }
    
    # 2. Проверяем что корзина не изменилась
    saved_hash = plan_data.get('cart_hash', '')
    cart_valid, current_hash = validate_cart_unchanged(db, user_id, saved_hash)
    
    if not cart_valid:
        logger.warning(f"Cart changed since plan was created. Saved: {saved_hash[:8]}, Current: {current_hash[:8]}")
        return {
            'status': 'error',
            'code': 'PLAN_CHANGED',
            'message': 'Корзина была изменена. Пожалуйста, сформируйте план заново.',
            'need_replan': True
        }
    
    # 3. Используем сохранённый план
    plan_payload = plan_data.get('plan_payload', {})
    
    # Проверяем success в плане
    if not plan_payload.get('success', False):
        logger.warning(f"Checkout blocked: {plan_payload.get('blocked_reason')}")
        return {
            'status': 'blocked',
            'message': plan_payload.get('blocked_reason') or 'Невозможно оформить заказ',
            'plan': plan_payload
        }
    
    suppliers = plan_payload.get('suppliers', [])
    
    if not suppliers:
        logger.warning("No suppliers in plan")
        return {
            'status': 'error',
            'code': 'EMPTY_PLAN',
            'message': 'План пуст. Добавьте товары в корзину.'
        }
    
    # 4. Создаём заказы из сохранённого плана
    created_orders = []
    total_amount = 0
    
    try:
        for supplier_data in suppliers:
            order_items = []
            
            for item in supplier_data.get('items', []):
                order_items.append({
                    'productName': item.get('product_name', ''),
                    'article': item.get('supplier_item_id', ''),
                    'quantity': item.get('final_qty', 0),
                    'price': item.get('price', 0),
                    'unit': 'кг' if item.get('unit_type') == 'WEIGHT' else 'л' if item.get('unit_type') == 'VOLUME' else 'шт',
                    'flags': item.get('flags', []),
                    'requested_qty': item.get('requested_qty', 0),
                    'supplier_changed': item.get('supplier_changed', False),
                    'brand_changed': item.get('brand_changed', False),
                    'qty_changed_by_topup': item.get('qty_changed_by_topup', False),
                })
            
            order_id = str(uuid_module.uuid4())
            supplier_subtotal = supplier_data.get('subtotal', 0)
            
            order_data = {
                'id': order_id,
                'supplier_company_id': supplier_data.get('supplier_id'),
                'customer_user_id': user_id,
                'amount': supplier_subtotal,
                'items': order_items,
                'status': 'pending',
                'delivery_address_id': request.delivery_address_id,
                'plan_id': request.plan_id,  # Ссылка на план
                'created_at': datetime.now(timezone.utc).isoformat(),
            }
            
            # Сохраняем в orders_v12 (основная коллекция заказов)
            db.orders_v12.insert_one(order_data)
            logger.info(f"Created order {order_id} for supplier {supplier_data.get('supplier_name')}, amount={supplier_subtotal}")
            
            total_amount += supplier_subtotal
            
            created_orders.append({
                'id': order_id,
                'supplier_id': supplier_data.get('supplier_id'),
                'supplier_name': supplier_data.get('supplier_name'),
                'amount': supplier_subtotal,
                'items_count': len(order_items),
            })
        
        # 5. Очищаем корзину ТОЛЬКО после успешного создания заказов
        db.cart_intents.delete_many({'user_id': user_id})
        db.cart_items_v12.delete_many({'user_id': user_id})
        
        # 6. Удаляем использованный план
        delete_plan_snapshot(db, request.plan_id, user_id)
        
        logger.info(f"=== CHECKOUT COMPLETE: {len(created_orders)} orders created, total={total_amount} ===")
        
        return {
            'status': 'ok',
            'message': f'Создано {len(created_orders)} заказов',
            'orders': created_orders,
            'total': total_amount
        }
        
    except Exception as e:
        logger.error(f"Checkout failed: {str(e)}")
        # НЕ очищаем корзину при ошибке!
        return {
            'status': 'error',
            'code': 'CHECKOUT_FAILED',
            'message': f'Ошибка создания заказа: {str(e)}'
        }


# === SUPPLIER MINIMUM MANAGEMENT ===

@router.get("/suppliers/minimums", summary="Получить минималки поставщиков")
async def get_supplier_minimums():
    """Возвращает минималки всех поставщиков"""
    db = get_db()
    
    # Получаем всех поставщиков с товарами
    supplier_ids = db.supplier_items.distinct('supplier_company_id', {'active': True})
    
    result = []
    for sid in supplier_ids:
        company = db.companies.find_one({'id': sid}, {'_id': 0, 'companyName': 1, 'name': 1, 'min_order_amount': 1})
        if company:
            result.append({
                'supplier_id': sid,
                'name': company.get('companyName', company.get('name', 'Unknown')),
                'min_order_amount': company.get('min_order_amount', 10000.0)
            })
    
    return {'suppliers': result}


@router.put("/suppliers/{supplier_id}/minimum", summary="Установить минималку поставщика")
async def set_supplier_minimum(
    supplier_id: str,
    min_order_amount: float = Query(..., ge=0, description="Минимальная сумма заказа в рублях")
):
    """Устанавливает минималку для поставщика"""
    db = get_db()
    
    result = db.companies.update_one(
        {'id': supplier_id},
        {'$set': {'min_order_amount': min_order_amount}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Поставщик не найден")
    
    return {
        'status': 'ok',
        'supplier_id': supplier_id,
        'min_order_amount': min_order_amount
    }


# === ORDERS HISTORY ===

@router.get("/orders", summary="Получить историю заказов")
async def get_orders_history(user_id: str = Query(..., description="ID пользователя")):
    """
    Возвращает историю заказов пользователя.
    Заказы отсортированы по дате (новые первые).
    
    ВАЖНО (P0.3): Читает из orders_v12 (основная коллекция).
    """
    db = get_db()
    
    # Читаем из orders_v12 (основная коллекция) + fallback на orders (старая)
    orders_v12 = list(db.orders_v12.find(
        {'customer_user_id': user_id},
        {'_id': 0}
    ).sort('created_at', -1))
    
    # Также проверяем старую коллекцию orders для обратной совместимости
    orders_old = list(db.orders.find(
        {'customer_user_id': user_id},
        {'_id': 0}
    ).sort('created_at', -1))
    
    # Объединяем и сортируем
    all_orders_raw = orders_v12 + orders_old
    all_orders_raw.sort(key=lambda x: x.get('created_at', ''), reverse=True)
    
    # Enrich with supplier names
    orders = []
    seen_ids = set()  # Избегаем дубликатов
    
    for order in all_orders_raw:
        order_id = order.get('id', order.get('created_at', ''))
        if order_id in seen_ids:
            continue
        seen_ids.add(order_id)
        
        supplier_id = order.get('supplier_company_id')
        company = db.companies.find_one({'id': supplier_id}, {'companyName': 1, 'name': 1})
        supplier_name = company.get('companyName', company.get('name', 'Unknown')) if company else 'Unknown'
        
        orders.append({
            'id': order_id,
            'supplier_id': supplier_id,
            'supplier_name': supplier_name,
            'amount': order.get('amount', 0),
            'status': order.get('status', 'pending'),
            'items': order.get('items', []),
            'items_count': len(order.get('items', [])),
            'created_at': order.get('created_at'),
            'delivery_address_id': order.get('delivery_address_id'),
        })
    
    return {
        'orders': orders,
        'total_count': len(orders)
    }


@router.get("/orders/{order_id}", summary="Получить детали заказа")
async def get_order_details(order_id: str):
    """Возвращает детали конкретного заказа"""
    db = get_db()
    
    # Ищем сначала в orders_v12, потом в orders
    order = db.orders_v12.find_one(
        {'id': order_id},
        {'_id': 0}
    )
    
    if not order:
        order = db.orders.find_one(
            {'id': order_id},
            {'_id': 0}
        )
    
    # Fallback: поиск по created_at (старый формат)
    if not order:
        order = db.orders.find_one(
            {'created_at': order_id},
            {'_id': 0}
        )
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    # Enrich with supplier name
    supplier_id = order.get('supplier_company_id')
    company = db.companies.find_one({'id': supplier_id}, {'companyName': 1, 'name': 1})
    supplier_name = company.get('companyName', company.get('name', 'Unknown')) if company else 'Unknown'
    
    return {
        'id': order.get('id', order.get('created_at', '')),
        'supplier_id': supplier_id,
        'supplier_name': supplier_name,
        'amount': order.get('amount', 0),
        'status': order.get('status', 'pending'),
        'items': order.get('items', []),
        'created_at': order.get('created_at'),
        'delivery_address_id': order.get('delivery_address_id'),
    }


# === OFFER ALTERNATIVES (P1 - Выбор оффера) ===

# Словари для извлечения компонентов из названия товара
# ВИД продукта (species)
SPECIES_PATTERNS = {
    'лосось': ['лосось', 'лососев', 'сёмга', 'семга', 'семги', 'сёмги', 'атлантическ'],
    'горбуша': ['горбуша', 'горбуш'],
    'кета': ['кета', 'кеты'],
    'форель': ['форель', 'форели'],
    'минтай': ['минтай', 'минтая'],
    'треска': ['треска', 'трески', 'трескова'],
    'сельдь': ['сельдь', 'сельди', 'селёдка', 'селедк'],
    'скумбрия': ['скумбрия', 'скумбри'],
    'курица': ['курица', 'курицы', 'куриц', 'курин', 'цыплен', 'цыплят', 'бройлер'],
    'говядина': ['говядина', 'говяжь', 'говяж', 'телятин'],
    'свинина': ['свинина', 'свинин', 'свиной', 'свиная'],
    'индейка': ['индейка', 'индейки', 'индюш'],
    'утка': ['утка', 'утки', 'утиная', 'утиное'],
    'кролик': ['кролик', 'кроличь', 'крольчат'],
    'баранина': ['баранина', 'баранин', 'ягнят', 'ягненок'],
}

# ФОРМА продукта (form)
FORM_PATTERNS = {
    'филе': ['филе', 'филей'],
    'тушка': ['тушка', 'тушки'],
    'стейк': ['стейк', 'стейки'],
    'потрошеный': ['потрошен', 'потрошён', 'птг', 'пбг'],
    'набор_суповой': ['набор', 'суповой', 'супов'],
    'консервы': ['консерв', 'ж/б', 'жб', 'натуральн'],
    'грудка': ['грудка', 'грудки', 'грудок'],
    'бедро': ['бедро', 'бедра', 'окорочок', 'окорочк'],
    'крыло': ['крыло', 'крылья', 'крылышк'],
    'фарш': ['фарш'],
    'котлеты': ['котлет'],
    'колбаса': ['колбас', 'сосиск', 'сардельк'],
}

# ТИП ОБРАБОТКИ (processing)
PROCESSING_PATTERNS = {
    'smoked': ['копчен', 'копч.', 'х/к', 'г/к', 'холодного копчения', 'горячего копчения'],
    'salted': ['солен', 'посол', 'слабосол', 'малосол', 'пресерв'],
    'dried': ['вялен', 'сушен'],
    'marinated': ['марин'],
    'canned': ['консерв', 'ж/б'],
    'chilled': ['охл', 'охлажд'],
    'frozen': ['с/м', 'свежеморож', 'заморож', 'морожен', 'зам.'],
    'fresh': ['свеж'],
}


def extract_product_components(name_norm: str) -> dict:
    """
    Извлекает ключевые компоненты из названия товара.
    
    Returns:
        dict с ключами: species, form, processing
    """
    name = name_norm.lower()
    
    # Определяем вид
    species = None
    for sp, patterns in SPECIES_PATTERNS.items():
        for p in patterns:
            if p in name:
                species = sp
                break
        if species:
            break
    
    # Определяем форму
    form = None
    for f, patterns in FORM_PATTERNS.items():
        for p in patterns:
            if p in name:
                form = f
                break
        if form:
            break
    
    # Определяем обработку
    processing = None
    for proc, patterns in PROCESSING_PATTERNS.items():
        for p in patterns:
            if p in name:
                processing = proc
                break
        if processing:
            break
    
    return {'species': species, 'form': form, 'processing': processing}


def calculate_relevance_score(source_comps: dict, candidate_comps: dict, 
                               source_name: str, candidate_name: str) -> int:
    """
    Вычисляет score релевантности кандидата к исходному товару.
    
    Scoring:
    - species match: +100
    - form match: +50  
    - processing match: +25
    - same brand: +10
    
    Returns:
        int score (больше = более релевантный)
    """
    score = 0
    
    # ВИД — самый важный (должен совпадать для истинной альтернативы)
    if source_comps['species'] and source_comps['species'] == candidate_comps['species']:
        score += 100
    elif source_comps['species'] is None or candidate_comps['species'] is None:
        score += 20  # Если не определён — небольшой бонус
    
    # ФОРМА — очень важна
    if source_comps['form'] and source_comps['form'] == candidate_comps['form']:
        score += 50
    elif source_comps['form'] is None or candidate_comps['form'] is None:
        score += 10
    
    # ОБРАБОТКА — важна но менее критична
    if source_comps['processing'] and source_comps['processing'] == candidate_comps['processing']:
        score += 25
    elif source_comps['processing'] is None or candidate_comps['processing'] is None:
        score += 5
    
    # Бонус за совпадение слов в названии (нечёткий matching)
    source_words = set(source_name.lower().split())
    candidate_words = set(candidate_name.lower().split())
    common_words = source_words & candidate_words
    # Исключаем стоп-слова
    stop_words = {'вес', 'кг', 'гр', 'шт', 'уп', 'россия', 'чили', 'с/м', 'охл'}
    meaningful_common = [w for w in common_words if len(w) >= 3 and w not in stop_words]
    score += len(meaningful_common) * 3
    
    return score


@router.get("/item/{item_id}/alternatives", summary="Получить альтернативные офферы")
async def get_item_alternatives(
    item_id: str, 
    limit: int = Query(10, le=20),
    mode: str = Query('strict', description="Режим: 'strict' (по умолчанию) или 'similar' (по кнопке)"),
    include_similar: bool = Query(False, description="DEPRECATED: используйте mode='similar'")
):
    """
    Возвращает альтернативные офферы для товара (v9.1 - "Нулевой мусор").
    
    РЕЖИМЫ ВЫДАЧИ:
    
    1. mode='strict' (по умолчанию):
       - Только точные аналоги
       - Если нет — возвращает пустой список
       - Similar не возвращается
    
    2. mode='similar' (по кнопке):
       - Возвращает Strict + Similar
       - Similar с лейблами отличий
    
    HARD-ПРАВИЛА (Strict 1-в-1):
    - PROCESSING_FORM: CANNED ≠ SMOKED ≠ FROZEN_RAW
    - CUT_TYPE: FILLET ≠ WHOLE_TUSHKA ≠ STEAK
    - SPECIES: окунь ≠ сибас ≠ скумбрия
    - IS_BOX: короб исключается если REF не короб
    - Креветки: state/form/caliber строго 1-в-1
    
    РАНЖИРОВАНИЕ:
    1. Близость размера/калибра
    2. Совпадение бренда
    3. ppu_value
    """
    # Backward compatibility: include_similar=true → mode='similar'
    if include_similar and mode == 'strict':
        mode = 'similar'
    
    db = get_db()
    
    # Получаем исходный товар
    source_item = db.supplier_items.find_one(
        {'id': item_id, 'active': True},
        {'_id': 0}
    )
    
    if not source_item:
        return {
            'source': None,
            'strict': [],
            'similar': [],
            'alternatives': [],
            'total': 0
        }
    
    product_core_id = source_item.get('product_core_id')
    
    # Получаем кандидатов из БД
    candidates_query = {
        'active': True,
        'price': {'$gt': 0},
        'id': {'$ne': item_id},
    }
    
    if product_core_id:
        candidates_query['product_core_id'] = product_core_id
    else:
        return {
            'source': {
                'id': source_item.get('id'),
                'name': source_item.get('name_raw', ''),
                'price': source_item.get('price', 0),
                'product_core_id': None,
            },
            'strict': [],
            'similar': [],
            'alternatives': [],
            'total': 0,
            'reason': 'no_product_core_id'
        }
    
    # Получаем кандидатов (увеличенный лимит для NPC фильтрации)
    raw_candidates = list(db.supplier_items.find(
        candidates_query,
        {'_id': 0}
    ).limit(200))  # topK=200 как в ТЗ
    
    # === NPC MATCHING (для SHRIMP/FISH/SEAFOOD/MEAT) ===
    # Проверяем, относится ли source к NPC домену
    source_npc_domain = get_item_npc_domain(source_item)
    use_npc = source_npc_domain is not None
    
    # Обогащаем данными поставщика (общая функция)
    supplier_cache = {}
    
    def get_supplier_info(supplier_id: str) -> dict:
        if not supplier_id:
            return {'name': 'Unknown', 'min_order': 10000}
        if supplier_id not in supplier_cache:
            company = db.companies.find_one(
                {'id': supplier_id}, 
                {'companyName': 1, 'name': 1, 'min_order_amount': 1}
            )
            supplier_cache[supplier_id] = {
                'name': company.get('companyName', company.get('name', 'Unknown')) if company else 'Unknown',
                'min_order': company.get('min_order_amount', 10000) if company else 10000
            }
        return supplier_cache[supplier_id]
    
    if use_npc:
        # === NPC PATH: применяем NPC фильтрацию ===
        logger.info(f"Using NPC matching for item {item_id}, domain={source_npc_domain}")
        
        # Сначала получаем кандидатов через v3 engine (для базовой фильтрации по product_core_id)
        v3_result = find_alternatives_v3(
            source_item=source_item,
            candidates=raw_candidates,
            limit=200,  # Берём много для NPC фильтрации
            strict_threshold=999  # Не применяем Similar threshold на этом этапе
        )
        
        # Собираем всех кандидатов из v3 для NPC фильтрации
        v3_candidates = []
        for alt in v3_result.strict:
            # Находим оригинальный item
            orig_item = next((c for c in raw_candidates if c.get('id') == alt.get('id')), None)
            if orig_item:
                v3_candidates.append(orig_item)
        
        # Применяем NPC фильтр
        npc_strict, npc_similar, npc_rejected = apply_npc_filter(
            source_item=source_item,
            candidates=v3_candidates if v3_candidates else raw_candidates,
            limit=limit,
            mode=mode  # 'strict' или 'similar'
        )
        
        # Если NPC вернул None - fallback на legacy
        if npc_strict is None:
            use_npc = False
            logger.info(f"NPC returned None for item {item_id}, falling back to legacy")
        else:
            # Форматируем NPC результаты
            def enrich_npc_item(npc_data: dict, mode: str) -> dict:
                item = npc_data['item']
                npc_result = npc_data['npc_result']
                npc_sig = npc_data['npc_signature']
                supplier_id = item.get('supplier_company_id')
                sup_info = get_supplier_info(supplier_id)
                
                return {
                    'id': item.get('id'),
                    'name': item.get('name_raw', ''),
                    'name_raw': item.get('name_raw', ''),
                    'price': item.get('price', 0),
                    'pack_qty': item.get('pack_qty'),
                    'unit_type': item.get('unit_type', 'PIECE'),
                    'brand_id': item.get('brand_id'),
                    'supplier_id': supplier_id,
                    'supplier_name': sup_info['name'],
                    'supplier_min_order': sup_info['min_order'],
                    'min_order_qty': item.get('min_order_qty', 1),
                    'match_score': npc_result.npc_score,
                    'match_mode': mode,
                    'difference_labels': npc_result.difference_labels,
                    # NPC specific fields
                    'npc_domain': npc_sig.npc_domain,
                    'npc_node_id': npc_sig.npc_node_id,
                }
            
            enriched_strict = [enrich_npc_item(x, 'strict') for x in npc_strict]
            enriched_similar = [enrich_npc_item(x, 'similar') for x in npc_similar]
            
            # Source enrichment
            source_npc_sig = extract_npc_signature(source_item)
            source_supplier_id = source_item.get('supplier_company_id')
            source_sup_info = get_supplier_info(source_supplier_id)
            
            enriched_source = {
                'id': source_item.get('id'),
                'name': source_item.get('name_raw', ''),
                'name_raw': source_item.get('name_raw', ''),
                'price': source_item.get('price', 0),
                'pack_qty': source_item.get('pack_qty'),
                'unit_type': source_item.get('unit_type', 'PIECE'),
                'brand_id': source_item.get('brand_id'),
                'product_core_id': product_core_id,
                'supplier_id': source_supplier_id,
                'supplier_name': source_sup_info['name'],
                'supplier_min_order': source_sup_info['min_order'],
                # NPC fields
                'npc_domain': source_npc_sig.npc_domain,
                'npc_node_id': source_npc_sig.npc_node_id,
                'npc_signature': {
                    'shrimp_species': source_npc_sig.shrimp_species,
                    'shrimp_caliber': source_npc_sig.shrimp_caliber,
                    'fish_species': source_npc_sig.fish_species,
                    'fish_cut': source_npc_sig.fish_cut,
                    'seafood_type': source_npc_sig.seafood_type,
                    'meat_animal': source_npc_sig.meat_animal,
                    'meat_cut': source_npc_sig.meat_cut,
                }
            }
            
            all_alternatives = enriched_strict + enriched_similar
            
            return {
                'source': enriched_source,
                'strict': enriched_strict,
                'similar': enriched_similar,
                'alternatives': all_alternatives,
                'strict_count': len(enriched_strict),
                'similar_count': len(enriched_similar),
                'total': len(all_alternatives),
                'total_candidates': len(v3_candidates) if v3_candidates else len(raw_candidates),
                'rejected_reasons': npc_rejected,
                'matching_mode': 'npc',
                'npc_domain': source_npc_domain,
            }
    
    # === LEGACY PATH: используем matching_engine_v3 ===
    result = find_alternatives_v3(
        source_item=source_item,
        candidates=raw_candidates,
        limit=limit,
        strict_threshold=4 if include_similar else 999
    )
    
    def enrich_item(alt: dict) -> dict:
        supplier_id = alt.get('supplier_company_id')
        sup_info = get_supplier_info(supplier_id)
        
        return {
            'id': alt.get('id'),
            'name': alt.get('name_raw', alt.get('name', '')),
            'name_raw': alt.get('name_raw', ''),
            'price': alt.get('price', 0),
            'pack_qty': alt.get('pack_qty'),
            'pack_value': alt.get('pack_value'),
            'unit_type': alt.get('unit_type', 'PIECE'),
            'brand_id': alt.get('brand_id'),
            'supplier_id': supplier_id,
            'supplier_name': sup_info['name'],
            'supplier_min_order': sup_info['min_order'],
            'min_order_qty': alt.get('min_order_qty', 1),
            'ppu_value': alt.get('ppu_value', 0),
            'min_line_total': alt.get('min_line_total', 0),
            'match_score': alt.get('match_score', 0),
            'match_mode': alt.get('match_mode', 'strict'),
            'brand_match': alt.get('brand_match', False),
            'pack_diff_pct': alt.get('pack_diff_pct', 0),
            'difference_labels': alt.get('difference_labels', []),
        }
    
    # Enrich source
    source_supplier_id = source_item.get('supplier_company_id')
    source_sup_info = get_supplier_info(source_supplier_id)
    source_data = result.source
    
    # Используем brand_id из signature (извлечённый из названия) если в БД пусто
    source_brand_id = source_item.get('brand_id') or source_data.get('brand_id')
    
    enriched_source = {
        'id': source_item.get('id'),
        'name': source_item.get('name_raw', ''),
        'name_raw': source_item.get('name_raw', ''),
        'price': source_item.get('price', 0),
        'pack_qty': source_item.get('pack_qty'),
        'pack_value': source_data.get('pack_value'),
        'unit_type': source_item.get('unit_type', 'PIECE'),
        'brand_id': source_brand_id,
        'product_core_id': product_core_id,
        'category_group': source_data.get('category_group'),
        'supplier_id': source_supplier_id,
        'supplier_name': source_sup_info['name'],
        'supplier_min_order': source_sup_info['min_order'],
        'signature': source_data.get('signature', {}),
    }
    
    # Enrich strict и similar
    enriched_strict = [enrich_item(alt) for alt in result.strict]
    enriched_similar = [enrich_item(alt) for alt in result.similar]
    
    # Backward compatibility: flat alternatives list
    all_alternatives = enriched_strict + enriched_similar
    
    return {
        'source': enriched_source,
        'strict': enriched_strict,
        'similar': enriched_similar,
        'alternatives': all_alternatives,  # Backward compatible
        'strict_count': result.strict_count,
        'similar_count': result.similar_count,
        'total': len(all_alternatives),
        'total_candidates': result.total_candidates,
        'rejected_reasons': result.rejected_reasons,
        'matching_mode': 'legacy',
    }


# === DATA QUALITY / VALIDATION ===

from .offer_validator import (
    validate_offer, validate_offers_batch, 
    mark_invalid_offers, cleanup_favorites_invalid,
    validate_cart_before_checkout, get_publishable_query
)


@router.get("/admin/data-quality", summary="Анализ качества данных")
async def get_data_quality_report():
    """
    Возвращает отчёт о качестве данных офферов.
    Показывает сколько офферов невалидны и почему.
    """
    db = get_db()
    
    total_active = db.supplier_items.count_documents({'active': True})
    
    # Count by validation issues
    no_price = db.supplier_items.count_documents({
        'active': True,
        '$or': [{'price': {'$lte': 0}}, {'price': None}, {'price': {'$exists': False}}]
    })
    
    no_unit = db.supplier_items.count_documents({
        'active': True,
        '$or': [{'unit_type': None}, {'unit_type': ''}, {'unit_type': {'$exists': False}}]
    })
    
    weight_volume_no_pack = db.supplier_items.count_documents({
        'active': True,
        'unit_type': {'$in': ['WEIGHT', 'VOLUME']},
        '$or': [{'pack_qty': {'$lte': 0}}, {'pack_qty': None}, {'pack_qty': {'$exists': False}}]
    })
    
    # Count publishable
    publishable_query = get_publishable_query()
    publishable = db.supplier_items.count_documents(publishable_query)
    
    # Get sample invalid items
    invalid_samples = list(db.supplier_items.find(
        {
            'active': True,
            '$or': [
                {'price': {'$lte': 0}},
                {'price': None},
                {'unit_type': None},
                {'unit_type': ''},
                {'unit_type': {'$in': ['WEIGHT', 'VOLUME']}, 'pack_qty': {'$lte': 0}}
            ]
        },
        {'_id': 0, 'name_raw': 1, 'price': 1, 'unit_type': 1, 'pack_qty': 1, 'supplier_company_id': 1}
    ).limit(20))
    
    # Enrich with supplier names
    for sample in invalid_samples:
        company = db.companies.find_one({'id': sample.get('supplier_company_id')}, {'companyName': 1})
        sample['supplier_name'] = company.get('companyName') if company else 'Unknown'
    
    return {
        'total_active': total_active,
        'publishable': publishable,
        'hidden': total_active - publishable,
        'issues': {
            'missing_or_invalid_price': no_price,
            'missing_unit_type': no_unit,
            'weight_volume_without_pack': weight_volume_no_pack
        },
        'invalid_samples': invalid_samples,
        'quality_score': round(publishable / total_active * 100, 1) if total_active > 0 else 0
    }


@router.post("/admin/cleanup-invalid", summary="Пометить невалидные офферы как inactive")
async def cleanup_invalid_offers(dry_run: bool = Query(True, description="Только показать что будет помечено")):
    """
    Помечает невалидные офферы как inactive.
    
    ВНИМАНИЕ: dry_run=False применит изменения!
    """
    db = get_db()
    result = mark_invalid_offers(db, dry_run=dry_run)
    return result


@router.post("/admin/cleanup-favorites", summary="Очистить невалидные позиции из избранного")
async def cleanup_invalid_favorites(user_id: Optional[str] = Query(None)):
    """
    Удаляет из избранного позиции, для которых нет валидных офферов.
    """
    db = get_db()
    result = cleanup_favorites_invalid(db, user_id)
    return result


@router.get("/admin/validate-cart", summary="Проверить корзину перед checkout")
async def validate_cart(user_id: str = Query(...)):
    """
    Валидирует корзину и удаляет невалидные позиции.
    Вызывается автоматически перед checkout.
    """
    db = get_db()
    is_valid, removed_items, messages = validate_cart_before_checkout(db, user_id)
    
    return {
        'is_valid': is_valid,
        'removed_items': removed_items,
        'messages': messages
    }


@router.post("/admin/validate-pricelist", summary="Валидировать прайс-лист поставщика")
async def validate_supplier_pricelist(supplier_id: str = Query(...)):
    """
    Валидирует все офферы поставщика и возвращает отчёт.
    Используется при загрузке прайса для feedback поставщику.
    """
    db = get_db()
    
    # Get all supplier items
    items = list(db.supplier_items.find(
        {'supplier_company_id': supplier_id},
        {'_id': 0}
    ))
    
    if not items:
        return {'error': 'Поставщик не найден или нет товаров'}
    
    # Validate batch
    result = validate_offers_batch(items)
    
    # Add supplier info
    company = db.companies.find_one({'id': supplier_id}, {'companyName': 1})
    result['supplier_name'] = company.get('companyName') if company else 'Unknown'
    result['supplier_id'] = supplier_id
    
    # Calculate rejection rate
    result['rejection_rate'] = round(result['invalid'] / result['total'] * 100, 1) if result['total'] > 0 else 0
    
    # Check if exceeds threshold (10%)
    result['exceeds_threshold'] = result['rejection_rate'] > 10
    result['threshold'] = 10
    
    return result
