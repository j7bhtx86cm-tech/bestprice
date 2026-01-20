"""
Best Price v12 Routes - Modular structure

Этот файл является точкой входа для всех роутов.
Логика разделена по модулям:
- catalog_routes.py: Каталог товаров, поиск
- cart_routes.py: Корзина, intents, checkout
- favorites_routes.py: Избранное
- orders_routes.py: Заказы
- admin_routes.py: Административные функции
- suppliers_routes.py: Поставщики
"""

from fastapi import APIRouter

# Основной роутер для /api/v12
router = APIRouter(prefix="/v12", tags=["BestPrice v12"])

# Импортируем модули (в будущем)
# from .catalog_routes import router as catalog_router
# from .cart_routes import router as cart_router
# from .favorites_routes import router as favorites_router
# from .orders_routes import router as orders_router
# from .admin_routes import router as admin_router
# from .suppliers_routes import router as suppliers_router

# router.include_router(catalog_router)
# router.include_router(cart_router)
# ... и т.д.

# Пока используем монолитный routes.py
# TODO: Постепенная миграция по модулям
