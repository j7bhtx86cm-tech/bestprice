#!/usr/bin/env python3
"""Detect Mongo URLs (env + local + docker), find TARGET_EMAIL in any DB. One-line stdout, no tracebacks."""
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
try:
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
except Exception:
    pass

TARGET_EMAIL = os.environ.get("TARGET_EMAIL", "integrita.supplier@example.com")
CONNECT_TIMEOUT_MS = 1800


def collect_candidate_urls():
    seen = set()
    urls = []

    def add(u):
        if u and u not in seen:
            seen.add(u)
            urls.append(u)

    # a) backend/.env
    env_url = os.environ.get("MONGO_URL", "").strip()
    if env_url:
        add(env_url)

    # b) standard local
    for host in ("localhost", "127.0.0.1", "0.0.0.0"):
        for port in (27017, 27018, 27019):
            add("mongodb://%s:%s" % (host, port))

    # c) docker mongo containers (host port only)
    try:
        out = subprocess.run(
            ["docker", "ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Ports}}"],
            capture_output=True, text=True, timeout=5
        )
        if out.returncode == 0 and out.stdout:
            for line in out.stdout.strip().splitlines():
                parts = line.split("\t")
                if len(parts) < 3:
                    continue
                name, image, ports = parts[0].lower(), parts[1].lower(), parts[2]
                if "mongo" not in name and "mongo" not in image:
                    continue
                # Ports: "0.0.0.0:27020->27017/tcp" or "27017/tcp"
                match = re.search(r"(?:0\.0\.0\.0|127\.0\.0\.1|::):(\d+)->\d+/", ports)
                if match:
                    add("mongodb://127.0.0.1:%s" % match.group(1))
    except Exception:
        pass

    return urls


def find_user_in_client(client):
    try:
        dbs = client.list_database_names()
    except Exception:
        return None, 0
    db_count = len([d for d in dbs if d not in ("admin", "local", "config")])
    for db_name in dbs:
        if db_name in ("admin", "local", "config"):
            continue
        db = client[db_name]
        for coll_name in ("users", "user"):
            try:
                doc = db.get_collection(coll_name).find_one({"email": TARGET_EMAIL})
                if doc is not None:
                    has_password = bool(doc.get("passwordHash") or doc.get("password"))
                    role = doc.get("role", "missing")
                    return (db_name, coll_name, has_password, role), db_count
            except Exception:
                continue
    return None, db_count


def main():
    try:
        from pymongo import MongoClient
    except ImportError:
        print("FOUND=NO best_mongo=NONE working_mongo_count=0 dbs_on_best=0")
        sys.exit(1)

    candidates = collect_candidate_urls()
    working = []  # (url, db_count)

    for url in candidates:
        try:
            client = MongoClient(url, serverSelectionTimeoutMS=CONNECT_TIMEOUT_MS)
            client.admin.command("ping")
        except Exception as e:
            err = "timeout" if "timed out" in str(e).lower() or "timeout" in str(e).lower() else "refused"
            continue
        result, db_count = find_user_in_client(client)
        try:
            client.close()
        except Exception:
            pass
        working.append((url, db_count))
        if result is not None:
            db_name, coll_name, has_password, role = result
            print("FOUND=YES mongo=%s db=%s collection=%s has_password=%s role=%s" % (
                url, db_name, coll_name, str(has_password).lower(), role))
            sys.exit(0)

    best_mongo = working[0][0] if working else "NONE"
    dbs_on_best = working[0][1] if working else 0
    print("FOUND=NO best_mongo=%s working_mongo_count=%s dbs_on_best=%s" % (
        best_mongo, len(working), dbs_on_best))
    for url, count in working[:3]:
        print("WORKING mongo=%s db_count=%s" % (url, count))
    sys.exit(1)


if __name__ == "__main__":
    main()
