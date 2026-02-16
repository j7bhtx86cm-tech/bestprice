# UI Download Proof

## Implementation

- **Component:** `frontend/src/pages/supplier/SupplierDocuments.js`
- **Button:** Eye icon (Просмотр / Скачать) next to each document
- **Behavior:**
  - `fetch GET /api/documents/{id}/download` with `Authorization: Bearer <token>`
  - Response as blob → `URL.createObjectURL(blob)`
  - PDF: open in new tab (`window.open`)
  - Other types: download via `<a download>`
  - 401/403: show error message in UI

## API

- **URL:** `GET /api/documents/{document_id}/download`
- **Auth:** Bearer token required
- **Success:** 200, `FileResponse` (blob)
- **Errors:** 401 (session expired), 403 (no access)

## Manual verification

1. Login as supplier
2. Go to "Документы от ресторанов"
3. Click Eye on a document (after contract accepted)
4. PDF opens in new tab; other files download

See screenshot: `evidence/screens/manual_ui_flow/05_supplier_click_view_opens_pdf.png`
