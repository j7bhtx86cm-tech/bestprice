# No Junk: Counts after manual flow

Run after Phase 2–3 (manual creation + ACL proof).

## Command

```bash
python3 scripts/verify_no_junk.py
```

## Expected

| Entity | Count | Notes |
|--------|-------|-------|
| suppliers (companies type=supplier) | 1 | Created via UI |
| restaurants (companies type=customer) | 1 | Created via UI |
| links (supplier_restaurant_settings) | 1 | Supplier accepted contract |
| documents | 1 | Restaurant uploaded 1 file |
| users | 2 | 1 supplier + 1 restaurant |

## Acceptance

No old/dev/seed records. Exactly 1/1/1/1.
