# Best Price Matching Engine - PRD

## Описание продукта
E-commerce платформа для B2B заказов с оптимизацией многопоставочных закупок.

## Выполненные задачи

### ✅ Phase 14 - Lexicon-based Matching Rules v1.3 (21 января 2026)

**Задача (P0)**: Исправить "Сравнить предложения" — выдавались нелогичные альтернативы (сосиски → курица филе, рыба ↔ птица).

**Реализовано:**

1. **Подключен словарь `lexicon_ru_v1_3.json`**
   - Загружается и кэшируется при старте backend
   - Содержит: product_kind, ingredient_synonyms, processing, state, cut_attrs, negative_blocks

2. **Создан модуль `/app/backend/bestprice_v12/matching_rules.py`**:
   - `extract_signature()` — извлечение match_signature из названия
   - `check_hard_blocks()` — HB1-HB5 (top_class, product_kind, main_ingredient, processing, state)
   - `check_negative_blocks()` — взаимоисключения (bidirectional!)
   - `determine_tier()` — определение Tier A/B/C
   - `find_alternatives()` — основная функция для API и оптимизатора

3. **Hard Blocks (HB):**
   - HB1: top_class должен совпадать (meat ≠ seafood ≠ dairy)
   - HB2: product_kind должен совпадать (sausages ≠ fillet)
   - HB3: main_ingredient должен совпадать (chicken ≠ fish)
   - HB4: processing — HARD IF PRESENT
   - HB5: state — HARD IF PRESENT

4. **Negative Blocks (bidirectional!):**
   - Сосиски/колбаса ≠ филе/грудка/тушка/фарш
   - Рыба ≠ птица/мясо
   - Копчёный ≠ обычный

5. **Tier System:**
   - Tier A: Идентичные (все HB + cut_attrs совпадают)
   - Tier B: Близкие (HB1-3 + без negative blocks)
   - Tier C: Аналоги (только при include_analogs=true)

6. **Scoring:** match_score DESC → price ASC

**Acceptance Criteria — ВСЕ ПРОЙДЕНЫ:**
- ✅ Сосиски/колбаса не показывают филе/грудку/тушку/фарш
- ✅ Рыба не показывает птицу/мясо и наоборот
- ✅ Копчёный не смешивается с обычным в Tier A/B
- ✅ Жирность строгая (±2%)
- ✅ Tier C только при include_analogs=true

**Файлы:**
- `/app/backend/bestprice_v12/lexicon_ru_v1_3.json` — словарь
- `/app/backend/bestprice_v12/matching_rules.py` — модуль matching
- `/app/backend/bestprice_v12/routes.py` — обновлён endpoint `/alternatives`

### ✅ Phase 13 - Топовый анализ и переработка "Сравнить предложение" (21 января 2026)

**Проблема**: После обновлений "Сравнить предложение" показывало нерелевантные товары:
- Для "Лосось филе с/м" показывались горбуша, консервы, суповые наборы
- Система не различала виды рыбы (лосось ≠ горбуша ≠ кета)
- Не учитывалась форма товара (филе ≠ тушка ≠ стейк)

**Глубокий анализ данных:**
1. **product_core_id слишком общий** — `seafood.salmon` включает лосось, горбушу, кету
2. **name_norm редко совпадает** — только 10 дубликатов из 7790 товаров
3. **Нужна семантическая классификация** по компонентам названия

**Решение — система извлечения компонентов и ранжирования:**

1. **Словари компонентов:**
   - `SPECIES_PATTERNS` — виды продукта (лосось, горбуша, курица, говядина...)
   - `FORM_PATTERNS` — форма (филе, тушка, стейк, грудка, фарш...)
   - `PROCESSING_PATTERNS` — обработка (с/м, охл, копчен, солен...)

2. **Функция `extract_product_components(name_norm)`**:
   - Извлекает вид, форму, обработку из названия
   - Пример: "Лосось филе с/м" → `{species: 'лосось', form: 'филе', processing: 'frozen'}`

3. **Функция `calculate_relevance_score()`**:
   - Scoring по совпадению компонентов:
     - Вид (species): +100 баллов
     - Форма (form): +50 баллов
     - Обработка (processing): +25 баллов
     - Общие слова: +3 балла за слово

4. **Новый алгоритм `/alternatives`**:
   1. Ищем точные совпадения `name_norm` (score=1000)
   2. Ищем по `product_core_id` от ДРУГИХ поставщиков
   3. Вычисляем score для каждого кандидата
   4. Сортируем по score (убывание), затем по цене (возрастание)
   5. Топ-10 наиболее релевантных

**Результат:**
- "Лосось филе с/м" → 10 альтернатив: ТОЛЬКО лосось/сёмга + филе + замороженные
- "Куриное филе" → 10 альтернатив: ТОЛЬКО курица + филе
- Нет горбуши, консервов, тушек или других нерелевантных товаров
- Ранжирование от наиболее похожих к наименее

**Файлы изменены:**
- `/app/backend/bestprice_v12/routes.py`:
  - `SPECIES_PATTERNS`, `FORM_PATTERNS`, `PROCESSING_PATTERNS`
  - `extract_product_components()`
  - `calculate_relevance_score()`
  - Полностью переписан endpoint `/item/{item_id}/alternatives`

### ✅ Phase 12 - Система квалификации типов обработки (21 января 2026)

**Проблема**: Модалка "Выберите предложение" для копчёного лосося показывала замороженный лосось и горбушу вместо идентичных копчёных товаров.

**Решение — система квалификации по типу обработки**:
1. **Создан модуль `PROCESSING_QUALIFIERS_ORDER`** с типами:
   - `smoked` — копчёный (холодн. копч., х/к, г/к)
   - `salted` — солёный (малосол, пресерв)
   - `frozen` — замороженный (с/м)
   - `chilled` — охлаждённый (охл)
   - `canned` — консервированный (ж/б)
   - `dried` — сушёный/вяленый
   - `marinated` — маринованный
   - `fresh` — свежий

2. **Функции `detect_processing_type()` и `build_processing_filter()`**:
   - Определяют тип обработки по названию
   - Строят MongoDB фильтр для поиска товаров с тем же типом
   
3. **Исправлены ложные срабатывания**:
   - "Горбуша ПБГ" теперь определяется как `frozen`, а не `smoked` (г/к внутри "кг/кор")
   - "Лосось с/г" — `frozen` (с/г = с головой, не г/к)

4. **Исправлена работа `\b` с кириллицей в MongoDB**:
   - MongoDB regex не поддерживает `\b` для кириллицы
   - Убраны word boundaries, синонимы ≥4 символов обеспечивают достаточную точность

**Результат**:
- Копчёный лосось → показывает только 3 копчёных товара (семга х/к, лосось х/к)
- Замороженный лосось → показывает только замороженные товары
- "куриное филе" → 42 товара (нет кукурузы!)
- "лосось копченый" → 3 товара (только копчёные)

**Файлы изменены**:
- `/app/backend/bestprice_v12/routes.py` — добавлены `PROCESSING_QUALIFIERS_ORDER`, `detect_processing_type()`, `build_processing_filter()`
- `/app/backend/search_synonyms.py` — добавлены синонимы для стеммов ("копчени", "солени"), убраны `\b`
- `/app/backend/bestprice_v12/search_service.py` — убраны `\b` из regex

### ✅ Phase 11 - Глубокое исправление поисковой системы (20 января 2026)

**Проблема**: По запросу "куриное филе" показывались нерелевантные товары (кукуруза, мука кукурузная и др.)

**Причина**: Слишком "fuzzy" поиск:
1. `short_tokens` обрезал слова до 4 символов и находил частичные совпадения
2. `synonym_regex` искал подстроки внутри слов (например "кур" внутри "шкуре")

**Решение**:
1. **Удалён `short_tokens` fallback** — слишком много ложных срабатываний
2. **Увеличен минимум символов для синонимов** — с 3 до 4 символов
3. **Приоритет поиска**:
   - `lemma_tokens $all` — основной, самый точный (морфологический)
   - `synonym_regex` — для синонимов
   - `exact tokens` — точные слова

**Файлы изменены**:
- `/app/backend/search_synonyms.py` — build_synonym_regex без short tokens
- `/app/backend/bestprice_v12/routes.py` — удалён short_tokens
- `/app/backend/bestprice_v12/search_service.py` — аналогичные изменения

### ✅ Phase 10 - Исправления по UI запросам (20 января 2026)

**1. Убран автокомплит из каталога**
- Восстановлен простой Input для поиска — показываются только карточки товаров
- Файл: `CustomerCatalog.js`

**2. Исправлена модалка "Выберите предложение"**
- Алгоритм теперь ищет по точному `name_norm` или `product_core_id` + похожее название
- Файл: `routes.py` → endpoint `/item/{item_id}/alternatives`

**1. Рефакторинг routes.py**
- Создана модульная структура в `routes_modules/`:
  - `cart_routes.py` - документация и модели для корзины
  - `orders_routes.py` - документация для заказов
  - `favorites_routes.py` - документация для избранного
- `search_service.py` вынесен как отдельный сервис поиска

**2. Frontend Autocomplete**
- Создан компонент `SearchAutocomplete.js`:
  - Debounce 250ms
  - Keyboard navigation (↑↓ Enter Escape)
  - Click outside to close
  - Показывает категорию и цену
- ~~Интегрирован в `CustomerCatalog.js`~~ (Удалён в Phase 10)
- Остался на странице "Избранное"

**3. Оптимизация индексов MongoDB**
- Создано **7 новых индексов** для supplier_items:
  - `idx_active_price_name` - для сортировки каталога
  - `idx_product_core_active` - для поиска альтернатив
  - `idx_active_super_price` - для фильтра по категории
  - `idx_id_active` - для быстрого поиска по ID
  - `idx_supplier_active_price` - для оптимизатора
- Всего **20 индексов** в supplier_items

### ✅ Phase 8 - Интеграция lemma_tokens и рефакторинг (20 января 2026)

**1. Интеграция lemma_tokens в поиск**
- Создан модуль `search_service.py` с функциями:
  - `tokenize_query()` - токенизация и лемматизация
  - `build_search_query()` - построение MongoDB query с lemma + fallback
  - `search_with_lemma_only()` - быстрый поиск по индексу
- Новый endpoint `GET /api/v12/search/quick` для autocomplete
- Поддержка морфологии: "куриная грудка" находит "филе грудки куриное"

**2. Расширены правила классификации**
- Добавлено 15+ новых правил в `fix_critical_classifications.py`:
  - Сахар порционный → staples.sugar
  - Чай с добавками → beverages.tea
  - Говядина/свинина → meat (не seafood)
- Исправлено дополнительно 23 товара

**3. Начат рефакторинг routes.py**
- Создан `routes_modules/` для будущей модульной структуры
- `search_service.py` вынесен как отдельный сервис

**Тестирование:**
- Поиск "молоко" → 5 результатов
- Поиск "куриная грудка" → 5 результатов  
- Поиск "икра лососевая" → 4 результата (все seafood.caviar)

### ✅ Phase 7 - Глубокий анализ и улучшения (20 января 2026)

**1. Анализ и исправление классификации**
- Исправлено 92 товара с критически неправильной классификацией
- Масло оливковое: `vegetables.olives` → `oils.olive` (73 товара)
- Куриная грудка: `seafood` → `meat.chicken` (10 товаров)
- Контейнеры для салата: `vegetables` → `packaging.container` (9 товаров)

**2. UI-индикатор изменения цены (порог 25%)**
- Добавлен компонент `PriceChangeIndicator` в `CustomerCart.js`
- Показывает TrendingUp/TrendingDown иконки при изменении цены >25%
- API возвращает `original_price` для каждого товара в плане

**3. Индекс `lemma_tokens` для поиска**
- Создан на 13921 документов
- Простой русский стеммер отрезает окончания
- Поиск по морфологии работает (тест: "икра лососевая", "молоко", "куриная грудка")

**4. Тестирование**
- 15/15 backend тестов прошло
- UI verified: цена икры 5724₽ (не 213₽), флаги SUPPLIER_CHANGED + AUTO_TOPUP_10PCT

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
