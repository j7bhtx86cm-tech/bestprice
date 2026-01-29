# SHRIMP_RULES_SPEC_v1.md
# Спецификация правил NPC Matching для домена SHRIMP
# Version: npc_shrimp_v12 (ZERO-TRASH)
# Date: 28 января 2026

---

## 1. Domain Detection

### Как определяется SHRIMP

**Файл:** `/app/backend/bestprice_v12/npc_matching_v9.py`
**Функция:** `_detect_npc_domain()` (строки 1003-1050)

#### Порядок проверок:

1. **FORBIDDEN_CLASS проверка ПЕРВАЯ** (строка 1013)
   - `check_blacklist(name_norm)` → если True → `return None`
   - Blacklisted items НЕ получают домен

2. **SHRIMP_EXCLUDES** (строка 1018)
   - Исключения: `со вкусом`, `вкус кревет`, `ароматизатор`, `чипс`, `снек`, `сухар`, `крекер`, `соус`

3. **SHRIMP_TERMS** (строки 610-619)
   ```python
   SHRIMP_TERMS = [
       'креветк', 'креветоч', 'shrimp', 'prawn',
       'ваннамей', 'ванамей', 'vannamei', 'vanamei', 'vannameii',
       'тигров', 'tiger',
       'королевск', 'king', 'royal',
       'лангустин', 'langoustine', 'langostin',
       'северн', 'северян', 'north', 'northern',
       'аргентин', 'argentin', 'argentina',
       'черномор',
   ]
   ```
   Если найден любой термин → `return 'SHRIMP'`

4. **Контекстное определение** `detect_shrimp_by_context()` (строка 666)
   - Условие: `has_caliber_pattern(name_norm)` AND `shrimp_attr_count >= 2`
   - SHRIMP_ATTRS: `б/г`, `с/г`, `очищ`, `с/м`, `в/п`, `шт/ф`, `iqf`, `block`, `во льду`

---

## 2. Parsed Attributes

**Файл:** `/app/backend/bestprice_v12/npc_matching_v9.py`
**Dataclass:** `NPCSignature` (строки 163-230)
**Функция:** `extract_npc_signature()` (строки 893-990)

### 2.1 species (вид креветок)

**Функция:** `extract_species()` (строки 476-530)

| Species | Токены |
|---------|--------|
| `vannamei` | ваннам, белоног, vanam, vannam |
| `tiger` | тигр, tiger |
| `argentine` | аргент, argentin |
| `northern` | северн, ботан, pandalus, coldwater, northern, норвеж, гренланд |
| `king` | королев, king, royal |
| `unspecified` | если ничего не найдено |

### 2.2 shrimp_caliber (калибр)

**Функция:** `extract_shrimp_caliber()` (строки 581-600)

**Regex:** `r'(\d{1,3})\s*[/\-:]\s*(\d{1,3})'`

**Поддерживаемые форматы:**
- `16/20`, `16-20`, `16 / 20`, `16 - 20`
- `16:20`, `16 : 20`
- `16/20*`, `16/20шт`

**Возвращает:** `(caliber_str, caliber_min, caliber_max)` → например `("16/20", 16, 20)`

### 2.3 shrimp_state (состояние)

**Функция:** `extract_shrimp_state()` (строки 681-690)

| State | Паттерны |
|-------|----------|
| `raw_frozen` | с/м, сыромороженн, raw frozen, зам сыр |
| `cooked_frozen` | в/м, варёномороженн, варено-морож, cooked frozen |

### 2.4 shrimp_form (форма)

**Функция:** `extract_shrimp_form()` (строки 692-713)

| Form | Паттерны |
|------|----------|
| `shell_on_head_on` | с/г, с голов, с головой, head on |
| `shell_on_head_off` | б/г, без голов, headless |
| `peeled_tail_on` | очищ + (хвост OR tail) |
| `peeled_tail_off` | очищ + (без хв OR tailless) |
| `peeled` | очищ, peeled, о/м (без уточнения хвоста) |

### 2.5 shrimp_tail_state (хвост)

**Функция:** `extract_shrimp_tail_state()` (строки 715-742)

| Tail State | Паттерны (regex) |
|------------|------------------|
| `tail_off` | `\bб/хв\b`, `\bб/х\b`, `\bбез\s*хв`, `безхв`, `tail-off` |
| `tail_on` | `\bс/хв\b`, `\bс/х\b`, `\bс\s*хвост`, `на\s*хвост`, `tail-on` |

### 2.6 shrimp_breaded (панировка)

**Функция:** `extract_shrimp_breaded()` (строки 744-754)

**Маркеры:**
```python
['панир', 'панко', 'темпур', 'кляр', 'breaded', 'tempura', 'batter',
 'torpedo', 'торпедо', 'в панир', 'в кляр', 'в темпур', 'хрустящ']
```

### 2.7 uom (единица измерения)

**Функция:** `extract_uom()` (строки 808-860)

| UOM | Условия |
|-----|---------|
| `kg` | unit_type = кг/kg, паттерн `\d+\s*кг` |
| `pcs` | unit_type = шт/pcs, паттерн `\d+\s*шт` |
| `pack` | unit_type = уп/pack |

### 2.8 net_weight_kg (нетто вес)

**Функция:** `extract_net_weight_kg()` (строки 756-806)

**Паттерны:**
- `\((\d+(?:[.,]\d+)?)\s*кг\)` → "(1,000 кг)"
- `нетто\s*(\d+(?:[.,]\d+)?)\s*кг` → "нетто 1.5кг"
- `(\d+(?:[.,]\d+)?)\s*кг\b` → "2кг"
- `(\d+)\s*г(?:р)?\b` → "500г" (конвертируется в кг)

---

## 3. Hard Gates (до ранжирования)

**Файл:** `/app/backend/bestprice_v12/npc_matching_v9.py`
**Функция:** `check_npc_strict()` (строки 1095-1320)

### Порядок применения gates (ВАЖНО: порядок имеет значение!)

| # | Gate | Условие | Reject Reason | Строки |
|---|------|---------|---------------|--------|
| 0 | FORBIDDEN_CLASS | `candidate.is_blacklisted` | `FORBIDDEN_CLASS:{reason}` | 1110-1114 |
| 0 | SOURCE_EXCLUDED | `source.is_excluded` | `SOURCE_EXCLUDED:{reason}` | 1116-1120 |
| 0 | CANDIDATE_EXCLUDED | `candidate.is_excluded` | `CANDIDATE_EXCLUDED:{reason}` | 1121-1124 |
| 1 | SHRIMP_DOMAIN | `source.npc_domain == 'SHRIMP'` | `NOT_SHRIMP:{domain}` | 1127-1134 |
| 2a | SPECIES | `source.species != cand.species` | `SPECIES_MISMATCH` | 1136-1149 |
| 2b | SHRIMP_STATE | `source.shrimp_state != cand.shrimp_state` | `SHRIMP_STATE_MISMATCH` | 1150-1158 |
| 2c | SHRIMP_FORM | `source.shrimp_form != cand.shrimp_form` | `SHRIMP_FORM_MISMATCH` | 1159-1167 |
| 2d | TAIL_STATE | REF имеет tail_state | `TAIL_STATE_MISMATCH` / `TAIL_STATE_UNKNOWN` | 1168-1183 |
| 2e | BREADED_FLAG | breaded mismatch | `BREADED_MISMATCH` | 1184-1194 |
| 2f | CALIBER | `source.caliber != cand.caliber` | `CALIBER_MISMATCH` / `CALIBER_MISSING` | 1195-1207 |
| 3 | UOM | `source.uom != cand.uom` (без net_weight) | `UOM_MISMATCH` | 1268-1287 |
| 4 | BOX | `source.is_box != cand.is_box` | `BOX_MISMATCH` | 1289-1300 |

### Логика TAIL_STATE Gate (2d)

```python
if source.shrimp_tail_state:  # Gate применяется ТОЛЬКО если REF имеет tail_state
    if candidate.shrimp_tail_state:
        if source.shrimp_tail_state != candidate.shrimp_tail_state:
            → REJECT "TAIL_STATE_MISMATCH"
    else:
        → REJECT "TAIL_STATE_UNKNOWN:ref={tail},cand=null"
```

### Логика BREADED Gate (2e)

```python
if source.shrimp_breaded:
    if not candidate.shrimp_breaded:
        → REJECT "BREADED_MISMATCH:source_breaded_candidate_not"
elif candidate.shrimp_breaded:
    → REJECT "BREADED_MISMATCH:candidate_breaded"
```

### Логика UOM Gate с весом (3)

```python
if source.uom != candidate.uom:
    if source.net_weight_kg and candidate.net_weight_kg:
        → PASS "UOM_BY_WEIGHT"  # Можно сравнивать по ₽/кг
    else:
        → REJECT "UOM_MISMATCH"
```

### FORBIDDEN_CLASS (Blacklist)

**Функция:** `check_blacklist()` (строки 332-350)
**Константа:** `GLOBAL_BLACKLIST_PATTERNS` (строки 302-320)

```python
GLOBAL_BLACKLIST_PATTERNS = [
    r'\bгёдза\b', r'\bгедза\b', r'\bпельмен', r'\bваренник', r'\bвареник',
    r'\bхинкали\b', r'\bманты\b', r'\bдим[-\s]?сам', r'\bхар[-\s]?гао',
    r'\bсалат\b', r'\bсуп\b', r'\bнабор\b', r'\bассорти\b', r'\bмикс\b',
    r'\bкоктейл[ь]?\b', r'\bсет\b', r'\bплатт?ер\b',
    r'\bкотлет', r'\bбургер', r'\bнаггетс', r'\bстрипс', r'\bпалочк',
    r'\bфрикадел', r'\bтефтел', r'\bлапша\b', r'\bпицц',
]
```

---

## 4. Candidate Retrieval

**Файл:** `/app/backend/bestprice_v12/routes.py`
**Функция:** `get_item_alternatives()` (строки 1638-2080)

### Ключ выборки

```python
candidates_query = {
    'active': True,
    'price': {'$gt': 0},
    'id': {'$ne': item_id},
}

if product_core_id:
    candidates_query['product_core_id'] = product_core_id  # ← КЛЮЧЕВОЙ ФИЛЬТР
```

**Строки:** 1717-1727

### Лимит

```python
raw_candidates = db.supplier_items.find(candidates_query).limit(200)
```

### Риски/Ограничения

1. **product_core_id группирует разные калибры** — все "ваннамей" имеют один product_core_id
2. **Калибр НЕ участвует в product_core_id** — это создаёт много кандидатов для фильтрации
3. **Лимит 200** — если больше 200 кандидатов, часть не попадёт в обработку

---

## 5. Ranking (после gates)

**Файл:** `/app/backend/bestprice_v12/npc_matching_v9.py`
**Функция:** `check_npc_strict()` → `rank_features` (строки 1300-1350)

### Порядок сортировки в strict_results

```python
strict_results.sort(key=lambda x: (
    -x['npc_result'].rank_features.get('caliber_exact', 0),  # 1. Точный калибр (высший)
    -x['npc_result'].rank_features.get('brand_match', 0),    # 2. Совпадение бренда
    -x['npc_result'].rank_features.get('country_match', 0),  # 3. Совпадение страны
    -x['npc_result'].text_similarity,                         # 4. Текстовое сходство
    x['item'].get('price', 999999),                           # 5. Цена (по возрастанию)
))
```

**Строки:** 1470-1480

### rank_features

| Feature | Значение | Условие |
|---------|----------|---------|
| `caliber_exact` | 1.0 | Точное совпадение калибра |
| `brand_match` | 1.0 | Совпадение бренда |
| `country_match` | 1.0 | Совпадение страны |

### UI Сортировка (Frontend)

**Файл:** `/app/frontend/src/components/OfferSelectModal.js` (строки 190-215)

```javascript
sortedAlternatives.sort((a, b) => {
    // 1. Тот же бренд первым
    if (sourceBrand) {
        if (brandA === sourceBrand && brandB !== sourceBrand) return -1;
    }
    // 2. По unit_price_per_kg
    return getUnitPrice(a) - getUnitPrice(b);
});
```

---

## 6. ZERO-TRASH / Legacy Policy

### Когда Legacy ЗАПРЕЩЁН

**Файл:** `/app/backend/bestprice_v12/routes.py` (строки 1768-1778)

```python
is_shrimp_like = looks_like_shrimp(name_norm)
has_caliber = has_caliber_pattern(name_norm)

if (is_shrimp_like or has_caliber) and not use_npc:
    use_npc = True  # Принудительно NPC path
```

**Правило:** Если REF выглядит как креветки ИЛИ имеет калибр-паттерн → legacy_v3 НИКОГДА не используется.

### REF_NOT_CLASSIFIED Response

**Файл:** `/app/backend/bestprice_v12/npc_matching_v9.py` (строки 1430-1450)

| Условие | Rejected Reason |
|---------|-----------------|
| `source.is_blacklisted` | `SOURCE_BLACKLISTED` |
| `source.is_excluded` | `SOURCE_EXCLUDED` |
| `is_shrimp_like and not npc_domain` | `REF_SHRIMP_LIKE_NOT_CLASSIFIED` |
| `has_caliber and not shrimp_caliber` | `REF_CALIBER_PARSE_FAILED` |
| `not npc_domain` | `REF_NOT_CLASSIFIED` |

### ref_debug Поля

**Функция:** `build_ref_debug()` (строки 1620-1700)

```json
{
    "ref_text_source_field": "name_raw",
    "ref_text_used": "КРЕВЕТКИ ваннамей 16/20 с/м",
    "ref_text_after_normalize": "креветки ваннамей 16/20 с/м",
    "looks_like_shrimp": true,
    "is_shrimp_by_context": false,
    "shrimp_attr_count": 2,
    "has_caliber_pattern": true,
    "caliber_pattern_match": "16/20",
    "is_blacklisted": false,
    "npc_domain": "SHRIMP",
    "ref_caliber": "16/20",
    "parse_method": "npc_v12",
    "ruleset_selected": "npc_shrimp_v12",
    "why_legacy": null,
    "why_empty_strict": null
}
```

---

## 7. API Contract

**Endpoint:** `GET /api/v12/item/{item_id}/alternatives`

**Файл:** `/app/backend/bestprice_v12/routes.py` (строки 1638-2080)

### Response Schema (Success)

```json
{
    "source": {
        "id": "uuid",
        "name": "string",
        "name_raw": "string",
        "price": 1200,
        "pack_qty": 1.0,
        "unit_type": "kg",
        "brand_id": "string",
        "product_core_id": "string",
        "supplier_id": "string",
        "supplier_name": "string",
        "npc_domain": "SHRIMP",
        "shrimp_caliber": "16/20"
    },
    "strict_after_gates": [
        {
            "id": "uuid",
            "name_raw": "string",
            "price": 1100,
            "unit_price_per_kg": 1100,
            "net_weight_kg": 1.0,
            "cand_parsed": {
                "shrimp_caliber": "16/20",
                "species": "vannamei",
                "shrimp_state": "raw_frozen",
                "shrimp_form": "shell_on_head_off",
                "shrimp_tail_state": null,
                "shrimp_breaded": false,
                "uom": "kg"
            },
            "passed_gates": ["SHRIMP_DOMAIN", "SPECIES", "SHRIMP_STATE", "SHRIMP_FORM", "BREADED_FLAG", "CALIBER", "UOM"]
        }
    ],
    "strict": [...],  // Backward compat
    "similar": [...],
    "alternatives": [...],  // Deprecated
    "strict_count": 10,
    "similar_count": 0,
    "total": 10,
    "total_candidates": 150,
    "rejected_reasons": {
        "CALIBER_MISMATCH": 45,
        "SPECIES_MISMATCH": 30,
        "FORBIDDEN_CLASS": 5,
        "NOT_SHRIMP": 20
    },
    "matching_mode": "npc",
    "npc_domain": "SHRIMP",
    "ruleset_version": "npc_shrimp_v12",
    "ref_parsed": {
        "npc_domain": "SHRIMP",
        "species": "vannamei",
        "shrimp_caliber": "16/20",
        "shrimp_state": "raw_frozen",
        "shrimp_form": "shell_on_head_off"
    },
    "ref_debug": {...},
    "debug_id": "abc12345"
}
```

### Response Headers

```
Cache-Control: no-store, no-cache, must-revalidate, max-age=0
Pragma: no-cache
Expires: 0
```

---

## 8. Frontend Contract

**Файл:** `/app/frontend/src/components/OfferSelectModal.js`

### Какой массив рендерится

```javascript
const strictAfterGates = data.strict_after_gates || data.strict || [];
setAlternatives(strictAfterGates);
```

**Строки:** 112-115

### Дополнительная валидация на клиенте

```javascript
if (refCaliber && refDomain === 'SHRIMP') {
    const validated = strictAfterGates.filter(item => {
        const candCaliber = item.cand_parsed?.shrimp_caliber;
        if (!candCaliber) return false;  // CALIBER_UNKNOWN
        if (candCaliber !== refCaliber) return false;  // CALIBER_MISMATCH
        return true;
    });
    setAlternatives(validated);
}
```

**Строки:** 118-130

### Empty State

```jsx
{allOffers.length <= 1 && (
    <div data-testid="no-strict-alternatives">
        <p>Нет сопоставимых предложений</p>
        <p>Strict-режим: альтернативы с точным совпадением параметров не найдены</p>
    </div>
)}
```

### Debug Banner (скрыт по умолчанию)

Показывается только при `?debug=1` или `localStorage.DEBUG_NPC === "1"`

---

## 9. Tests

**Директория:** `/app/backend/tests/`

### Тестовые группы

| Файл | Кейсы | Описание |
|------|-------|----------|
| `test_npc_matching_v9.py` | 50+ | Unit tests для NPC функций |
| `test_shrimp_v1_zero_trash.py` | 30+ | ZERO-TRASH правила |
| `test_shrimp_v12_autocheck.py` | 44 | Автопроверки по реальным кейсам |
| `test_shrimp_caliber_regression.py` | 100+ | Regression калибра |
| `test_shrimp_v12_regression.py` | 110+ | Полная regression suite |

**Всего: 334 теста**

### Acceptance Criteria

1. **CALIBER**: Если `ref_caliber != null` → в strict ТОЛЬКО тот же калибр
2. **CALIBER_UNKNOWN**: Если `ref_caliber != null` и `cand_caliber == null` → REJECT
3. **SPECIES**: vannamei ≠ northern ≠ tiger
4. **FORBIDDEN_CLASS**: гёдза/пельмени НИКОГДА в strict
5. **TAIL_STATE**: REF б/х → кандидат только б/х (если REF имеет tail_state)
6. **BREADED**: панировка ≠ обычная
7. **UOM_BY_WEIGHT**: pcs+weight сравнимы с kg

---

## Invariant: Что нельзя сломать при добавлении новых доменов

1. **Hard Gates для SHRIMP обязательны** — CALIBER, SPECIES, STATE, FORM, TAIL_STATE, BREADED всегда проверяются в указанном порядке

2. **FORBIDDEN_CLASS глобален** — гёдза/пельмени блокируются ДО определения домена

3. **Legacy fallback запрещён для shrimp-like** — если `looks_like_shrimp() or has_caliber_pattern()` → только NPC path

4. **Калибр — НИКОГДА не ослабляется** — если REF имеет калибр, кандидат с другим калибром всегда REJECT

5. **Empty strict лучше мусора** — при неопределённом REF возвращаем пустой strict, не fallback на legacy

6. **API contract стабилен** — `strict_after_gates`, `rejected_reasons`, `debug_id`, `ref_parsed`, `ref_debug` всегда присутствуют

7. **334 теста — baseline** — любое изменение не должно ломать существующие тесты

---

## Файловая структура

```
/app/backend/bestprice_v12/
├── npc_matching_v9.py      # NPC logic, gates, parsing
├── routes.py               # API endpoints
├── matching_engine_v3.py   # Legacy (не используется для SHRIMP)
└── routes_modules/         # Модульные роутеры

/app/frontend/src/components/
└── OfferSelectModal.js     # UI модала

/app/backend/tests/
├── test_npc_matching_v9.py
├── test_shrimp_v1_zero_trash.py
├── test_shrimp_v12_autocheck.py
├── test_shrimp_caliber_regression.py
└── test_shrimp_v12_regression.py

/app/memory/
├── PRD.md                  # Product Requirements
└── SHRIMP_RULES_SPEC_v1.md # This file
```
