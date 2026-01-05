# ТЕХНИЧЕСКОЕ ЗАДАНИЕ: "BestPrice v12 — Полная коррекция матчинга, единиц, фасовок, total_cost, product_core, аудит"

## 0) Контекст и цель

Сейчас система:
- выдаёт абсурдные совпадения и/или завышенные проценты,
- неправильно учитывает вес/объём/шт, из-за чего "1 кг" может отображаться как "5 г" и считаться некорректно,
- из-за широкой классификации (super_class) матчится "фарш" на "суповой набор", "пшеничная" на "ржаную" и т.п.

**Цель:** сделать поиск/матчинг физически корректным, предсказуемым и стабильным:
- 0 абсурдных матчей,
- корректный расчёт количества упаковок и total_cost,
- корректный match_percent (0..100) с сильным штрафом за плохую фасовку,
- узкая классификация через product_core,
- диагностика и аудит на всём каталоге.

---

## 1) Ограничения (обязательные)

1. **Single Source of Truth:** использовать ТОЛЬКО `BESTPRICE_IDEAL_MASTER_v12_PATCH_FULL.xlsx` для правил (бренды/алиасы/категории/ядра/pack rules).
2. **Прайсы не трогать:** ничего не удалять/не перезаливать прайсы. Работаем поверх текущей БД.
3. **Поиск не должен падать:** никаких 500, только `not_found` с `reason_code`.
4. **Guards должны быть включены** и применяться к кандидату (candidate), а не к reference.

---

## 2) P0 (КРИТИЧНО СРОЧНО): единицы, фасовка, packs_needed, total_cost, запрет физически невозможных матчей

### 2.1 Нормализация единиц измерения

Для reference и candidate всегда вычислять:
- **unit_type:** `WEIGHT | VOLUME | PIECE | UNKNOWN`
- **base_qty:** количество в базовой единице:
  - WEIGHT → grams
  - VOLUME → milliliters
  - PIECE → pieces

**Парсинг из текста должен понимать:** 
кг/г, л/мл, шт/pcs, а также типовые форматы: `5 г`, `1кг`, `0.5 кг`, `10x200г`, `200 шт x 5 г`, `~5кг`, `300-400г`, `4/5`, `4-5кг`.

### 2.2 Правильный расчёт количества упаковок и total_cost

При выборе победителя использовать только стоимость закрытия потребности:

```python
packs_needed = ceil(required_base_qty / offer_pack_base_qty)
total_cost = packs_needed * offer_price
```

**Важно:**
- "5 г" — это WEIGHT, а не pieces. Никаких ошибок типа "5 г = 1 штука".
- Если `offer_pack_base_qty` неизвестен → не резать жёстко, а:
  - присваивать `pack_status=UNKNOWN`,
  - применять штраф в ранжировании,
  - но не позволять кандидату с неизвестной фасовкой победить кандидата с известной фасовкой при прочих равных.

### 2.3 UNIT_MISMATCH rejection (только реальная несовместимость)

Запрещаем матчинг, если unit_type несовместимы:
- WEIGHT ↔ VOLUME → REJECT (если нет явной конверсии по плотности, а её нет)
- WEIGHT ↔ PIECE → REJECT
- VOLUME ↔ PIECE → REJECT
- UNKNOWN → допускается только при отсутствии других кандидатов и с большим штрафом + лог reason_code.

### 2.4 Отображение результата в UI/ответе (обязательное)

В ответе API (и в toast) добавить:
- `selected_pack_base_qty` (например 5g)
- `required_base_qty` (например 1000g)
- `packs_needed` (например 200)
- `computed_total_cost` (например 1188₽)
- строка пояснения: "200 × 5 г = 1000 г"

**Без этого пользователь будет видеть "5 г" и считать, что ошибка, даже если расчёт верный.**

---

## 3) P0: match_percent должен отражать смысл (и фасовку), а не "красивую цифру"

### 3.1 match_percent 0..100 (строго)

Всегда clamp 0..100.

### 3.2 Новая логика match_percent (минимально достаточная)

Сделать match_percent зависимым от:
- **core_match / точности категории** (см. P1 product_core) — базово +60
- **anchors / guards** — +20
- **pack_fit** — +10 (только если фасовка близка; если packs_needed очень большой → штраф)
- **brand** — +10 (только если brand_critical=ON и совпало)

**Штрафы:**
- Если `packs_needed` слишком велик (пример: 1кг из 5г → 200 упаковок) → сильный штраф к match_percent, чтобы это не могло стать 90–100%.
- Если pack UNKNOWN → штраф.
- Если category fallback (из super_class без core) → штраф.

---

## 4) P1: Product Core (узкая классификация) + строгий матчинг

### 4.1 Ввести product_core (или product_core_id) в supplier_items

**Примеры:**
- `meat.beef.ground` (фарш)
- `meat.beef.soup_set` (суповой набор)
- `staples.flour.wheat`
- `staples.flour.rye`
- `condiments.wasabi`
- `condiments.salt`
- и т.д.

### 4.2 Backfill (без прайсов)

Скрипт массового enrichment для всех active supplier_items:
- заполнить `super_class` (если пусто/other),
- заполнить `product_core`,
- заполнить `pack_base_qty` и `unit_type`,
- заполнить `brand_id` (если возможно из текста/алиасов).

### 4.3 Правило матчинга

- Если у reference определён `product_core` → искать ТОЛЬКО внутри этого core.
- Если core не определён → НЕ подбирать "наугад", а:
  - пробовать ограниченный fallback (super_class),
  - при низкой уверенности → `not_found` + `reason_code CORE_NOT_DETECTED`.

**Это лечит:** "фарш → суповой набор", "пшеничная → ржаная", "васаби → соль".

---

## 5) Brand logic (обязательные правила)

- **brand_critical=OFF:** бренд полностью игнорируется (никаких "мягких предпочтений").
- **brand_critical=ON:** строгое совпадение:
  - либо по `brand_id`,
  - либо по извлечению бренда из текста (алиасы),
  - иначе `not_found` с `reason_code BRAND_REQUIRED_NOT_FOUND`.

---

## 6) Guards (обязательная проверка)

- Guards применяются к `candidate.name_raw`:
  - `FORBIDDEN_TOKENS` → reject
  - `REQUIRED_ANCHORS` → reject
- Guards выполняются **до ранжирования**.
- Guards НЕ должны быть "узкими только для 10 категорий": расширить минимум на ключевые проблемные группы (мясо/мука/специи/рыба/сыр).

---

## 7) Диагностика и устойчивость

### 7.1 Debug/version

Должен существовать `/api/debug/version`:
- build_sha, build_time, env
- db_name, collection_name
- sot_file
- guards_enabled (true/false)

### 7.2 Трассировка запроса

Каждый поиск возвращает `request_id` и печатает `SEARCH_SUMMARY` одной строкой JSON:
- counts по стадиям:
  - total
  - after_super_class
  - after_guards
  - after_brand
  - after_unit_filter
  - after_pack
  - finalists
- selected_id, packs_needed, total_cost, match_percent
- outcome, reason_code

### 7.3 Никаких падений

Любая ошибка → `status=not_found` + `reason_code`, лог SAFE.

---

## 8) Batch Audit (обязательное для "идеальной системы")

Сделать job, который прогоняет все active supplier_items и генерирует отчёты:

**Папка:** `/app/backend/audits/<timestamp>/`

**Файлы:**
1. `audit_summary.json`
2. `supplier_items_audit.csv` (pack/unit/core/brand coverage + issue_codes)
3. `matching_audit.csv` (результаты симуляции)
4. `bad_matches_top500.csv`
5. `unit_mismatch_report.csv` (НОВЫЙ: все случаи несовместимых единиц)
6. `pack_outlier_report.csv` (НОВЫЙ: где packs_needed > N, например >20)

---

## 9) Acceptance Criteria (жёсткие)

1. **НЕТ случаев:** "1 кг → 5 г" без пересчёта количества упаковок.
   - Либо корректно: `packs_needed=200` и `total_cost` правильный,
   - либо `not_found` (если unit mismatch/нет данных).

2. **match_percent никогда не завышен** при огромной разнице фасовки.

3. **"васаби → соль", "пшеничная → ржаная", "фарш → суповой набор" невозможны** (либо правильный товар, либо not_found).

4. **brand_critical=OFF** реально игнорирует бренд, **brand_critical=ON** строго требует бренд.

5. **batch audit** формируется без падений, `bad_matches` → 0, причины NOT_FOUND прозрачны.

---

## 10) Что НЕ делать на этом этапе

- Не менять прайс-импорт.
- Не ломать UI (только добавить нужные поля/пояснение packs_needed).
- Не "ослаблять" guards ради покрытия.

---

## Примечание по файлу master

Файл `BESTPRICE_IDEAL_MASTER_v12_PATCH_FULL.xlsx` должен быть в `/app/backend/`.
Если в новом форке его нет — запросить у пользователя.
