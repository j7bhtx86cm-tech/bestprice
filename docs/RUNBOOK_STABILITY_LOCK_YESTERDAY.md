# Runbook: вчерашняя стабильная точка + фикс 500 каталога

## Зафиксированный тег/коммит

- **Тег:** `stability-lock-2026-02-20`
- **Коммит:** `f07f768` (вчерашняя стабильная точка)
- **Ветка:** `restore/yesterday-stable` (создана от тега)
- **Фикс:** GET /api/v12/catalog не даёт 500 — ответ сериализуется через _json_sanitize (ObjectId/datetime/Decimal → JSON-safe).

## Как запустить smoke 10x

Из корня репозитория (пароль/токен в лог не пишутся):

```bash
API_BASE_URL=http://127.0.0.1:8001 CUSTOMER_EMAIL="<email>" CUSTOMER_PASSWORD="<password>" python3 scripts/run_smoke_10x.py
```

Требуется: backend на 8001, валидные учётные данные customer (например из `backend/.env` или после init_suppliers/seed).

## Правило

**Каталог и логин НЕ трогаем без воспроизведения бага и trace_id** (или эквивалентного идентификатора запроса для разбора).
