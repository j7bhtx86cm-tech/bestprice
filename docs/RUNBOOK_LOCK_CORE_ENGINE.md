# Runbook: восстановление состояния LOCK Core Engine (2026-02-22)

Восстановление кода и БД до зафиксированной версии «НЕ ПОТЕРЯЕМ».

## 3.1 Checkout кода

```bash
git fetch --all --tags
git checkout core-engine-lock-2026-02-22
```

## 3.2 Restore DB

Распаковать снимок и восстановить MongoDB (подставьте актуальный URI при необходимости):

```bash
tar -xzf artifacts/db_snapshots/test_database__core-engine-lock-2026-02-22.tgz -C /tmp
mongorestore --drop --uri="mongodb://localhost:27017/test_database" "/tmp/test_database__core-engine-lock-2026-02-22/test_database"
```

## 3.3 Verify / Smoke (должны быть зелёные)

```bash
python3 scripts/dev/hard_reset_backend_8001.py
python3 scripts/dev/ensure_backend_up.py

python3 scripts/core_engine_selfcheck_v1.py
python3 scripts/dev/checkout_smoke_curl.py
python3 scripts/dev/supplier_respond_flow_smoke_v1.py
python3 scripts/dev/customer_orders_flow_smoke_v1.py
```

## 3.4 Информация о снапшоте

- **Имя файла .tgz:** `test_database__core-engine-lock-2026-02-22.tgz`
- **Контрольная сумма:** см. файл `artifacts/db_snapshots/test_database__core-engine-lock-2026-02-22.sha256` (строка sha256).

Проверка после восстановления:

```bash
cat artifacts/db_snapshots/test_database__core-engine-lock-2026-02-22.sha256
shasum -a 256 -c artifacts/db_snapshots/test_database__core-engine-lock-2026-02-22.sha256
```
