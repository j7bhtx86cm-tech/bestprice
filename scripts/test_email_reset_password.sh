#!/bin/bash
# E2E тест: Email reset password → Login
# Запуск: из корня репозитория, backend должен быть запущен, seed_data.py выполнен
# supplier1@example.com

set -e
BASE_URL="${VERIFY_BASE_URL:-http://127.0.0.1:8000}"
EMAIL="supplier1@example.com"
NEW_PASS="newpass456"

echo "1. POST /api/auth/forgot-password..."
curl -s -X POST "${BASE_URL}/api/auth/forgot-password" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"role\":\"supplier\"}"
echo ""
echo ""

echo "2. Проверьте логи backend — скопируйте token из ссылки:"
echo "   RESET LINK: http://localhost:3000/supplier/reset-password?token=XXXXX"
echo ""
read -p "Введите token (значение после token=): " TOKEN

if [ -z "$TOKEN" ]; then
  echo "Token не задан. Выход."
  exit 1
fi

echo ""
echo "3. POST /api/auth/reset-password..."
curl -s -X POST "${BASE_URL}/api/auth/reset-password" \
  -H "Content-Type: application/json" \
  -d "{\"token\":\"${TOKEN}\",\"newPassword\":\"${NEW_PASS}\"}"
echo ""
echo ""

echo "4. Login с новым паролем..."
LOGIN=$(curl -s -X POST "${BASE_URL}/api/auth/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"${EMAIL}\",\"password\":\"${NEW_PASS}\"}")
echo "$LOGIN" | head -c 300
echo ""
if echo "$LOGIN" | grep -q "access_token"; then
  echo ""
  echo "✅ ALL CHECKS PASSED: email reset → login успешен"
else
  echo ""
  echo "❌ Login с новым паролем не удался"
  exit 1
fi
