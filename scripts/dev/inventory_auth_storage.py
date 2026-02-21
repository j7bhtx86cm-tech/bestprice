#!/usr/bin/env python3
"""Inventory where users might live in current Mongo. Read-only, no secrets in output."""
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
TARGET_EMAIL = os.environ.get("TARGET_EMAIL", "integrita.supplier@example.com")

# Suspicious collection name patterns (case-insensitive)
CONTAINS_PATTERN = re.compile(r"user|users|auth|account|profile", re.I)
EXPLICIT_NAMES = {"users", "user", "accounts", "auth_users", "suppliers", "restaurants"}

EMAIL_FIELDS = ("email", "e_mail", "mail", "login", "username", "user_email", "supplier_email")
SECRET_KEY_PATTERN = re.compile(r"password|hash|jwt|token|secret|salt", re.I)


def is_suspicious_collection(name):
    return name.lower() in EXPLICIT_NAMES or bool(CONTAINS_PATTERN.search(name))


def has_password_like(doc):
    if not doc:
        return False
    for k, v in (doc or {}).items():
        if SECRET_KEY_PATTERN.search(k) and v:
            return True
    return False


def mask_value(val):
    if val is None:
        return "NONE"
    s = str(val).strip()
    if not s:
        return "NONE"
    if "@" in s:
        parts = s.split("@", 1)
        left = parts[0]
        if len(left) <= 2:
            return "***@" + (parts[1] if len(parts) > 1 else "")
        return left[:2] + "***@" + (parts[1] if len(parts) > 1 else "")
    if len(s) >= 6 and s.isdigit():
        return s[:2] + "***" + s[-2:]
    return s[:2] + "***" if len(s) > 2 else "***"


def safe_keys(doc, max_keys=12):
    if not doc:
        return []
    out = []
    for k in doc:
        if SECRET_KEY_PATTERN.search(k):
            continue
        out.append(k)
        if len(out) >= max_keys:
            break
    return out


def find_in_collection(coll, target_email):
    """Returns (doc, field_used) or (None, None)."""
    regex = re.compile(re.escape(target_email), re.I)
    for field in EMAIL_FIELDS:
        try:
            doc = coll.find_one({field: target_email})
            if doc is not None:
                return doc, field
            doc = coll.find_one({field: regex})
            if doc is not None:
                return doc, field
        except Exception:
            continue
    return None, None


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("FOUND=NO target=%s" % TARGET_EMAIL)
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
    except Exception:
        print("FOUND=NO target=%s" % TARGET_EMAIL)
        sys.exit(1)

    dbs = [d for d in client.list_database_names() if d not in ("admin", "local", "config")]

    for db_name in dbs:
        db = client[db_name]
        try:
            coll_names = db.list_collection_names()
        except Exception:
            continue
        for coll_name in coll_names:
            if not is_suspicious_collection(coll_name):
                continue
            coll = db[coll_name]
            try:
                count = coll.estimated_document_count()
            except Exception:
                count = 0
            doc, field = find_in_collection(coll, TARGET_EMAIL)
            if doc is not None:
                has_pw = has_password_like(doc)
                role = doc.get("role", "missing")
                uid = doc.get("_id")
                id_str = str(uid) if uid is not None else "missing"
                print("FOUND db=%s coll=%s field=%s has_password=%s role=%s id=%s" % (
                    db_name, coll_name, field, str(has_pw).lower(), role, id_str))
                sys.exit(0)

    # Not found: report inventory
    print("FOUND=NO target=%s" % TARGET_EMAIL)
    candidate = None
    candidate_count = -1

    for db_name in dbs:
        db = client[db_name]
        try:
            coll_names = db.list_collection_names()
        except Exception:
            continue
        suspicious = [c for c in coll_names if is_suspicious_collection(c)]
        if not suspicious:
            continue
        print("DB %s" % db_name)
        for coll_name in suspicious:
            coll = db[coll_name]
            try:
                count = coll.estimated_document_count()
            except Exception:
                count = 0
            if count > candidate_count:
                candidate_count = count
                candidate = (db_name, coll_name)
            keys = []
            sample_email = "NONE"
            try:
                proj = {k: 1 for k in ["email", "e_mail", "mail", "login", "username", "user_email", "supplier_email", "role", "_id"] if k != "_id"}
                proj["_id"] = 1
                sample = coll.find_one({}, projection=proj)
                if sample:
                    keys = safe_keys(sample, 12)
                    for f in EMAIL_FIELDS:
                        if f in sample and sample[f]:
                            sample_email = mask_value(sample[f])
                            break
            except Exception:
                pass
            print("  COL %s count=%s sample_keys=%s sample_email=%s" % (
                coll_name, count, ",".join(keys) if keys else "NONE", sample_email))
        print("")

    if candidate and candidate_count >= 0:
        print("CANDIDATE db=%s coll=%s count=%s" % (candidate[0], candidate[1], candidate_count))
    sys.exit(1)


if __name__ == "__main__":
    main()
