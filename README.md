# BestPrice — B2B Matching Engine

B2B e-commerce платформа для оптимизации многопоставочных закупок в HoReCa.

## Локальная разработка (без Emergent)

Полная инструкция: **[LOCAL_DEV.md](./LOCAL_DEV.md)**

### Запуск backend

```bash
docker compose up -d                                    # MongoDB
cd backend && uvicorn server:app --reload --port 8000   # API
```

Фронтенд (опционально): `cd frontend && yarn start` → http://localhost:3000  
Backend: http://127.0.0.1:8000

### Инициализация поставщиков и Excel с доступами

Скрипт создаёт пользователей для входа в ЛК поставщиков, привязывает компании к пользователям, создаёт `supplier_settings` и выгружает Excel с доступами.

```bash
# из корня репозитория; читает backend/.env (MONGO_URL, DB_NAME)
python scripts/init_suppliers.py
```

После выполнения выводится путь к файлу и `✅ EXPORTED`.  
**Путь к Excel:** `_exports/supplier_accesses.xlsx`  
Колонки: supplier_email, password_plain, company_id, user_id, role, login_url, notes.

Доп. опции:
- `--dry-run` — не писать в БД и файл (нужен доступ к Mongo для списка компаний)
- `--base-url http://127.0.0.1:8000` — URL для колонки login_url в Excel

### Эталонный сценарий (реквизиты + 1/1/1/1)

Воспроизведение эталонного flow с полностью заполненными реквизитами:

```bash
ALLOW_DESTRUCTIVE=1 bash scripts/clean_slate_local.sh
bash scripts/run_backend.sh
bash scripts/run_frontend.sh
bash scripts/prod_minimal_e2e.sh --no-junk
```

Результат: 1 supplier, 1 restaurant (полные реквизиты + ЭДО/GUID), 1 link, 1 document.  
Доказательства: `evidence/REQUISITES_FLOW_PROOF.md`, `evidence/CONTRACT_SUPPLIERS_API_PROOF.txt`, `evidence/SUPPLIER_REQUISITES_API_PROOF.txt`.

### Проверка сценария (E2E)

Скрипт проверяет: наличие Excel, логин, GET/PUT настроек, загрузку и импорт прайса, отображение в «мои прайсы» и в каталоге поставщика. Backend должен быть запущен, `init_suppliers.py` уже выполнен (в Excel есть валидные пароли).

```bash
python scripts/verify_e2e.py
```

При успехе: `✅ ALL CHECKS PASSED` и exit code 0. При ошибке — сообщение и exit 1.  
Переменная окружения `VERIFY_BASE_URL` (по умолчанию `http://127.0.0.1:8000`) задаёт базовый URL API.

Зависимости для verify: `pip install openpyxl requests` (обычно уже есть в проекте).

**Проверка Romax прайс-листа (supplier price-list API):**  
`API_BASE_URL=http://127.0.0.1:8001 python scripts/verify_romax_import.py` — результат в `evidence/ROMAX_IMPORT_FIX_PROOF.txt`, exit 0/1.

**Восстановление пароля (без ручной настройки):**
- **Email:** ссылка `RESET LINK:` печатается в backend-логах
- **OTP по телефону:** по умолчанию SMS не нужен — OTP печатается в backend-логах как `OTP CODE: ###### (to +79213643475)`
- Для реального SMS: `SMS_PROVIDER=twilio`, `TWILIO_ACCOUNT_SID`, `TWILIO_AUTH_TOKEN`, `TWILIO_PHONE_FROM`

Тест phone reset: `./scripts/test_phone_reset_password.sh`  
Тест email reset: `./scripts/test_email_reset_password.sh`

### Примеры curl после init

Подставьте email и пароль из `_exports/supplier_accesses.xlsx`.

```bash
# логин
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email":"aifrut.1-00001@company.com","password":"YOUR_PASSWORD"}'

# настройки поставщика (подставьте Bearer TOKEN из ответа логина)
curl -s -H "Authorization: Bearer TOKEN" http://127.0.0.1:8000/api/supplier-settings/my

# мои прайс-листы
curl -s -H "Authorization: Bearer TOKEN" http://127.0.0.1:8000/api/price-lists/my
```