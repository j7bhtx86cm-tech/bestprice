"""
BestPrice v12 Routes Modules

Модульная структура роутов:
- cart_routes: Корзина и intents
- orders_routes: История заказов
- favorites_routes: Избранное

Использование:
    from bestprice_v12.routes_modules import cart_router, orders_router, favorites_router
    
    # Инициализация БД
    cart_routes.set_db(db)
    orders_routes.set_db(db)
    favorites_routes.set_db(db)
    
    # Подключение к main router
    main_router.include_router(cart_router)
    main_router.include_router(orders_router)
    main_router.include_router(favorites_router)
"""

from .cart_routes import router as cart_router, set_db as set_cart_db
from .orders_routes import router as orders_router, set_db as set_orders_db
from .favorites_routes import router as favorites_router, set_db as set_favorites_db


def init_all_routers(db):
    """Инициализирует все модульные роутеры с подключением к БД"""
    set_cart_db(db)
    set_orders_db(db)
    set_favorites_db(db)


__all__ = [
    'cart_router',
    'orders_router', 
    'favorites_router',
    'init_all_routers',
    'set_cart_db',
    'set_orders_db',
    'set_favorites_db'
]
