#!/usr/bin/env python3
"""Find which DB contains TARGET_EMAIL in users/user collection. One-line output, no tracebacks."""
import os
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


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("FOUND_DB=NONE")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL)
        dbs = client.list_database_names()
    except Exception:
        print("FOUND_DB=NONE")
        sys.exit(1)
    for db_name in dbs:
        if db_name in ("admin", "local", "config"):
            continue
        db = client[db_name]
        for coll_name in ("users", "user"):
            try:
                coll = db.get_collection(coll_name)
                doc = coll.find_one({"email": TARGET_EMAIL})
                if doc is not None:
                    has_password = bool(doc.get("passwordHash") or doc.get("password"))
                    role = doc.get("role", "missing")
                    print("FOUND_DB=%s collection=%s has_password=%s role=%s" % (
                        db_name, coll_name, str(has_password).lower(), role))
                    sys.exit(0)
            except Exception:
                continue
    print("FOUND_DB=NONE")
    sys.exit(1)


if __name__ == "__main__":
    main()
