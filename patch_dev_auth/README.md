# DEV Auth Bypass — восстановление доступа без пароля (локально)

## Описание

Позволяет войти в кабинет **поставщика** и **ресторана** без пароля, только в DEV/LOCAL окружении.

- Backend: endpoint `POST /api/dev/login` (404 в проде)
- Frontend: кнопки «DEV: Войти как поставщик» / «DEV: Войти как ресторан» на `/auth`

## ENV-флаги

| Переменная | Где | Значение |
|------------|-----|----------|
| `DEV_AUTH_BYPASS` | backend/.env | `1` |
| `REACT_APP_DEV_AUTH_BYPASS` | frontend/.env | `1` |

## Шаги настройки

### 1. Backend

В `backend/.env` (или создайте из `.env.example`):
```env
DEV_AUTH_BYPASS=1
```
Если `.env` нет — скопируйте `backend/.env.example` в `backend/.env` и добавьте строку выше.

### 2. Frontend

В `frontend/.env`:
```env
REACT_APP_DEV_AUTH_BYPASS=1
REACT_APP_BACKEND_URL=http://localhost:8000
```

### 3. Применение изменений

**Вариант A — полный патч (если подходит текущее состояние репо):**
```bash
cd /path/to/bestprice
git apply patch_dev_auth/dev_auth.patch
```

**Вариант B — вручную:**
- Скопировать `patch_dev_auth/frontend/src/context/AuthContext.js` → `frontend/src/context/`
- Скопировать `patch_dev_auth/frontend/src/pages/AuthPage.js` → `frontend/src/pages/`
- В `backend/server.py` добавить блок DEV AUTH (см. `server_dev_login_snippet.py` перед `@api_router.post("/auth/login")`)

### 4. Запуск

```bash
# Backend
cd backend
uvicorn server:app --reload --host 127.0.0.1 --port 8000

# Frontend (в другом терминале)
cd frontend
npm start
```

## Использование

1. Открыть http://localhost:3000/auth
2. Внизу появятся кнопки:
   - **DEV: Войти как поставщик** → `/supplier/price-list`
   - **DEV: Войти как ресторан** → `/customer` (каталог)
3. Нажать нужную кнопку — вход без пароля.

## Логика

- Если в БД есть пользователь с нужной ролью — используется он.
- Если нет — создаётся минимальный DEV-пользователь и компания.
- В production (или без флагов) endpoint возвращает 404, кнопок нет.

## Проверка

- С флагами: кнопки видны, вход работает.
- Без флагов / в production: кнопок нет, `POST /api/dev/login` → 404.
