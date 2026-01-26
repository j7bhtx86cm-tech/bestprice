# Best Price Matching Engine - PRD v12

## Описание продукта
E-commerce платформа для B2B заказов с оптимизацией многопоставочных закупок.

## ✅ Выполненные задачи

### Phase 18 - NPC Matching v10 «Нулевой мусор» + приоритет идентичности — 26 января 2026

**Задача (P0)**: ТЗ v10 — жёсткие формы + бренд + страна + 85% guard

#### HARD GATES (Strict):

**1. PROCESSING_FORM** — CANNED ≠ SMOKED ≠ FROZEN_RAW ≠ CHILLED
**2. CUT_TYPE** — WHOLE ≠ FILLET ≠ STEAK ≠ MINCED  
**3. SPECIES** — окунь ≠ сибас ≠ тилапия ≠ скумбрия
**4. IS_BOX** — в обе стороны (короб ↔ не короб)
**5. BRAND GATE** — если у REF есть brand → только тот же бренд
**6. 85% GUARD** — если бренда нет → similarity >= 0.85
**7. SHRIMP** — species/form/state/caliber строго 1-в-1

#### РАНЖИРОВАНИЕ Strict:
1. size_score (близость размера/калибра)
2. country_score (та же страна +50)
3. brand_score (тот же бренд +50)
4. npc_score (остальное)

#### Новые rejected reasons:
- `BRAND_MISMATCH` — разные бренды
- `SIMILARITY_TOO_LOW` — <85% similarity

#### Тесты:
- ✅ 24 unit-тестов прошли

---

### Phase 17 - NPC Matching Layer v9 (Финальное ТЗ) — 26 января 2026

**Задача (P0)**: Реализация NPC-matching слоя для сложных категорий

#### Описание:
NPC (Node-based Product Classification) — дополнительный слой фильтрации для категорий MEAT, FISH, SEAFOOD, SHRIMP. Работает **поверх** matching_engine_v3.py, обеспечивая высокоточную классификацию и предотвращая "мусорные" результаты (гёдза в креветках, бульон в филе).

#### Архитектура:
```
/api/v12/item/{item_id}/alternatives
    │
    ├── [NPC Domain?] ─Yes─> NPC Matching (npc_matching_v9.py)
    │                         │
    │                         ├── Load candidates from matching_engine_v3 (topK=200)
    │                         ├── Apply NPC hard exclusions
    │                         ├── Filter by npc_node_id
    │                         └── Split Strict/Similar + labels
    │
    └── [Non-NPC] ──────────> Legacy Matching (matching_engine_v3.py)
```

#### Реализовано:

**1. NPC Domains:**
- `SHRIMP` — креветки (ваннамей, тигровые, аргентинские, северные)
- `FISH` — рыба (лосось, форель, треска, тунец, и др.)
- `SEAFOOD` — морепродукты (кальмары, мидии, гребешки, крабы)
- `MEAT` — мясо и птица (говядина, свинина, курица, индейка, колбасы)

**2. Hard Exclusions (из lexicon_npc_v9.json):**
- ✅ Гёдза/пельмени/дамплинги → исключены из SHRIMP/MEAT
- ✅ Бульоны (Knorr, Арикон) → исключены из MEAT
- ✅ Соусы (терияки, майонез) → исключены
- ✅ Нори/чука/водоросли → исключены из SEAFOOD
- ✅ Крабовые палочки/сурими → исключены (имитация)
- ✅ "Со вкусом креветки" → исключено (не креветка)
- ✅ Рибай/ribeye → MEAT (не FISH)

**3. NPC Node Filtering:**
- Схема `npc_schema_v9.xlsx` содержит 73 узла:
  - SHRIMP: 27 nodes (по species + caliber_band + состояние)
  - FISH: 12 nodes (по species)
  - SEAFOOD: 5 nodes (по type)
  - MEAT: 29 nodes (по animal + cut)
- **Strict**: требует совпадение npc_node_id
- **Similar**: разрешает соседние узлы с лейблами

**4. Атрибуты для matching:**
- SHRIMP: species, caliber, caliber_band, peeled, headless, cooked
- FISH: species, cut, skin (on/off), canned
- SEAFOOD: type
- MEAT: animal, cut
- Общие: state_frozen, state_chilled, is_breaded

**5. Fallback Rules:**
- REF без npc_node_id → legacy результат (NPC skip)
- Candidate без npc_node_id → запрещён в Strict, разрешён в Similar с лейблом

#### Файлы:
- `/app/backend/bestprice_v12/npc_matching_v9.py` — NPC модуль (NEW)
- `/app/backend/bestprice_v12/npc_schema_v9.xlsx` — схема NPC узлов
- `/app/backend/bestprice_v12/lexicon_npc_v9.json` — лексикон исключений
- `/app/backend/bestprice_v12/regression_checklist_v9.xlsx` — чеклист тестов
- `/app/backend/bestprice_v12/routes.py` — обновлён endpoint
- `/app/backend/tests/test_npc_matching_v9.py` — 46 unit-тестов (NEW)

#### API Response (NPC mode):
```json
{
  "source": {
    "npc_domain": "SHRIMP",
    "npc_node_id": "shr_002",
    "npc_signature": {
      "shrimp_species": "vannamei",
      "shrimp_caliber": "21/25"
    }
  },
  "strict": [...],
  "similar": [...],
  "matching_mode": "npc",
  "npc_domain": "SHRIMP",
  "rejected_reasons": {"NODE_MISMATCH": 23, "STATE_MISMATCH": 20}
}
```

---

### Phase 16 - Matching Engine v3.0 (ТЗ v12) — 22 января 2026

**Задача (P0)**: Полная реализация ТЗ v12 — "Offer Matching & Сравнить предложения"

#### Реализовано:

**1. Двухрежимная выдача:**
- **Strict** — точные аналоги по hard-атрибутам
- **Similar** — если Strict < 4, добавляется блок "Похожие" с лейблами отличий
- Similar никогда не подмешивается в Strict

**2. Hard-атрибуты per group (матрица правил):**
- **Общие**: `product_form`, `unit_type` (WEIGHT ≠ PIECE ≠ VOLUME)
- **Тип продукта**: `product_type` (bouillon ≠ sauce ≠ fillet ≠ canned)
- **Мясо/рыба**: chilled/frozen, part_type, skin, breaded
- **Молочка**: condensed ≠ dairy ≠ plant ≠ lactose_free ≠ coconut
- **Соусы/бренды**: приоритет бренда → потом другие
- **Посуда**: тип совпадает (крышка ≠ стакан ≠ вилка)
- **Порционные**: только с порционными (0.3г ≠ 1кг)

**3. Фасовка и масштаб:**
- Режим A (посуда/порционка): ±10%
- Режим B (бакалея): ±20%
- Multipack: сравнивает единицу порции
- 1кг vs 145г — не смешивается

**4. Ранжирование (Strict):**
1. Бренд (если задан — сначала тот же)
2. Близость фасовки
3. ppu_value (цена за единицу)
4. min_line_total

**5. Лейблы отличий (для Similar):**
- "Бренд другой"
- "Фасовка: X vs Y"
- "В панировке", "На коже/Без кожи"
- "Форма: frozen/chilled"

**6. Извлечение бренда из названия:**
- Известные бренды (Heinz, Barilla, Bonduelle, etc.) распознаются автоматически

#### Файлы:
- `/app/backend/bestprice_v12/matching_engine_v3.py` — новый движок (v3.0)
- `/app/backend/bestprice_v12/routes.py` — обновлён endpoint
- `/app/backend/tests/test_matching_v3.py` — 23 unit-теста
- `/app/backend/tests/test_integration_alternatives.py` — 13 интеграционных тестов

#### Регрессионные тесты (15 из 15):
1. ✅ Перец 0.3г → НЕ кг
2. ✅ Сахар порционный → НЕ 5кг
3. ✅ Стакан → только стаканы
4. ✅ Крышки → только крышки (размер 1:1)
5. ✅ Вилка → только вилки
6. ✅ Контейнеры → контейнеры
7. ✅ Heinz → приоритет бренда
8. ✅ Анчоус 145г → НЕ весовой
9. ✅ **Бульон рыбный → НЕ филе/соус** (NEW!)
10. ✅ Рыба филе → НЕ консервы
11. ✅ Рыба на коже → НЕ без кожи
12. ✅ Креветки → НЕ панировка в Strict
13. ✅ Молоко → НЕ сгущёнка
14. ✅ Молоко кокосовое → НЕ обычное
15. ✅ Соус рыбный → НЕ бульон/филе

---

## API Endpoints

### GET /api/v12/item/{item_id}/alternatives

**Query params:**
- `limit` (int, default 10, max 20)
- `include_similar` (bool, default true)

**Response:**
```json
{
  "source": {
    "id": "...",
    "name": "Соус ХАЙНЦ Барбекю 1кг",
    "price": 296.55,
    "brand_id": "heinz",
    "product_core_id": "condiments.bbq",
    "category_group": null,
    "signature": {...}
  },
  "strict": [...],
  "similar": [...],
  "alternatives": [...],  // backward compatible
  "strict_count": 10,
  "similar_count": 0,
  "total": 10,
  "rejected_reasons": {"PACK_MISMATCH": 8}
}
```

**Alternative item:**
```json
{
  "id": "...",
  "name_raw": "СОУС барбекю 1 кг HEINZ",
  "price": 366.0,
  "brand_id": "heinz",
  "match_score": 180,
  "match_mode": "strict",
  "brand_match": true,
  "pack_diff_pct": 0.0,
  "difference_labels": []
}
```

---

## Архитектура

```
/app/backend/bestprice_v12/
├── npc_matching_v9.py      # NPC matching layer (v9 - Финальное ТЗ)
├── matching_engine_v3.py   # Core matching engine (v3.0 - ТЗ v12)
├── matching_rules_v2.py    # Legacy (v2.0)
├── matching_rules.py       # Legacy (v1.3 lexicon-based)
├── routes.py               # API endpoints
├── npc_schema_v9.xlsx      # NPC node schema
├── lexicon_npc_v9.json     # NPC exclusion lexicon
└── tests/
    ├── test_npc_matching_v9.py       # 46 NPC unit tests
    ├── test_matching_v3.py           # 23 unit tests
    └── test_integration_alternatives.py  # 13 integration tests
```

---

## Тестовые аккаунты
- Customer: `customer@bestprice.ru` / `password123`

---

## Предстоящие задачи

### P1 - Рефакторинг routes.py
- Перенос endpoints в `/routes_modules/`

### P2 - UI Improvements
- Показать лейблы отличий в "Сравнить предложения"
- Разделить визуально Strict и Similar

### P3 - Будущие улучшения
- Интеграция auto_classifier.py в импорт прайс-листов
- Telegram-бот для уведомлений
- UI для отладки решений matching
- A/B тестирование поиска
