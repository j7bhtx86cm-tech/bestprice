# Best Price Matching Engine - Product Requirements Document

## Дата последнего обновления: 2026-01-10

## Оригинальная проблема
Система "Best Price" для поиска лучших цен на товары из избранного работала некорректно:
- Неверные матчи: "васаби" → "соль", "пшеничная мука" → "ржаная мука"
- **FIXED (2026-01-10)**: "Кальмар" → "Курица" (КРИТИЧЕСКАЯ ошибка seafood vs meat)
- **FIXED (2026-01-10)**: "Креветки с хвостом" → "Креветки без хвоста" (игнорирование атрибутов)
- **FIXED (2026-01-10)**: Низкий match_percent (62%) принимался без предупреждения
- **FIXED (2026-01-10)**: "Лангустины аргентинские" не находили совпадений (ложное срабатывание на "гус")
- Ошибки расчета: запрос "1 кг" удовлетворялся товаром "5 г"
- Бессмысленные `match_percent` scores
- **FIXED**: Дубли при повторной загрузке прайс-листов
- **FIXED**: BestPrice не учитывал min_order_qty

## Текущий статус: ✅ P0 CRITICAL MATCHING + VALIDATION COMPLETE (2026-01-10)

### Build SHA: (latest)

---

## P0 CRITICAL MATCHING FIXES (2026-01-10) ✅ COMPLETED + VALIDATED

### Исправленные критические ошибки

#### 1. SEAFOOD vs MEAT Cross-Match Prevention ✅
- **Проблема**: Кальмар филе матчился с курицей
- **Решение**: Новая функция `check_category_mismatch()` в `p0_hotfix_stabilization.py`
- **SEAFOOD_KEYWORDS**: 51+ ключевых слов (кальмар, креветка, лосось, ...)
- **MEAT_KEYWORDS**: 36 ключевых слов (исправлено: "гус" → "гусь", "гуся", "гусин")
- **Приоритет super_class**: Если super_class известен, он имеет приоритет над keyword detection
- **Тестирование**: 31/31 тестов прошли

#### 2. Attribute Compatibility Guard ✅
- **Проблема**: Креветки с хвостом матчились с креветками без хвоста
- **Решение**: Новая функция `check_attribute_compatibility()` в `p0_hotfix_stabilization.py`
- Проверяемые атрибуты:
  - Креветки: с хвостом / без хвоста, очищенные / неочищенные
  - Кальмары: без кожи / с кожей, чищеные / нечищеные

#### 3. Super Class Mapper Fix ✅
- **Проблема**: "Кальмар филе" классифицировался как `meat` (из-за слова "филе")
- **Решение**: Добавлены правила в `direct_map_priority` в `universal_super_class_mapper.py`:
  - `'кальмар филе': 'seafood.squid'`
  - `'лосось филе': 'seafood.salmon'`
  - И другие seafood+филе комбинации

#### 4. Default brand_critical=True ✅
- **Проблема**: По умолчанию brand_critical=False
- **Решение**: Изменено на `brand_critical=True` в `server.py` строка 2371
- При добавлении в избранное товар по умолчанию строго привязан к бренду

#### 5. Пороги сходства (95%/90%) ✅ NEW
- **Проблема**: Система принимала любой match_percent без проверки порога
- **Решение**: 
  - `THRESHOLD_BRAND_CRITICAL = 95%` - для товаров с критичным брендом
  - `THRESHOLD_BRAND_NOT_CRITICAL = 90%` - для остальных товаров
- Если match_percent ниже порога → срабатывает "Stick with Favorite"

#### 6. Stick with Favorite Logic ✅ NEW
- **Проблема**: При низком совпадении система возвращала неподходящий товар
- **Решение**: Если match_percent < threshold, система ищет и возвращает оригинальный товар из избранного
- **3 стратегии поиска оригинала**:
  1. По supplier_id + product_id (самый надёжный)
  2. По exact name_raw match (fallback)
  3. По name_norm prefix match (последняя надежда)
- Оригинальный товар возвращается с `match_percent=100%` и `stick_with_favorite=True`

#### 7. Улучшенная формула match_percent ✅ NEW
- **Старая формула**: base_score=60 + core(20) + guards(10) + brand(10) = max 100, обычно 90
- **Новая формула** (rapidfuzz):
  - Name similarity (token_set_ratio): 50% веса (0-50 баллов)
  - Product core match: 25 баллов
  - Guards passed: 15 баллов
  - Brand match: 10 баллов (если brand_critical)
- Теперь match_percent отражает реальное качество совпадения

### Результаты тестирования (2026-01-10)
- **Unit tests**: 28/28 passed
- **API verification**: 
  - Кальмар филе → Кальмар филе (оригинал, 100%) ✅
  - Низкий match (62%) → Stick with favorite → 100% ✅
  - Seafood не матчится с meat ✅

---

## FULL BATCH AUDIT REPORT (2026-01-09)

### Общая статистика
- **Total active items**: 7907
- **Inactive items**: 16
- **Suppliers**: 9 (Алиди, Интегрита, Ромакс, Восток-Запад, Айфрут, Нордико, РБД, Сладкая жизнь, ПраймФудс)

### Качество данных (FINAL - All Targets Met)
| Метрика | Значение | Target | Статус |
|---------|----------|--------|--------|
| Product core coverage | **95.8%** (7578) | 80%+ | ✅ |
| Brand high confidence | **34.8%** (2751) | 20%+ | ✅ |
| Brand coverage (total) | 77.4% (6119) | - | ✅ |
| Geography coverage | **42.5%** (3361) | 40%+ | ✅ |

### Unit type distribution
- PIECE: 72.3% (5716)
- WEIGHT: 25.6% (2025)
- VOLUME: 2.1% (166)

---

### P1 Tasks (2026-01-09) ✅ COMPLETED

#### P1.1 - BestPrice UI min_order_qty ✅
- API возвращает `min_order_qty`, `actual_qty` в response
- Формула P0.5 работает корректно в UI
- Тест: qty=3, min_order=2 → actual_qty=4, total_cost=price*4 ✅

#### P1.2 - Brand Coverage Improvement ✅
- **Original**: 8.3% high confidence
- **Target**: 20%+ high confidence
- **Achieved**: **34.8%** high confidence (2751 items)
- Добавлено 73+ брендов в strict список
- Total brand coverage: 77.4%

#### P1.3 - Geography Coverage Improvement ✅
- **Original**: 22.4%
- **Target**: 40%+
- **Achieved**: **42.5%** (3361 items)
- Улучшены паттерны извлечения (тайский→ТАИЛАНД, итальянский→ИТАЛИЯ)
- Добавлена география по брендам (Aroy-D→ТАИЛАНД, MUTTI→ИТАЛИЯ)

#### P1.4 - Product Core Coverage Improvement ✅
- **Original**: 67.9%
- **Target**: 80%+
- **Achieved**: **95.8%** (7578 items)
- Добавлены правила для: 
  - ТЕСТО (bakery.dough, dough.puff, dough.yeast)
  - Молочные продукты (dairy.cheese.*, dairy.cream, dairy.milk)
  - Овощи и фрукты
  - Выпечка (bakery.*, pizza)
  - Напитки (beverages.tea, coffee, cocoa)
  - Снеки
  - Упаковка (packaging.*)
  - Морепродукты (seafood.shellfish.*)
  - Круп (staples.cereals.*)
  - Бульоны (ready_meals.broth)

---

### P0 Import & BestPrice Requirements (2026-01-09) ✅ COMPLETED

**Все P0 задачи реализованы и протестированы (17/17 тестов):**

#### P0.1 - Upsert on Import ✅
- Заменён `insert_one` на `upsert` с уникальным ключом
- Ключ: `supplier_id:article` (если есть артикул) или `supplier_id:normalize(productName):unitType`
- Индекс `unique_key_1` создан в MongoDB
- Результат: 7923 записи с unique_key, дубликаты невозможны

#### P0.2 - One Active Pricelist per Supplier ✅
- При импорте нового прайса автоматически деактивируются старые позиции
- Поле `active: false` + `deactivated_at` для старых записей
- Результат: 7907 активных, 16 неактивных позиций

#### P0.3 - Import min_order_qty ✅
- Колонки "Минимальный заказ" и "Количество в упаковке" импортируются
- Поля `min_order_qty` и `pack_qty` добавлены в схему
- Результат: 153 товара с min_order_qty > 1

#### P0.4 - Unit Priority ✅
- `unitType` из файла имеет приоритет над парсингом из названия
- Поле `unit_type` (WEIGHT/VOLUME/PIECE) добавлено в схему
- Результат: явная типизация единиц для всех товаров

#### P0.5 - BestPrice total_cost Calculation ✅
- Формула: `total_cost = ceil(user_qty / min_order_qty) * min_order_qty * price`
- Сортировка кандидатов по `total_cost`, не по `price`
- Реализовано в `sort_key` функции (server.py)

#### P0.6 - Safe Pricelist Deactivation ✅
- `POST /api/price-lists/{id}/deactivate` - деактивация прайс-листа
- `DELETE /api/price-lists/{id}` - полное удаление (только admin)
- `GET /api/price-lists/supplier/{id}` - список прайсов с counts

### Новые файлы:
- `/app/backend/pricelist_importer_v2.py` - P0-совместимый импортер
- `/app/backend/tests/test_p0_requirements.py` - 17 тестов P0

### Импортированные поставщики (9):
| Поставщик | Позиций |
|-----------|---------|
| Алиди | 1587 |
| Интегрита | 1984 |
| Ромакс | 1310 |
| Восток-Запад | 928 |
| Айфрут | 789 |
| Нордико | 629 |
| РБД | 434 |
| Сладкая жизнь | 217 |
| ПраймФудс | 29 |

---

### Geography Cascade (City > Region > Country) (2026-01-06) ✅
**Каскадная фильтрация по географии с приоритетом: Город > Регион > Страна**

Если у товара в избранном указаны географические атрибуты:
- `origin_city` (высший приоритет) → фильтрация по городу
- `origin_region` (средний приоритет) → фильтрация по региону
- `origin_country` (низший приоритет) → фильтрация по стране

**Новые поля в debug_log:**
- `geo_as_brand`: true/false
- `geo_filter_type`: 'city', 'region', или 'country'
- `geo_filter_value`: значение фильтра

**Тестирование: 17/17 тестов прошли**
- Region filter (КАМЧАТКА): ✅
- City filter priority (МУРМАНСК): ✅
- Country filter (РОССИЯ): ✅
- No geo → стандартная логика бренда: ✅

### NEW: Auto-extraction of Geography from Names (2026-01-06) ✅
**Модуль `geography_extractor.py` автоматически извлекает страну/регион/город из названий:**
- "Говядина БЕЛАРУСЬ" → origin_country: 'БЕЛАРУСЬ'
- "Краб Камчатка" → origin_region: 'КАМЧАТКА'
- "СОУС Барбекю Россия" → origin_country: 'РОССИЯ'
- Обработка false positives: "соус чили" ≠ Чили (страна)

**Покрытие после backfill:**
- origin_country: 1868/8218 (22.7%)
- origin_region: 101/8218 (1.2%)
- origin_city: 47/8218 (0.6%)

### Brand Coverage Improvement (2026-01-06) ✅
- Добавлено 40+ новых брендов в `brand_extractor.py`
- **Покрытие брендов: 100%** (все товары имеют brand_id)
- High confidence: 35%, Medium: 18%, Low: 47%

### Full Batch Audit Results
| Метрика | Начало | Финал | Цель | Статус |
|---------|--------|-------|------|--------|
| `other` | 8.8% | **2.1%** | <3% | ✅ |
| Pack parsing | 89% | **95%** | 95%+ | ✅ |
| Low Confidence | 13% | **9%** | <10% | ✅ |
| Brand coverage | 0% | **100%** | 50%+ | ✅ |
| Geo coverage | 0% | **22.7%** | - | ✅ |

### Brand Modes
- **STRICT** — только указанный бренд (если Heinz → только Heinz)
- **ANY** — любой бренд, выбирается самый дешевый
- **GEO_AS_BRAND** — география (город/регион/страна) переопределяет бренд для фильтрации

## Архитектура решения

### Ключевые модули
```
/app/backend/
├── server.py                  # FastAPI, поисковый pipeline v12
├── unit_normalizer.py         # Нормализация единиц, packs_needed, total_cost
├── product_core_classifier.py # Узкая классификация (product_core_id)
├── universal_super_class_mapper.py # Широкая классификация с GUARD RULES
├── p0_hotfix_stabilization.py # Guards (anchors/forbidden tokens)
└── backfill_product_core.py   # Backfill script для обновления данных
```

### Pipeline поиска
1. **active filter** → только активные товары
2. **product_core STRICT match** → строгое совпадение категории
3. **guards** → anchor/forbidden токены на кандидатах
4. **brand filter** → если brand_critical=true
5. **unit_gate** → проверка совместимости единиц (WEIGHT vs VOLUME)
6. **pack/total_cost calculation** → расчет packs_needed и стоимости
7. **ranking** → сортировка по total_cost

### GUARD RULES (защита от ложных срабатываний)
Добавлены в `universal_super_class_mapper.py`:
- `бобы/эдамаме` → `vegetables.beans` (NOT seafood)
- `персик/ананас` → `canned.фрукты` (NOT seafood)
- `бумага для выпечки` → `disposables.paper` (NOT staples)
- `желатин/агар/пектин` → `additives.*` (высший приоритет)
- `соль/сахар` → правильные категории
- `рибай/ribeye` → `meat.beef.ribeye`

## Реализованные функции

### P0 Import & BestPrice (NEW 2026-01-09) ✅
- [x] P0.1: Upsert on import (unique_key)
- [x] P0.2: One active pricelist per supplier
- [x] P0.3: Import min_order_qty
- [x] P0.4: Unit priority (file > parsed)
- [x] P0.5: total_cost = ceil(qty/min_order_qty) * min_order_qty * price
- [x] P0.6: Safe pricelist deactivation endpoints

### P0 Matching (Критичные) ✅
- [x] Unit normalization (kg→g, l→ml, шт)
- [x] Correct `packs_needed` calculation
- [x] Correct `total_cost` calculation
- [x] UNIT_MISMATCH gate
- [x] PACK_OUTLIER gate (packs > 20)
- [x] Diagnostic fields в API response

### P1 (Важные) ✅
- [x] Strict `product_core_id` matching
- [x] CORE_MISMATCH hard rule
- [x] GUARD RULES для предотвращения false positives
- [x] Backfill script для обновления данных
- [x] Правило для ribeye/рибай

### P2 (Улучшения) ⏳
- [ ] Full batch audit на 8.2k товаров
- [ ] Brand extraction/backfill
- [ ] Unit parsing для листов/рулон/уп/блок/саше

## Результаты тестирования

### Smoke Test (2026-01-05)
- **Build SHA**: 806eea0
- **Success Rate**: 95% (19/20 товаров)
- **NOT_FOUND**: 1 (brand_critical=true, бренд отсутствует)

### Исправленные false positives:
| Товар | Было | Стало |
|-------|------|-------|
| БОБЫ соевые | seafood.shrimp | vegetables.beans |
| ПЕРСИКИ | seafood.shrimp | canned.фрукты |
| БУМАГА | staples.рис | disposables.paper |
| ЖЕЛАТИН пакет | disposables.bags | additives.gelatin |
| РИС БАСМАТИ | staples.рис (тыква!) | staples.рис.басмати |
| РИБАЙ PRIME | meat.beef (not_found) | meat.beef.ribeye |

## API Endpoints

### POST /api/cart/add-from-favorite
Основной endpoint поиска. Response включает:
- `status`: ok | not_found
- `ref_product_core`: категория запроса
- `selected_product_core`: категория найденного товара
- `packs_needed`: количество упаковок
- `computed_total_cost`: итоговая стоимость
- `debug_log`: диагностика (request_id, build_sha, counts)

### GET /api/debug/version
Проверка версии билда.

## Backlog

### Высокий приоритет (P1)
1. **Brand Coverage Improvement**: Увеличить покрытие брендов с ~53% высокой/средней уверенности до 70%+
2. **Full Batch Audit**: Полный аудит после P0 изменений

### Средний приоритет (P2)
1. Telegram Bot интеграция
2. Расширенные права пользователей
3. Рефакторинг server.py (разбиение на модули)

### Низкий приоритет (P3)
1. История изменений цен
2. Уведомления о скидках
3. Расширение unit parsing для сложных форматов

## Технический долг
- Монолитный server.py (~3900 строк) требует разбиения
- Часть товаров имеет `product_core_id: 'other'` (~2.1%)
- Нужна валидация guards на полном каталоге

## Credentials
- Customer: `customer@bestprice.ru` / `password123`
