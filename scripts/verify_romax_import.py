#!/usr/bin/env python3
"""
Проверка supplier price-list API (тот же endpoint, что страница /supplier/price-list):
- items_count >= 100
- первый элемент: article/code == 2001 или "2001", name содержит "Говядина"
Пишет evidence/ROMAX_IMPORT_FIX_PROOF.txt. Выход: 0 = PASS, 1 = FAIL.
Требуется: запущенный backend, поставщик Romax с импортированным прайсом (≥100 строк).
"""
import os
import sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from _env import load_env

load_env()

# API_BASE_URL из env, по умолчанию http://127.0.0.1:8001
API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8001").rstrip("/")
API = f"{API_BASE_URL}/api"

ROMAX_EMAIL = os.environ.get("ROMAX_EMAIL", "romax.supplier@example.com")
ROMAX_PASSWORD = os.environ.get("ROMAX_PASSWORD", "Romax#2026")

try:
    import requests
except ImportError:
    print("ERROR: pip install requests")
    sys.exit(1)


def main():
    ts = datetime.now(timezone.utc).isoformat()
    lines = [
        "timestamp=" + ts,
        "API_BASE_URL=" + API_BASE_URL,
    ]

    # Логин поставщика (тот же контекст, что страница /supplier/price-list)
    r = requests.post(
        f"{API}/auth/login",
        json={"email": ROMAX_EMAIL, "password": ROMAX_PASSWORD},
        timeout=30,
    )
    if r.status_code != 200:
        lines.append("total=0")
        lines.append("first_item.article=")
        lines.append("first_item.name=")
        lines.append("RESULT: FAIL (login failed)")
        _write(lines)
        sys.exit(1)

    token = r.json().get("access_token")
    headers = {"Authorization": f"Bearer {token}"}

    # GET supplier price-list (тот же endpoint, что дергает localhost:3000/supplier/price-list)
    pl = requests.get(f"{API}/supplier/price-list", headers=headers, timeout=30)
    if pl.status_code != 200:
        lines.append("total=0")
        lines.append("first_item.article=")
        lines.append("first_item.name=")
        lines.append("RESULT: FAIL (price-list request failed)")
        _write(lines)
        sys.exit(1)

    data = pl.json()
    items = data if isinstance(data, list) else (data.get("items") or [])
    total = len(items) if isinstance(data, list) else (data.get("total") or data.get("items_count") or len(items))

    lines.append("total=" + str(total))
    if not items:
        lines.append("first_item.article=")
        lines.append("first_item.name=")
        lines.append("RESULT: FAIL (no items)")
        _write(lines)
        sys.exit(1)

    first = items[0]
    article = first.get("article", first.get("code", ""))
    name = first.get("name", first.get("productName", ""))
    lines.append("first_item.article=" + str(article))
    lines.append("first_item.name=" + str(name)[:120])

    # Проверки
    fail_reasons = []
    if total < 100:
        fail_reasons.append("items_count < 100")
    art_ok = article in ("2001", 2001) or str(article).strip() == "2001"
    if not art_ok:
        fail_reasons.append("first item article/code != 2001")
    if "Говядина" not in (name or ""):
        fail_reasons.append("first item name does not contain 'Говядина'")

    if fail_reasons:
        lines.append("RESULT: FAIL (" + "; ".join(fail_reasons) + ")")
        _write(lines)
        sys.exit(1)

    lines.append("RESULT: PASS")
    _write(lines)
    sys.exit(0)


def _write(lines):
    out = ROOT / "evidence" / "ROMAX_IMPORT_FIX_PROOF.txt"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


if __name__ == "__main__":
    main()
