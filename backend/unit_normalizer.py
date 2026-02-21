"""
Compat shim: re-export pack/unit API from backend.pipeline.unit_normalizer.
Use: from backend.unit_normalizer import ... (or from backend.pipeline.unit_normalizer import ...)
"""
from backend.pipeline.unit_normalizer import (
    UnitType,
    PackInfo,
    parse_pack_from_text,
    calculate_packs_needed,
    format_pack_explanation,
    calculate_pack_penalty,
)
__all__ = [
    "UnitType",
    "PackInfo",
    "parse_pack_from_text",
    "calculate_packs_needed",
    "format_pack_explanation",
    "calculate_pack_penalty",
]
