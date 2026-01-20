"""
Favorites Routes Module - Избранное

Endpoints для работы с избранным.
"""

import logging
import uuid
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/favorites", tags=["Favorites"])


# === DB Access ===

_db = None

def set_db(db):
    global _db
    _db = db

def get_db():
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


# === Helpers ===

def generate_id():
    return str(uuid.uuid4())


def get_item_by_id(db, item_id: str):
    return db.supplier_items.find_one(
        {'id': item_id, 'active': True},
        {'_id': 0}
    )


# === Endpoints ===

@router.get("", summary="Получить избранное")
async def get_favorites(
    user_id: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0),
    search: Optional[str] = Query(None, description="Поиск по названию")
):
    """Получить список избранного с актуальными ценами"""
    db = get_db()
    
    query = {'user_id': user_id}
    
    favorites = list(db.favorites_v12.find(
        query,
        {'_id': 0}
    ).skip(skip).limit(limit))
    
    total = db.favorites_v12.count_documents(query)
    
    # Обогащаем актуальными данными товаров
    enriched = []
    for fav in favorites:
        item = get_item_by_id(db, fav.get('reference_id'))
        if item:
            fav['name'] = item.get('name_raw', fav.get('product_name', ''))
            fav['current_price'] = item.get('price')
            fav['unit_type'] = item.get('unit_type', 'PIECE')
            fav['super_class'] = item.get('super_class')
            fav['active'] = True
            fav['supplier_company_id'] = item.get('supplier_company_id')
            
            # Фильтр по поиску
            if search:
                if search.lower() not in fav['name'].lower():
                    continue
            
            enriched.append(fav)
        else:
            # Товар неактивен
            fav['active'] = False
            if not search:  # Показываем неактивные только без поиска
                enriched.append(fav)
    
    return {
        'favorites': enriched,
        'total': len(enriched) if search else total,
        'skip': skip,
        'limit': limit
    }


@router.post("", summary="Добавить в избранное")
async def add_to_favorites(
    user_id: str = Query(...),
    reference_id: str = Query(..., description="ID товара")
):
    """Добавить товар в избранное"""
    db = get_db()
    
    # Проверяем товар
    item = get_item_by_id(db, reference_id)
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден или неактивен")
    
    # Проверяем дубликат
    existing = db.favorites_v12.find_one({
        'user_id': user_id,
        'reference_id': reference_id
    })
    
    if existing:
        return {
            'status': 'exists',
            'message': 'Товар уже в избранном',
            'favorite_id': existing.get('id')
        }
    
    # Создаём запись
    favorite_id = f"fav_{reference_id}_{generate_id()[:8]}"
    
    favorite = {
        'id': favorite_id,
        'user_id': user_id,
        'reference_id': reference_id,
        'product_name': item.get('name_raw', ''),
        'price': item.get('price', 0),
        'unit_type': item.get('unit_type', 'PIECE'),
        'super_class': item.get('super_class'),
        'created_at': datetime.now(timezone.utc)
    }
    
    db.favorites_v12.insert_one(favorite)
    
    logger.info(f"Added to favorites for user {user_id}: {item.get('name_raw', '')[:30]}")
    
    return {
        'status': 'ok',
        'favorite_id': favorite_id
    }


@router.delete("/{favorite_id}", summary="Удалить из избранного")
async def delete_favorite(
    favorite_id: str,
    user_id: str = Query(...)
):
    """Удалить товар из избранного"""
    db = get_db()
    
    # Пробуем удалить по ID избранного
    result = db.favorites_v12.delete_one({
        'user_id': user_id,
        '$or': [
            {'id': favorite_id},
            {'reference_id': favorite_id}  # Также поддерживаем удаление по reference_id
        ]
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Позиция не найдена в избранном")
    
    return {'status': 'ok', 'deleted_count': 1}


@router.post("/clear", summary="Очистить избранное")
async def clear_favorites(user_id: str = Query(...)):
    """Удалить ВСЕ товары из избранного"""
    db = get_db()
    
    before = db.favorites_v12.count_documents({'user_id': user_id})
    result = db.favorites_v12.delete_many({'user_id': user_id})
    after = db.favorites_v12.count_documents({'user_id': user_id})
    
    logger.info(f"Cleared favorites for user {user_id}: {result.deleted_count} items")
    
    return {
        'status': 'ok',
        'deleted_count': result.deleted_count,
        'remaining_count': after
    }
