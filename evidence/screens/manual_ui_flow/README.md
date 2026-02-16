# Manual UI Flow Screenshots

Для реальных скринов:
- вручную в браузере после воспроизведения сценария (см. ниже)
- или `playwright install chromium` + доработать `scripts/manual_ui_flow_playwright.py`

## Воспроизведение перед скриншотами

```bash
ALLOW_DESTRUCTIVE=1 bash scripts/clean_slate_local.sh
bash scripts/run_backend.sh
bash scripts/run_frontend.sh
bash scripts/prod_minimal_e2e.sh --no-junk
```

Логин: supplier@example.com / restaurant@example.com, пароль: TestPass123!

## Файлы и шаги захвата

- **05_supplier_preview_requisites.png** — Страница /supplier/documents. Войти как поставщик. На карточке ресторана видны 4 поля preview: Название, ИНН, Телефон, Email (с данными или —).

- **06_supplier_full_requisites_expanded.png** — Та же страница. Кликнуть синюю кнопку «Показать реквизиты». Виден раскрытый full-блок: юр. название, ИНН, ОГРН, адреса, Номер ЭДО, GUID, контакты, адреса доставки.

- **07_supplier_documents_clickable.png** — Страница /supplier/documents. В блоке «Документы» видно кнопки документов (без иконки «глаз» и без даты). Каждая строка — кликабельная кнопка.

- **08_customer_contract_suppliers.png** — Страница /customer/documents. Войти как ресторан. Блок «Статус договоров с поставщиками» показывает фактических поставщиков из системы (E2E Supplier Test) и статус «Принят» или «Ожидание».
