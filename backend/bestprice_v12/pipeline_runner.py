"""
Core pipeline runner: apply_rules → build_masters → market_snapshot → history_rollup.
One entry point: run_core_pipeline(db, ruleset_version_id, scope).
Writes pipeline_runs for control; each step logged with start/end/time_ms + trace_id.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

COLLECTION_RUNS = "pipeline_runs"
STATUS_RUNNING = "RUNNING"
STATUS_OK = "OK"
STATUS_FAIL = "FAIL"


async def _step_apply_rules(db, scope: Dict[str, Any], trace_id: str) -> Dict[str, Any]:
    """Set quality status on supplier_items in scope (publishable → status=OK)."""
    supplier_id = scope.get("supplier_company_id")
    pricelist_id = scope.get("pricelist_id")
    if not supplier_id:
        return {"ok": 0, "error": "missing supplier_company_id"}
    q = {"supplier_company_id": supplier_id, "active": True}
    if pricelist_id:
        q["price_list_id"] = pricelist_id
    # Publishable: price>0, unit_type, pack for WEIGHT/VOLUME
    update = await db.supplier_items.update_many(
        {
            **q,
            "price": {"$gt": 0},
            "unit_type": {"$exists": True, "$ne": None, "$ne": ""},
            "$or": [
                {"unit_type": {"$in": ["WEIGHT", "VOLUME"]}, "pack_qty": {"$gt": 0}},
                {"unit_type": "PIECE"},
            ],
        },
        {"$set": {"status": "OK", "quality_flags": []}},
    )
    return {"ok": update.modified_count, "matched": update.matched_count}


def _master_fingerprint(supplier_id: str, supplier_item_id: str, ruleset_version_id: str, name_raw: Optional[str] = None) -> str:
    """Stable fingerprint for master; never null. Fallback from stable fields."""
    raw = f"{ruleset_version_id}|{supplier_id}|{supplier_item_id}|{(name_raw or '')}"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"fallback|{h}"


async def _step_build_masters(db, scope: Dict[str, Any], ruleset_version_id: str, trace_id: str) -> Dict[str, Any]:
    """Create masters and master_links for supplier items in scope. Idempotent per supplier+ruleset."""
    supplier_id = scope.get("supplier_company_id")
    pricelist_id = scope.get("pricelist_id")
    if not supplier_id:
        return {"masters": 0, "links": 0, "error": "missing supplier_company_id"}

    # Idempotency: clear previous masters/links/snapshot for this supplier+ruleset
    await db.masters.delete_many({"ruleset_version_id": ruleset_version_id, "supplier_id": supplier_id})
    await db.master_links.delete_many({"ruleset_version_id": ruleset_version_id, "supplier_id": supplier_id})
    await db.master_market_snapshot_current.delete_many({"ruleset_version_id": ruleset_version_id, "supplier_id": supplier_id})

    q = {"supplier_company_id": supplier_id, "active": True}
    if pricelist_id:
        q["price_list_id"] = pricelist_id
    cursor = db.supplier_items.find(q, {"_id": 0, "id": 1, "name_raw": 1})
    items = await cursor.to_list(length=10000)
    masters_created = 0
    links_created = 0
    skipped = 0
    for it in items:
        si_id = it.get("id")
        if not si_id:
            skipped += 1
            continue
        name_raw = (it.get("name_raw") or "").strip()
        fingerprint = _master_fingerprint(supplier_id, si_id, ruleset_version_id, name_raw)
        if not fingerprint or not isinstance(fingerprint, str):
            logger.warning("skipped master due to missing fingerprint fields supplier_item_id=%s", si_id)
            skipped += 1
            continue
        master_id = str(uuid.uuid4())
        await db.masters.insert_one({
            "id": master_id,
            "ruleset_version_id": ruleset_version_id,
            "supplier_id": supplier_id,
            "fingerprint": fingerprint,
            "created_at": datetime.now(timezone.utc),
        })
        masters_created += 1
        await db.master_links.insert_one({
            "id": str(uuid.uuid4()),
            "master_id": master_id,
            "supplier_item_id": si_id,
            "sku_id": si_id,  # avoid unique index (ruleset_version_id, sku_id) dup on null
            "supplier_id": supplier_id,
            "ruleset_version_id": ruleset_version_id,
            "created_at": datetime.now(timezone.utc),
        })
        links_created += 1
    if skipped:
        logger.info("build_masters_v1 skipped %s items (no id or fingerprint)", skipped)
    return {"masters": masters_created, "links": links_created, "skipped": skipped}


async def _step_market_snapshot(db, scope: Dict[str, Any], ruleset_version_id: str, trace_id: str) -> Dict[str, Any]:
    """Write master_market_snapshot_current for scope."""
    supplier_id = scope.get("supplier_company_id")
    if not supplier_id:
        return {"count": 0, "error": "missing supplier_company_id"}
    snap_id = str(uuid.uuid4())
    await db.master_market_snapshot_current.insert_one({
        "id": snap_id,
        "ruleset_version_id": ruleset_version_id,
        "supplier_id": supplier_id,
        "trace_id": trace_id,
        "created_at": datetime.now(timezone.utc),
    })
    return {"count": 1}


async def _step_history_rollup(db, scope: Dict[str, Any], ruleset_version_id: str, trace_id: str) -> Dict[str, Any]:
    """Write sku_price_history and master_market_history_daily."""
    supplier_id = scope.get("supplier_company_id")
    if not supplier_id:
        return {"history": 0, "daily": 0, "error": "missing supplier_company_id"}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await db.sku_price_history.insert_one({
        "supplier_id": supplier_id,
        "date": today,
        "ruleset_version_id": ruleset_version_id,
        "trace_id": trace_id,
        "created_at": datetime.now(timezone.utc),
    })
    await db.master_market_history_daily.insert_one({
        "ruleset_version_id": ruleset_version_id,
        "supplier_id": supplier_id,
        "date": today,
        "trace_id": trace_id,
        "created_at": datetime.now(timezone.utc),
    })
    history_count = await db.sku_price_history.count_documents({"supplier_id": supplier_id, "date": today})
    daily_count = await db.master_market_history_daily.count_documents({"supplier_id": supplier_id, "date": today})
    return {"history": history_count, "daily": daily_count}


async def run_core_pipeline(
    db,
    ruleset_version_id: str,
    scope: Dict[str, Any],
    import_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run: apply_rules → build_masters → market_snapshot → history_rollup.
    scope: { supplier_company_id, pricelist_id? }
    Creates pipeline_runs doc; returns run_id and status.
    """
    run_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    steps: List[Dict[str, Any]] = []
    doc = {
        "_id": run_id,
        "import_id": import_id or scope.get("pricelist_id"),
        "batch_id": import_id or scope.get("pricelist_id"),
        "ruleset_version_id": ruleset_version_id,
        "status": STATUS_RUNNING,
        "steps": steps,
        "created_at": now,
        "updated_at": now,
        "trace_id": trace_id,
    }
    await db[COLLECTION_RUNS].insert_one(doc)
    logger.info("pipeline start run_id=%s trace_id=%s scope=%s", run_id, trace_id, scope)

    step_names = [
        ("apply_rules_v1", _step_apply_rules),
        ("build_masters_v1", _step_build_masters),
        ("market_snapshot_v1", _step_market_snapshot),
        ("history_rollup_v1", _step_history_rollup),
    ]
    for name, fn in step_names:
        step_start = datetime.now(timezone.utc)
        step_info = {"name": name, "status": STATUS_RUNNING, "started_at": step_start, "finished_at": None, "error": None, "trace_id": trace_id}
        steps.append(step_info)
        await db[COLLECTION_RUNS].update_one(
            {"_id": run_id},
            {"$set": {"steps": steps, "updated_at": datetime.now(timezone.utc)}},
        )
        try:
            if name == "apply_rules_v1":
                out = await fn(db, scope, trace_id)
            else:
                out = await fn(db, scope, ruleset_version_id, trace_id)
            step_end = datetime.now(timezone.utc)
            step_info["status"] = STATUS_OK
            step_info["finished_at"] = step_end
            step_info["result"] = out
            step_info["time_ms"] = int((step_end - step_start).total_seconds() * 1000)
            logger.info("pipeline step %s ok run_id=%s time_ms=%s", name, run_id, step_info["time_ms"])
        except Exception as e:
            step_end = datetime.now(timezone.utc)
            step_info["status"] = STATUS_FAIL
            step_info["finished_at"] = step_end
            step_info["error"] = str(e)[:500]
            step_info["time_ms"] = int((step_end - step_start).total_seconds() * 1000)
            logger.exception("pipeline step %s fail run_id=%s", name, run_id)
            await db[COLLECTION_RUNS].update_one(
                {"_id": run_id},
                {"$set": {"status": STATUS_FAIL, "steps": steps, "updated_at": step_end}},
            )
            return {"run_id": run_id, "status": STATUS_FAIL, "trace_id": trace_id}

    await db[COLLECTION_RUNS].update_one(
        {"_id": run_id},
        {"$set": {"status": STATUS_OK, "steps": steps, "updated_at": datetime.now(timezone.utc)}},
    )
    logger.info("pipeline ok run_id=%s trace_id=%s", run_id, trace_id)
    return {"run_id": run_id, "status": STATUS_OK, "trace_id": trace_id}
