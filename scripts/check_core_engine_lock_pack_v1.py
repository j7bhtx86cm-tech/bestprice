#!/usr/bin/env python3
"""
Check Core Engine lock pack: required files exist.
Required: docs/RUNBOOK_CORE_ENGINE_LOCK.md, scripts/core_engine_selfcheck_v1.py, scripts/check_core_engine_lock_pack_v1.py.
Optional: artifacts/core_engine_selfcheck_v1.log (if present, not checked).
Exit 0 + CORE_ENGINE_PACK_OK when all required files present.
"""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

RUNBOOK = ROOT / "docs" / "RUNBOOK_CORE_ENGINE_LOCK.md"
SELFCHECK_SCRIPT = ROOT / "scripts" / "core_engine_selfcheck_v1.py"
PACK_CHECK_SCRIPT = ROOT / "scripts" / "check_core_engine_lock_pack_v1.py"


def main():
    missing = []
    if not RUNBOOK.exists():
        missing.append("docs/RUNBOOK_CORE_ENGINE_LOCK.md")
    if not SELFCHECK_SCRIPT.exists():
        missing.append("scripts/core_engine_selfcheck_v1.py")
    if not PACK_CHECK_SCRIPT.exists():
        missing.append("scripts/check_core_engine_lock_pack_v1.py")
    if missing:
        print("CORE_ENGINE_PACK_FAIL: %s" % ", ".join(missing))
        sys.exit(1)
    print("CORE_ENGINE_PACK_OK")
    sys.exit(0)


if __name__ == "__main__":
    main()
