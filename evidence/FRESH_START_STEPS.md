# Phase 2: Manual creation (UI only)

**Required credentials for no-junk E2E:** use these exact values so `collect_acl_proof --use-existing` works.

- Supplier: `supplier@example.com` / `TestPass123!`
- Restaurant: `restaurant@example.com` / `TestPass123!`

---

## Prerequisites

1. Clean slate done: `ALLOW_DESTRUCTIVE=1 bash scripts/clean_slate_local.sh`
2. Backend: `bash scripts/run_backend.sh` (8001)
3. Frontend: `bash scripts/run_frontend.sh` (3000)

---

## Step 1: Create supplier

1. Open http://localhost:3000
2. Go to supplier auth (e.g. /supplier/auth or "Я поставщик" → регистрация)
3. Register:
   - **Email**: `supplier@example.com`
   - **Password**: `TestPass123!`
   - **ИНН**: `7707083893`
   - **Название**: `ООО Поставщик Продуктов`
   - **ОГРН**: `1027700132195`
   - **Адреса, телефон, контакты**: any valid
   - **Согласие**: ✓
4. **Screenshot**: `evidence/screens/fresh_start/02_supplier_registered.png`

---

## Step 2: Create restaurant

1. Open new incognito window or log out
2. Go to customer auth (e.g. /customer/auth)
3. Register:
   - **Email**: `restaurant@example.com`
   - **Password**: `TestPass123!`
   - **ИНН**: `7701234567`
   - **Название**: `ООО Ресторан Вкусно`
   - **ОГРН**: `1027701234567`
   - **Адреса, контакты**: any valid
   - **Согласие**: ✓
4. **Screenshot**: `evidence/screens/fresh_start/03_restaurant_registered.png`

---

## Step 3: Link and verify order

1. Log in as **supplier**
2. Go to "Документы от ресторанов"
3. Accept contract for the new restaurant
4. New restaurant must be at the top (newest first)

---

## Step 4: Upload document (restaurant)

1. Log in as **restaurant**
2. Go to Documents / Мои документы
3. **Screenshot**: `evidence/screens/docs_flow/01_restaurant_upload_page.png`
4. Upload a PDF
5. **Screenshot**: `evidence/screens/docs_flow/02_doc_uploaded_success.png`

---

## Step 5: Verify supplier sees document

1. Log in as **supplier**
2. Go to "Документы от ресторанов"
3. **Screenshot**: `evidence/screens/docs_flow/03_supplier_documents_list_sorted.png` (new restaurant on top)
4. **Screenshot**: `evidence/screens/docs_flow/04_supplier_sees_doc.png` (document visible)

---

## Then run

```bash
# Phase 3–4: ACL + No junk
python3 scripts/collect_acl_proof.py --use-existing
python3 scripts/verify_no_junk.py

# Phase 5: Minimal E2E
bash scripts/prod_minimal_e2e.sh --no-junk
```
