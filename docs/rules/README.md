# ALL RULES pack (v1)

Один артефакт «все правила»: человекочитаемый и машиночитаемый снимок правил из MongoDB.

## Содержимое

- **ALL_RULES.md** — полный текст от первого до последнего: ruleset versions, global quality rules, словари (category_dictionary_entries, base_product, token_aliases, seed_dict_rules, brand_aliases), сводка STRICT/SOFT по категориям.
- **ALL_RULES.json** — те же данные в JSON для автогенерации UI/документации.

Источник данных: **MongoDB** (коллекции rulesets, ruleset_versions, global_quality_rules, словари). Файл `docs/artifacts/artifacts_all_category_rules.docx` — приложение/витрина, не единственный источник.

## Как обновить одной командой

Из корня репозитория:

```bash
python3 scripts/build_all_rules_doc_v1.py
```

Требуется доступ к Mongo (переменные `MONGO_URL`, `DB_NAME` или `backend/.env`). Запись в БД не выполняется (read-only).

## Проверка пакета

```bash
python3 scripts/check_all_rules_pack_v1.py
```

Проверяет наличие файлов, секции в ALL_RULES.md, валидность и ключи ALL_RULES.json. Успех: строка `ALL_RULES_CHECK_OK`.

## Полный экспорт (zip)

Для полного дампа правил и словарей в zip:

```bash
python3 scripts/export_all_rulesets_v1.py
```

Архив создаётся в `artifacts/rulesets_export_<date>.zip`.
