"""
BestPrice v12 - API Routes

FastAPI роутер для v12 функционала
"""

import logging
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
    calculate_ppu_value, calculate_min_line_total, normalize_text,
    STOP_WORDS
)
from russian_stemmer import stem_token_safe, generate_lemma_tokens

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/v12", tags=["BestPrice v12"])


# === CATALOG ENDPOINTS ===

import re

@router.get("/catalog", summary="Получить каталог с Best Price")
async def get_catalog(
    super_class: Optional[str] = Query(None, description="Фильтр по категории"),
    search: Optional[str] = Query(None, description="Поиск по названию"),
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
    - BestPrice ranking: match → brand → ppu/price → min_line_total
    """
    db = get_db()
    
    # Базовый фильтр
    query = {'active': True, 'price': {'$gt': 0}}
    
    # Фильтр по категории
    if super_class:
        query['super_class'] = {'$regex': f'^{super_class}', '$options': 'i'}
    
    # Фильтр по поставщику
    if supplier_id:
        query['supplier_company_id'] = supplier_id
    
    # === SEARCH LOGIC (v12 FINAL) ===
    q_tokens = []
    q_lemmas = []
    detected_brand_id = None
    is_search_mode = False
    last_token_raw = ''
    
    if search and search.strip():
        # Tokenize query with lemmas
        q_tokens, q_lemmas = tokenize_with_lemmas(search)
        
        if q_tokens:
            is_search_mode = True
            last_token_raw = q_tokens[-1]
            last_token_lemma = stem_token_safe(last_token_raw)
            
            # Check if last token looks like a complete word
            # If the raw token != its lemma, it's likely complete (e.g., креветки → креветк)
            # If raw == lemma and short, it's likely partial (e.g., крев → крев)
            is_last_token_complete = (
                last_token_raw != last_token_lemma or  # Has ending stripped
                len(last_token_raw) >= 6  # Long enough to be a word
            )
            
            if len(q_tokens) == 1:
                # Single token
                if is_last_token_complete and q_lemmas:
                    # Complete word: use lemma search
                    query['lemma_tokens'] = {'$all': q_lemmas}
                else:
                    # Partial: use prefix search
                    escaped_last = re.escape(last_token_raw)
                    query['name_norm'] = {'$regex': f'(^|\\s){escaped_last}'}
            else:
                # Multiple tokens
                # Use lemmas for all tokens except potentially partial last one
                if is_last_token_complete:
                    # All tokens complete: use lemma_tokens for all
                    query['lemma_tokens'] = {'$all': q_lemmas}
                else:
                    # Last token partial: lemmas for first N-1, prefix for last
                    full_lemmas = generate_lemma_tokens(q_tokens[:-1])
                    if full_lemmas:
                        query['lemma_tokens'] = {'$all': full_lemmas}
                    escaped_last = re.escape(last_token_raw)
                    query['name_norm'] = {'$regex': f'(^|\\s){escaped_last}'}
            
            # Detect brand from query tokens
            detected_brand_id = detect_brand_from_query(db, q_tokens)
            if not detected_brand_id:
                detected_brand_id = detect_brand_from_query(db, q_lemmas)
        else:
            # Empty tokens after filtering
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
            if detected_brand_id and item.get('brand_id') == detected_brand_id:
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
        # 1) match_score DESC
        # 2) brand_boost DESC
        # 3) ppu_value ASC (not null first)
        # 4) price ASC (fallback when ppu is null)
        # 5) min_line_total ASC (tie-breaker)
        # 6) name_norm ASC
        def sort_key(item):
            ppu = item.get('_ppu_value')
            price = item.get('_price', 0)
            
            # PPU sorting: not-null first (lower better), nulls use price as fallback
            if ppu is not None:
                ppu_priority = 0  # Has PPU
                ppu_sort = ppu
            else:
                ppu_priority = 1  # No PPU, use price
                ppu_sort = price
            
            return (
                -item.get('_match_score', 0),      # 1) match_score DESC
                -item.get('_brand_boost', 0),      # 2) brand_boost DESC
                ppu_priority,                      # 3) PPU items first
                ppu_sort,                          # 4) ppu/price ASC
                item.get('_min_line_total', 0),    # 5) min_line_total ASC
                item.get('name_norm', '')          # 6) name_norm ASC
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
