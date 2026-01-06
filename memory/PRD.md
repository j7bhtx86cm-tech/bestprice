# Best Price Matching Engine - Product Requirements Document

## Дата последнего обновления: 2026-01-06

## Оригинальная проблема
Система "Best Price" для поиска лучших цен на товары из избранного работала некорректно:
- Неверные матчи: "васаби" → "соль", "пшеничная мука" → "ржаная мука"
- Ошибки расчета: запрос "1 кг" удовлетворялся товаром "5 г"
- Бессмысленные `match_percent` scores

## Текущий статус: ✅ Geography Cascade + Auto-extraction + Brand Improvement

### Build SHA: (latest)

### NEW: Geography Cascade (City > Region > Country) (2026-01-06) ✅
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

### P0 (Критичные) ✅
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
1. **Brand Coverage Improvement**: Увеличить покрытие брендов с ~50% до 70%+ путём добавления известных брендов в `brand_extractor.py`
2. **Full Batch Audit**: Полный аудит на ~8.2k товаров после всех изменений

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
