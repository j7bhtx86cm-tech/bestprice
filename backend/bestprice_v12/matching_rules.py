"""
BestPrice v12 - Unified Matching Rules Module
=============================================

Модуль для сопоставления товаров (alternatives, optimizer).
Использует lexicon_ru_v1_3.json для извлечения match_signature и применения hard/soft правил.

Стратегия:
- HB1: top_class должен совпадать
- HB2: product_kind должен совпадать  
- HB3: main_ingredient должен совпадать
- HB4: processing — HARD IF PRESENT (если есть в референсе)
- HB5: state — HARD IF PRESENT (если есть в референсе)
- Negative blocks — взаимоисключения (сосиски≠филе, рыба≠птица)

Tiers:
- Tier A: Идентичные (все HB + cut_attrs совпадают)
- Tier B: Близкие (HB1-3, без нарушения negative blocks)
- Tier C: Аналоги (только при include_analogs=true)

Author: BestPrice v12
Version: 1.3
"""

import json
import re
import os
import logging
from typing import Dict, List, Optional, Tuple, Any
from pathlib import Path
from functools import lru_cache

logger = logging.getLogger(__name__)

# === LEXICON LOADING AND CACHING ===

_LEXICON_CACHE: Optional[Dict] = None

def get_lexicon_path() -> Path:
    """Get path to lexicon file."""
    return Path(__file__).parent / "lexicon_ru_v1_3.json"


def load_lexicon() -> Dict:
    """Load and cache lexicon dictionary."""
    global _LEXICON_CACHE
    
    if _LEXICON_CACHE is not None:
        return _LEXICON_CACHE
    
    lexicon_path = get_lexicon_path()
    
    if not lexicon_path.exists():
        logger.error(f"Lexicon file not found: {lexicon_path}")
        raise FileNotFoundError(f"Lexicon file not found: {lexicon_path}")
    
    with open(lexicon_path, 'r', encoding='utf-8') as f:
        _LEXICON_CACHE = json.load(f)
    
    logger.info(f"Lexicon loaded: v{_LEXICON_CACHE.get('version', '?')} ({lexicon_path})")
    return _LEXICON_CACHE


def get_lexicon() -> Dict:
    """Get cached lexicon (load if needed)."""
    return load_lexicon()


# === SIGNATURE EXTRACTION ===

class MatchSignature:
    """
    Match signature for a product item.
    Contains all extracted attributes for matching.
    """
    def __init__(self):
        self.top_class: Optional[str] = None
        self.product_kind: Optional[str] = None
        self.main_ingredient: Optional[str] = None
        self.processing: Optional[str] = None
        self.state: Optional[str] = None
        self.cut_attrs: List[str] = []
        self.fat_pct: Optional[float] = None
        self.brand: Optional[str] = None
        self.raw_name: str = ""
        self.normalized_name: str = ""
    
    def to_dict(self) -> Dict:
        return {
            'top_class': self.top_class,
            'product_kind': self.product_kind,
            'main_ingredient': self.main_ingredient,
            'processing': self.processing,
            'state': self.state,
            'cut_attrs': self.cut_attrs,
            'fat_pct': self.fat_pct,
            'brand': self.brand,
        }
    
    def __repr__(self):
        return f"MatchSignature({self.to_dict()})"


def normalize_text(text: str) -> str:
    """Normalize text for matching: lowercase, collapse whitespace."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    return text


def expand_abbreviations(text: str, lexicon: Dict) -> str:
    """Expand common abbreviations using lexicon."""
    abbreviations = lexicon.get('abbreviations', {})
    
    for abbr, full in abbreviations.items():
        # Use word boundary to avoid partial replacements
        pattern = r'\b' + re.escape(abbr) + r'\b'
        text = re.sub(pattern, full, text, flags=re.IGNORECASE)
    
    return text


def extract_fat_pct(text: str, lexicon: Dict) -> Optional[float]:
    """Extract fat percentage from text."""
    fat_markers = lexicon.get('fat_markers', {})
    patterns = fat_markers.get('fat_pct_regex', [])
    
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            try:
                return float(match.group(1))
            except (ValueError, IndexError):
                continue
    
    # Simple pattern: digit followed by %
    simple_match = re.search(r'(\d{1,2}(?:[.,]\d)?)\s*%', text)
    if simple_match:
        try:
            return float(simple_match.group(1).replace(',', '.'))
        except ValueError:
            pass
    
    return None


def detect_top_class(text: str, lexicon: Dict) -> Optional[str]:
    """Detect top_class from text using lexicon keywords."""
    keywords = lexicon.get('top_class_keywords', {})
    
    for top_class, tokens in keywords.items():
        for token in tokens:
            if token.lower() in text:
                return top_class
    
    return None


def detect_product_kind(text: str, lexicon: Dict) -> Optional[str]:
    """Detect product_kind from text using lexicon."""
    kinds = lexicon.get('product_kind', {})
    
    # Sort by token length (longer tokens first) for better matching
    sorted_kinds = sorted(
        [(kind, tokens) for kind, tokens in kinds.items()],
        key=lambda x: -max(len(t) for t in x[1]) if x[1] else 0
    )
    
    for kind, tokens in sorted_kinds:
        for token in tokens:
            # Handle regex patterns (e.g., "огурц.*марин")
            if '.*' in token or '?' in token or '+' in token:
                if re.search(token, text, re.IGNORECASE):
                    return kind
            elif token.lower() in text:
                return kind
    
    return None


def detect_main_ingredient(text: str, lexicon: Dict) -> Optional[str]:
    """Detect main_ingredient from text using lexicon synonyms."""
    synonyms = lexicon.get('ingredient_synonyms', {})
    
    # Sort by token length
    sorted_synonyms = sorted(
        [(ing, tokens) for ing, tokens in synonyms.items()],
        key=lambda x: -max(len(t) for t in x[1]) if x[1] else 0
    )
    
    for ingredient, tokens in sorted_synonyms:
        for token in tokens:
            if token.lower() in text:
                return ingredient
    
    return None


def detect_processing(text: str, lexicon: Dict) -> Optional[str]:
    """Detect processing type from text."""
    processing_dict = lexicon.get('processing', {})
    
    for proc_type, tokens in processing_dict.items():
        for token in tokens:
            if token.lower() in text:
                return proc_type
    
    return None


def detect_state(text: str, lexicon: Dict) -> Optional[str]:
    """Detect state (frozen/chilled) from text."""
    states = lexicon.get('state', {})
    
    for state, tokens in states.items():
        for token in tokens:
            if token.lower() in text:
                return state
    
    return None


def detect_cut_attrs(text: str, lexicon: Dict) -> List[str]:
    """Detect cut attributes (fillet, boneless, etc.) from text."""
    cut_attrs_dict = lexicon.get('cut_attrs', {})
    found_attrs = []
    
    for attr, tokens in cut_attrs_dict.items():
        for token in tokens:
            if token.lower() in text:
                if attr not in found_attrs:
                    found_attrs.append(attr)
                break
    
    return found_attrs


def extract_signature(name: str, brand: Optional[str] = None) -> MatchSignature:
    """
    Extract MatchSignature from product name.
    
    Args:
        name: Product name (raw or normalized)
        brand: Optional brand name
    
    Returns:
        MatchSignature with extracted attributes
    """
    lexicon = get_lexicon()
    sig = MatchSignature()
    
    sig.raw_name = name
    
    # Normalize and expand abbreviations
    normalized = normalize_text(name)
    normalized = expand_abbreviations(normalized, lexicon)
    sig.normalized_name = normalized
    
    # Extract all attributes
    sig.top_class = detect_top_class(normalized, lexicon)
    sig.product_kind = detect_product_kind(normalized, lexicon)
    sig.main_ingredient = detect_main_ingredient(normalized, lexicon)
    sig.processing = detect_processing(normalized, lexicon)
    sig.state = detect_state(normalized, lexicon)
    sig.cut_attrs = detect_cut_attrs(normalized, lexicon)
    sig.fat_pct = extract_fat_pct(normalized, lexicon)
    sig.brand = brand
    
    return sig


# === HARD BLOCKS AND NEGATIVE BLOCKS ===

def check_hard_blocks(ref_sig: MatchSignature, cand_sig: MatchSignature) -> Tuple[bool, List[str]]:
    """
    Check hard block rules (HB1-HB5).
    
    Returns:
        (passed, reasons) - passed=True if candidate passes all hard blocks
    """
    reasons = []
    
    # HB1: top_class must match
    if ref_sig.top_class and cand_sig.top_class:
        if ref_sig.top_class != cand_sig.top_class:
            reasons.append(f"HB1_top_class_mismatch: {ref_sig.top_class} != {cand_sig.top_class}")
    
    # HB2: product_kind must match
    if ref_sig.product_kind and cand_sig.product_kind:
        if ref_sig.product_kind != cand_sig.product_kind:
            reasons.append(f"HB2_product_kind_mismatch: {ref_sig.product_kind} != {cand_sig.product_kind}")
    
    # HB3: main_ingredient must match
    if ref_sig.main_ingredient and cand_sig.main_ingredient:
        if ref_sig.main_ingredient != cand_sig.main_ingredient:
            # Check for synonym groups
            if not are_ingredients_equivalent(ref_sig.main_ingredient, cand_sig.main_ingredient):
                reasons.append(f"HB3_main_ingredient_mismatch: {ref_sig.main_ingredient} != {cand_sig.main_ingredient}")
    
    # HB4: processing - HARD IF PRESENT in reference
    if ref_sig.processing:
        if cand_sig.processing and ref_sig.processing != cand_sig.processing:
            reasons.append(f"HB4_processing_mismatch: {ref_sig.processing} != {cand_sig.processing}")
        elif not cand_sig.processing:
            reasons.append(f"HB4_processing_missing: ref={ref_sig.processing}, cand=None")
    
    # HB5: state - HARD IF PRESENT in reference
    if ref_sig.state:
        if cand_sig.state and ref_sig.state != cand_sig.state:
            reasons.append(f"HB5_state_mismatch: {ref_sig.state} != {cand_sig.state}")
        elif not cand_sig.state:
            # State missing in candidate - soft warning, not hard block
            pass
    
    passed = len(reasons) == 0
    return passed, reasons


def are_ingredients_equivalent(ing1: str, ing2: str) -> bool:
    """Check if two ingredients are equivalent (same synonym group)."""
    if ing1 == ing2:
        return True
    
    lexicon = get_lexicon()
    synonyms = lexicon.get('ingredient_synonyms', {})
    
    # Find groups containing each ingredient
    group1 = None
    group2 = None
    
    for group_name, tokens in synonyms.items():
        tokens_lower = [t.lower() for t in tokens]
        if ing1.lower() in tokens_lower or ing1 == group_name:
            group1 = group_name
        if ing2.lower() in tokens_lower or ing2 == group_name:
            group2 = group_name
    
    # Same group = equivalent
    if group1 and group2 and group1 == group2:
        return True
    
    return False


def check_negative_blocks(ref_sig: MatchSignature, cand_sig: MatchSignature) -> Tuple[bool, List[str]]:
    """
    Check negative block rules (mutual exclusions).
    
    ВАЖНО: Negative blocks работают в ОБЕ стороны!
    Если сосиски не могут быть заменены на филе, то и филе не может быть заменено на сосиски.
    
    Returns:
        (passed, reasons) - passed=True if no negative blocks triggered
    """
    lexicon = get_lexicon()
    negative_blocks = lexicon.get('negative_blocks', [])
    reasons = []
    
    for block in negative_blocks:
        block_name = block.get('name', 'unknown')
        
        # Check top_class based blocks (bidirectional)
        if 'if_ref_top_class' in block:
            ref_class = block['if_ref_top_class']
            reject_classes = block.get('reject_offer_if_top_class_in', [])
            
            # Direction 1: ref matches condition, cand in reject list
            if ref_sig.top_class == ref_class:
                if cand_sig.top_class in reject_classes:
                    reasons.append(f"NEGATIVE_{block_name}: ref={ref_sig.top_class}, cand={cand_sig.top_class}")
            
            # Direction 2 (bidirectional): cand matches condition, ref in reject list
            if cand_sig.top_class == ref_class:
                if ref_sig.top_class in reject_classes:
                    reasons.append(f"NEGATIVE_{block_name}_REV: cand={cand_sig.top_class}, ref={ref_sig.top_class}")
        
        # Check product_kind based blocks (bidirectional)
        if 'if_ref_kind_in' in block:
            ref_kinds = block['if_ref_kind_in']
            reject_kinds = block.get('reject_offer_if_kind_in', [])
            
            # Direction 1: ref kind in condition, cand kind in reject
            if ref_sig.product_kind in ref_kinds:
                if cand_sig.product_kind in reject_kinds:
                    reasons.append(f"NEGATIVE_{block_name}: ref_kind={ref_sig.product_kind}, cand_kind={cand_sig.product_kind}")
            
            # Direction 2 (bidirectional): cand kind in condition, ref kind in reject
            if cand_sig.product_kind in reject_kinds:
                if ref_sig.product_kind in ref_kinds:
                    # This is the reverse direction - fillet should not show sausages
                    pass  # Already covered by direction 1
            
            # Additional bidirectional check: if cand is in ref_kinds and ref is in reject_kinds
            if cand_sig.product_kind in ref_kinds:
                if ref_sig.product_kind in reject_kinds:
                    reasons.append(f"NEGATIVE_{block_name}_REV: cand_kind={cand_sig.product_kind}, ref_kind={ref_sig.product_kind}")
    
    passed = len(reasons) == 0
    return passed, reasons


def check_fat_tolerance(ref_sig: MatchSignature, cand_sig: MatchSignature) -> Tuple[bool, Optional[str]]:
    """
    Check fat percentage tolerance (±2%).
    
    Returns:
        (passed, reason)
    """
    lexicon = get_lexicon()
    fat_markers = lexicon.get('fat_markers', {})
    tolerance = fat_markers.get('fat_tolerance_pct', 2)
    
    if ref_sig.fat_pct is not None:
        if cand_sig.fat_pct is None:
            return False, f"FAT_MISSING: ref={ref_sig.fat_pct}%, cand=None"
        
        diff = abs(ref_sig.fat_pct - cand_sig.fat_pct)
        if diff > tolerance:
            return False, f"FAT_MISMATCH: ref={ref_sig.fat_pct}%, cand={cand_sig.fat_pct}%, diff={diff}%"
    
    return True, None


# === TIER DETERMINATION ===

def determine_tier(ref_sig: MatchSignature, cand_sig: MatchSignature, 
                   include_analogs: bool = False) -> Tuple[Optional[str], int, List[str]]:
    """
    Determine the tier for a candidate match.
    
    Args:
        ref_sig: Reference item signature
        cand_sig: Candidate item signature
        include_analogs: Whether to include Tier C
    
    Returns:
        (tier, score, badges) - tier is 'A', 'B', 'C', or None (rejected)
    """
    badges = []
    score = 0
    
    # Check negative blocks first (absolute rejection)
    neg_passed, neg_reasons = check_negative_blocks(ref_sig, cand_sig)
    if not neg_passed:
        return None, 0, neg_reasons
    
    # Check hard blocks
    hb_passed, hb_reasons = check_hard_blocks(ref_sig, cand_sig)
    
    # Check fat tolerance
    fat_passed, fat_reason = check_fat_tolerance(ref_sig, cand_sig)
    if not fat_passed:
        badges.append(fat_reason)
    
    # Tier A: All HB pass + cut_attrs match + fat matches
    if hb_passed and fat_passed:
        # Check cut_attrs match
        cut_match = True
        if ref_sig.cut_attrs:
            for attr in ref_sig.cut_attrs:
                if attr not in cand_sig.cut_attrs:
                    cut_match = False
                    badges.append(f"CUT_ATTR_DIFF: {attr}")
        
        if cut_match:
            # Tier A - Identical
            score = calculate_score(ref_sig, cand_sig, 'A')
            return 'A', score, badges
        else:
            # Tier B - cut_attrs differ
            score = calculate_score(ref_sig, cand_sig, 'B')
            return 'B', score, badges
    
    # Tier B: HB1-3 pass, but processing/state don't match
    # Check if only HB4/HB5 failed (processing/state)
    hb_critical = []
    for reason in hb_reasons:
        if 'HB1' in reason or 'HB2' in reason or 'HB3' in reason:
            hb_critical.append(reason)
    
    if not hb_critical:
        # Only HB4/HB5 failed - Tier B with warnings
        for reason in hb_reasons:
            badges.append(reason)
        if not fat_passed:
            return None, 0, badges  # Fat mismatch is strict
        score = calculate_score(ref_sig, cand_sig, 'B')
        return 'B', score, badges
    
    # Tier C: Analogs (only if include_analogs=True)
    if include_analogs:
        # Check if at least top_class and main_ingredient match
        if ref_sig.top_class == cand_sig.top_class:
            if are_ingredients_equivalent(ref_sig.main_ingredient or '', cand_sig.main_ingredient or ''):
                badges.extend(hb_reasons)
                score = calculate_score(ref_sig, cand_sig, 'C')
                return 'C', score, badges
    
    # Rejected
    return None, 0, hb_reasons


def calculate_score(ref_sig: MatchSignature, cand_sig: MatchSignature, tier: str) -> int:
    """
    Calculate match score within a tier.
    
    Scoring:
    - Base score by tier: A=1000, B=500, C=100
    - Brand match: +50
    - Ingredient exact match: +30
    - Product kind exact match: +20
    - Processing exact match: +15
    - State exact match: +10
    """
    base_scores = {'A': 1000, 'B': 500, 'C': 100}
    score = base_scores.get(tier, 0)
    
    # Brand boost
    if ref_sig.brand and cand_sig.brand:
        if ref_sig.brand.lower() == cand_sig.brand.lower():
            score += 50
    
    # Exact matches
    if ref_sig.main_ingredient == cand_sig.main_ingredient:
        score += 30
    
    if ref_sig.product_kind == cand_sig.product_kind:
        score += 20
    
    if ref_sig.processing == cand_sig.processing:
        score += 15
    
    if ref_sig.state == cand_sig.state:
        score += 10
    
    # Cut attrs overlap
    if ref_sig.cut_attrs and cand_sig.cut_attrs:
        overlap = len(set(ref_sig.cut_attrs) & set(cand_sig.cut_attrs))
        score += overlap * 5
    
    return score


# === MAIN MATCHING FUNCTION ===

def find_alternatives(
    source_item: Dict,
    candidates: List[Dict],
    include_analogs: bool = False,
    limit: int = 10
) -> Dict[str, List[Dict]]:
    """
    Find alternative offers for a source item.
    
    Args:
        source_item: Source item dict with 'name_raw', 'brand', etc.
        candidates: List of candidate items to check
        include_analogs: Whether to include Tier C
        limit: Max items per tier
    
    Returns:
        {
            'source': {...},
            'tiers': {
                'A': [...],
                'B': [...],
                'C': [...]  # only if include_analogs
            }
        }
    """
    # Extract source signature
    source_name = source_item.get('name_raw', source_item.get('name', ''))
    source_brand = source_item.get('brand')
    ref_sig = extract_signature(source_name, source_brand)
    
    # Process candidates
    tier_a = []
    tier_b = []
    tier_c = []
    
    for cand in candidates:
        cand_name = cand.get('name_raw', cand.get('name', ''))
        cand_brand = cand.get('brand')
        cand_sig = extract_signature(cand_name, cand_brand)
        
        tier, score, badges = determine_tier(ref_sig, cand_sig, include_analogs)
        
        if tier:
            result = {
                **cand,
                'match_score': score,
                'match_tier': tier,
                'match_badges': badges,
                'match_signature': cand_sig.to_dict(),
            }
            
            if tier == 'A':
                tier_a.append(result)
            elif tier == 'B':
                tier_b.append(result)
            elif tier == 'C':
                tier_c.append(result)
    
    # Sort each tier: score DESC, then price ASC
    def sort_key(item):
        return (-item.get('match_score', 0), item.get('price', 0))
    
    tier_a.sort(key=sort_key)
    tier_b.sort(key=sort_key)
    tier_c.sort(key=sort_key)
    
    # Apply limits
    tier_a = tier_a[:limit]
    tier_b = tier_b[:limit]
    tier_c = tier_c[:limit] if include_analogs else []
    
    return {
        'source': {
            **source_item,
            'match_signature': ref_sig.to_dict(),
        },
        'tiers': {
            'A': tier_a,
            'B': tier_b,
            'C': tier_c,
        }
    }


# === UTILITY FUNCTIONS ===

def explain_match(ref_name: str, cand_name: str, include_analogs: bool = False) -> Dict:
    """
    Explain matching decision between two items.
    Useful for debugging.
    """
    ref_sig = extract_signature(ref_name)
    cand_sig = extract_signature(cand_name)
    
    hb_passed, hb_reasons = check_hard_blocks(ref_sig, cand_sig)
    neg_passed, neg_reasons = check_negative_blocks(ref_sig, cand_sig)
    fat_passed, fat_reason = check_fat_tolerance(ref_sig, cand_sig)
    tier, score, badges = determine_tier(ref_sig, cand_sig, include_analogs)
    
    return {
        'reference': {
            'name': ref_name,
            'signature': ref_sig.to_dict(),
        },
        'candidate': {
            'name': cand_name,
            'signature': cand_sig.to_dict(),
        },
        'hard_blocks': {
            'passed': hb_passed,
            'reasons': hb_reasons,
        },
        'negative_blocks': {
            'passed': neg_passed,
            'reasons': neg_reasons,
        },
        'fat_check': {
            'passed': fat_passed,
            'reason': fat_reason,
        },
        'result': {
            'tier': tier,
            'score': score,
            'badges': badges,
        }
    }


# === INITIALIZATION ===

def init_matching_rules():
    """Initialize matching rules module (load lexicon)."""
    try:
        lexicon = load_lexicon()
        logger.info(f"Matching rules initialized with lexicon v{lexicon.get('version', '?')}")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize matching rules: {e}")
        return False


# Pre-load lexicon on module import
try:
    load_lexicon()
except Exception as e:
    logger.warning(f"Could not pre-load lexicon: {e}")
