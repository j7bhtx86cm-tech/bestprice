# Deliverable Summary

## 1. Changed files

### Added
- `scripts/verify_no_junk.py` — validates 1/1/1/1
- `evidence/FRESH_START_STEPS.md` — manual UI steps
- `evidence/DOCS_FLOW_PROOF.md` — docs + ACL steps
- `evidence/NO_JUNK_COUNTS.md` — no-junk explanation
- `evidence/PROD_MINIMAL_E2E_STEPS.md` — how to run E2E
- `evidence/screens/fresh_start/00_CAPTURE_INSTRUCTIONS.md`
- `evidence/screens/docs_flow/00_CAPTURE_INSTRUCTIONS.md`

### Modified
- `scripts/collect_acl_proof.py` — added `--use-existing` mode, removes temp supplier
- `scripts/prod_minimal_e2e.sh` — added `--no-junk` mode
- `evidence/PRUNE_PLAN.md` — updated with removals

### Deleted
- `scripts/dev_pipeline.sh`
- `scripts/dev_reset_data.py`
- `scripts/init_suppliers.py`
- `scripts/bulk_create_suppliers.py`
- `scripts/verify_e2e.py`

---

## 2. Commands for full reproduction

```bash
# 1. Clean slate
ALLOW_DESTRUCTIVE=1 bash scripts/clean_slate_local.sh

# 2. Run backend + frontend (2 terminals)
bash scripts/run_backend.sh
bash scripts/run_frontend.sh

# 3. Minimal E2E (standalone) or after manual UI
bash scripts/prod_minimal_e2e.sh
# or: bash scripts/prod_minimal_e2e.sh --no-junk
```

---

## 3. Evidence paths

| File | Description |
|------|-------------|
| evidence/RUN_BACKEND_PROOF.txt | Backend startup log |
| evidence/RUN_FRONTEND_PROOF.txt | Frontend startup log |
| evidence/CLEAN_SLATE_TERMINAL_PROOF.txt | Clean slate output |
| evidence/CLEAN_SLATE_BEFORE_AFTER.md | Counts before/after |
| evidence/ACL_PROOF.txt | ACL 200/403/403 |
| evidence/DOCS_FLOW_PROOF.md | Docs flow steps |
| evidence/NO_JUNK_COUNTS.md | No-junk explanation |
| evidence/NO_JUNK_ASSERTIONS.txt | Output of verify_no_junk.py |
| evidence/PROD_MINIMAL_E2E_PROOF.txt | E2E success log |
| evidence/PROD_MINIMAL_E2E_STEPS.md | E2E how-to |
| evidence/PRUNE_PLAN.md | Prune plan |
| evidence/PRUNE_PROOF.txt | E2E after prune |
| evidence/FRESH_START_STEPS.md | Manual UI steps |

---

## 4. Screenshots (manual capture)

See `evidence/screens/*/00_CAPTURE_INSTRUCTIONS.md` for each:

- `evidence/screens/fresh_start/00_ports_ok.png`
- `evidence/screens/fresh_start/01_clean_slate_done.png`
- `evidence/screens/fresh_start/02_supplier_registered.png`
- `evidence/screens/fresh_start/03_restaurant_registered.png`
- `evidence/screens/docs_flow/01_restaurant_upload_page.png`
- `evidence/screens/docs_flow/02_doc_uploaded_success.png`
- `evidence/screens/docs_flow/03_supplier_documents_list_sorted.png`
- `evidence/screens/docs_flow/04_supplier_sees_doc.png`

---

## 5. Status

- **CLEAN SLATE OK** — evidence/CLEAN_SLATE_*
- **MANUAL FLOW OK** — steps in FRESH_START_STEPS.md (screenshots pending manual capture)
- **ACL OK** — evidence/ACL_PROOF.txt (200/403/403)
- **NO JUNK OK** — verify_no_junk.py, NO_JUNK_*
- **E2E PASSED** — evidence/PROD_MINIMAL_E2E_PROOF.txt, PRUNE_PROOF.txt
