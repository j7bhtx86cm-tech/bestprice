# FISH FILLET Matching Rules Specification v1

## Версия документа
- **Version**: 1.0
- **Date**: January 2026
- **Ruleset**: `npc_fish_fillet_v1`

---

## 1. Обзор домена FISH_FILLET

### 1.1 Цель
Домен FISH_FILLET обеспечивает **ZERO-TRASH** strict matching для категории "Рыба → Филе". Система должна:
- Гарантировать, что `strict` показывает **только** точные аналоги
- Никогда не путать филе с тушкой, стейком или другими типами разделки
- Возвращать пустой список, если нет надёжных аналогов

### 1.2 Философия Zero-Trash
**Лучше пустой результат, чем мусор.**

Если REF-товар:
- Не классифицируется уверенно → пустой strict
- Похож на филе, но domain не определён → пустой strict
- Legacy fallback **ЗАПРЕЩЁН**

---

## 2. Сигнатура товара (FishFilletSignature)

### 2.1 Обязательные поля

| Поле | Тип | Описание |
|------|-----|----------|
| `npc_domain` | string | "FISH_FILLET" |
| `fish_species` | string | Вид рыбы: salmon, cod, pollock, etc. |
| `cut_type` | enum | FILLET, WHOLE, STEAK, CARCASS, MINCED, LIVER |
| `skin_flag` | enum | skin_on, skin_off, unknown |
| `breaded_flag` | bool | true/false |
| `state` | enum | frozen, chilled, unknown |
| `uom` | string | kg, pcs, pack |
| `net_weight_kg` | float | Нетто вес в кг |

### 2.2 Дополнительные поля

| Поле | Тип | Описание |
|------|-----|----------|
| `brand_id` | string | ID бренда |
| `brand_name` | string | Название бренда |
| `origin_country` | string | Страна происхождения |
| `is_box` | bool | Короб/ящик |

---

## 3. Определение вида рыбы (fish_species)

### 3.1 Маппинг species → токены

```
salmon: ['лосось', 'лососев', 'лосося', 'сёмга', 'семга', 'атлантическ']
trout: ['форель', 'форели']
cod: ['треска', 'трески', 'трескова', 'трескового']
pollock: ['минтай', 'минтая']
tuna: ['тунец', 'тунца']
halibut: ['палтус', 'палтуса']
mackerel: ['скумбри']
herring: ['сельд', 'сельди']
seabass: ['сибас', 'сибаса']
dorado: ['дорад', 'дорадо']
tilapia: ['тилапи']
perch: ['окун', 'окуня', 'судак']
pike: ['щук', 'щуки']
pangasius: ['пангасиус']
hake: ['хек', 'хека', 'мерлуз']
flounder: ['камбал']
zander: ['судак', 'судака']
carp: ['карп', 'сазан']
catfish: ['сом', 'сома']
haddock: ['пикш']
pink_salmon: ['горбуш']
chum_salmon: ['кета', 'кеты']
coho_salmon: ['кижуч']
sockeye_salmon: ['нерк']
```

### 3.2 Логика
1. Нормализуем название в нижний регистр
2. Ищем первое совпадение токена
3. Возвращаем species или `None`

---

## 4. Тип разделки (cut_type)

### 4.1 Приоритет определения

1. **LIVER** (печень) — проверяется первым
2. **FILLET** (филе) — наивысший приоритет среди разделок
3. **MINCED** (фарш)
4. **STEAK** (стейк, кусок, порция)
5. **CARCASS** (каркас, хребет)
6. **WHOLE** (тушка, целая, н/р, н/п) — последний

### 4.2 Паттерны

```
LIVER: ['печень']
FILLET: ['филе', 'fillet', 'filet', 'филей', 'филе-кусок', 'филе-порц']
MINCED: ['фарш', 'mince', 'ground']
STEAK: ['стейк', 'steak', 'кусок', 'порц', 'ломт']
CARCASS: ['каркас', 'хребет', 'хребты', 'спинк', 'carcass']
WHOLE: ['тушка', 'тушки', 'целая', 'целый', 'whole', 'н/р', 'н/п', 'неразд', 'непотр', 'потрош', 'с головой', 'без голов', 'б/г', 'с/г']
```

### 4.3 Критическое правило
**FILLET имеет абсолютный приоритет** над WHOLE:
- "филе трески потрошёная" → FILLET (не WHOLE)

---

## 5. Состояние кожи (skin_flag)

### 5.1 Паттерны

```
SKIN_OFF: ['\bбез\s*кож', '\bб/к\b', '\bskin[\s\-]?off\b', '\bskinless\b', '\bбескож']
SKIN_ON: ['\bна\s*кож', '\bс\s*кож', '\bskin[\s\-]?on\b', '\bс/к\b']
```

### 5.2 Приоритет
- `skin_off` проверяется **первым** (для случаев типа "без кожи на коже")

---

## 6. Панировка (breaded_flag)

### 6.1 Паттерны

```
BREADED: ['панир', 'панко', 'breaded', 'batter', 'в кляр', 'кляр', 'хрустящ', 'tempura', 'темпур']
```

### 6.2 Логика
- Любое совпадение → `breaded_flag = true`
- Иначе → `breaded_flag = false`

---

## 7. Состояние (state)

### 7.1 Паттерны

```
FROZEN: ['с/м', 'свежеморож', 'свежемороз', 'зам', 'замор', 'мороз', 'frozen']
CHILLED: ['охл', 'охлажд', 'chilled', 'свеж']
```

### 7.2 Приоритет
- `frozen` проверяется **первым** (для "свежемороженое")

---

## 8. Чёрный список (Blacklist / FORBIDDEN_CLASS)

### 8.1 Запрещённые паттерны

```regex
# Полуфабрикаты / готовые блюда
\bгёдза\b, \bгедза\b, \bпельмен, \bваренник, \bвареник
\bхинкали\b, \bманты\b
\bполуфабрикат, \bп/ф\b, \bготовое\s+блюдо

# Супы/салаты/наборы
\bсуп\b, \bсупа\b, \bсупов\b, \bсалат, \bнабор
\bассорти\b, \bмикс\b, \bсет\b

# Котлеты/наггетсы
\bкотлет, \bнаггетс, \bфрикадел, \bтефтел, \bбургер

# Имитация
\bсо\s+вкусом\b, \bкрабов\w*\s+палоч, \bсурими\b

# Консервы/пресервы
\bконсерв, \bпресерв, \bж/б\b, \bв\s+масле\b, \bв\s+томат

# Копчёное/солёное
\bкопч, \bх/к\b, \bг/к\b, \bсолён, \bсолен, \bмалосол

# Икра/субпродукты (кроме LIVER)
\bикра\b, \bмолок\b, \bпечень\b
```

### 8.2 Логика
- Совпадение **любого** паттерна → товар **БЛОКИРУЕТСЯ**
- Blacklisted товар **НИКОГДА** не попадает в strict

---

## 9. Hard Gates (Strict режим)

### 9.1 Порядок проверки

| # | Gate | Описание | Fail = Block |
|---|------|----------|--------------|
| 0 | FORBIDDEN_CLASS | Blacklist check | ✓ |
| 1 | DOMAIN | npc_domain == "FISH_FILLET" | ✓ |
| 2 | SPECIES | Вид рыбы совпадает | ✓ |
| 3 | CUT_TYPE | Тип разделки совпадает (КРИТИЧНО!) | ✓ |
| 4 | BREADED_FLAG | Панировка совпадает | ✓ |
| 5 | SKIN_FLAG | Кожа совпадает (если известно у REF) | ✓ |
| 6 | STATE | Состояние совпадает (если известно у REF) | ✓ |
| 7 | UOM | Единица измерения совпадает | ✓ |
| 8 | BOX | Короб ↔ не короб | ✓ |
| 9 | WEIGHT_TOLERANCE | ±20% по весу | Не блокирует |

### 9.2 Критические правила

#### CUT_TYPE (Gate #3)
**Это КЛЮЧЕВОЙ gate!**
- FILLET ≠ WHOLE ≠ STEAK ≠ CARCASS ≠ MINCED
- REF "филе" → CAND "тушка" = **REJECTED**
- REF "филе" → CAND "стейк" = **REJECTED**
- REF "тушка" → CAND "филе" = **REJECTED** (REF не FISH_FILLET)

#### SPECIES (Gate #2)
- Вид рыбы **ВСЕГДА** приоритетнее бренда и цены
- треска ≠ минтай ≠ лосось
- сёмга = лосось (тот же species)

#### BREADED_FLAG (Gate #4)
- В панировке ≠ без панировки
- в кляре = в панировке = темпура

#### Conditional Gates (5, 6)
- SKIN_FLAG применяется **только если у REF известен skin_flag**
- STATE применяется **только если у REF известен state**

---

## 10. Ранжирование (Sorting)

### 10.1 Порядок сортировки

1. `species_exact` — вид совпадает
2. `cut_exact` — разделка совпадает
3. `breaded_exact` — панировка совпадает
4. `skin_exact` — кожа совпадает
5. `state_exact` — состояние совпадает
6. `weight_score` — ближе по граммовке
7. `brand_match` — бренд совпадает
8. `country_match` — страна совпадает
9. `text_similarity` — текстовая похожесть
10. `price` ASC — цена по возрастанию

### 10.2 Weight Score
- Формула: `100 * (1 - weight_diff_pct)`
- weight_diff_pct = |ref_weight - cand_weight| / ref_weight
- Tolerance: ≤20%

---

## 11. API Response

### 11.1 Обязательные поля

```json
{
  "source": { ... },
  "strict_after_gates": [ ... ],
  "rejected_reasons": { ... },
  "npc_domain": "FISH_FILLET",
  "ruleset_version": "npc_fish_fillet_v1",
  "ref_parsed": {
    "npc_domain": "FISH_FILLET",
    "fish_species": "cod",
    "cut_type": "FILLET",
    "skin_flag": "skin_off",
    "breaded_flag": false,
    "state": "frozen",
    "uom": "kg",
    "net_weight_kg": 1.0
  },
  "ref_debug": {
    "ref_text_used": "...",
    "looks_like_fish_fillet": true,
    "is_blacklisted": false,
    "npc_domain": "FISH_FILLET",
    "fish_species": "cod",
    "cut_type": "FILLET",
    "ruleset_selected": "npc_fish_fillet_v1",
    "why_empty_strict": null
  },
  "debug_id": "abc123"
}
```

### 11.2 Candidate Item Fields

```json
{
  "id": "...",
  "name_raw": "...",
  "price": 750,
  "supplier_id": "...",
  "supplier_name": "...",
  "match_score": 295,
  "weight_score": 100,
  "unit_price_per_kg": 750,
  "net_weight_kg": 1.0,
  "npc_domain": "FISH_FILLET",
  "fish_species": "cod",
  "cut_type": "FILLET",
  "skin_flag": "skin_off",
  "passed_gates": ["FISH_FILLET_DOMAIN", "SPECIES", "CUT_TYPE", ...],
  "rank_features": { ... },
  "cand_parsed": { ... }
}
```

---

## 12. Примеры

### 12.1 Валидный match

**REF**: "Филе трески без кожи с/м 1кг"
**CAND**: "Треска филе б/к свежемороженое 1кг"

```
✓ DOMAIN: FISH_FILLET == FISH_FILLET
✓ SPECIES: cod == cod
✓ CUT_TYPE: FILLET == FILLET
✓ BREADED: false == false
✓ SKIN_FLAG: skin_off == skin_off
✓ STATE: frozen == frozen
✓ UOM: kg == kg
✓ BOX: false == false
✓ WEIGHT: 1.0kg == 1.0kg (0% diff)

RESULT: PASSED STRICT ✓
```

### 12.2 Rejected: CUT_TYPE mismatch

**REF**: "Филе трески без кожи с/м 1кг"
**CAND**: "Треска тушка с/м б/г 1кг"

```
✓ DOMAIN check...
✓ SPECIES: cod == cod
✗ CUT_TYPE: FILLET != WHOLE

RESULT: REJECTED (CUT_TYPE_MISMATCH:FILLET!=WHOLE)
```

### 12.3 Rejected: SPECIES mismatch

**REF**: "Филе трески без кожи с/м 1кг"
**CAND**: "Минтай филе б/к с/м 1кг"

```
✓ DOMAIN check...
✗ SPECIES: cod != pollock

RESULT: REJECTED (SPECIES_MISMATCH:cod!=pollock)
```

### 12.4 Rejected: BREADED mismatch

**REF**: "Филе минтая в панировке 500г"
**CAND**: "Минтай филе с/м 500г"

```
✓ DOMAIN check...
✓ SPECIES: pollock == pollock
✓ CUT_TYPE: FILLET == FILLET
✗ BREADED: true != false

RESULT: REJECTED (BREADED_MISMATCH:source_breaded_candidate_not)
```

---

## 13. Тестовые сценарии (Acceptance Criteria)

| # | Сценарий | Ожидаемый результат |
|---|----------|---------------------|
| 1 | REF: тушка → CAND: филе | REJECTED (REF not FISH_FILLET) |
| 2 | REF: филе → CAND: тушка | REJECTED (CUT_TYPE_MISMATCH) |
| 3 | REF: филе → CAND: стейк | REJECTED (CUT_TYPE_MISMATCH) |
| 4 | REF: в панировке → CAND: без | REJECTED (BREADED_MISMATCH) |
| 5 | REF: треска → CAND: минтай | REJECTED (SPECIES_MISMATCH) |
| 6 | REF: на коже → CAND: без кожи | REJECTED (SKIN_MISMATCH) |
| 7 | REF: с/м → CAND: охл | REJECTED (STATE_MISMATCH) |
| 8 | REF: кг → CAND: шт (без веса) | REJECTED (UOM_MISMATCH) |
| 9 | REF: 200г → CAND: 150г | PASSED (within ±20%) |
| 10 | Нет корректных аналогов | strict = [] |

---

## 14. Интеграция

### 14.1 Файлы
- **Module**: `/app/backend/bestprice_v12/npc_fish_fillet.py`
- **Routes**: `/app/backend/bestprice_v12/routes.py`
- **Tests**: `/app/backend/tests/test_fish_fillet_regression.py`

### 14.2 API Endpoint
```
GET /api/v12/item/{item_id}/alternatives
```

### 14.3 Приоритет доменов
1. FISH_FILLET (если REF похож на fish fillet)
2. SHRIMP (если REF похож на креветки)
3. Legacy v3 (остальное)

---

## 15. Changelog

### v1.0 (January 2026)
- Initial implementation
- 104 regression tests
- Full ZERO-TRASH compliance
- Integration with routes.py
