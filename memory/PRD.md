# Best Price Matching Engine - PRD v12

## Описание продукта
E-commerce платформа для B2B заказов с оптимизацией многопоставочных закупок.

## ✅ Выполненные задачи

### Phase 23 - КРИТИЧЕСКИЙ ФИКС: Отключение Legacy Fallback — 28 января 2026

**ПРОБЛЕМА:** При неклассифицируемом REF система откатывалась на legacy v3 движок, который НЕ применял hard gates. Это позволяло "мусорным" результатам (гёдза, другой калибр и т.д.) попадать в strict режим.

**РЕШЕНИЕ:**
1. **`npc_matching_v9.py` (строка 1341-1344):** 
   - Изменено `return None, None, None` → `return [], [], {'REF_NOT_CLASSIFIED': 1}`
   - Теперь при неклассифицируемом REF возвращается пустой strict список вместо fallback на legacy

2. **`routes.py` (строки 1778-1813):**
   - Убрана логика `use_npc = False` при `npc_strict is None`
   - Добавлен явный return для случая `REF_NOT_CLASSIFIED` с информативным ответом
   - Legacy fallback ПОЛНОСТЬЮ ОТКЛЮЧЁН для режима strict

**ИНВАРИАНТ STRICT:**
- Если у REF не распознан `npc_domain` → strict = [] (пустой список)
- Legacy engine НИКОГДА не используется для NPC доменов (SHRIMP/FISH/SEAFOOD/MEAT)
- Это гарантирует "нулевой мусор" — лучше пустой список, чем некорректные результаты

**Тестирование:**
- ✅ **334 теста** прошли без изменений
- ✅ Backend успешно перезапущен
- ✅ API возвращает `ruleset_version: 'npc_shrimp_v12'` и корректную структуру

---

### Phase 22 - NPC Matching SHRIMP v12 — Caliber Fix + Debug Output — 27 января 2026

**КРИТИЧЕСКИЙ ФИКС:** При REF "ваннамей 16/20" в выдачу попадали 31/40, 26/30, 21/25 — ИСПРАВЛЕНО.

**Изменения в API (`routes.py`):**
- NPC фильтрация применяется **напрямую к raw_candidates** (без v3 preprocessing)
- Добавлен `ruleset_version: 'npc_shrimp_v12'`
- Добавлен `ref_parsed` — распарсенные атрибуты REF
- Добавлен `cand_parsed` — распарсенные атрибуты кандидата
- Добавлен `passed_gates[]` для каждого кандидата
- Добавлен `rank_features{}` для каждого кандидата

**Hard Gates (все применяются ДО ранжирования):**
1. `FORBIDDEN_CLASS` — гёдза/пельмени/вареники/хинкали/суп/салат/набор/ассорти/котлеты/наггетсы/лапша
2. `SHRIMP-only` — candidate.class != SHRIMP → REJECT NOT_SHRIMP
3. `species` — vannamei ≠ tiger ≠ north
4. `state` — с/м ≠ в/м
5. `form` — очищ ≠ неочищ
6. `caliber` — ВСЕГДА hard gate (16/20 ≠ 21/25 ≠ 31/40)
7. `tail_state` — с хвостом ≠ без хвоста
8. `breaded_flag` — панировка ≠ без
9. `UOM` — шт ≠ кг

**Калибр нормализация:**
- `16/20`, `16-20`, `16 / 20`, `16/20*`, `16/20 шт/ф` → `16/20`

**Ranking (только после hard gates):**
1. `brand_match` (НЕ block!)
2. `country_match` (НЕ block!)
3. `ppu`

**Тестирование:**
- ✅ **334 теста** прошли
- ✅ 121 caliber regression тестов
- ✅ 32 кейса 16/20 vs 31/40/26/30/21/25/гёдза — все REJECT

---

### Phase 21 - NPC Matching SHRIMP — Final Regression Suite — 27 января 2026

**Полная реализация по ТЗ:**

#### 1. Режимы:
- `strict` (default): только корректные альтернативы, может быть пусто
- `similar` (by param): включается по `mode=similar`

#### 2. Hard Gates (строго 1-в-1):
- `SHRIMP-only`: candidate.category MUST be SHRIMP
- `species`: vannamei ≠ tiger ≠ north
- `state`: с/м ≠ в/м
- `form`: очищ ≠ неочищ
- `caliber`: НИКОГДА не ослаблять
- `tail_state`: с хвостом ≠ без хвоста (с/хв, б/хв...)
- `breaded_flag`: панировка/темпура/кляр ≠ без
- `UOM`: шт vs кг НЕ смешивать

#### 3. Forbidden Class (NEVER показывать):
гёдза, пельмени, вареники, хинкали, лапша, суп, салат, набор, ассорти, микс, котлеты, наггетсы, полуфабрикаты, закуска

#### 4. Ranking (после hard gates):
1. `same_brand` first (НЕ block!)
2. `same_country` first (НЕ block!)
3. `ppu` (цена за единицу)

#### 5. Debug Output:
- `passed_gates[]`
- `rejected_reason`
- `rank_features{brand_match, country_match, caliber_exact, ...}`

#### 6. Автотесты:
- ✅ **213 тестов** прошли
- ✅ 84 regression кейсов (forbidden, hard gates, ranking)
- ✅ Integration tests
- ✅ 0 false positives (мусор не проходит)
- ✅ 0 false negatives (хорошие товары проходят)

---

### Phase 20 - NPC Matching v12 «Fix 5 Cases + AutoCheck» — 27 января 2026

**Исправлены 5 критических багов:**

#### A) FORBIDDEN_CLASS — Гёдза/пельмени/наборы
- Ранний reject ДО всех гейтов
- Расширен blacklist: добавлен `микс`, `закуска`
- Проверка работает И в Strict, И в Similar

#### B) tail_state — Парсер "с/хв", "б/хв"
- Распознаёт: `с/хв`, `с хв`, `с хвостом`, `хвостик`, `tail-on`, `t-on`
- Распознаёт: `б/хв`, `без хв`, `без хвоста`, `tail-off`, `t-off`, `tailless`
- Если REF tail_state=null → не гейт, только ranking bonus

#### C) breaded_flag — Панировка/темпура/кляр
- Hard gate 1-в-1: plain ↔ breaded запрещено

#### D) UOM gate — шт vs кг
- Hard gate: `kg` ↔ `pcs` запрещено

#### E) Ранжирование — Калибр > Бренд
**Новый порядок:**
1. `caliber_exact` — TOP PRIORITY
2. `size_score` (близость размера)
3. `tail_match`
4. `breaded_match`
5. `text_similarity`
6. `brand_match` (НЕ выше калибра!)
7. `country_match` (НЕ выше калибра!)
8. `ppu`

#### F) Debug Output
- `passed_gates[]` — список пройденных gates
- `rejected_reason` — причина блокировки
- `rank_features{}` — все параметры ранжирования

**Тестирование:**
- ✅ 129 тестов прошли (24 + 61 + 44 новых)
- ✅ 5 AutoCheck кейсов (SHR-01..SHR-05)
- ✅ Полная регрессия

---

### Phase 19 - NPC Matching v11 «SHRIMP Zero-Trash» — 27 января 2026

**ТЗ v11 SHRIMP (новое):**

#### 0. Global NEVER Blacklist (Strict + Similar):
Товары с этими словами **ВСЕГДА** блокируются:
- гёдза, пельмени, вареники, хинкали
- суп, салат, набор, ассорти
- котлеты, наггетсы, фрикадели
- лапша, удон, рамен
- соус, чипсы, снеки, крекер

#### 1. SHRIMP-only Gate:
Если REF = SHRIMP → candidate должен быть SHRIMP, иначе `REJECT NOT_SHRIMP`

#### 2. Hard Gates для SHRIMP (строго 1-в-1):
- **species** (vannamei ≠ tiger ≠ north ≠ king)
- **shrimp_state** (с/м ≠ в/м)
- **shrimp_form** (очищ ≠ неочищ)
- **tail_state** (с хвостом ≠ без хвоста) — НОВОЕ
- **breaded_flag** (панировка/темпура/кляр) — НОВОЕ
- **shrimp_caliber** — НИКОГДА не ослабляется

#### 3. UOM Gate:
шт vs кг не смешиваются в Strict

#### 4. Brand/Country — ТОЛЬКО ранжирование:
- НЕ являются hard gates
- Влияют только на порядок в результатах

#### 5. Ранжирование (после hard gates):
1. brand_match (тот же бренд выше)
2. country_match (та же страна выше)
3. text_similarity
4. ppu

#### 6. Debug Output:
- `rejected_reason` — причина блокировки
- `passed_gates` — пройденные gates
- `rank_features` — параметры ранжирования

**Тестирование:**
- ✅ 85 тестов прошли (24 + 61 новых)
- ✅ Полное покрытие всех hard gates

---

### Phase 18 - NPC Matching v10 «Нулевой мусор» — 26 января 2026

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

### ТЗ v9.2 — Финальные уточнения — 27 января 2026

**Реализовано:**
1. **Порядок фильтров**: SIZE_TOLERANCE проверяется **до** 85% guard
2. **Допуск размера ±20%**: Строгий допуск для fish size ranges
   - `255-311г` vs `340-400г` (diff 30.7%) → **BLOCKED** ✅
   - `255-311г` vs `280-340г` (diff 9.5%) → **PASS** ✅

**Тестирование:**
- ✅ 24/24 pytest тестов прошли
- ✅ Ручная верификация размерного допуска прошла

### ТЗ SHRIMP v1 (Zero-Trash) — 27 января 2026

**Реализовано полностью по ТЗ:**

**Hard-gates (обязательные 1-к-1):**
1. **Вид продукта** — только креветки, запрещены: гёдза, пельмени, п/ф, панировка, соусы, снеки, лапша
2. **species** — vannamei ≠ tiger ≠ north (строго 1-к-1)
3. **shrimp_form** — сыроморож ≠ варёно-морож (строго 1-к-1)
4. **shrimp_state** — очищ ≠ неочищ ≠ хвост (строго 1-к-1)
5. **shrimp_caliber** — НИКОГДА не ослабляется (16/20 ≠ 21/25)

**Упаковка:**
- Box-rule: retail ≠ короб (в обе стороны)
- Граммовка: приоритет ближайшей

**Бренд и страна:**
- Brand gate: если REF brand есть → только тот же бренд, иначе пусто
- Country: влияет на ранжирование, НЕ блокирует

**Запреты:**
- Консервы (ж/б) — BLOCKED
- Копчёные (х/к, г/к) — BLOCKED
- П/ф, панировка — BLOCKED

**Тестирование:**
- ✅ 38 тестов в `test_shrimp_v1_zero_trash.py`
- ✅ 24 теста в `test_npc_matching_v9.py`
- ✅ Всего: 62 теста прошли

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
