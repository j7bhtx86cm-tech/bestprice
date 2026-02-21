#!/usr/bin/env python3
"""
Assert rules count from artifacts: rulesets_export_*.zip, rules_pack*.xlsx/csv/json, rules_registry*.json.
Output: ARTIFACT_RULES_OK source=<file> rules_count=<n> if n>=25, else ARTIFACT_RULES_FAIL best_source=... rules_count=... expected>=25.
No secrets in stdout.
"""
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ARTIFACTS = ROOT / "artifacts"

RULES_KEYS = ("rules", "rules_registry", "global_rules", "category_rules", "validations", "quality_rules")


def _count_rules_in_data(data):
    """Count rule-like items: list of dicts with rule_code/code/id, or dict with RULES_KEYS arrays."""
    if isinstance(data, list):
        n = 0
        for item in data:
            if isinstance(item, dict):
                code = item.get("rule_code") or item.get("code") or item.get("id")
                if code is not None and str(code).strip():
                    n += 1
            elif isinstance(item, str) and item.strip():
                n += 1
        return n
    if isinstance(data, dict):
        best = 0
        for key in RULES_KEYS:
            arr = data.get(key)
            if isinstance(arr, list):
                best = max(best, _count_rules_in_data(arr))
        return best
    return 0


def _count_from_json_path(path: Path) -> int:
    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
        data = json.loads(text)
        return _count_rules_in_data(data)
    except Exception:
        return 0


def _count_from_zip(zip_path: Path) -> tuple:
    """Return (max_rules_count, best_inner_path)."""
    best_count = 0
    best_inner = ""
    try:
        with zipfile.ZipFile(zip_path, "r") as z:
            for name in z.namelist():
                name_lower = name.lower()
                if "rules_registry" not in name_lower and "registries" not in name_lower:
                    continue
                if not name_lower.endswith(".json"):
                    continue
                try:
                    with z.open(name) as fp:
                        raw = fp.read(500000).decode("utf-8", errors="ignore")
                        data = json.loads(raw)
                        cnt = _count_rules_in_data(data)
                        if cnt > best_count:
                            best_count = cnt
                            best_inner = name
                except Exception:
                    pass
    except Exception:
        pass
    return best_count, best_inner or zip_path.name


def _count_from_table(path: Path) -> int:
    """Count rows with rule_code from csv/xlsx."""
    try:
        import pandas as pd
    except ImportError:
        return 0
    try:
        if path.suffix.lower() == ".csv":
            df = pd.read_csv(path, sep=None, engine="python", nrows=500)
        else:
            df = pd.read_excel(path, nrows=500)
    except Exception:
        return 0
    cols_lower = {str(c).lower(): c for c in df.columns}
    if "rule_code" not in cols_lower:
        for k in cols_lower:
            if "rule" in k and "code" in k:
                return int(df[cols_lower[k]].notna().sum())
        return 0
    return int(df[cols_lower["rule_code"]].notna().sum())


def main():
    if not ARTIFACTS.is_dir():
        print("ARTIFACT_RULES_FAIL best_source=NONE rules_count=0 expected>=25")
        return
    candidates = []
    # rulesets_export_*.zip
    for f in sorted(ARTIFACTS.glob("rulesets_export_*.zip"), key=lambda p: -p.stat().st_mtime):
        cnt, _ = _count_from_zip(f)
        candidates.append((cnt, str(f)))
    # rules_pack*.xlsx / .csv / .json
    for pat in ("rules_pack*.xlsx", "rules_pack*.csv", "rules_pack*.json"):
        for f in sorted(ARTIFACTS.glob(pat), key=lambda p: -p.stat().st_mtime):
            if f.suffix.lower() == ".json":
                cnt = _count_from_json_path(f)
            else:
                cnt = _count_from_table(f)
            candidates.append((cnt, str(f)))
    # rules_registry*.json
    for f in sorted(ARTIFACTS.glob("rules_registry*.json"), key=lambda p: -p.stat().st_mtime):
        cnt = _count_from_json_path(f)
        candidates.append((cnt, str(f)))
    if not candidates:
        print("ARTIFACT_RULES_FAIL best_source=NONE rules_count=0 expected>=25")
        return
    best_count = max(c[0] for c in candidates)
    best_source = next(c[1] for c in candidates if c[0] == best_count)
    if best_count >= 25:
        print("ARTIFACT_RULES_OK source=%s rules_count=%s" % (best_source, best_count))
    else:
        print("ARTIFACT_RULES_FAIL best_source=%s rules_count=%s expected>=25" % (best_source, best_count))


if __name__ == "__main__":
    main()
