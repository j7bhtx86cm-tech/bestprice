"""
BestPrice v12 - Plan Snapshot Management

Управление снапшотами оптимизированных планов для checkout.

КЛЮЧЕВЫЕ ПРАВИЛА:
1. План генерируется при нажатии "Оформить заказ"
2. План сохраняется в БД с уникальным plan_id
3. Checkout использует сохранённый план, а НЕ пересчитывает
4. Если корзина изменилась - возвращаем PLAN_CHANGED
"""

import hashlib
import json
import uuid
import logging
from typing import Dict, Any, Optional, Tuple, List
from datetime import datetime, timezone, timedelta
from pymongo.database import Database

logger = logging.getLogger(__name__)

# TTL для плана (в минутах)
PLAN_TTL_MINUTES = 60


def compute_cart_hash(db: Database, user_id: str) -> str:
    """
    Вычисляет хэш корзины для проверки изменений.
    
    Хэш включает:
    - supplier_item_id каждого intent
    - qty каждого intent
    - locked флаг
    
    Сортируем для детерминированности.
    """
    intents = list(db.cart_intents.find(
        {'user_id': user_id},
        {'_id': 0, 'supplier_item_id': 1, 'qty': 1, 'locked': 1}
    ).sort('supplier_item_id', 1))
    
    # Формируем строку для хэширования
    hash_parts = []
    for intent in intents:
        part = f"{intent.get('supplier_item_id', '')}:{intent.get('qty', 0)}:{intent.get('locked', False)}"
        hash_parts.append(part)
    
    hash_string = "|".join(hash_parts)
    return hashlib.sha256(hash_string.encode()).hexdigest()[:32]


def get_min_order_map(db: Database) -> Dict[str, float]:
    """
    Получает текущие минималки поставщиков.
    Используется для сохранения в snapshot.
    """
    min_map = {}
    for comp in db.companies.find({'type': 'supplier'}, {'_id': 0, 'id': 1, 'min_order_amount': 1}):
        min_map[comp['id']] = comp.get('min_order_amount', 10000.0)
    return min_map


def save_plan_snapshot(
    db: Database,
    user_id: str,
    plan_payload: Dict[str, Any],
    cart_hash: str,
    min_order_map: Dict[str, float]
) -> str:
    """
    Сохраняет snapshot плана в БД.
    
    Returns: plan_id (UUID)
    """
    plan_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(minutes=PLAN_TTL_MINUTES)
    
    snapshot = {
        'plan_id': plan_id,
        'user_id': user_id,
        'created_at': now.isoformat(),
        'expires_at': expires_at.isoformat(),
        'cart_hash': cart_hash,
        'min_order_map': min_order_map,
        'plan_payload': plan_payload,
    }
    
    # Удаляем старые планы пользователя
    db.cart_plans_v12.delete_many({'user_id': user_id})
    
    # Сохраняем новый
    db.cart_plans_v12.insert_one(snapshot)
    
    logger.info(f"Saved plan snapshot {plan_id} for user {user_id}, hash={cart_hash[:8]}...")
    
    return plan_id


def load_plan_snapshot(
    db: Database,
    plan_id: str,
    user_id: str
) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
    """
    Загружает snapshot плана из БД.
    
    Returns: (plan_data, error_message)
    - plan_data: dict с plan_payload, cart_hash, min_order_map если найден
    - error_message: строка с ошибкой если план не найден/истёк
    """
    snapshot = db.cart_plans_v12.find_one(
        {'plan_id': plan_id, 'user_id': user_id},
        {'_id': 0}
    )
    
    if not snapshot:
        return None, "План не найден. Пожалуйста, сформируйте план заново."
    
    # Проверяем TTL
    expires_at = snapshot.get('expires_at')
    if expires_at:
        expires_dt = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
        if datetime.now(timezone.utc) > expires_dt:
            # Удаляем просроченный план
            db.cart_plans_v12.delete_one({'plan_id': plan_id})
            return None, "План устарел (прошло более 60 минут). Пожалуйста, сформируйте план заново."
    
    return {
        'plan_payload': snapshot.get('plan_payload'),
        'cart_hash': snapshot.get('cart_hash'),
        'min_order_map': snapshot.get('min_order_map'),
        'created_at': snapshot.get('created_at'),
    }, None


def validate_cart_unchanged(
    db: Database,
    user_id: str,
    saved_cart_hash: str
) -> Tuple[bool, str]:
    """
    Проверяет что корзина не изменилась с момента генерации плана.
    
    Returns: (is_valid, current_hash)
    """
    current_hash = compute_cart_hash(db, user_id)
    is_valid = (current_hash == saved_cart_hash)
    
    if not is_valid:
        logger.warning(
            f"Cart hash mismatch for user {user_id}: "
            f"saved={saved_cart_hash[:8]}... current={current_hash[:8]}..."
        )
    
    return is_valid, current_hash


def delete_plan_snapshot(db: Database, plan_id: str, user_id: str) -> bool:
    """Удаляет snapshot после успешного checkout."""
    result = db.cart_plans_v12.delete_one({'plan_id': plan_id, 'user_id': user_id})
    return result.deleted_count > 0


def cleanup_expired_plans(db: Database) -> int:
    """Очищает просроченные планы. Можно вызывать периодически."""
    now = datetime.now(timezone.utc).isoformat()
    result = db.cart_plans_v12.delete_many({'expires_at': {'$lt': now}})
    if result.deleted_count > 0:
        logger.info(f"Cleaned up {result.deleted_count} expired plan snapshots")
    return result.deleted_count
