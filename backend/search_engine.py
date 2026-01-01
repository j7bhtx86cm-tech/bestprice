"""Enhanced Search Engine - Final Architecture per Clean Spec

VERSION 3.3 (January 1, 2026):
CRITICAL FIX: Use Overlap Coefficient for ALL modes (not just brand_critical=ON)

TOKEN SCORING (FINAL):
- ALL modes: score = common_tokens / min(ref_tokens, cand_tokens)
- This is Overlap Coefficient (aka Szymkiewicz–Simpson coefficient)
- Prevents penalty for candidates with MORE descriptive information
- Example: "Кукуруза LUTIK 425мл" vs "Кукуруза сахарная LUTIK 425мл Китай ключом"
  → Score = 3/3 = 1.0 (not 3/5 = 0.6)

THRESHOLDS (different for each mode):
- brand_critical=OFF: min_score >= 70%
- brand_critical=ON: min_score >= 85%

WHY OVERLAP NOT JACCARD:
- Jaccard penalizes extra descriptive tokens ("китай", "ключом", "сахарная")
- Overlap checks "does candidate cover all reference tokens?"
- Allows finding cheaper variants with MORE detailed names

BASED ON: Clean Technical Specification - BestPrice MVP

ARCHITECTURE:
- Two separate entities: Reference (favorite v2) vs Supplier Item (pricelist)
- Never mix reference with supplier_item
- Search uses ONLY normalized fields, NOT raw titles

CANDIDATE GUARD (Step 1):
- Minimum 2 common meaningful tokens required
- Category must match (if specified)
- Units must be compatible (kg ↔ kg, l ↔ l, pcs ↔ pcs)
- Prohibits absurd matches: ketchup ≠ water, lamb ≠ sauce

BRAND/ORIGIN RULES (Step 2):
- brand_critical=false → brand AND origin COMPLETELY IGNORED
- brand_critical=true + has brand_id → only same brand_id
- brand_critical=true + no brand but has origin → origin_critical (country required)

PACK & PRICE (Step 3):
- Pack tolerance: ±20% (0.8x - 1.2x)
- Price calculation: ceil(required_qty / pack_value) × price
- Selection by minimum total_cost

PROHIBITIONS:
❌ Don't use raw title for logic
❌ Don't mix reference and supplier_item
❌ Don't consider brand when brand_critical=OFF
❌ Don't jump between categories
"""
import logging
import re
from typing import Optional, List, Dict, Any, Set, Tuple
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


# Guard rules - conflicting product types
GUARD_CONFLICTS = {
    'кетчуп': {'соус', 'паста', 'майонез', 'горчица'},
    'соус': {'кетчуп', 'паста', 'майонез'},
    'паста': {'соус', 'кетчуп'},
    'майонез': {'кетчуп', 'соус', 'горчица'},
    'горчица': {'майонез', 'кетчуп'},
    'масло': {'маргарин', 'спред'},
    'маргарин': {'масло', 'спред'},
    'молоко': {'сливки', 'кефир', 'йогурт'},
    'сливки': {'молоко', 'кефир'},
    'томатный': {'острый', 'сырный', 'грибной'},
    'острый': {'томатный', 'сырный'},
}

# Category synonyms for matching
CATEGORY_SYNONYMS = {
    'fish': {'рыба', 'морепродукты', 'seafood'},
    'meat': {'мясо', 'птица', 'poultry'},
    'dairy': {'молочные', 'молоко', 'сыр'},
    'sauce': {'соусы', 'кетчуп', 'майонез'},
    'oil': {'масла', 'жиры'},
    'grocery': {'бакалея', 'крупы'},
}

# Unit normalization
UNIT_NORM_MAP = {
    'кг': 'kg', 'kg': 'kg', 'килограмм': 'kg',
    'г': 'g', 'g': 'g', 'грамм': 'g', 'гр': 'g',
    'л': 'l', 'l': 'l', 'литр': 'l', 'литра': 'l',
    'мл': 'ml', 'ml': 'ml', 'миллилитр': 'ml',
    'шт': 'pcs', 'pcs': 'pcs', 'штук': 'pcs', 'штука': 'pcs',
}


def normalize_unit(unit: str) -> str:
    """Normalize unit to standard form"""
    if not unit:
        return 'kg'  # default
    return UNIT_NORM_MAP.get(unit.lower().strip(), unit.lower())


def extract_pack_value(name: str, unit: str = None) -> Optional[float]:
    """Extract pack value from product name
    
    Examples:
    - "Кетчуп 800г" → 0.8 (kg)
    - "Соус 1л" → 1.0 (l)
    - "Масло ~5кг/кор" → 5.0 (kg)
    """
    if not name:
        return None
    
    name_lower = name.lower()
    
    # Pattern for box weight first (~5 кг, вес 5кг, 5кг/кор)
    box_match = re.search(r'[~≈]?\s*(\d+[,.]?\d*)\s*(кг|л)\s*(\/кор|кор)?', name_lower)
    if box_match:
        value = float(box_match.group(1).replace(',', '.'))
        unit_found = box_match.group(2)
        return value
    
    # Pattern for grams/ml
    gram_match = re.search(r'(\d+[,.]?\d*)\s*(г|гр|мл)\b', name_lower)
    if gram_match:
        value = float(gram_match.group(1).replace(',', '.'))
        unit_found = gram_match.group(2)
        # Convert g to kg, ml to l
        if unit_found in ('г', 'гр'):
            return value / 1000
        elif unit_found == 'мл':
            return value / 1000
    
    # Pattern for kg/l
    kg_match = re.search(r'(\d+[,.]?\d*)\s*(кг|л)\b', name_lower)
    if kg_match:
        value = float(kg_match.group(1).replace(',', '.'))
        return value
    
    return None


def extract_tokens(name: str) -> Set[str]:
    """Extract meaningful tokens from product name"""
    if not name:
        return set()
    
    # Normalize
    name_lower = name.lower().replace('ё', 'е')
    
    # Remove numbers and special chars
    name_clean = re.sub(r'[\d.,/\\~≈%×x*]+', ' ', name_lower)
    name_clean = re.sub(r'[^\w\s]', ' ', name_clean)
    
    # Split and filter
    tokens = set(name_clean.split())
    
    # Remove filler words
    fillers = {
        'кг', 'г', 'гр', 'л', 'мл', 'шт', 'упак', 'упаковка', 'пакет',
        'вес', 'нетто', 'брутто', 'кор', 'коробка', 'ящик',
        'и', 'в', 'с', 'на', 'к', 'из', 'для', 'по', 'от', 'до',
        'инд', 'индивидуальный', 'порционный', 'порция',
        'тр', 'tr', 'prb', 'rf', 'professional', 'pro', 'chef',
    }
    tokens = tokens - fillers
    
    # Remove very short tokens
    tokens = {t for t in tokens if len(t) >= 2}
    
    return tokens


def check_guard_conflict(ref_tokens: Set[str], cand_tokens: Set[str], ref_category: Optional[str] = None, cand_category: Optional[str] = None) -> bool:
    """Check if there's a guard conflict between reference and candidate
    
    Returns True if CONFLICT (should reject candidate)
    
    Checks:
    1. Category mismatch (if both specified)
    2. Token-based conflicts (кетчуп ≠ вода)
    """
    # Check 1: Category must match if both are specified
    if ref_category and cand_category:
        ref_cat_norm = ref_category.lower().strip()
        cand_cat_norm = cand_category.lower().strip()
        if ref_cat_norm != cand_cat_norm:
            return True  # CONFLICT: different categories
    
    # Check 2: Token-based conflicts
    for ref_token in ref_tokens:
        if ref_token in GUARD_CONFLICTS:
            conflicts = GUARD_CONFLICTS[ref_token]
            # Check if any candidate token is in conflicts
            if cand_tokens & conflicts:
                return True  # CONFLICT
    
    return False


def is_pack_in_range(ref_pack: Optional[float], cand_pack: Optional[float]) -> Tuple[bool, str]:
    """Check if candidate pack is in acceptable range (±20% of reference)
    
    Returns: (is_valid, reason)
    """
    # If reference has no pack, accept any (but will penalize in scoring)
    if not ref_pack or ref_pack <= 0:
        return (True, "ref_pack_unknown")
    
    # If candidate has no pack, reject
    if not cand_pack or cand_pack <= 0:
        return (False, "cand_pack_unknown")
    
    # ±20% tolerance
    min_pack = ref_pack * 0.8  # -20%
    max_pack = ref_pack * 1.2  # +20%
    
    if min_pack <= cand_pack <= max_pack:
        return (True, f"in_range_{min_pack:.3f}-{max_pack:.3f}")
    elif cand_pack < min_pack:
        return (False, f"too_small_{cand_pack:.3f}<{min_pack:.3f}")
    else:
        return (False, f"too_large_{cand_pack:.3f}>{max_pack:.3f}")


def units_compatible(ref_unit: str, cand_unit: str) -> bool:
    """Check if units are compatible"""
    ref_norm = normalize_unit(ref_unit)
    cand_norm = normalize_unit(cand_unit)
    
    # Direct match
    if ref_norm == cand_norm:
        return True
    
    # kg and g are compatible
    if {ref_norm, cand_norm} <= {'kg', 'g'}:
        return True
    
    # l and ml are compatible
    if {ref_norm, cand_norm} <= {'l', 'ml'}:
        return True
    
    return False


@dataclass
class SearchDebugEvent:
    """Debug event for search operations with comprehensive logging"""
    
    # Input
    search_id: str = ""
    timestamp: str = ""
    reference_name: str = ""
    reference_pack: Optional[float] = None
    reference_unit: Optional[str] = None
    reference_tokens: List[str] = field(default_factory=list)
    brand_id: Optional[str] = None
    brand_family_id: Optional[str] = None
    brand_critical: bool = False
    requested_qty: Optional[float] = None
    
    # Phase info
    phase: str = "main"
    
    # Counters (before/after each filter)
    total_candidates: int = 0
    candidates_after_brand_filter: int = 0
    candidates_after_unit_filter: int = 0
    candidates_after_pack_filter: int = 0
    candidates_after_token_filter: int = 0
    candidates_after_guard_filter: int = 0
    final_candidates: int = 0
    
    # Filter details
    filters_applied: List[str] = field(default_factory=list)
    pack_rejections: List[dict] = field(default_factory=list)
    guard_rejections: List[str] = field(default_factory=list)
    
    # Result
    status: str = "not_found"  # "ok", "not_found", "insufficient_data", "error"
    failure_reason: Optional[str] = None
    selected_item_id: Optional[str] = None
    selected_price: Optional[float] = None
    selected_pack: Optional[float] = None
    selected_brand_id: Optional[str] = None
    selected_total_cost: Optional[float] = None
    selected_price_per_unit: Optional[float] = None
    
    # Timing
    duration_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "search_id": self.search_id,
            "timestamp": self.timestamp,
            "reference": {
                "name": self.reference_name[:50] if self.reference_name else None,
                "pack": self.reference_pack,
                "unit": self.reference_unit,
                "tokens": self.reference_tokens[:10] if self.reference_tokens else [],
                "brand_id": self.brand_id,
                "brand_family_id": self.brand_family_id,
                "brand_critical": self.brand_critical,
                "requested_qty": self.requested_qty
            },
            "phase": self.phase,
            "counters": {
                "total": self.total_candidates,
                "after_brand_filter": self.candidates_after_brand_filter,
                "after_unit_filter": self.candidates_after_unit_filter,
                "after_pack_filter": self.candidates_after_pack_filter,
                "after_token_filter": self.candidates_after_token_filter,
                "after_guard_filter": self.candidates_after_guard_filter,
                "final": self.final_candidates
            },
            "filters_applied": self.filters_applied,
            "pack_rejections_sample": self.pack_rejections[:5],
            "guard_rejections_sample": self.guard_rejections[:5],
            "result": {
                "status": self.status,
                "failure_reason": self.failure_reason,
                "selected_item_id": self.selected_item_id,
                "selected_price": self.selected_price,
                "selected_pack": self.selected_pack,
                "selected_brand_id": self.selected_brand_id,
                "selected_total_cost": self.selected_total_cost,
                "selected_price_per_unit": self.selected_price_per_unit
            },
            "duration_ms": self.duration_ms
        }


@dataclass
class SearchResult:
    """Result of search"""
    status: str  # "ok", "not_found", "insufficient_data", "error"
    selected_offer: Optional[Dict[str, Any]] = None
    top_candidates: List[Dict[str, Any]] = field(default_factory=list)
    debug_event: SearchDebugEvent = field(default_factory=SearchDebugEvent)
    message: Optional[str] = None


class EnhancedSearchEngine:
    """Enhanced search engine with pack range filtering and guard rules
    
    Matching Flow:
    1. Brand filter (only if brand_critical=true)
    2. Unit filter (kg/l/pcs compatibility)
    3. Pack range filter (0.5x - 2x)
    4. Token filter (meaningful tokens match)
    5. Guard filter (кетчуп ≠ соус)
    6. Economics: sort by total_cost, score is tie-breaker
    """
    
    def __init__(self, brand_master=None):
        """Initialize search engine"""
        self.brand_master = brand_master
        if self.brand_master is None:
            try:
                from brand_master import get_brand_master
                self.brand_master = get_brand_master()
            except Exception as e:
                logger.warning(f"Could not load brand master: {e}")
                self.brand_master = None
    
    def search(
        self,
        reference_item: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        brand_critical: bool = False,
        requested_qty: float = 1.0,
        company_map: Optional[Dict[str, str]] = None,
        score_threshold: Optional[float] = None
    ) -> SearchResult:
        """Run enhanced search with pack range filtering and score thresholds
        
        Args:
            reference_item: Reference product with name_raw, pack, unit_norm, brand_id
            candidates: List of candidate items
            brand_critical: If True, filter by brand; if False, ignore brand completely
            requested_qty: Requested quantity for total_cost calculation
            company_map: Mapping of company_id -> company_name
            score_threshold: Minimum score threshold (defaults: 0.85 for brand_critical, 0.70 otherwise)
        """
        import time
        import uuid
        
        start_time = time.time()
        company_map = company_map or {}
        
        # Determine score threshold based on brand_critical
        if score_threshold is None:
            score_threshold = 0.85 if brand_critical else 0.70
        
        # Extract reference data
        ref_name = reference_item.get('name_raw', '')
        ref_pack = reference_item.get('pack') or reference_item.get('pack_value')
        ref_unit = reference_item.get('unit_norm', 'kg')
        ref_brand = reference_item.get('brand_id')
        ref_tokens = extract_tokens(ref_name)
        
        # If pack not provided, try to extract from name
        if not ref_pack:
            ref_pack = extract_pack_value(ref_name, ref_unit)
        
        # Initialize debug event
        debug = SearchDebugEvent(
            search_id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            reference_name=ref_name,
            reference_pack=ref_pack,
            reference_unit=ref_unit,
            reference_tokens=list(ref_tokens)[:10],
            brand_id=ref_brand,
            brand_critical=brand_critical,
            requested_qty=requested_qty,
            total_candidates=len(candidates)
        )
        
        # Get brand family info
        if ref_brand and self.brand_master:
            debug.brand_family_id = self.brand_master.get_brand_family_id(ref_brand)
        
        try:
            # Check for required data
            if not ref_name.strip():
                debug.status = "insufficient_data"
                debug.failure_reason = "no_product_name"
                debug.duration_ms = (time.time() - start_time) * 1000
                return SearchResult(
                    status="insufficient_data",
                    debug_event=debug,
                    message="Недостаточно данных: нет названия товара"
                )
            
            logger.info(f"🔍 ENHANCED SEARCH:")
            logger.info(f"   ref='{ref_name[:50]}'")
            logger.info(f"   pack={ref_pack}, unit={ref_unit}, brand={ref_brand}")
            logger.info(f"   brand_critical={brand_critical}, score_threshold={score_threshold:.2f}")
            logger.info(f"   tokens={list(ref_tokens)[:5]}")
            
            # === FILTER 1: BRAND OR ORIGIN (only if brand_critical=true) ===
            if brand_critical:
                filtered = self._filter_by_brand_or_origin(candidates, reference_item, debug)
                debug.filters_applied.append(f"brand_or_origin_filter: ENABLED (brand_critical=true)")
            else:
                filtered = candidates
                debug.filters_applied.append("brand_or_origin_filter: DISABLED (brand_critical=false)")
            
            debug.candidates_after_brand_filter = len(filtered)
            
            if brand_critical and len(filtered) == 0:
                debug.status = "not_found"
                debug.failure_reason = "no_candidates_for_brand_or_origin"
                debug.duration_ms = (time.time() - start_time) * 1000
                return SearchResult(
                    status="not_found",
                    debug_event=debug,
                    message=f"Нет товаров с требуемым брендом/происхождением"
                )
            
            # === FILTER 2: UNIT ===
            unit_filtered = [
                c for c in filtered
                if units_compatible(ref_unit, c.get('unit_norm', 'kg'))
            ]
            debug.candidates_after_unit_filter = len(unit_filtered)
            debug.filters_applied.append(f"unit_filter: {ref_unit}")
            
            # === FILTER 3: PACK RANGE (±20%) ===
            pack_filtered = []
            for c in unit_filtered:
                cand_pack = c.get('net_weight_kg') or c.get('net_volume_l') or c.get('pack_value')
                if not cand_pack:
                    cand_pack = extract_pack_value(c.get('name_raw', ''), c.get('unit_norm'))
                
                is_valid, reason = is_pack_in_range(ref_pack, cand_pack)
                
                if is_valid:
                    c['_pack_value'] = cand_pack  # Store for later
                    pack_filtered.append(c)
                else:
                    # Track rejections for debug
                    if len(debug.pack_rejections) < 10:
                        debug.pack_rejections.append({
                            'name': c.get('name_raw', '')[:40],
                            'pack': cand_pack,
                            'reason': reason
                        })
            
            debug.candidates_after_pack_filter = len(pack_filtered)
            if ref_pack:
                debug.filters_applied.append(f"pack_filter: {ref_pack*0.8:.2f}-{ref_pack*1.2:.2f} (±20%)")
            else:
                debug.filters_applied.append("pack_filter: DISABLED (ref_pack unknown)")
            
            # === FILTER 4: TOKEN MATCHING WITH SCORE THRESHOLD ===
            # CANDIDATE GUARD: Require minimum 2 common meaningful tokens
            token_filtered = []
            for c in pack_filtered:
                cand_tokens = extract_tokens(c.get('name_raw', ''))
                
                # CRITICAL: When brand_critical=OFF, EXCLUDE brand tokens from scoring
                # This allows finding OTHER brands (e.g., Царский vs Heinz)
                if not brand_critical:
                    # Remove brand-specific tokens from BOTH reference and candidate
                    ref_tokens_clean = ref_tokens.copy()
                    cand_tokens_clean = cand_tokens.copy()
                    
                    # Remove reference brand token (if exists)
                    if ref_brand and ref_brand.strip():
                        ref_tokens_clean.discard(ref_brand.lower())
                    
                    # Remove candidate brand token (if exists)
                    cand_brand = c.get('brand_id')
                    if cand_brand and cand_brand.strip():
                        cand_tokens_clean.discard(cand_brand.lower())
                    
                    # Calculate common tokens WITHOUT brands
                    common_tokens = ref_tokens_clean & cand_tokens_clean
                    
                    # CRITICAL: Minimum 2 common NON-BRAND tokens required
                    if len(common_tokens) < 2:
                        continue
                    
                    # For brand_critical=OFF: Simple ratio - common / ref_tokens
                    # This focuses on "does candidate have what I'm looking for?"
                    # Not penalized by extra candidate tokens
                    token_score = len(common_tokens) / len(ref_tokens_clean) if len(ref_tokens_clean) > 0 else 0
                else:
                    # For brand_critical=ON: Use Overlap Coefficient (strict)
                    common_tokens = ref_tokens & cand_tokens
                    
                    # Minimum 2 common tokens required
                    if len(common_tokens) < 2:
                        continue
                    
                    # Overlap: common / min(ref, cand)
                    min_tokens = min(len(ref_tokens), len(cand_tokens))
                    token_score = len(common_tokens) / min_tokens if min_tokens > 0 else 0
                
                # Apply score threshold
                if token_score >= score_threshold:
                    c['_common_tokens'] = common_tokens
                    c['_token_score'] = token_score
                    token_filtered.append(c)
            
            debug.candidates_after_token_filter = len(token_filtered)
            if brand_critical:
                debug.filters_applied.append(f"token_filter: min_tokens=2, min_score={score_threshold:.2f} (WITH brand)")
            else:
                debug.filters_applied.append(f"token_filter: min_tokens=2, min_score={score_threshold:.2f} (NO brand)")
            
            # === FILTER 5: GUARD RULES (category + token conflicts) ===
            guard_filtered = []
            ref_category = reference_item.get('category')
            
            for c in token_filtered:
                cand_tokens = extract_tokens(c.get('name_raw', ''))
                cand_category = c.get('category')
                
                if check_guard_conflict(ref_tokens, cand_tokens, ref_category, cand_category):
                    debug.guard_rejections.append(c.get('name_raw', '')[:40])
                else:
                    guard_filtered.append(c)
            
            debug.candidates_after_guard_filter = len(guard_filtered)
            debug.filters_applied.append("guard_filter: category + token_conflicts")
            
            # Final candidates
            final_candidates = guard_filtered
            debug.final_candidates = len(final_candidates)
            
            if not final_candidates:
                debug.status = "not_found"
                debug.failure_reason = "no_candidates_after_filters"
                debug.duration_ms = (time.time() - start_time) * 1000
                return SearchResult(
                    status="not_found",
                    debug_event=debug,
                    message="Не найдено подходящих товаров"
                )
            
            # === ECONOMICS: Calculate price_per_base_unit and total_cost ===
            scored = []
            for c in final_candidates:
                item = c
                item_pack = c.get('_pack_value') or 1.0
                item_price = c.get('price') or 0
                item_unit = c.get('unit_norm', 'kg')
                
                # CORRECT LOGIC based on unit:
                # - If unit is pcs/шт: price is per piece → compare directly
                # - If unit is kg/l/кг/л: price is per kg/l → calculate price_per_unit
                
                if ref_unit in ['pcs', 'шт']:
                    # For pieces: price IS per piece
                    price_per_unit = item_price
                    total_cost = requested_qty * item_price
                else:
                    # For kg/l: price is ALREADY per kg/l in catalog
                    # pack_value is minimum weight (e.g., 1.6kg for salmon)
                    # Just use price as price_per_unit
                    price_per_unit = item_price  # This IS price/kg from catalog
                    total_cost = requested_qty * item_price  # Total for requested kg/l
                
                # Token score as tie-breaker
                token_score = c.get('_token_score', 0)
                
                scored.append({
                    'item': item,
                    'price_per_unit': price_per_unit,
                    'total_cost': total_cost,
                    'token_score': token_score,
                    'pack_value': item_pack
                })
            
            # Sort by total_cost (cheapest first), then by token_score (tie-breaker)
            scored.sort(key=lambda x: (x['total_cost'], -x['token_score']))
            
            # Select winner
            winner = scored[0]
            winner_item = winner['item']
            
            logger.info(f"✅ FOUND {len(scored)} candidates")
            logger.info(f"   Winner: {winner_item.get('name_raw', '')[:40]}")
            logger.info(f"   Price: {winner_item.get('price')}₽, Pack: {winner['pack_value']}")
            logger.info(f"   Total cost: {winner['total_cost']:.2f}₽ for {requested_qty} units")
            
            # Update debug
            debug.status = "ok"
            debug.selected_item_id = winner_item.get('id')
            debug.selected_price = winner_item.get('price')
            debug.selected_pack = winner['pack_value']
            debug.selected_brand_id = winner_item.get('brand_id')
            debug.selected_total_cost = winner['total_cost']
            debug.selected_price_per_unit = winner['price_per_unit']
            
            # Build selected offer
            selected_offer = {
                'supplier_id': winner_item.get('supplier_company_id'),
                'supplier_name': company_map.get(winner_item.get('supplier_company_id'), 'Unknown'),
                'supplier_item_id': winner_item.get('id'),
                'name_raw': winner_item.get('name_raw'),
                'price': winner_item.get('price'),
                'currency': 'RUB',
                'unit_norm': winner_item.get('unit_norm', 'kg'),
                'pack_value': winner['pack_value'],
                'pack_unit': winner_item.get('base_unit', 'kg'),
                'price_per_base_unit': winner['price_per_unit'],
                'total_cost': winner['total_cost'],
                'units_needed': requested_qty / winner['pack_value'] if winner['pack_value'] > 0 else 1,
                'score': winner['token_score'],
                'brand_id': winner_item.get('brand_id')
            }
            
            # Build top candidates
            top = []
            for s in scored[:5]:
                top.append({
                    'supplier_item_id': s['item'].get('id'),
                    'name_raw': s['item'].get('name_raw'),
                    'price': s['item'].get('price'),
                    'brand_id': s['item'].get('brand_id'),
                    'pack_value': s['pack_value'],
                    'price_per_unit': s['price_per_unit'],
                    'total_cost': s['total_cost'],
                    'token_score': s['token_score'],
                    'supplier': company_map.get(s['item'].get('supplier_company_id'), 'Unknown')
                })
            
            debug.duration_ms = (time.time() - start_time) * 1000
            
            return SearchResult(
                status="ok",
                selected_offer=selected_offer,
                top_candidates=top,
                debug_event=debug
            )
            
        except Exception as e:
            logger.error(f"❌ SEARCH ERROR: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            debug.status = "error"
            debug.failure_reason = f"exception: {str(e)}"
            debug.duration_ms = (time.time() - start_time) * 1000
            
            return SearchResult(
                status="error",
                debug_event=debug,
                message=f"Ошибка поиска: {str(e)}"
            )
    
    def _filter_by_brand_or_origin(
        self,
        candidates: List[Dict[str, Any]],
        reference_item: Dict[str, Any],
        debug: SearchDebugEvent
    ) -> List[Dict[str, Any]]:
        """Filter candidates by brand_id OR origin (for non-branded items)
        
        Logic:
        - If reference has brand_id → filter by brand_id (with family fallback)
        - If reference has NO brand but has origin → filter by origin
        - Origin matching: country (required) + region/city (if present in reference)
        """
        brand_id = reference_item.get('brand_id')
        
        # Case 1: Has brand_id → filter by brand
        if brand_id:
            return self._filter_by_brand(candidates, brand_id, debug)
        
        # Case 2: No brand, check origin
        origin_country = reference_item.get('origin_country')
        origin_region = reference_item.get('origin_region')
        origin_city = reference_item.get('origin_city')
        
        if not origin_country:
            # No brand and no origin → cannot apply strict filter
            debug.filters_applied.append("origin_filter: SKIPPED (no brand_id and no origin)")
            return []
        
        # Filter by origin
        origin_filtered = []
        for c in candidates:
            cand_country = (c.get('origin_country') or '').lower().strip()
            cand_region = (c.get('origin_region') or '').lower().strip()
            cand_city = (c.get('origin_city') or '').lower().strip()
            
            ref_country_norm = origin_country.lower().strip()
            
            # Country must match
            if cand_country != ref_country_norm:
                continue
            
            # If reference has region, it must match
            if origin_region:
                ref_region_norm = origin_region.lower().strip()
                if cand_region != ref_region_norm:
                    continue
            
            # If reference has city, it must match
            if origin_city:
                ref_city_norm = origin_city.lower().strip()
                if cand_city != ref_city_norm:
                    continue
            
            origin_filtered.append(c)
        
        origin_spec = origin_country
        if origin_region:
            origin_spec += f"/{origin_region}"
        if origin_city:
            origin_spec += f"/{origin_city}"
        
        debug.filters_applied.append(f"origin_filter: {origin_spec} → {len(origin_filtered)} matches")
        
        return origin_filtered
    
    def _filter_by_brand(
        self,
        candidates: List[Dict[str, Any]],
        brand_id: str,
        debug: SearchDebugEvent
    ) -> List[Dict[str, Any]]:
        """Filter candidates by brand_id with family fallback"""
        brand_lower = brand_id.lower()
        
        # First try exact brand_id match
        brand_filtered = [
            c for c in candidates
            if c.get('brand_id') and c['brand_id'].lower() == brand_lower
        ]
        
        # If 0 results and has family, try family filter
        if len(brand_filtered) == 0 and self.brand_master:
            brand_family_id = self.brand_master.get_brand_family_id(brand_id)
            
            if brand_family_id:
                logger.info(f"🔗 BRAND FAMILY FALLBACK: {brand_id} -> {brand_family_id}")
                
                family_members = self.brand_master.get_family_members(brand_family_id)
                family_members_set = set(m.lower() for m in family_members)
                family_members_set.add(brand_family_id.lower())
                
                brand_filtered = [
                    c for c in candidates
                    if c.get('brand_id') and c['brand_id'].lower() in family_members_set
                ]
                
                debug.filters_applied.append(
                    f"brand_family_fallback: {brand_family_id}, members={list(family_members_set)}"
                )
        
        return brand_filtered


# Quality report functions

def generate_brand_quality_report(products: List[dict], pricelists: List[dict]) -> dict:
    """Generate quality report for brand coverage"""
    product_map = {p['id']: p for p in products}
    
    supplier_stats = {}
    products_without_brand = []
    
    for pl in pricelists:
        supplier_id = pl.get('supplierId')
        product_id = pl.get('productId')
        product = product_map.get(product_id, {})
        
        if supplier_id not in supplier_stats:
            supplier_stats[supplier_id] = {
                'total': 0,
                'with_brand': 0,
                'without_brand': 0
            }
        
        supplier_stats[supplier_id]['total'] += 1
        
        if product.get('brand_id'):
            supplier_stats[supplier_id]['with_brand'] += 1
        else:
            supplier_stats[supplier_id]['without_brand'] += 1
            if len(products_without_brand) < 50:
                products_without_brand.append({
                    'product_id': product_id,
                    'name': product.get('name', 'N/A'),
                    'supplier_id': supplier_id
                })
    
    for stats in supplier_stats.values():
        if stats['total'] > 0:
            stats['brand_coverage_pct'] = round(100 * stats['with_brand'] / stats['total'], 1)
        else:
            stats['brand_coverage_pct'] = 0
    
    total_items = sum(s['total'] for s in supplier_stats.values())
    total_with_brand = sum(s['with_brand'] for s in supplier_stats.values())
    
    return {
        'overall': {
            'total_items': total_items,
            'with_brand': total_with_brand,
            'without_brand': total_items - total_with_brand,
            'brand_coverage_pct': round(100 * total_with_brand / max(total_items, 1), 1)
        },
        'by_supplier': supplier_stats,
        'sample_without_brand': products_without_brand[:20]
    }


def generate_search_failure_report(failed_searches: List[SearchDebugEvent]) -> dict:
    """Generate report of failed searches"""
    failure_reasons = {}
    failed_names = []
    
    for event in failed_searches:
        reason = event.failure_reason or 'unknown'
        failure_reasons[reason] = failure_reasons.get(reason, 0) + 1
        
        if event.reference_name and len(failed_names) < 50:
            failed_names.append({
                'name': event.reference_name,
                'brand_critical': event.brand_critical,
                'reason': reason,
                'phase': event.phase
            })
    
    sorted_reasons = sorted(failure_reasons.items(), key=lambda x: -x[1])
    
    return {
        'total_failures': len(failed_searches),
        'failure_reasons': dict(sorted_reasons),
        'sample_failed_searches': failed_names
    }


# Backward compatibility - keep old class name
TwoPhaseSearchEngine = EnhancedSearchEngine
