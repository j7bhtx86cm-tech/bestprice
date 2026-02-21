#!/usr/bin/env python3
"""Find the single MongoDB DB where all 3 working emails exist. Stdout: FOUND_DB=<name> COLLECTOR=<users|user|mixed> or FOUND_DB=NONE."""
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
        sys.exit(1)

    dbs = [d for d in client.list_database_names() if d not in ("admin", "local", "config")]

    for db_name in dbs:
        db = client[db_name]
        found_by_coll = {}  # email -> "users" | "user"
        for email in REQUIRED_EMAILS:
            for coll_name in ("users", "user"):
                try:
                    doc = db.get_collection(coll_name).find_one({"email": email})
                    if doc is not None:
                        found_by_coll[email] = coll_name
                        break
                except Exception:
                    continue
        if len(found_by_coll) == 3:
            colls = set(found_by_coll.values())
            if colls == {"users"}:
                collector = "users"
            elif colls == {"user"}:
                collector = "user"
            else:
                collector = "mixed"
            print("FOUND_DB=%s COLLECTOR=%s" % (db_name, collector))
            # Fix backend/.env so DB_NAME points to this DB (preserve quote style)
            env_path = ROOT / "backend" / ".env"
            if env_path.exists():
                lines = env_path.read_text(encoding="utf-8").splitlines()
                out = []
                for line in lines:
                    s = line.strip()
                    if s.startswith("DB_NAME="):
                        if '"' in line or "'" in line:
                            out.append('DB_NAME="%s"' % db_name)
                        else:
                            out.append("DB_NAME=%s" % db_name)
                    else:
                        out.append(line)
                env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
            else:
                env_path.parent.mkdir(parents=True, exist_ok=True)
                env_path.write_text(
                    'MONGO_URL="%s"\nDB_NAME="%s"\n' % (os.environ.get("MONGO_URL", "mongodb://localhost:27017"), db_name),
                    encoding="utf-8",
                )
            sys.exit(0)

    print("FOUND_DB=NONE")
    sys.exit(1)


if __name__ == "__main__":
    main()
