# CORE ENGINE v1 — LOCK

**Дата:** 2026-02-21

**Напоминание:** каталог/логин (API v12) не трогаем.

**Версия (после коммита и тега):**
```bash
git describe --tags --always
git rev-parse HEAD
```

---

## Команды

**Selfcheck (одна команда проверки ядра):**
```bash
python3 scripts/core_engine_selfcheck_v1.py
```
- Запускает E2E, пишет лог в `artifacts/core_engine_selfcheck_v1.log`.
- **Требование:** последняя строка вывода = `✅ CORE_ENGINE_OK` (при успехе) или `❌ CORE_ENGINE_FAIL` (при провале).

**Pack check (проверка наличия lock-пака):**
```bash
python3 scripts/check_core_engine_lock_pack_v1.py
```
- **Требование:** последняя строка вывода = `CORE_ENGINE_PACK_OK` при наличии всех нужных файлов.

---

## Команда E2E (напрямую)

```bash
python3 scripts/e2e_import_pipeline_v1.py | tee artifacts/e2e_import_pipeline_v1.log
```

**Критерии приёмки ядра:**
- финальная строка `✅ E2E_PIPELINE_OK`
- наличие `pipeline_run_id` и `status=OK`
- counts > 0 для `masters`, `master_links`, `master_market_snapshot_current`

**Правило изменения:**  
Любые правки pipeline допускаются только если до и после правок E2E зелёный. Если E2E красный — правки запрещены.

---

## Как поднять backend (dev)

Работает из любой директории (в т.ч. из `backend/`). Не нужно вручную делать `cd backend && ...` — скрипты сами находят корень репо через `git rev-parse --show-toplevel` и выставляют нужный cwd.

**Поднять backend на порту 8001 (с освобождением порта и проверкой /docs → 200):**
```bash
python3 scripts/dev/ensure_backend_up.py
```
- Ожидаемые строки в выводе: `PORT_8001_CLEARED_OK`, затем `BACKEND_UP_OK`.
- PID сохраняется в `artifacts/dev_backend_8001.pid`, лог — в `artifacts/dev_backend_8001.log`.

**Остановить backend на 8001:**
```bash
python3 scripts/dev/stop_backend_8001.py
```
- Ожидаемая последняя строка: `BACKEND_STOPPED_OK`.

---

## Восстановление dev-логинов

Чтобы логин в UI работал для Integrita / Romax / Restaurant (и smoke печатал SUPPLIER_LOGIN_OK и RESTAURANT_LOGIN_OK):

1. `python3 scripts/dev/ensure_auth_fixtures.py`
2. `python3 scripts/dev/auth_smoke_v2.py`
3. UI: `/supplier/auth` и обычный логин (или страница входа ресторана).

---

## AUTO_PIPELINE_AFTER_IMPORT

- **Как выключить:** `AUTO_PIPELINE_AFTER_IMPORT=false`
- **Как включить:** `AUTO_PIPELINE_AFTER_IMPORT=true` (по умолчанию, если переменная не задана — pipeline запускается)
