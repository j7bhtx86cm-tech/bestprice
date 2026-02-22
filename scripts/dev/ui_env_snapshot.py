#!/usr/bin/env python3
"""Print UI_API_BASE and BACKEND_DOCS_STATUS for dev checks. No secrets."""
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FRONTEND_ENV = ROOT / "frontend" / ".env"
BACKEND_DOCS = "http://127.0.0.1:8001/docs"


def main():
    ui_base = os.environ.get("REACT_APP_BACKEND_URL", "")
    if not ui_base and FRONTEND_ENV.exists():
        for line in FRONTEND_ENV.read_text(encoding="utf-8", errors="replace").splitlines():
            line = line.strip()
            if line.startswith("REACT_APP_BACKEND_URL=") and "=" in line:
                ui_base = line.split("=", 1)[1].strip().strip('"').strip("'")
                break
    if not ui_base:
        ui_base = "http://127.0.0.1:8001"
    print("UI_API_BASE=%s" % ui_base)

    try:
        import urllib.request
        req = urllib.request.Request(BACKEND_DOCS, method="GET")
        with urllib.request.urlopen(req, timeout=5) as r:
            print("BACKEND_DOCS_STATUS=%s" % r.status)
    except Exception as e:
        code = getattr(e, "code", None) or getattr(e, "status", None)
        print("BACKEND_DOCS_STATUS=%s" % (code if code is not None else "ERR"))
    sys.exit(0)


if __name__ == "__main__":
    main()
