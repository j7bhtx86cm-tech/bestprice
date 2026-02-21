#!/usr/bin/env python3
"""
Self-check: import backend.server and backend.pipeline.unit_normalizer without errors.
Must be run from repo root. Prints exactly one final line to stdout:
  BACKEND_IMPORT_OK (exit 0) or BACKEND_IMPORT_FAIL: <reason> (exit 1).
No traceback/secrets on stdout; detailed log only in artifacts/backend_import_selfcheck_v1.log.
"""
import io
import os
import sys
import traceback
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ARTIFACTS = REPO_ROOT / "artifacts"
LOG_FILE = ARTIFACTS / "backend_import_selfcheck_v1.log"


def main():
    if str(REPO_ROOT) not in sys.path:
        sys.path.insert(0, str(REPO_ROOT))

    ARTIFACTS.mkdir(parents=True, exist_ok=True)
    log_lines = []

    def log(msg: str):
        log_lines.append(msg)

    # Suppress stdout/stderr during import so only one final line is printed
    devnull = io.StringIO()
    old_stdout, old_stderr = sys.stdout, sys.stderr
    try:
        sys.stdout = devnull
        sys.stderr = devnull
        log("Checking backend.pipeline.unit_normalizer...")
        import backend.pipeline.unit_normalizer  # noqa: F401
        log("Checking backend.server...")
        import backend.server  # noqa: F401
    except Exception as e:
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        reason = str(e)
        if not reason or len(reason) > 500:
            reason = type(e).__name__
        log("FAIL: " + reason)
        log(traceback.format_exc())
        try:
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(log_lines))
        except Exception:
            pass
        print(f"BACKEND_IMPORT_FAIL: {reason}")
        return 1
    finally:
        sys.stdout = old_stdout
        sys.stderr = old_stderr

    print("BACKEND_IMPORT_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
