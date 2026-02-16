# Prune Plan: Removed / Kept

## Removed (dev / junk-creating)

| File | Reason |
|------|--------|
| scripts/dev_pipeline.sh | Reset+seed creates supplier1/2, restaurant1/2 |
| scripts/dev_reset_data.py | Used by dev_pipeline |
| scripts/init_suppliers.py | Creates suppliers from Excel |
| scripts/bulk_create_suppliers.py | Bulk creation |
| scripts/verify_e2e.py | Excel-based E2E, requires init_suppliers |

## Kept

| File | Purpose |
|------|---------|
| run_backend.sh | Start backend 8001 |
| run_frontend.sh | Start frontend 3000 |
| clean_slate_local.sh | Wipe data (ALLOW_DESTRUCTIVE=1) |
| clean_slate_local.py | Clean slate impl |
| prod_minimal_e2e.sh | One-command E2E |
| prove_new_restaurant_docs_e2e.py | Standalone E2E entities |
| collect_acl_proof.py | ACL proof |
| verify_no_junk.py | 1/1/1/1 validation |
| count_collections.py | Before/after counts |
| test_email_reset_password.sh | Feature test |
| test_phone_reset_password.sh | Feature test |

## Do not use in prod flow

- backend/seed_data.py — creates test suppliers/restaurants; use clean_slate + manual UI instead.
