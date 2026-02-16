# Requisites Flow Proof

## Reproduction chain

```bash
# 1. Clean slate (destructive)
ALLOW_DESTRUCTIVE=1 bash scripts/clean_slate_local.sh

# 2. Start backend
bash scripts/run_backend.sh

# 3. Start frontend (optional for API proofs)
bash scripts/run_frontend.sh

# 4. Bootstrap + verify (creates 1/1/1/1 with full requisites, 1 doc)
bash scripts/prod_minimal_e2e.sh --no-junk
```

## Bootstrap creates

- **1 supplier**: supplier@example.com, company "E2E Supplier Test"
- **1 restaurant**: restaurant@example.com, company "E2E Restaurant Test" with full requisites:
  - companyName, inn, ogrn, legalAddress, actualAddress, phone, email
  - contactPersonName, contactPersonPosition, contactPersonPhone
  - deliveryAddresses
  - edoNumber: EDO-REF-001, guid: guid-reference-flow-001
- **1 link**: supplier ↔ restaurant (contract accepted)
- **1 document**: type "Договор"

## Supplier UI (supplier/documents)

- **4 fields preview** (always visible): Название, ИНН, Телефон, Email (or "—" if empty)
- **Blue button** "Показать реквизиты" expands full block
- **Full block** includes: Юр. название, ИНН, ОГРН, адреса, Номер ЭДО, GUID, контакты
- **Documents**: clickable buttons, no eye icon, no date

## Customer UI (customer/documents)

- **Статус договоров с поставщиками**: list from GET /api/customer/contract-suppliers
- Only real suppliers (companies type=supplier) in DB
- Correct status (accepted/pending) per supplier

## Verify

- `verify_no_junk.py`: 1 supplier, 1 restaurant, 1 link, 1 document, 2 users
- `verify_contract_suppliers_match_companies.py`: endpoint ⊆ companies
- `collect_requisites_proof.py`: preview + full in API

## Auto-link (отдельная проверка)

Новый поставщик автоматически привязывается ко всем ресторанам (supplier_restaurant_settings, status pending).

```bash
bash scripts/prod_auto_link_check.sh
```

Доказательство: `evidence/AUTO_LINK_NEW_SUPPLIER_PROOF.txt`
