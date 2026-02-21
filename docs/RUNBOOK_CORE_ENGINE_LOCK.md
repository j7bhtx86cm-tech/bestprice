# CORE ENGINE v1 — LOCK

**Дата:** 2026-02-21

**Версия (после коммита и тега):**
```bash
git describe --tags --always
git rev-parse HEAD
```

**Команда E2E:**
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

## AUTO_PIPELINE_AFTER_IMPORT

- **Как выключить:** `AUTO_PIPELINE_AFTER_IMPORT=false`
- **Как включить:** `AUTO_PIPELINE_AFTER_IMPORT=true` (по умолчанию, если переменная не задана — pipeline запускается)
