#!/usr/bin/env python3
"""Idempotent auth fixtures: ensure Integrita, Romax, Restaurant users exist in DB with correct role and password."""
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass

MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "bestprice_local")

# Reuse backend's hasher so login verification matches
def _hash_password(password: str) -> str:
    import bcrypt
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

FIXTURES = [
    {"email": "integrita.supplier@example.com", "password": "Integrita#2026", "role": "supplier"},
    {"email": "romax.supplier@example.com", "password": "Romax#2026", "role": "supplier"},
    {"email": "gmfile@gmail.com", "password": "Krevetochna#2026", "role": "customer"},
]


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("AUTH_FIXTURES_FAIL: pymongo not installed")
        sys.exit(1)
    try:
        client = MongoClient(MONGO_URL, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[DB_NAME]
    except Exception as e:
        print("AUTH_FIXTURES_FAIL: %s" % (str(e)[:80]))
        sys.exit(1)

    created = 0
    updated = 0
    now = datetime.now(timezone.utc).isoformat()

    for f in FIXTURES:
        email = f["email"]
        password = f["password"]
        role = f["role"]
        pw_hash = _hash_password(password)
        existing = db.users.find_one({"email": email}, {"_id": 0, "id": 1, "passwordHash": 1, "role": 1})
        if existing is None:
            user_id = str(uuid.uuid4())
            db.users.insert_one({
                "id": user_id,
                "email": email,
                "passwordHash": pw_hash,
                "role": role,
                "createdAt": now,
                "updatedAt": now,
            })
            created += 1
        else:
            db.users.update_one(
                {"email": email},
                {"$set": {"passwordHash": pw_hash, "role": role, "updatedAt": now}}
            )
            updated += 1

    print("AUTH_FIXTURES_OK created=%s updated=%s db=%s" % (created, updated, DB_NAME))
    sys.exit(0)


if __name__ == "__main__":
    main()
