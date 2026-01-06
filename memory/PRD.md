# Best Price Matching Engine - Product Requirements Document

## Дата последнего обновления: 2026-01-06

## Оригинальная проблема
Система "Best Price" для поиска лучших цен на товары из избранного работала некорректно:
- Неверные матчи: "васаби" → "соль", "пшеничная мука" → "ржаная мука"
- Ошибки расчета: запрос "1 кг" удовлетворялся товаром "5 г"
- Бессмысленные `match_percent` scores

## Текущий статус: ✅ P2 Complete

### Full Batch Audit Results (2026-01-06)
| Метрика | Начало | После P1 | После P2 | Цель |
|---------|--------|----------|----------|------|
| `other` | 8.8% | 4.3% | **2.2%** | <3% ✅ |
| Brand coverage | 0% | 5% | **50%** | 50%+ ✅ |
| High Confidence | 12% | 19% | 18% | - |

### Data Coverage (8218 items)
- Product Core: 100%
- Super Class: 100%
- Brand: **50%** ✅ (было 5%)
- Pack parsing: 89%
- Unit Type: 89%

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

### Высокий приоритет
1. Full batch audit и анализ оставшихся NOT_FOUND
2. Расширение GUARD RULES по результатам аудита
3. Улучшение unit parsing для сложных форматов

### Средний приоритет
1. Brand extraction из названий товаров
2. Рефакторинг server.py (вынос pipeline)
3. Telegram Bot интеграция

### Низкий приоритет
1. Расширенные права пользователей
2. История изменений цен
3. Уведомления о скидках

## Технический долг
- Монолитный server.py (~3800 строк) требует разбиения
- Часть товаров имеет `product_core_id: 'other'` (~10%)
- Нужна валидация guards на полном каталоге

## Credentials
- Customer: `customer@bestprice.ru` / `password123`
