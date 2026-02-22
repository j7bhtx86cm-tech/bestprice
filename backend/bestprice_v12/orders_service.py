"""
Order → OrderItems → OrderSupplierRequests domain service.
Restaurant creates order, adds items (per supplier), submits; suppliers respond.
Sync API for use from scripts; can be wrapped in async later for HTTP API.
Uses string ids (order id = uuid, company ids = companies.id).
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

ORDER_STATUSES = ("DRAFT", "SENT_TO_SUPPLIER", "PARTIALLY_CONFIRMED", "CONFIRMED", "REJECTED", "CANCELLED")
ITEM_STATUSES = ("PENDING", "CONFIRMED", "REJECTED", "UPDATED")
REQUEST_STATUSES = ("PENDING", "CONFIRMED", "PARTIALLY_CONFIRMED", "REJECTED")


def _require_company_id_format(x: str, field_name: str = "company_id") -> None:
    """Assert non-empty string; fail fast to avoid 'Company not found' from invalid ids."""
    if not isinstance(x, str) or not x.strip():
        raise ValueError("%s must be a non-empty string, got %s" % (field_name, type(x).__name__))


def _require_status(value: str, allowed_set: tuple, field_name: str = "status") -> None:
    """Assert value is in allowed_set (e.g. ORDER_STATUSES); ValueError otherwise."""
    if value not in allowed_set:
        raise ValueError("%s must be one of %s, got %r" % (field_name, allowed_set, value))


def ensure_indexes(db) -> None:
    """Create indexes for orders, order_items, order_supplier_requests. Idempotent."""
    db.orders.create_index("customer_company_id")
    db.orders.create_index("status")
    db.orders.create_index("created_at")
    db.order_items.create_index("order_id")
    db.order_items.create_index("target_supplier_company_id")
    db.order_items.create_index([("order_id", 1), ("target_supplier_company_id", 1)])
    db.order_supplier_requests.create_index(
        [("order_id", 1), ("supplier_company_id", 1)],
        unique=True,
    )
    db.order_supplier_requests.create_index("supplier_company_id")
    db.order_supplier_requests.create_index("status")
    db.order_supplier_requests.create_index("submitted_at")


def create_order(
    db,
    customer_company_id: str,
    created_by_user_id: str,
) -> Dict[str, Any]:
    """Create order with status DRAFT. Uses id (string uuid); no _id as primary key in doc."""
    _require_company_id_format(customer_company_id, "customer_company_id")
    _require_company_id_format(created_by_user_id, "created_by_user_id")
    now = datetime.now(timezone.utc)
    order_id = str(uuid.uuid4())
    doc = {
        "id": order_id,
        "customer_company_id": customer_company_id,
        "status": "DRAFT",
        "created_at": now,
        "updated_at": now,
        "created_by_user_id": created_by_user_id,
    }
    db.orders.insert_one(doc)
    return doc


def add_order_item(
    db,
    order_id: str,
    target_supplier_company_id: str,
    name_snapshot: str,
    qty: float,
    unit: Optional[str] = None,
    supplier_item_id: Optional[str] = None,
) -> Dict[str, Any]:
    """Add item to order. qty > 0; order must exist and be DRAFT."""
    _require_company_id_format(target_supplier_company_id, "target_supplier_company_id")
    if qty <= 0:
        raise ValueError("qty must be > 0")
    order = db.orders.find_one({"id": order_id})
    if not order:
        raise ValueError("order not found")
    if order.get("status") != "DRAFT":
        raise ValueError("order is not DRAFT")
    now = datetime.now(timezone.utc)
    item_id = str(uuid.uuid4())
    doc = {
        "id": item_id,
        "order_id": order_id,
        "target_supplier_company_id": target_supplier_company_id,
        "supplier_item_id": supplier_item_id,
        "name_snapshot": name_snapshot,
        "qty": qty,
        "unit": unit or "шт",
        "status": "PENDING",
        "updated_at": now,
    }
    db.order_items.insert_one(doc)
    return doc


def submit_order(db, order_id: str, submitted_by_user_id: str) -> Dict[str, Any]:
    """
    Submit order: create order_supplier_requests per supplier, set items to PENDING, order to SENT_TO_SUPPLIER.
    """
    _require_company_id_format(submitted_by_user_id, "submitted_by_user_id")
    order = db.orders.find_one({"id": order_id})
    if not order:
        raise ValueError("order not found")
    if order.get("status") != "DRAFT":
        raise ValueError("order is not DRAFT")
    items = list(db.order_items.find({"order_id": order_id}))
    if not items:
        raise ValueError("order has no items")
    suppliers = set()
    for it in items:
        sid = it.get("target_supplier_company_id")
        if not sid:
            raise ValueError("item missing target_supplier_company_id")
        suppliers.add(sid)
    now = datetime.now(timezone.utc)
    for sid in suppliers:
        db.order_supplier_requests.update_one(
            {"order_id": order_id, "supplier_company_id": sid},
            {
                "$set": {
                    "status": "PENDING",
                    "submitted_at": now,
                    "updated_at": now,
                }
            },
            upsert=True,
        )
    db.order_items.update_many({"order_id": order_id}, {"$set": {"status": "PENDING", "updated_at": now}})
    db.orders.update_one(
        {"id": order_id},
        {"$set": {"status": "SENT_TO_SUPPLIER", "updated_at": now}},
    )
    return {
        "order_id": order_id,
        "suppliers_count": len(suppliers),
        "items_count": len(items),
        "order_status": "SENT_TO_SUPPLIER",
    }


def supplier_respond(
    db,
    order_id: str,
    supplier_company_id: str,
    responded_by_user_id: str,
    decision: str,
    items: Optional[List[Dict[str, Any]]] = None,
    comment: Optional[str] = None,
) -> Dict[str, Any]:
    """
    decision: CONFIRM | REJECT at request level.
    items: optional list of { item_id, decision, reason_code?, reason_text?, confirmed_qty? }.
    If items omitted: confirm all items for this supplier.
    """
    _require_company_id_format(supplier_company_id, "supplier_company_id")
    _require_company_id_format(responded_by_user_id, "responded_by_user_id")
    if decision not in ("CONFIRM", "REJECT"):
        raise ValueError("decision must be CONFIRM or REJECT")
    req = db.order_supplier_requests.find_one({"order_id": order_id, "supplier_company_id": supplier_company_id})
    if not req:
        raise ValueError("order_supplier_requests not found")
    if req.get("status") not in ("PENDING",):
        raise ValueError("request already responded")
    now = datetime.now(timezone.utc)
    supplier_items = list(db.order_items.find({"order_id": order_id, "target_supplier_company_id": supplier_company_id}))
    if not supplier_items:
        raise ValueError("no items for this supplier")

    items_by_id = {it["id"]: it for it in supplier_items}
    if items is None or len(items) == 0:
        # confirm all
        for it in supplier_items:
            db.order_items.update_one(
                {"id": it["id"]},
                {
                    "$set": {
                        "status": "CONFIRMED",
                        "supplier_decision": {"decision": "CONFIRM"},
                        "confirmed_qty": it["qty"],
                        "updated_at": now,
                    }
                },
            )
        request_status = "CONFIRMED"
        counts = {"confirmed": len(supplier_items), "rejected": 0, "updated": 0}
    else:
        confirmed, rejected, updated = 0, 0, 0
        for row in items:
            item_id = row.get("item_id")
            if not item_id or item_id not in items_by_id:
                continue
            it = items_by_id[item_id]
            dec = row.get("decision", decision)
            reason_code = row.get("reason_code", "")
            reason_text = row.get("reason_text", "")
            confirmed_qty = row.get("confirmed_qty")
            if dec == "REJECT":
                db.order_items.update_one(
                    {"id": item_id},
                    {
                        "$set": {
                            "status": "REJECTED",
                            "supplier_decision": {"decision": "REJECT", "reason_code": reason_code, "reason_text": reason_text},
                            "updated_at": now,
                        }
                    },
                )
                rejected += 1
            else:
                q = it["qty"]
                if confirmed_qty is not None and confirmed_qty != q:
                    db.order_items.update_one(
                        {"id": item_id},
                        {
                            "$set": {
                                "status": "UPDATED",
                                "supplier_decision": {"decision": "CONFIRM", "confirmed_qty": confirmed_qty},
                                "confirmed_qty": confirmed_qty,
                                "updated_at": now,
                            }
                        },
                    )
                    updated += 1
                else:
                    db.order_items.update_one(
                        {"id": item_id},
                        {
                            "$set": {
                                "status": "CONFIRMED",
                                "supplier_decision": {"decision": "CONFIRM"},
                                "confirmed_qty": confirmed_qty if confirmed_qty is not None else q,
                                "updated_at": now,
                            }
                        },
                    )
                    confirmed += 1
        counts = {"confirmed": confirmed, "rejected": rejected, "updated": updated}
        after_items = list(db.order_items.find({"order_id": order_id, "target_supplier_company_id": supplier_company_id}))
        statuses = [x["status"] for x in after_items]
        if all(s == "CONFIRMED" for s in statuses):
            request_status = "CONFIRMED"
        elif all(s == "REJECTED" for s in statuses):
            request_status = "REJECTED"
        else:
            request_status = "PARTIALLY_CONFIRMED"

    db.order_supplier_requests.update_one(
        {"order_id": order_id, "supplier_company_id": supplier_company_id},
        {
            "$set": {
                "status": request_status,
                "responded_at": now,
                "responded_by_user_id": responded_by_user_id,
                "comment": comment or "",
                "updated_at": now,
            }
        },
    )

    # Recompute order status (UPPER from enum)
    all_reqs = list(db.order_supplier_requests.find({"order_id": order_id}))
    req_statuses = [r["status"] for r in all_reqs]
    if all(s == "CONFIRMED" for s in req_statuses):
        order_status = "CONFIRMED"
    elif any(s == "PENDING" for s in req_statuses):
        order_status = "SENT_TO_SUPPLIER"
    elif all(s == "REJECTED" for s in req_statuses):
        order_status = "REJECTED"
    else:
        order_status = "PARTIALLY_CONFIRMED"
    _require_status(order_status, ORDER_STATUSES, "order_status")
    db.orders.update_one({"id": order_id}, {"$set": {"status": order_status, "updated_at": now}})

    return {
        "supplier_request_status": request_status,
        "counts": counts,
        "order_status": order_status,
    }


