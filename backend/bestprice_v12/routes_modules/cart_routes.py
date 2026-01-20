"""
Cart Routes - Корзина и checkout

Endpoints:
- POST /cart/add - Добавить в корзину (legacy)
- GET /cart - Получить корзину
- GET /cart/intents - Получить intents
- DELETE /cart/intents - Очистить все intents
- POST /cart/intent - Добавить intent (новая модель)
- PUT /cart/intent/{item_id} - Обновить qty
- DELETE /cart/intent/{item_id} - Удалить intent
- GET /cart/plan - Получить оптимизированный план
- POST /cart/checkout - Подтвердить и создать заказы
- POST /cart/topup/{supplier_id} - Автодобивка
- DELETE /cart - Очистить корзину
- PUT /cart/{cart_item_id} - Обновить количество (legacy)
- DELETE /cart/{cart_item_id} - Удалить из корзины (legacy)
"""

import logging
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Cart"])


# === Pydantic Models ===

class AddIntentRequest(BaseModel):
    """Запрос на добавление intent в корзину"""
    user_id: str
    supplier_item_id: str
    qty: float = Field(gt=0, description="Количество > 0")
    locked: bool = False


class UpdateIntentRequest(BaseModel):
    """Запрос на обновление quantity"""
    qty: float = Field(gt=0)


class CheckoutRequest(BaseModel):
    """Запрос на checkout"""
    user_id: str
    plan_id: str = Field(..., description="ID плана из /cart/plan")


# === Helper Functions ===

def get_db():
    """Получить подключение к БД"""
    from .catalog import get_db as catalog_get_db
    return catalog_get_db()


def get_item_by_id(db, item_id: str):
    """Получить товар по ID"""
    return db.supplier_items.find_one(
        {'id': item_id, 'active': True},
        {'_id': 0}
    )


# === Cart Endpoints ===

# Note: Actual implementation remains in routes.py
# This file serves as documentation and future refactoring target

"""
Future migration plan:
1. Move endpoint implementations here
2. Update routes.py to import from this module
3. Remove old code from routes.py
4. Test thoroughly

Example endpoint structure:

@router.post("/intent")
async def add_intent(request: AddIntentRequest):
    db = get_db()
    
    # Validate item exists
    item = get_item_by_id(db, request.supplier_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден или неактивен")
    
    # Create intent
    intent = {
        'id': generate_id(),
        'user_id': request.user_id,
        'supplier_item_id': request.supplier_item_id,
        'product_name': item.get('name_raw', ''),
        'price': item.get('price', 0),
        'qty': request.qty,
        'unit_type': item.get('unit_type', 'PIECE'),
        'product_core_id': item.get('product_core_id'),
        'super_class': item.get('super_class'),
        'locked': request.locked,
        'created_at': datetime.now(timezone.utc)
    }
    
    # Upsert (update if exists, insert if not)
    db.cart_intents_v12.update_one(
        {'user_id': request.user_id, 'supplier_item_id': request.supplier_item_id},
        {'$set': intent},
        upsert=True
    )
    
    return {'status': 'ok', 'intent': intent}
"""
