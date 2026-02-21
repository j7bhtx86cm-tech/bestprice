"""
Core pipeline runner: apply_rules → build_masters → market_snapshot → history_rollup.
One entry point: run_core_pipeline(db, ruleset_version_id, scope).
Writes pipeline_runs for control; each step logged with start/end/time_ms + trace_id.
"""
import hashlib
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

# Repo root for pipeline_events.log (backend/bestprice_v12/pipeline_runner.py -> parent.parent.parent)
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent

try:
    from bson import ObjectId
except ImportError:
    ObjectId = None

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


def _master_fingerprint(supplier_id: str, supplier_item_id: str, ruleset_version_id: Any, name_raw: Optional[str] = None) -> str:
    """Stable fingerprint for master; never null. Fallback from stable fields. ruleset_version_id can be ObjectId or str."""
    raw = f"{ruleset_version_id}|{supplier_id}|{supplier_item_id}|{(name_raw or '')}"
    h = hashlib.sha1(raw.encode("utf-8")).hexdigest()
    return f"fallback|{h}"


async def _step_build_masters(db, scope: Dict[str, Any], ruleset_version_id: Any, trace_id: str) -> Dict[str, Any]:
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
        if not fingerprint or not isinstance(fingerprint, str) or fingerprint.strip() == "":
            logger.warning("skipped master: fingerprint missing supplier_item_id=%s", si_id)
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


async def _step_market_snapshot(db, scope: Dict[str, Any], ruleset_version_id: Any, trace_id: str) -> Dict[str, Any]:
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


async def _step_history_rollup(db, scope: Dict[str, Any], ruleset_version_id: Any, trace_id: str) -> Dict[str, Any]:
    """Write sku_price_history (one per supplier_item, sku_id=supplier_item._id ObjectId) and master_market_history_daily. Idempotent per ruleset+supplier+date."""
    supplier_id = scope.get("supplier_company_id")
    if not supplier_id:
        return {"history": 0, "daily": 0, "error": "missing supplier_company_id"}
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    await db.sku_price_history.delete_many({"ruleset_version_id": ruleset_version_id, "supplier_id": supplier_id, "date": today})
    await db.master_market_history_daily.delete_many({"ruleset_version_id": ruleset_version_id, "supplier_id": supplier_id, "date": today})

    q = {"supplier_company_id": supplier_id, "active": True}
    if scope.get("pricelist_id"):
        q["price_list_id"] = scope["pricelist_id"]
    cursor = db.supplier_items.find(q, {"_id": 1})
    items = await cursor.to_list(length=10000)
    history_inserted = 0
    for it in items:
        sku_id = it.get("_id")
        if not sku_id or (ObjectId is not None and not isinstance(sku_id, ObjectId)):
            logger.warning("history_skip_missing_sku_id supplier_id=%s item_id=%s", supplier_id, it.get("_id"))
            continue
        await db.sku_price_history.insert_one({
            "supplier_id": supplier_id,
            "sku_id": sku_id,
            "date": today,
            "ruleset_version_id": ruleset_version_id,
            "trace_id": trace_id,
            "created_at": datetime.now(timezone.utc),
        })
        history_inserted += 1
    await db.master_market_history_daily.insert_one({
        "ruleset_version_id": ruleset_version_id,
        "master_id": supplier_id,  # avoid unique index (ruleset_version_id, master_id, date) dup on null
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
    ruleset_version_id: Any,
    scope: Dict[str, Any],
    import_id: Optional[str] = None,
    version_name: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Run: apply_rules → build_masters → market_snapshot → history_rollup.
    ruleset_version_id must be ObjectId (_id from ruleset_versions).
    scope: { supplier_company_id, pricelist_id? }
    Creates pipeline_runs doc; returns run_id and status.
    """
    run_id = str(uuid.uuid4())
    trace_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc)
    supplier_id = scope.get("supplier_company_id")
    steps: List[Dict[str, Any]] = []
    doc = {
        "_id": run_id,
        "import_id": import_id or scope.get("pricelist_id"),
        "batch_id": import_id or scope.get("pricelist_id"),
        "ruleset_version_id": ruleset_version_id,
        "supplier_id": supplier_id,
        "status": STATUS_RUNNING,
        "steps": steps,
        "created_at": now,
        "updated_at": now,
        "trace_id": trace_id,
    }
    await db[COLLECTION_RUNS].insert_one(doc)
    logger.info(
        "PIPELINE_RUN_CREATED run_id=%s import_id=%s supplier_id=%s ruleset_version_id=%s",
        run_id, doc.get("import_id"), supplier_id, ruleset_version_id,
    )
    try:
        events_file = _REPO_ROOT / "artifacts" / "pipeline_events.log"
        events_file.parent.mkdir(parents=True, exist_ok=True)
        with open(events_file, "a", encoding="utf-8") as ef:
            ef.write(
                "PIPELINE_RUN_CREATED run_id=%s import_id=%s supplier_id=%s ruleset_version_id=%s\n"
                % (run_id, doc.get("import_id"), supplier_id, ruleset_version_id)
            )
    except Exception:
        pass

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
    logger.info("pipeline ok run_id=%s trace_id=%s version_name=%s", run_id, trace_id, version_name or "")
    return {"run_id": run_id, "status": STATUS_OK, "trace_id": trace_id}
