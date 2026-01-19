"""
BestPrice v12 - API Routes

FastAPI роутер для v12 функционала
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
sys.path.insert(0, '/app/backend')
from search_utils import (
    tokenize, tokenize_with_lemmas, detect_brand_from_query,
    detect_brands_enhanced, BrandDetectionResult,
    calculate_ppu_value, calculate_min_line_total, normalize_text,
    STOP_WORDS
)
from russian_stemmer import stem_token_safe, generate_lemma_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v12", tags=["BestPrice v12"])


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
            is_last_token_complete = (
                last_token_raw != last_token_lemma or
                len(last_token_raw) >= 6
            )
            
            # Build text search query
            if len(q_tokens) == 1:
                if is_last_token_complete and q_lemmas:
                    query['lemma_tokens'] = {'$all': q_lemmas}
                else:
                    escaped_last = re.escape(last_token_raw)
                    query['name_norm'] = {'$regex': f'(^|\\s){escaped_last}'}
            else:
                if is_last_token_complete:
                    query['lemma_tokens'] = {'$all': q_lemmas}
                else:
                    full_lemmas = generate_lemma_tokens(q_tokens[:-1])
                    if full_lemmas:
                        query['lemma_tokens'] = {'$all': full_lemmas}
                    escaped_last = re.escape(last_token_raw)
                    query['name_norm'] = {'$regex': f'(^|\\s){escaped_last}'}
            
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
    build_final_plan, get_plan_summary_for_ui,
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


@router.delete("/cart/intents", summary="Очистить все intents")
async def clear_cart_intents(user_id: str = Query(..., description="ID пользователя")):
    """Очищает все intents пользователя"""
    db = get_db()
    
    result = db.cart_intents.delete_many({'user_id': user_id})
    
    return {'status': 'ok', 'deleted_count': result.deleted_count}


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


@router.get("/cart/plan", summary="Получить оптимизированный план")
async def get_cart_plan(user_id: str = Query(..., description="ID пользователя")):
    """
    Запускает оптимизатор и возвращает план распределения по поставщикам.
    
    Вызывать ТОЛЬКО при нажатии "Оформить заказ".
    До этого корзина отображается как есть (без оптимизации).
    """
    db = get_db()
    
    from .optimizer import optimize_cart, plan_to_dict
    
    result = optimize_cart(db, user_id)
    
    return plan_to_dict(result)


@router.post("/cart/checkout", summary="Подтвердить и создать заказы")
async def checkout_cart(user_id: str = Query(..., description="ID пользователя")):
    """
    Финализирует корзину и создаёт заказы.
    
    1. Валидирует корзину (удаляет невалидные позиции)
    2. Пересчитывает план
    3. Проверяет что все поставщики >= минималки
    4. Создаёт заказы
    5. Очищает корзину
    """
    db = get_db()
    
    # 0. Валидация корзины - удаляем невалидные позиции
    from .offer_validator import validate_cart_before_checkout
    cart_valid, removed_items, validation_messages = validate_cart_before_checkout(db, user_id)
    
    # 1. Пересчитываем план с новым оптимизатором
    from .optimizer import optimize_cart, plan_to_dict
    result = optimize_cart(db, user_id)
    
    # 2. Проверяем success
    if not result.success:
        response = {
            'status': 'blocked',
            'message': result.blocked_reason or 'Невозможно оформить заказ',
            'plan': plan_to_dict(result)
        }
        # Добавляем информацию об удалённых позициях
        if removed_items:
            response['removed_items'] = removed_items
            response['validation_messages'] = validation_messages
        return response
    
    # 3. Создаём заказы для каждого поставщика
    created_orders = []
    
    for supplier_plan in result.suppliers:
        order_items = []
        for line in supplier_plan.lines:
            product_name = line.intent.product_name if line.intent else ''
            if line.offer:
                product_name = line.offer.name_raw or product_name
            
            order_items.append({
                'productName': product_name,
                'article': line.offer.supplier_item_id if line.offer else '',
                'quantity': line.final_qty,
                'price': line.offer.price if line.offer else 0,
                'unit': 'кг' if (line.offer and line.offer.unit_type == 'WEIGHT') else 'л' if (line.offer and line.offer.unit_type == 'VOLUME') else 'шт',
                'flags': line.flags,
                'requested_qty': line.requested_qty,
                'supplier_changed': line.supplier_changed,
                'brand_changed': line.brand_changed,
                'qty_changed_by_topup': line.qty_changed_by_topup,
            })
        
        # Создаём заказ
        order_data = {
            'supplier_company_id': supplier_plan.supplier_id,
            'customer_user_id': user_id,
            'amount': supplier_plan.subtotal,
            'items': order_items,
            'status': 'pending',
            'created_at': datetime.now(timezone.utc).isoformat(),
        }
        
        # Сохраняем (используем существующую коллекцию orders)
        db.orders.insert_one(order_data)
        created_orders.append({
            'supplier_id': supplier_plan.supplier_id,
            'supplier_name': supplier_plan.supplier_name,
            'amount': supplier_plan.subtotal,
            'items_count': len(order_items),
        })
    
    # 4. Очищаем корзину
    db.cart_intents.delete_many({'user_id': user_id})
    # Также очищаем старую корзину на всякий случай
    db.cart_items_v12.delete_many({'user_id': user_id})
    
    return {
        'status': 'ok',
        'message': f'Создано {len(created_orders)} заказов',
        'orders': created_orders,
        'total': result.total
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
    """
    db = get_db()
    
    orders_raw = list(db.orders.find(
        {'customer_user_id': user_id},
        {'_id': 0}
    ).sort('created_at', -1))
    
    # Enrich with supplier names
    orders = []
    for order in orders_raw:
        supplier_id = order.get('supplier_company_id')
        company = db.companies.find_one({'id': supplier_id}, {'companyName': 1, 'name': 1})
        supplier_name = company.get('companyName', company.get('name', 'Unknown')) if company else 'Unknown'
        
        orders.append({
            'id': order.get('created_at', ''),  # Use created_at as ID for now
            'supplier_id': supplier_id,
            'supplier_name': supplier_name,
            'amount': order.get('amount', 0),
            'status': order.get('status', 'pending'),
            'items': order.get('items', []),
            'items_count': len(order.get('items', [])),
            'created_at': order.get('created_at'),
        })
    
    return {
        'orders': orders,
        'total_count': len(orders)
    }


@router.get("/orders/{order_id}", summary="Получить детали заказа")
async def get_order_details(order_id: str):
    """Возвращает детали конкретного заказа"""
    db = get_db()
    
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
        'id': order.get('created_at', ''),
        'supplier_id': supplier_id,
        'supplier_name': supplier_name,
        'amount': order.get('amount', 0),
        'status': order.get('status', 'pending'),
        'items': order.get('items', []),
        'created_at': order.get('created_at'),
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
