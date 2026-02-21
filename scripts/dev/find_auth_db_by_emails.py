#!/usr/bin/env python3
"""Find DB where all 3 working emails exist. Search all collections (any with email field). Read-only. Stdout: one line FOUND_DB=... or FOUND_DB=NONE + per-email lines."""
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

REQUIRED_EMAILS = [
    "integrita.supplier@example.com",
    "romax.supplier@example.com",
    "gmfuel@gmail.com",
]


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("FOUND_DB=NONE")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
    except Exception:
        print("FOUND_DB=NONE")
        for e in REQUIRED_EMAILS:
            print("FOUND %s: NONE" % e)
        sys.exit(1)

    dbs = [d for d in client.list_database_names() if d not in ("admin", "local", "config")]

    # For each email: list of (db, coll, count)
    found_per_email = {e: [] for e in REQUIRED_EMAILS}

    for db_name in dbs:
        db = client[db_name]
        try:
            coll_names = db.list_collection_names()
        except Exception:
            continue
        for coll_name in coll_names:
            coll = db[coll_name]
            for email in REQUIRED_EMAILS:
                try:
                    doc = coll.find_one({"email": email}, {"_id": 1})
                    if doc is not None:
                        n = coll.count_documents({"email": email})
                        found_per_email[email].append((db_name, coll_name, n))
                except Exception:
                    continue

    # Is there a DB that has all 3?
    for db_name in dbs:
        has_all = all(
            any(f[0] == db_name for f in found_per_email[email])
            for email in REQUIRED_EMAILS
        )
        if has_all:
            colls = set()
            for email in REQUIRED_EMAILS:
                for (d, c, _) in found_per_email[email]:
                    if d == db_name:
                        colls.add(c)
            print("FOUND_DB=%s COLLECTIONS=%s" % (db_name, ",".join(sorted(colls))))
            sys.exit(0)

    print("FOUND_DB=NONE")
    for email in REQUIRED_EMAILS:
        entries = found_per_email[email]
        if not entries:
            print("FOUND %s: NONE" % email)
        else:
            for (db_name, coll_name, count) in entries:
                print("FOUND %s: db=%s coll=%s count=%s" % (email, db_name, coll_name, count))
    sys.exit(1)


if __name__ == "__main__":
    main()
