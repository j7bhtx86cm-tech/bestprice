# Best Price Matching Engine - PRD

## Описание продукта
E-commerce платформа для B2B заказов с оптимизацией многопоставочных закупок.

## Выполненные задачи

### ✅ Phase 6 - Исправление неадекватных замен товаров (20 января 2026)

**Проблема: Икра за 5724₽ заменялась на товар за 213₽**

**Корневая причина:**
- Классификатор присваивал разные `product_core_id` для одного товара:
  - Неактивная версия: `seafood.caviar`  
  - Активная версия: `seafood.salmon`
- Правило "лосось" срабатывало раньше "икра" из-за порядка в CLASSIFICATION_RULES
- Оптимизатор выбирал **САМЫЙ ДЕШЁВЫЙ** товар без проверки адекватности цены

**Решения:**

1. **Исправлен auto_classifier.py:**
   - Правило `seafood.caviar` перемещено ПЕРЕД `seafood.salmon`
   - Добавлены negative lookahead: `(?!.*икр)` для лосось/горбуша
   - Добавлено исключение: `(?!.*кабачк)` для икры

2. **Добавлен фильтр цены в optimizer.py:**
   - Новый флаг `PRICE_TOLERANCE_EXCEEDED`
   - Замены фильтруются по диапазону ±50%/+100% от исходной цены
   - Если нет адекватных — берутся 3 ближайших по цене

3. **Переклассифицированы 43 товара:**
   - Все икорные товары теперь имеют `seafood.caviar`
   - "Икра из кабачков" → `vegetables.zucchini`

**Результат:**
- Икра за 5724₽ теперь находит замену за 5724₽ (та же икра от другого поставщика)
- Нет больше замен на совершенно другие товары

### ✅ Phase 5 - Исправление product_core_id (20 января 2026)

**Проблема: "Яйцо перепелиное" не переносилось в заказ (код OTHER)**

**Корневая причина:**
- 77% товаров (5998 из 7790) не имели `product_core_id`
- Без `product_core_id` оптимизатор не может найти альтернативы
- Яйцо перепелиное Солигорская имело `product_core_id: null`

**Решение:**
1. Создан скрипт `/app/backend/fix_product_core_id.py`:
   - Назначает `product_core_id = super_class` для товаров без core_id
   - Исправлено 5998 товаров за одну операцию

2. Исправлен `/app/backend/auto_classifier.py`:
   - Правило `eggs.quail` перемещено ПЕРЕД `eggs.chicken` (специфичные правила первыми)

**Результат:**
- 0% товаров без `product_core_id` (было 77%)
- Яйцо перепелиное теперь имеет `product_core_id: eggs.quail`
- 3 альтернативы доступны для яйца перепелиного
- Оптимизатор успешно находит товары

### ✅ Phase 4 - Избранное и модалка офферов (20 января 2026)

**Очистка избранного (ВЫПОЛНЕНО)**
- Добавлен `POST /api/v12/favorites/clear` endpoint
- Возвращает `deleted_count` и `remaining_count`
- Кнопка "Очистить всё" на странице избранного с `data-testid="clear-favorites-btn"`
- Принудительная перезагрузка избранного после очистки

**Модалка "Сравнить предложения" (ВЫПОЛНЕНО)**
- Guard-логика: модалка не рендерится пока `sourceItem` не установлен (`if (!sourceItem) return null`)
- Корректная обработка пустого списка альтернатив
- Действие "Выбрать и в корзину" добавляет выбранный оффер с указанным количеством
- Работает из каталога и избранного
- data-testid: `compare-offers-btn`, `confirm-offer-btn`, `offer-qty-input`

**API альтернатив (ВЫПОЛНЕНО)**
- `GET /api/v12/item/{item_id}/alternatives` возвращает source и alternatives list
- Поиск по `product_core_id` + fallback по похожему названию
- Возвращает supplier_name, price, pack_qty для каждой альтернативы

### ✅ Phase 3 Hotfix - Checkout стабильность (20 января 2026)

**P0.1 - Plan Snapshot (ВЫПОЛНЕНО)**
- `/api/v12/cart/plan` сохраняет snapshot в `cart_plans_v12` с plan_id, cart_hash, plan_payload
- `/api/v12/cart/checkout` принимает plan_id и использует сохранённый план
- При изменении корзины возвращается `PLAN_CHANGED` (409) 
- TTL плана: 60 минут

**P0.2 - Reason Codes для недоступных товаров (ВЫПОЛНЕНО)**
- Добавлен `UnavailableReason` enum в optimizer.py
- Коды: `OFFER_INACTIVE`, `PRICE_INVALID`, `MIN_QTY_NOT_MET`, `PACK_TOLERANCE_FAILED`, `STRICT_ATTR_MISMATCH`, `CLASSIFICATION_MISSING`, `NO_SUPPLIER_OFFERS`, `OTHER`
- Каждая unfulfilled позиция имеет `unavailable_reason_code` и `reason` text

**P0.3 - Заказы в истории (ВЫПОЛНЕНО)**
- Checkout создаёт заказы в `orders_v12` коллекции
- `/api/v12/orders` возвращает историю заказов (читает из orders_v12 + orders)
- Корзина очищается ТОЛЬКО после успешного создания заказа

**P1.1 - Скрыть поставщиков в Draft корзине (ВЫПОЛНЕНО)**
- В корзине до "Оформить заказ" товары показываются единым списком без группировки

**P1.2 - Ручной ввод количества в корзине (ВЫПОЛНЕНО)**
- Добавлен `EditableQty` компонент с numeric input

**P1.3 - Управление количеством в каталоге (ВЫПОЛНЕНО)**
- Добавлен блок `- [число] +` на карточку товара
- Default qty = 1
- "В корзину" добавляет выбранное количество

**P1.4 - Удалены кнопки (ВЫПОЛНЕНО)**
- Убрана кнопка "Все в корзину" из избранного
- Убрана кнопка "Обновить" из каталога

### ✅ Предыдущие задачи

- **GOLD Migration** - Миграция на новые прайс-листы (8 поставщиков)
- **Two-Phase Cart** - Draft корзина (намерения) + Checkout Plan (оптимизация)
- **Advanced Search** - Поиск с русской морфологией
- **Data Quality Gate** - Фильтрация невалидных офферов
- **Optimizer V3** - Минималки поставщиков, +10% topup, redistribution

## Архитектура

```
/app/
├── backend/
│   ├── server.py                    # FastAPI entry point
│   ├── bestprice_v12/
│   │   ├── routes.py               # API endpoints
│   │   ├── optimizer.py            # Cart optimization logic
│   │   ├── plan_snapshot.py        # NEW: Plan snapshot management
│   │   ├── catalog.py              # Catalog generation
│   │   ├── cart.py                 # Cart operations
│   │   └── favorites.py            # Favorites management
└── frontend/
    └── src/pages/customer/
        ├── CustomerCart.js          # Two-phase cart UI
        ├── CustomerCatalog.js       # Catalog with qty selector
        ├── CustomerFavorites.js     # Favorites (no "Все в корзину")
        └── CustomerOrders.js        # Order history
```

## Ключевые API Endpoints

| Endpoint | Method | Описание |
|----------|--------|----------|
| `/api/v12/cart/intent` | POST | Добавить/обновить intent в корзину |
| `/api/v12/cart/intents` | GET | Получить все intents (Draft) |
| `/api/v12/cart/plan` | GET | Генерация оптимизированного плана (возвращает plan_id) |
| `/api/v12/cart/checkout` | POST | Создание заказов (принимает plan_id) |
| `/api/v12/orders` | GET | История заказов |
| `/api/v12/catalog` | GET | Каталог товаров |
| `/api/v12/favorites` | GET/POST/DELETE | Избранное |

## Ключевые коллекции MongoDB

| Коллекция | Описание |
|-----------|----------|
| `cart_intents` | Намерения пользователя (Draft корзина) |
| `cart_plans_v12` | NEW: Snapshots оптимизированных планов |
| `orders_v12` | Заказы (новая коллекция) |
| `orders` | Заказы (старая, для совместимости) |
| `supplier_items` | Товары поставщиков |
| `companies` | Компании (поставщики с min_order_amount) |

## Тестирование

**Backend Tests**: `/app/tests/test_phase3_checkout_orders.py`
- 15 тестов, 100% pass rate
- Покрытие: P0.1, P0.2, P0.3, P1.3, Cart API

**Test Credentials**:
- Email: `customer@bestprice.ru`
- Password: `password123`
- User ID: `0b3f0b09-d8ba-4ff9-9d2a-519e1c34067e`

## Upcoming Tasks (P1-P2)

- **P1**: UI для выбора оффера при нескольких вариантах товара
- **P2**: Интеграция `auto_reclassifier.py` в импорт прайс-листов

## Backlog (P3)

- Отчёты для поставщиков по качеству прайс-листов
- Telegram Bot интеграция
- Рефакторинг routes.py (разбить на cart_routes, order_routes, catalog_routes)
- UI для Match Debugging
