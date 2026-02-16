# Docs Flow Proof

## Steps

1. Restaurant uploads document via UI (Documents / Мои документы)
2. Supplier accepts contract (Документы от ресторанов → Принять)
3. Supplier sees document under restaurant (newest first)
4. ACL: 200 (linked), 403 (no token), 403 (unlinked)

## Run ACL proof

```bash
python3 scripts/collect_acl_proof.py --use-existing
```

Requires: 1 supplier, 1 restaurant, 1 document created manually. Uses supplier@example.com, restaurant@example.com, TestPass123!

Output: evidence/ACL_PROOF.txt
