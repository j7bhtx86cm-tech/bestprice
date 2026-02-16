# Manual UI Flow Proof

## 1. Ссылки на скрины

| Шаг | Файл | Статус |
|-----|------|--------|
| 1 | evidence/screens/manual_ui_flow/01_ports_ok.png | Реальный (frontend 3000) |
| 1 | evidence/screens/manual_ui_flow/01_ports_api.png | Реальный (backend 8001/docs) |
| 2 | evidence/screens/manual_ui_flow/02_supplier_registered.png | Требует ручной захват* |
| 3 | evidence/screens/manual_ui_flow/03_restaurant_registered.png | Требует ручной захват* |
| 4 | evidence/screens/manual_ui_flow/04_restaurant_uploaded_doc.png | Требует ручной захват* |

\* Playwright: React app не рендерится в headless (см. evidence/PLAYWRIGHT_ERROR_LOG.txt). Захватить вручную в браузере.

## 2. Команды проверки

```bash
# No junk
python3 scripts/verify_no_junk.py

# ACL proof (использует supplier@, restaurant@ из API)
SUPPLIER_EMAIL=e2e_supplier@example.com RESTAURANT_EMAIL=e2e_restaurant@example.com \
  SUPPLIER_PASSWORD=TestPass123! RESTAURANT_PASSWORD=TestPass123! \
  python3 scripts/collect_acl_proof.py --use-existing
```

## 3. Результаты

**verify_no_junk.py** — PASS, exactly 1/1/1/1:
- suppliers: 1
- restaurants: 1
- links: 1
- documents: 1
- users: 2

**ACL_PROOF.txt** — 200/403/403:
- Linked supplier: 200
- No token: 403
- Unlinked supplier: 403

## 4. Playwright

Playwright blocked — см. evidence/PLAYWRIGHT_ERROR_LOG.txt. Для авто-скринов: запустить `python3 scripts/manual_ui_flow_playwright.py` или `capture_screenshots_after_api.py` вручную в терминале (не в Cursor sandbox).
