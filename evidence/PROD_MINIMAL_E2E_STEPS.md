# Prod Minimal E2E — How to run

## One-command check

```bash
bash scripts/prod_minimal_e2e.sh
```

**Standalone mode** (default): Creates test entities, runs ACL proof. Backend must be on 8001.

---

## After manual UI flow (no junk)

```bash
bash scripts/prod_minimal_e2e.sh --no-junk
```

**No-junk mode**: Verifies 1/1/1/1 counts, runs ACL with existing entities. Requires:
- 1 supplier (supplier@example.com), 1 restaurant (restaurant@example.com), 1 link, 1 document
- Credentials: TestPass123!

---

## Expectations

- `1. Backend OK`
- `2. Running verify_no_junk.py...` (--no-junk) or `prove_new_restaurant_docs_e2e.py` (default)
- `3. Running collect_acl_proof.py...`
- `E2E PASSED`

Exit 0 = success.
