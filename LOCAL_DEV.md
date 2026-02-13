# BestPrice — локальная разработка без Emergent

Полностью автономный запуск и тестирование проекта на своей машине.

---

## Требования

- **Python 3.10+**
- **Node.js 18+** и **yarn**
- **Docker** (для MongoDB) или установленный MongoDB локально
- **Git**

---

## 1. MongoDB

### Вариант A: Docker

```bash
docker compose up -d
```

MongoDB будет доступен на `localhost:27017`.

### Вариант B: Локальная установка

Установите MongoDB и запустите сервис. Убедитесь, что он слушает порт 27017.

---

## 2. Backend (FastAPI)

```bash
cd backend

# Виртуальное окружение
python -m venv venv
source venv/bin/activate   # Linux/macOS
# или: venv\Scripts\activate  # Windows

# Зависимости
pip install -r requirements.txt

# Конфиг (если нет .env — скопируйте из .env.example)
# cp .env.example .env

# Запуск сервера
uvicorn server:app --reload --host 0.0.0.0 --port 8000
```

API: http://localhost:8000  
Docs: http://localhost:8000/docs

### Первичные данные (опционально)

```bash
# Создать тестовые аккаунты
python create_test_accounts.py

# Или загрузить seed data
python seed_data.py
```

---

## 3. Frontend (React)

```bash
cd frontend

# Зависимости
yarn install

# Настроить backend URL для локальной разработки
# В .env установите:
# REACT_APP_BACKEND_URL=http://localhost:8000
```

Создайте или обновите `frontend/.env`:

```
REACT_APP_BACKEND_URL=http://localhost:8000
REACT_APP_ENABLE_VISUAL_EDITS=false
ENABLE_HEALTH_CHECK=false
```

```bash
# Запуск dev-сервера
yarn start
```

Frontend: http://localhost:3000

---

## 4. Тестовые аккаунты

| Роль       | Email                  | Пароль       |
|-----------|------------------------|--------------|
| Поставщик | supplier@bestprice.ru  | supplier123  |
| Ресторан  | restaurant@bestprice.ru| restaurant123|

---

## 5. Тестирование

### Backend (pytest)

```bash
cd backend
pytest tests/ -v
```

Основные тесты:

- `tests/test_shrimp_v1_zero_trash.py` — SHRIMP matching
- `tests/test_fish_fillet_regression.py` — FISH_FILLET matching
- `tests/test_npc_matching_v9.py` — NPC matching v9
- `tests/test_integration_alternatives.py` — API alternatives

### Правила валидации

```bash
python rules_validator.py
```

---

## 6. Emergent vs локальная версия

| Компонент            | Emergent                    | Локально                      |
|----------------------|-----------------------------|-------------------------------|
| Backend              | Emergent cloud              | `uvicorn server:app`          |
| Frontend             | Emergent preview            | `yarn start`                  |
| MongoDB              | Emergent-managed            | Docker / локальный MongoDB    |
| Visual edits         | Включены в Emergent UI      | Выключены (`false` в .env)    |
| Health check plugin  | Используется в K8s          | Выключен (`false` в .env)     |

Плагины Emergent (`plugins/visual-edits`, `plugins/health-check`) по умолчанию выключены. Проект полностью работает без них.

---

## 7. Структура запуска

```
Терминал 1:  docker compose up -d          # MongoDB
Терминал 2:  cd backend && uvicorn server:app --reload --port 8000
Терминал 3:  cd frontend && yarn start     # React на :3000
```

После этого:

- **Каталог ресторана:** http://localhost:3000/customer/catalog
- **Панель поставщика:** http://localhost:3000/supplier

---

## 8. Устранение неполадок

**MongoDB connection refused**  
Проверьте, что MongoDB запущен (`docker compose ps` или `brew services list`).

**CORS errors**  
В `backend/.env` добавьте: `CORS_ORIGINS=http://localhost:3000`

**Frontend не видит API**  
Убедитесь, что `REACT_APP_BACKEND_URL=http://localhost:8000` в `frontend/.env`.

**ImportError: unit_normalizer / rules_validator**  
Запускайте команды из директории `backend` (текущая директория должна быть backend).
