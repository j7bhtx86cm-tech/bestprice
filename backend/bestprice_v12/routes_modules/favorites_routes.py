"""
Favorites Routes - Избранное

Endpoints:
- GET /favorites - Получить избранное
- POST /favorites - Добавить в избранное
- DELETE /favorites/{favorite_id} - Удалить из избранного
- POST /favorites/clear - Очистить всё избранное
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Favorites"])


# === Pydantic Models ===

class AddFavoriteRequest(BaseModel):
    """Запрос на добавление в избранное"""
    user_id: str
    reference_id: str  # supplier_item_id


class FavoriteItem(BaseModel):
    """Элемент избранного"""
    id: str
    user_id: str
    reference_id: str
    product_name: str
    price: float
    unit_type: str
    super_class: Optional[str] = None


# === Helper Functions ===

def get_db():
    """Получить подключение к БД"""
    from .catalog import get_db as catalog_get_db
    return catalog_get_db()


# === Favorites Endpoints ===

"""
Future implementation:

@router.get("/favorites")
async def get_favorites(
    user_id: str = Query(...),
    limit: int = Query(100, ge=1, le=500),
    skip: int = Query(0, ge=0)
):
    db = get_db()
    
    favorites = list(db.favorites_v12.find(
        {'user_id': user_id},
        {'_id': 0}
    ).skip(skip).limit(limit))
    
    total = db.favorites_v12.count_documents({'user_id': user_id})
    
    # Enrich with current prices
    for fav in favorites:
        item = db.supplier_items.find_one(
            {'id': fav.get('reference_id'), 'active': True},
            {'_id': 0, 'price': 1, 'name_raw': 1}
        )
        if item:
            fav['current_price'] = item.get('price')
            fav['name'] = item.get('name_raw')
    
    return {
        'favorites': favorites,
        'total': total,
        'skip': skip,
        'limit': limit
    }


@router.post("/favorites/clear")
async def clear_favorites(user_id: str = Query(...)):
    db = get_db()
    
    before = db.favorites_v12.count_documents({'user_id': user_id})
    result = db.favorites_v12.delete_many({'user_id': user_id})
    after = db.favorites_v12.count_documents({'user_id': user_id})
    
    return {
        'status': 'ok',
        'deleted_count': result.deleted_count,
        'remaining_count': after
    }
"""
