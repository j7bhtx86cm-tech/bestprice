"""
Orders Routes Module - История заказов

Endpoints для просмотра истории заказов.
"""

import logging
from typing import Optional, List
from datetime import datetime

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/orders", tags=["Orders"])


# === DB Access ===

_db = None

def set_db(db):
    global _db
    _db = db

def get_db():
    if _db is None:
        raise RuntimeError("Database not initialized")
    return _db


# === Endpoints ===

@router.get("", summary="Получить историю заказов")
async def get_orders(
    user_id: str = Query(..., description="ID пользователя"),
    limit: int = Query(50, ge=1, le=100),
    skip: int = Query(0, ge=0),
    status: Optional[str] = Query(None, description="Фильтр по статусу")
):
    """
    Получить список заказов пользователя.
    
    Статусы: pending, confirmed, shipped, delivered, cancelled
    """
    db = get_db()
    
    query = {'user_id': user_id}
    if status:
        query['status'] = status
    
    # Получаем заказы
    orders = list(db.orders_v12.find(
        query,
        {'_id': 0}
    ).sort('created_at', -1).skip(skip).limit(limit))
    
    total = db.orders_v12.count_documents(query)
    
    # Добавляем имена поставщиков
    supplier_ids = list(set(o.get('supplier_id') for o in orders if o.get('supplier_id')))
    if supplier_ids:
        companies = {
            c['id']: c.get('companyName', c.get('name', 'Unknown'))
            for c in db.companies.find({'id': {'$in': supplier_ids}}, {'_id': 0})
        }
        for order in orders:
            sid = order.get('supplier_id')
            if sid:
                order['supplier_name'] = companies.get(sid, 'Unknown')
    
    return {
        'orders': orders,
        'total': total,
        'skip': skip,
        'limit': limit,
        'has_more': skip + len(orders) < total
    }


@router.get("/{order_id}", summary="Получить детали заказа")
async def get_order_detail(
    order_id: str,
    user_id: str = Query(..., description="ID пользователя")
):
    """Получить детальную информацию о заказе"""
    db = get_db()
    
    order = db.orders_v12.find_one(
        {'order_id': order_id, 'user_id': user_id},
        {'_id': 0}
    )
    
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден")
    
    # Добавляем имя поставщика
    supplier_id = order.get('supplier_id')
    if supplier_id:
        company = db.companies.find_one({'id': supplier_id}, {'_id': 0})
        if company:
            order['supplier_name'] = company.get('companyName', company.get('name', 'Unknown'))
            order['supplier_contact'] = company.get('email')
    
    return order
