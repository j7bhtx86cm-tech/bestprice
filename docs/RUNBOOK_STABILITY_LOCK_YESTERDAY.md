# Runbook: восстановление и фиксация «вчерашней» стабильной версии

## Стабильный коммит (после фикса 500 каталога)

- **Тег:** `stability-lock-2026-02-20` (базовая точка)
- **Фикс 500:** GET /api/v12/catalog возвращает 200; причина 500 — несериализуемые типы в ответе (ObjectId/datetime/Decimal); фикс: _json_sanitize в bestprice_v12/routes.py, глобальный 500 handler с trace_id в server.py.
- **Ветка:** `restore/yesterday-stable` (или текущая после фикса)

## Команда smoke 10x

Из корня репозитория, с заданными учётными данными customer (пароль в лог не пишется):

```bash
API_BASE_URL=http://127.0.0.1:8001 CUSTOMER_EMAIL=<email> CUSTOMER_PASSWORD='<password>' python3 scripts/run_smoke_10x.py
```

Один прогон (логин + /auth/me + GET /api/v12/catalog×3):

```bash
API_BASE_URL=... CUSTOMER_EMAIL=... CUSTOMER_PASSWORD='...' python3 scripts/smoke_customer_catalog.py
```

## Где лежит лог

- **Файл:** `artifacts/smoke_10x_yesterday_stable.log`
- Итог в конце файла: `SMOKE_10X_OK` или `SMOKE_10X_FAIL` с номерами попыток и причинами.

## Правило стабильности

**Каталог и логин не менять без:** нового бага + воспроизведения + trace_id (или эквивалентного идентификатора запроса/сессии для разбора инцидента).

## Тег фиксации

- **Тег:** `yesterday-stable-locked-2026-02-21` (на коммит ветки `restore/yesterday-stable`)
