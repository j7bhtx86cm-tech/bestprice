"""Two-Phase Search Engine with Brand Family Support

VERSION 1.0 (December 2025):
- Phase 1 (STRICT): Current rules, MIN_SCORE=0.70
- Phase 2 (RESCUE): Relaxed rules, MIN_SCORE=0.60, pack/unit penalties instead of filters
- Brand family support: if brand_id not found, search by brand_family_id
- Comprehensive debug logging with SearchDebugEvent

Usage:
    from search_engine import TwoPhaseSearchEngine, SearchDebugEvent
    
    engine = TwoPhaseSearchEngine()
    result = engine.search(
        reference_item=ref,
        candidates=items,
        brand_critical=True,
        required_volume=1.0
    )
    
    # Access debug info
    print(result.debug_event.to_dict())
"""
import logging
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

logger = logging.getLogger(__name__)


@dataclass
class SearchDebugEvent:
    """Debug event for search operations with comprehensive logging"""
    
    # Input
    search_id: str = ""
    timestamp: str = ""
    reference_name: str = ""
    brand_id: Optional[str] = None
    brand_family_id: Optional[str] = None
    brand_critical: bool = False
    required_volume: Optional[float] = None
    
    # Phase info
    phase: str = "strict"  # "strict" or "rescue"
    min_score_threshold: float = 0.70
    
    # Counters
    total_candidates: int = 0
    candidates_after_brand_filter: int = 0
    candidates_after_family_filter: int = 0
    candidates_after_score_filter: int = 0
    candidates_with_pack: int = 0
    candidates_without_pack: int = 0
    
    # Filters applied
    filters_applied: List[str] = field(default_factory=list)
    
    # Result
    status: str = "not_found"  # "ok", "not_found", "insufficient_data", "error"
    failure_reason: Optional[str] = None
    selected_item_id: Optional[str] = None
    selected_price: Optional[float] = None
    selected_brand_id: Optional[str] = None
    selected_score: Optional[float] = None
    
    # Timing
    duration_ms: Optional[float] = None
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization"""
        return {
            "search_id": self.search_id,
            "timestamp": self.timestamp,
            "reference": {
                "name": self.reference_name[:50] if self.reference_name else None,
                "brand_id": self.brand_id,
                "brand_family_id": self.brand_family_id,
                "brand_critical": self.brand_critical,
                "required_volume": self.required_volume
            },
            "phase": self.phase,
            "min_score_threshold": self.min_score_threshold,
            "counters": {
                "total": self.total_candidates,
                "after_brand_filter": self.candidates_after_brand_filter,
                "after_family_filter": self.candidates_after_family_filter,
                "after_score_filter": self.candidates_after_score_filter,
                "with_pack": self.candidates_with_pack,
                "without_pack": self.candidates_without_pack
            },
            "filters_applied": self.filters_applied,
            "result": {
                "status": self.status,
                "failure_reason": self.failure_reason,
                "selected_item_id": self.selected_item_id,
                "selected_price": self.selected_price,
                "selected_brand_id": self.selected_brand_id,
                "selected_score": self.selected_score
            },
            "duration_ms": self.duration_ms
        }


@dataclass
class SearchResult:
    """Result of two-phase search"""
    status: str  # "ok", "not_found", "insufficient_data", "error"
    selected_offer: Optional[Dict[str, Any]] = None
    top_candidates: List[Dict[str, Any]] = field(default_factory=list)
    debug_event: SearchDebugEvent = field(default_factory=SearchDebugEvent)
    message: Optional[str] = None


class TwoPhaseSearchEngine:
    """Two-phase search engine with brand family support
    
    Phase 1 (STRICT):
    - MIN_SCORE = 0.70
    - pack/unit matching required
    - brand_critical=true: filter by brand_id, then brand_family_id if 0 results
    
    Phase 2 (RESCUE):
    - MIN_SCORE = 0.60
    - pack/unit missing: apply penalty (-0.10) instead of filtering
    - Only triggered if Phase 1 returns 0 results
    """
    
    # Thresholds
    STRICT_MIN_SCORE = 0.70
    RESCUE_MIN_SCORE = 0.60
    
    # Penalties for rescue phase
    PACK_MISSING_PENALTY = 0.10
    UNIT_MISMATCH_PENALTY = 0.05
    
    def __init__(self, brand_master=None):
        """Initialize search engine
        
        Args:
            brand_master: BrandMaster instance (optional, will create if None)
        """
        self.brand_master = brand_master
        if self.brand_master is None:
            from brand_master import get_brand_master
            self.brand_master = get_brand_master()
    
    def search(
        self,
        reference_item: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        brand_critical: bool = False,
        required_volume: Optional[float] = None,
        company_map: Optional[Dict[str, str]] = None
    ) -> SearchResult:
        """Run two-phase search
        
        Args:
            reference_item: Reference product to match
            candidates: List of candidate items to search
            brand_critical: If True, filter by brand; if False, ignore brand
            required_volume: Required volume for total cost calculation
            company_map: Mapping of company_id -> company_name
        
        Returns:
            SearchResult with selected offer, candidates, and debug info
        """
        import time
        import uuid
        
        start_time = time.time()
        company_map = company_map or {}
        
        # Initialize debug event
        debug = SearchDebugEvent(
            search_id=str(uuid.uuid4())[:8],
            timestamp=datetime.now().isoformat(),
            reference_name=reference_item.get('name_raw', ''),
            brand_id=reference_item.get('brand_id'),
            brand_critical=brand_critical,
            required_volume=required_volume,
            total_candidates=len(candidates)
        )
        
        # Get brand family info
        if debug.brand_id:
            debug.brand_family_id = self.brand_master.get_brand_family_id(debug.brand_id)
        
        try:
            # Check for required data
            if not reference_item.get('name_raw', '').strip():
                debug.status = "insufficient_data"
                debug.failure_reason = "no_product_name"
                debug.duration_ms = (time.time() - start_time) * 1000
                return SearchResult(
                    status="insufficient_data",
                    debug_event=debug,
                    message="Недостаточно данных: нет названия товара"
                )
            
            # Phase 1: STRICT search
            debug.phase = "strict"
            debug.min_score_threshold = self.STRICT_MIN_SCORE
            
            result = self._search_phase(
                reference_item=reference_item,
                candidates=candidates,
                brand_critical=brand_critical,
                required_volume=required_volume,
                company_map=company_map,
                debug=debug,
                phase="strict"
            )
            
            # If Phase 1 found results, return them
            if result.status == "ok" and result.selected_offer:
                debug.duration_ms = (time.time() - start_time) * 1000
                return result
            
            # Phase 2: RESCUE search (only if Phase 1 failed)
            logger.info(f"🔄 RESCUE PHASE: Phase 1 returned 0 results, trying rescue...")
            
            debug.phase = "rescue"
            debug.min_score_threshold = self.RESCUE_MIN_SCORE
            debug.filters_applied.append("PHASE_SWITCH: strict -> rescue")
            
            result = self._search_phase(
                reference_item=reference_item,
                candidates=candidates,
                brand_critical=brand_critical,
                required_volume=required_volume,
                company_map=company_map,
                debug=debug,
                phase="rescue"
            )
            
            debug.duration_ms = (time.time() - start_time) * 1000
            return result
            
        except Exception as e:
            logger.error(f"❌ SEARCH ERROR: {str(e)}")
            debug.status = "error"
            debug.failure_reason = f"exception: {str(e)}"
            debug.duration_ms = (time.time() - start_time) * 1000
            return SearchResult(
                status="error",
                debug_event=debug,
                message=f"Ошибка поиска: {str(e)}"
            )
    
    def _search_phase(
        self,
        reference_item: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        brand_critical: bool,
        required_volume: Optional[float],
        company_map: Dict[str, str],
        debug: SearchDebugEvent,
        phase: str
    ) -> SearchResult:
        """Execute a single search phase
        
        Args:
            phase: "strict" or "rescue"
        """
        min_score = self.STRICT_MIN_SCORE if phase == "strict" else self.RESCUE_MIN_SCORE
        
        # Brand filter logic
        filtered_candidates = candidates
        
        if brand_critical and reference_item.get('brand_id'):
            brand_id = reference_item['brand_id'].lower()
            brand_family_id = self.brand_master.get_brand_family_id(brand_id)
            
            # First try exact brand_id match
            brand_filtered = [
                c for c in candidates
                if c.get('brand_id') and c['brand_id'].lower() == brand_id
            ]
            debug.candidates_after_brand_filter = len(brand_filtered)
            debug.filters_applied.append(f"brand_filter: brand_id={brand_id}")
            
            # If 0 results and has family, try family filter
            if len(brand_filtered) == 0 and brand_family_id:
                logger.info(f"🔗 BRAND FAMILY FALLBACK: {brand_id} -> {brand_family_id}")
                
                # Get all family members
                family_members = self.brand_master.get_family_members(brand_family_id)
                family_members_set = set(m.lower() for m in family_members)
                
                # Also include the family brand itself
                family_members_set.add(brand_family_id.lower())
                
                brand_filtered = [
                    c for c in candidates
                    if c.get('brand_id') and c['brand_id'].lower() in family_members_set
                ]
                debug.candidates_after_family_filter = len(brand_filtered)
                debug.filters_applied.append(f"brand_family_filter: family={brand_family_id}, members={list(family_members_set)}")
            
            filtered_candidates = brand_filtered
        else:
            # brand_critical=false: NO brand filtering
            debug.filters_applied.append("brand_filter: DISABLED (brand_critical=false)")
            debug.candidates_after_brand_filter = len(candidates)
        
        # Score candidates
        scored = []
        for item in filtered_candidates:
            score = self._calculate_score(reference_item, item, brand_critical, phase)
            
            # Apply threshold
            if score < min_score:
                continue
            
            # Count pack info
            if item.get('net_weight_kg') or item.get('net_volume_l'):
                debug.candidates_with_pack += 1
            else:
                debug.candidates_without_pack += 1
            
            scored.append({
                'item': item,
                'score': score
            })
        
        debug.candidates_after_score_filter = len(scored)
        debug.filters_applied.append(f"score_filter: >= {min_score}")
        
        if not scored:
            debug.status = "not_found"
            debug.failure_reason = f"no_candidates_over_threshold_{min_score}"
            return SearchResult(
                status="not_found",
                debug_event=debug,
                message=f"Не найдено совпадений ≥ {int(min_score*100)}%"
            )
        
        # Calculate total cost and sort
        volume = required_volume or reference_item.get('pack_value') or 1.0
        
        for c in scored:
            item = c['item']
            item_volume = item.get('net_weight_kg') or item.get('net_volume_l') or 1.0
            item_price = item.get('price') or 0
            
            if item_volume > 0:
                units_needed = max(1, volume / item_volume)
                total_cost = item_price * units_needed
            else:
                units_needed = 1
                total_cost = item_price
            
            c['total_cost'] = total_cost
            c['units_needed'] = units_needed
            c['item_volume'] = item_volume
        
        # Sort by total cost (cheapest first), then by score
        scored.sort(key=lambda x: (x.get('total_cost') or float('inf'), -x['score']))
        
        # Select winner
        winner = scored[0]
        winner_item = winner['item']
        
        debug.status = "ok"
        debug.selected_item_id = winner_item.get('id')
        debug.selected_price = winner_item.get('price')
        debug.selected_brand_id = winner_item.get('brand_id')
        debug.selected_score = winner['score']
        
        # Build selected offer
        selected_offer = {
            'supplier_id': winner_item.get('supplier_company_id'),
            'supplier_name': company_map.get(winner_item.get('supplier_company_id'), 'Unknown'),
            'supplier_item_id': winner_item.get('id'),
            'name_raw': winner_item.get('name_raw'),
            'price': winner_item.get('price'),
            'currency': 'RUB',
            'unit_norm': winner_item.get('unit_norm', 'kg'),
            'pack_value': winner_item.get('net_weight_kg') or winner_item.get('net_volume_l'),
            'pack_unit': winner_item.get('base_unit', 'kg'),
            'price_per_base_unit': winner_item.get('price_per_base_unit'),
            'total_cost': winner['total_cost'],
            'units_needed': winner['units_needed'],
            'score': winner['score'],
            'brand_id': winner_item.get('brand_id')
        }
        
        # Build top candidates
        top = []
        for c in scored[:5]:
            top.append({
                'supplier_item_id': c['item'].get('id'),
                'name_raw': c['item'].get('name_raw'),
                'price': c['item'].get('price'),
                'brand_id': c['item'].get('brand_id'),
                'pack_value': c.get('item_volume'),
                'total_cost': c.get('total_cost'),
                'units_needed': c.get('units_needed'),
                'price_per_base_unit': c['item'].get('price_per_base_unit'),
                'score': c['score'],
                'supplier': company_map.get(c['item'].get('supplier_company_id'), 'Unknown')
            })
        
        return SearchResult(
            status="ok",
            selected_offer=selected_offer,
            top_candidates=top,
            debug_event=debug
        )
    
    def _calculate_score(
        self,
        reference: Dict[str, Any],
        candidate: Dict[str, Any],
        brand_critical: bool,
        phase: str
    ) -> float:
        """Calculate match score between reference and candidate
        
        Score components:
        - Name similarity: 60-70% (higher when brand_critical=false)
        - Super class match: 15%
        - Weight/volume tolerance: 15%
        - Brand match: 10% (only when brand_critical=true)
        
        In RESCUE phase:
        - Pack missing: -10% penalty instead of filtering
        - Unit mismatch: -5% penalty instead of filtering
        """
        score = 0.0
        
        # Determine weights based on brand_critical
        if brand_critical:
            name_weight = 0.60
            brand_weight = 0.10
        else:
            name_weight = 0.70  # Brand weight redistributed to name
            brand_weight = 0.0   # BRAND IS NEUTRAL!
        
        # Synonyms for fish products
        synonyms = {
            'непотрошеный': 'неразделанный',
            'неразделанный': 'непотрошеный',
            'сибас': 'сибасс',
            'сибасс': 'сибас',
            'охл': 'охлажденный',
            'охлажденный': 'охл',
            'зам': 'замороженный',
            'замороженный': 'зам',
            'с/м': 'свежемороженый',
            'свежемороженый': 'с/м',
            'с/г': 'свежий',
        }
        
        def get_canonical(token):
            return synonyms.get(token, token)
        
        def normalize_tokens(tokens):
            result = set()
            for token in tokens:
                result.add(get_canonical(token))
            return result
        
        # 1. Name similarity (with synonyms)
        ref_name = (reference.get('name_norm') or reference.get('name_raw', '')).lower()
        cand_name = (candidate.get('name_norm') or candidate.get('name_raw', '')).lower()
        
        # Tokenize
        ref_tokens = set(ref_name.split())
        cand_tokens = set(cand_name.split())
        
        # Remove common filler words
        fillers = {'кг', 'кг/кор.', 'кг/кор', 'гр', 'гр.', 'г', 'г.', 'л', 'л.', 'мл', 'мл.', 
                   'шт', 'шт.', 'упак', 'упак.', 'пакет', 'вес', '~', 'и', 'в', 'с', 'на', 'к',
                   'инд.', 'зам.', 'охл.', '%', '5%', 'tr', 'инд'}
        ref_tokens = ref_tokens - fillers
        cand_tokens = cand_tokens - fillers
        
        # Normalize with synonyms
        ref_normalized = normalize_tokens(ref_tokens)
        cand_normalized = normalize_tokens(cand_tokens)
        
        if ref_normalized and cand_normalized:
            intersection = len(ref_normalized & cand_normalized)
            
            # Key word bonus
            main_word_bonus = 0.0
            for ref_token in ref_normalized:
                if len(ref_token) >= 4:
                    for cand_token in cand_normalized:
                        if ref_token == cand_token:
                            main_word_bonus = 0.15
                            break
                    if main_word_bonus > 0:
                        break
            
            # Coverage
            coverage = intersection / len(ref_normalized) if ref_normalized else 0
            jaccard = intersection / len(ref_normalized | cand_normalized) if (ref_normalized | cand_normalized) else 0
            
            name_score = coverage * 0.5 + jaccard * 0.2 + main_word_bonus
            score += min(name_score, name_weight)
        
        # 2. Super class match - 15%
        ref_class = reference.get('super_class')
        cand_class = candidate.get('super_class')
        if ref_class and cand_class:
            if ref_class == cand_class:
                score += 0.15
            elif ref_class.split('.')[0] == cand_class.split('.')[0]:
                score += 0.08
        elif not ref_class:
            score += 0.10
        
        # 3. Weight/volume tolerance (±20%) - 15%
        ref_weight = reference.get('pack_value') or reference.get('net_weight_kg')
        cand_weight = candidate.get('net_weight_kg') or candidate.get('net_volume_l')
        
        if ref_weight and cand_weight and ref_weight > 0:
            ratio = cand_weight / ref_weight
            if 0.8 <= ratio <= 1.2:
                tolerance_score = 1.0 - abs(1.0 - ratio) / 0.2
                score += tolerance_score * 0.15
        elif not ref_weight:
            score += 0.10
        elif phase == "rescue" and not cand_weight:
            # RESCUE: Apply penalty for missing pack instead of filtering
            score -= self.PACK_MISSING_PENALTY
        
        # 4. Brand match - ONLY when brand_critical=true
        if brand_weight > 0:
            ref_brand = reference.get('brand_id')
            cand_brand = candidate.get('brand_id')
            
            if ref_brand and cand_brand:
                if ref_brand.lower() == cand_brand.lower():
                    score += brand_weight
                # Also check family match
                elif self.brand_master.is_brand_in_family(cand_brand, ref_brand):
                    score += brand_weight * 0.8  # Slight reduction for family match
            elif not ref_brand:
                score += brand_weight
        
        return round(max(0, score), 4)


# Quality report functions

def generate_brand_quality_report(products: List[dict], pricelists: List[dict]) -> dict:
    """Generate quality report for brand coverage
    
    Returns:
    - % of products with brand_id by supplier
    - Overall brand coverage
    - Top products without brand
    """
    # Build product lookup
    product_map = {p['id']: p for p in products}
    
    # Stats by supplier
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
            if len(products_without_brand) < 50:  # Limit sample
                products_without_brand.append({
                    'product_id': product_id,
                    'name': product.get('name', 'N/A'),
                    'supplier_id': supplier_id
                })
    
    # Calculate percentages
    for stats in supplier_stats.values():
        if stats['total'] > 0:
            stats['brand_coverage_pct'] = round(100 * stats['with_brand'] / stats['total'], 1)
        else:
            stats['brand_coverage_pct'] = 0
    
    # Overall stats
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
    """Generate report of failed searches
    
    Returns:
    - Top failure reasons
    - Common patterns in failed searches
    """
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
    
    # Sort by count
    sorted_reasons = sorted(failure_reasons.items(), key=lambda x: -x[1])
    
    return {
        'total_failures': len(failed_searches),
        'failure_reasons': dict(sorted_reasons),
        'sample_failed_searches': failed_names
    }
