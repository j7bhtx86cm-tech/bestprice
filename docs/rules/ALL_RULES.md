# ALL RULES (v1)

Generated: 2026-02-20T18:17:13.110904+00:00

---

## 1. Ruleset versions

- **v1** | id=`6997f2fe3bac31cefafecdef` | created=2026-02-20T05:37:02.162000 | active=True
- **Archived_block_all** | id=`6997f1fffd5b4b179fa49d65` | created=2026-02-20T05:32:47.555000 | active=False
- **Ruleset v1** | id=`6997f04c247d93b0af8ca1ad` | created=2026-02-20T05:25:32.133000 | active=True

## 2. Global quality rules

- **INVALID_RANGE** | severity=INVALID | payload={"min_must_be_less_than_max": true}
- **JUNK_NAME** | severity=HIDDEN | payload={"min_len": 3, "digits_ratio_gt": 0.7, "min_letters": 1, "pure_number": true, "min_word_tokens": 1}
- **LOW_CATEGORY_CONFIDENCE** | severity=HIDDEN | payload={"ok_threshold": 0.85, "hidden_threshold": 0.6}
- **LOW_PARSE_CONFIDENCE** | severity=HIDDEN | payload={"threshold": 0.6}
- **MISSING_MUST_FIELDS** | severity=HIDDEN | payload={}
- **NEGATIVE_OR_ZERO_VALUES** | severity=INVALID | payload={"fields": ["weight_kg", "volume_ml", "pack_weight_kg", "piece_weight_g"]}
- **PIT_CONFLICT** | severity=INVALID | payload={"field": "pit_flag", "values": ["with_pit", "without_pit"]}
- **PRICE_NORMALIZATION_REQUIRED** | severity=INVALID | payload={}
- **PRICE_REQUIRED** | severity=INVALID | payload={}
- **RAW_BOILED_CONFLICT** | severity=INVALID | payload={"field": "processing_state", "values": ["raw", "boiled"]}
- **SKIN_CONFLICT** | severity=INVALID | payload={"field": "skin_flag", "values": ["skin_on", "skinless"]}
- **STATE_CONFLICT** | severity=INVALID | payload={"field": "state", "values": ["fresh", "chilled", "frozen"]}

## 3. Dictionaries (v1)

### category_dictionary_entries: 412 entries
  - {"category_code": "bakery", "keyword": "хлеб", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "хлеб"}
  - {"category_code": "bakery", "keyword": "багет", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "багет"}
  - {"category_code": "bakery", "keyword": "булочка", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "булочка"}
  - {"category_code": "bakery", "keyword": "лаваш", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "лаваш"}
  - {"category_code": "bakery", "keyword": "чиабатта", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "чиабатта"}
  - {"category_code": "bakery", "keyword": "круассан", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "круассан"}
  - {"category_code": "bakery", "keyword": "слойка", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "слойка"}
  - {"category_code": "bakery", "keyword": "батон", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "батон"}
  - {"category_code": "bakery", "keyword": "лепешка", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "лепешка"}
  - {"category_code": "bakery", "keyword": "булка", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "булка"}
  - {"category_code": "bakery", "keyword": "каравай", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "каравай"}
  - {"category_code": "bakery", "keyword": "сухарь", "type": "POSITIVE", "weight": 5, "scope": "BASE", "_key": "сухарь"}
  - {"category_code": "bakery", "keyword": "белый", "type": "POSITIVE", "weight": 2, "scope": "CONTEXT", "_key": "белый"}
  - {"category_code": "bakery", "keyword": "ржаной", "type": "POSITIVE", "weight": 2, "scope": "CONTEXT", "_key": "ржаной"}
  - {"category_code": "bakery", "keyword": "зерновой", "type": "POSITIVE", "weight": 2, "scope": "CONTEXT", "_key": "зерновой"}
  - ... and 397 more

### base_product_dictionary_entries: 606 entries
  - {"category_code": "bakery", "keyword": "багет", "type": "POSITIVE", "_key": "багет"}
  - {"category_code": "bakery", "keyword": "баранка", "type": "POSITIVE", "_key": "баранка"}
  - {"category_code": "bakery", "keyword": "батон", "type": "POSITIVE", "_key": "батон"}
  - {"category_code": "bakery", "keyword": "белый", "type": "POSITIVE", "_key": "белый"}
  - {"category_code": "bakery", "keyword": "бублик", "type": "POSITIVE", "_key": "бублик"}
  - {"category_code": "bakery", "keyword": "булка", "type": "POSITIVE", "_key": "булка"}
  - {"category_code": "bakery", "keyword": "булочка", "type": "POSITIVE", "_key": "булочка"}
  - {"category_code": "bakery", "keyword": "заморож", "type": "POSITIVE", "_key": "заморож"}
  - {"category_code": "bakery", "keyword": "зерновой", "type": "POSITIVE", "_key": "зерновой"}
  - {"category_code": "bakery", "keyword": "каравай", "type": "POSITIVE", "_key": "каравай"}
  - {"category_code": "bakery", "keyword": "кекс", "type": "POSITIVE", "_key": "кекс"}
  - {"category_code": "bakery", "keyword": "контейнер", "type": "NEGATIVE", "_key": "контейнер"}
  - {"category_code": "bakery", "keyword": "коробка", "type": "NEGATIVE", "_key": "коробка"}
  - {"category_code": "bakery", "keyword": "крендель", "type": "POSITIVE", "_key": "крендель"}
  - {"category_code": "bakery", "keyword": "круассан", "type": "POSITIVE", "_key": "круассан"}
  - ... and 485 more

### token_aliases: 46 entries
  - {"field": "cut", "raw": "филе", "canonical": "fillet", "_key": "филе"}
  - {"field": "cut", "raw": "fillet", "canonical": "fillet", "_key": "fillet"}
  - {"field": "cut", "raw": "стейк", "canonical": "steak", "_key": "стейк"}
  - {"field": "cut", "raw": "steak", "canonical": "steak", "_key": "steak"}
  - {"field": "cut", "raw": "тушка", "canonical": "whole", "_key": "тушка"}
  - {"field": "cut", "raw": "цел", "canonical": "whole", "_key": "цел"}
  - {"field": "cut", "raw": "whole", "canonical": "whole", "_key": "whole"}
  - {"field": "pit_flag", "raw": "без кост", "canonical": "without_pit", "_key": "без кост"}
  - {"field": "pit_flag", "raw": "без кости", "canonical": "without_pit", "_key": "без кости"}
  - {"field": "pit_flag", "raw": "without pit", "canonical": "without_pit", "_key": "without pit"}
  - {"field": "pit_flag", "raw": "с кост", "canonical": "with_pit", "_key": "с кост"}
  - {"field": "pit_flag", "raw": "с костью", "canonical": "with_pit", "_key": "с костью"}
  - {"field": "pit_flag", "raw": "with pit", "canonical": "with_pit", "_key": "with pit"}
  - {"field": "processing_state", "raw": "вар", "canonical": "boiled", "_key": "вар"}
  - {"field": "processing_state", "raw": "варен", "canonical": "boiled", "_key": "варен"}
  - ... and 31 more

## 4. Category summary (STRICT / SOFT)

STRICT categories require base_product (and often state/cut) to be parsed; otherwise item is HIDDEN (MISSING_MUST_FIELDS). SOFT categories allow base_product_unknown and do not hide for missing base_product.

| Category | base_product must_mode |
|----------|------------------------|
| bakery | NO |
| canned | NO |
| desserts | NO |
| drinks | NO |
| fish | ALWAYS |
| fresh_produce | ALWAYS |
| frozen_produce | ALWAYS |
| frozen_semi | NO |
| grocery | NO |
| meat | ALWAYS |
| poultry | ALWAYS |
| sausages | NO |
| seafood | ALWAYS |

- **STRICT (must identify product):** fish, fresh_produce, frozen_produce, meat, poultry, seafood

- **SOFT (unknown allowed):** grocery, canned, drinks, bakery, desserts, sausages, frozen_semi
