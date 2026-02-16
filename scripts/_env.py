"""Unified env loader for Python scripts. Same source as backend and load_env.sh."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_ENV_LOADED = False


def load_env():
    global _ENV_LOADED
    if _ENV_LOADED:
        return
    from dotenv import load_dotenv
    load_dotenv(ROOT / "backend" / ".env", override=False)
    _ENV_LOADED = True


def get_mongo_url():
    load_env()
    return os.environ.get("MONGO_URL", "mongodb://localhost:27017")


def get_db_name():
    load_env()
    return os.environ.get("DB_NAME", "bestprice_local")
