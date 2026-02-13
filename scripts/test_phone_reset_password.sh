#!/bin/bash
# E2E тест: Phone OTP reset password → Login
# Запуск: из корня репозитория, backend должен быть запущен, seed_data.py выполнен
# Телефон supplier1: +7 921 364 34 75

set -e
BASE_URL="${VERIFY_BASE_URL:-http://127.0.0.1:8000}"
PHONE="+79213643475"
NEW_PASS="newpass789"
EMAIL="supplier1@example.com"

echo "1. POST /api/auth/phone/request-otp..."
curl -s -X POST "${BASE_URL}/api/auth/phone/request-otp" \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"${PHONE}\",\"role\":\"supplier\"}"
echo ""
echo ""

echo "2. Проверьте логи backend — скопируйте OTP (6 цифр):"
echo "   OTP CODE: 123456 (to +79213643475)"
echo ""
read -p "Введите OTP из логов: " OTP

if [ -z "$OTP" ]; then
  echo "OTP не задан. Выход."
  exit 1
fi

echo ""
echo "3. POST /api/auth/phone/reset-password..."
curl -s -X POST "${BASE_URL}/api/auth/phone/reset-password" \
  -H "Content-Type: application/json" \
  -d "{\"phone\":\"${PHONE}\",\"role\":\"supplier\",\"otp\":\"${OTP}\",\"new_password\":\"${NEW_PASS}\"}"
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
  echo "✅ ALL CHECKS PASSED: phone OTP reset → login успешен"
else
  echo ""
  echo "❌ Login с новым паролем не удался"
  exit 1
fi
