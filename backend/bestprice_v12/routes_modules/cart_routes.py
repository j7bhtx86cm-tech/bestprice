"""
Cart Routes Module - Корзина, intents, checkout

Полная реализация endpoints для работы с корзиной.
"""

import logging
import uuid
from typing import Optional, List
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/cart", tags=["Cart"])


# === Pydantic Models ===

class AddIntentRequest(BaseModel):
    user_id: str
    supplier_item_id: str
    qty: float = Field(gt=0)
    locked: bool = False


class UpdateQtyRequest(BaseModel):
    qty: float = Field(gt=0)


class CheckoutRequest(BaseModel):
    user_id: str
    plan_id: str


class TopupRequest(BaseModel):
    user_id: str
    auto_select: bool = True


# === DB Access ===

_db = None

def set_db(db):
    """Устанавливает подключение к БД"""
    global _db
    _db = db

def get_db():
    """Получает подключение к БД"""
    if _db is None:
        raise RuntimeError("Database not initialized. Call set_db() first.")
    return _db


# === Helpers ===

def generate_id():
    return str(uuid.uuid4())


def get_item_by_id(db, item_id: str, active_only: bool = True):
    """Получить товар по ID"""
    query = {'id': item_id}
    if active_only:
        query['active'] = True
    return db.supplier_items.find_one(query, {'_id': 0})


def get_user_intents(db, user_id: str) -> List[dict]:
    """Получить все intents пользователя"""
    return list(db.cart_intents_v12.find(
        {'user_id': user_id},
        {'_id': 0}
    ))


def enrich_intent_with_item(db, intent: dict) -> dict:
    """Обогащает intent данными товара"""
    item = get_item_by_id(db, intent.get('supplier_item_id'), active_only=False)
    if item:
        intent['current_price'] = item.get('price')
        intent['active'] = item.get('active', False)
        intent['supplier_company_id'] = item.get('supplier_company_id')
    return intent


# === Endpoints ===

@router.get("/intents", summary="Получить intents пользователя")
async def get_intents(user_id: str = Query(...)):
    """Получить все позиции в черновике корзины"""
    db = get_db()
    
    intents = get_user_intents(db, user_id)
    
    # Обогащаем данными товаров
    for intent in intents:
        enrich_intent_with_item(db, intent)
    
    return {
        'intents': intents,
        'count': len(intents)
    }


@router.post("/intent", summary="Добавить товар в корзину")
async def add_intent(request: AddIntentRequest):
    """Добавить товар в черновик корзины (upsert)"""
    db = get_db()
    
    # Проверяем существование товара
    item = get_item_by_id(db, request.supplier_item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Товар не найден или неактивен")
    
    # Формируем intent
    intent_id = f"intent_{request.supplier_item_id}_{generate_id()[:8]}"
    
    intent = {
        'id': intent_id,
        'user_id': request.user_id,
        'supplier_item_id': request.supplier_item_id,
        'product_name': item.get('name_raw', ''),
        'price': item.get('price', 0),
        'qty': request.qty,
        'unit_type': item.get('unit_type', 'PIECE'),
        'product_core_id': item.get('product_core_id'),
        'super_class': item.get('super_class'),
        'pack_qty': item.get('pack_qty'),
        'supplier_company_id': item.get('supplier_company_id'),
        'locked': request.locked,
        'created_at': datetime.now(timezone.utc),
        'updated_at': datetime.now(timezone.utc)
    }
    
    # Upsert
    result = db.cart_intents_v12.update_one(
        {'user_id': request.user_id, 'supplier_item_id': request.supplier_item_id},
        {'$set': intent, '$setOnInsert': {'id': intent_id}},
        upsert=True
    )
    
    action = 'updated' if result.matched_count > 0 else 'created'
    logger.info(f"Intent {action} for user {request.user_id}: {item.get('name_raw', '')[:30]}")
    
    return {
        'status': 'ok',
        'action': action,
        'intent': intent
    }


@router.put("/intent/{item_id}", summary="Обновить количество")
async def update_intent(
    item_id: str,
    request: UpdateQtyRequest,
    user_id: str = Query(...)
):
    """Обновить количество товара в корзине"""
    db = get_db()
    
    result = db.cart_intents_v12.update_one(
        {'user_id': user_id, 'supplier_item_id': item_id},
        {'$set': {'qty': request.qty, 'updated_at': datetime.now(timezone.utc)}}
    )
    
    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Позиция не найдена в корзине")
    
    return {'status': 'ok', 'new_qty': request.qty}


@router.delete("/intent/{item_id}", summary="Удалить из корзины")
async def delete_intent(item_id: str, user_id: str = Query(...)):
    """Удалить товар из корзины"""
    db = get_db()
    
    result = db.cart_intents_v12.delete_one({
        'user_id': user_id,
        'supplier_item_id': item_id
    })
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Позиция не найдена")
    
    return {'status': 'ok', 'deleted_count': 1}


@router.delete("/intents", summary="Очистить корзину")
async def clear_intents(user_id: str = Query(...)):
    """Удалить все товары из корзины"""
    db = get_db()
    
    result = db.cart_intents_v12.delete_many({'user_id': user_id})
    
    logger.info(f"Cleared {result.deleted_count} intents for user {user_id}")
    
    return {
        'status': 'ok',
        'deleted_count': result.deleted_count
    }


# Note: /cart/plan и /cart/checkout остаются в routes.py
# так как они используют сложную логику optimizer.py
