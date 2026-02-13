# Поставщик ↔ Ресторан: договор и пауза

## Эндпоинты

| Метод | Путь | Описание |
|-------|------|----------|
| GET | `/api/supplier/restaurant-documents` | Список ресторанов с документами и статусом договора |
| POST | `/api/supplier/accept-contract` | Принять договор (body: `{ restaurantId }`) |
| GET | `/api/supplier/restaurants` | Список «Мои рестораны» (только contract_accepted=true) |
| GET | `/api/suppliers/me/restaurants` | То же, альтернативный путь |
| PATCH | `/api/suppliers/me/restaurants/{restaurant_id}` | Пауза (body: `{ is_paused: true|false }`) |

## Модель

Коллекция `supplier_restaurant_settings`:
- `supplierId`, `restaurantId` — связь поставщик ↔ ресторан
- `contract_accepted` — договор принят (по умолчанию false)
- `is_paused` — пауза отгрузок (по умолчанию false)

## Блокировка заказов

При `is_paused=true` попытка создать заказ от ресторана к этому поставщику возвращает 403:
```
Поставщик поставил ваш ресторан на паузу. Отгрузка временно недоступна.
```

## Проверка

```bash
# 1. Запустить seed (Ресторан Вкусно уже с contract_accepted)
cd backend && python seed_data.py

# 2. Логин поставщиком (supplier1@example.com / password123)

# 3. GET Мои рестораны — должен быть «Ресторан Вкусно»
curl -H "Authorization: Bearer TOKEN" http://localhost:8000/api/supplier/restaurants

# 4. PATCH пауза
curl -X PATCH -H "Authorization: Bearer TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"is_paused":true}' \
  http://localhost:8000/api/suppliers/me/restaurants/RESTAURANT_ID
```
