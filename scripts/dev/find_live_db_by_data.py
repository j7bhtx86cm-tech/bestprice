#!/usr/bin/env python3
"""Find DB with live data (pricelists/supplier_items/restaurants etc.), set backend/.env DB_NAME. Read-only except .env."""
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

CANDIDATE_COLLECTIONS = [
    "pricelists",
    "supplier_items",
    "companies",
    "restaurants",
    "partners",
    "restaurant_suppliers",
    "supplier_restaurants",
    "catalog_items",
    "imports",
    "pipeline_runs",
]

SCORE_RULES = [
    ("pricelists", 100),
    ("supplier_items", 50),
    ("companies", 20),
    ("restaurants", 20),
    ("partners", 10),
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
    best_db = None
    best_score = 0
    best_top = []

    for db_name in dbs:
        db = client[db_name]
        score = 0
        top = []
        coll_counts = {}
        for coll_name in CANDIDATE_COLLECTIONS:
            try:
                if coll_name not in db.list_collection_names():
                    continue
                cnt = db[coll_name].estimated_document_count()
                coll_counts[coll_name] = cnt
                if cnt > 0:
                    for name, points in SCORE_RULES:
                        if name == coll_name:
                            score += points
                            top.append("%s:%s" % (coll_name, cnt))
                            break
                    else:
                        score += 5
                        top.append("%s:%s" % (coll_name, cnt))
            except Exception:
                continue
        if score > best_score:
            best_score = score
            best_db = db_name
            best_top = top

    if best_score == 0 or best_db is None:
        print("FOUND_DB=NONE")
        sys.exit(1)

    print("FOUND_DB=%s SCORE=%s TOP=%s" % (best_db, best_score, ",".join(best_top)))

    env_path = ROOT / "backend" / ".env"
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()
        out = []
        for line in lines:
            s = line.strip()
            if s.startswith("DB_NAME="):
                if '"' in line or "'" in line:
                    out.append('DB_NAME="%s"' % best_db)
                else:
                    out.append("DB_NAME=%s" % best_db)
            else:
                out.append(line)
        env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
    else:
        env_path.parent.mkdir(parents=True, exist_ok=True)
        env_path.write_text(
            'MONGO_URL="%s"\nDB_NAME="%s"\n' % (os.environ.get("MONGO_URL", "mongodb://localhost:27017"), best_db),
            encoding="utf-8",
        )
    sys.exit(0)


if __name__ == "__main__":
    main()
