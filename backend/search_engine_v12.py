"""
BestPrice Search Engine V12 - Production Ready

Implements the COMPLETE v12 specification:
1. Strict product_core_id guard (prevents кетчуп→вода)
2. Anchor terms guard (anti-jump protection)
3. Brand Critical OFF: COMPLETELY ignores brand_id
4. Brand Critical ON: Strict brand_id or origin matching
5. Pack ±20% tolerance (without x2 multiplier)
6. total_cost ranking (with qty and rounding)
7. step_qty handling (кратность)
8. Price status filtering (VALID only)
9. Null-safe (no 500 errors)

Usage:
    engine = SearchEngineV12()
    result = engine.search(reference_item, candidates, brand_critical=False, requested_qty=1.0)
"""
import logging
import re
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple
from pymongo import MongoClient
import os
import math

logger = logging.getLogger(__name__)


# ==================== HELPER FUNCTIONS ====================

def normalize_text(text: str) -> str:
    """Normalize text for matching"""
    if not text:
        return ""
    
    text = str(text).lower().strip()
    text = text.replace('ё', 'е')
    
    # Replace punctuation with spaces
    text = text.replace('"', ' ').replace("'", ' ').replace('«', ' ').replace('»', ' ')
    text = text.replace('.', ' ').replace(',', ' ').replace(';', ' ').replace(':', ' ')
    text = text.replace('/', ' ').replace('\\', ' ').replace('-', ' ').replace('_', ' ')
    
    # Remove other special chars
    text = re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)
    
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


def extract_tokens(text: str) -> set:
    """Extract meaningful tokens from text"""
    if not text:
        return set()
    
    norm = normalize_text(text)
    words = norm.split()
    
    # Filter out very short words and stop words
    stop_words = {'и', 'в', 'на', 'с', 'из', 'для', 'по', 'до', 'от', 'за', 'a', 'an', 'the', 'of', 'in', 'to'}
    
    tokens = {w for w in words if len(w) >= 2 and w not in stop_words}
    
    return tokens


def extract_pack_value(name: str) -> Optional[float]:
    """Extract pack value from product name (e.g., '800г' -> 0.8, '2л' -> 2.0)"""
    if not name:
        return None
    
    name = name.lower()
    
    # Pattern: number + unit
    patterns = [
        (r'(\d+[\.,]?\d*)\s*кг', 1.0),      # kg
        (r'(\d+[\.,]?\d*)\s*г', 0.001),     # g -> kg
        (r'(\d+[\.,]?\d*)\s*л', 1.0),       # l
        (r'(\d+[\.,]?\d*)\s*мл', 0.001),    # ml -> l
        (r'(\d+[\.,]?\d*)\s*шт', 1.0),      # pcs
    ]
    
    for pattern, multiplier in patterns:
        match = re.search(pattern, name)
        if match:
            try:
                value = float(match.group(1).replace(',', '.'))
                return value * multiplier
            except:
                continue
    
    return None


def is_pack_in_tolerance(ref_pack: Optional[float], cand_pack: Optional[float], tolerance_pct: float = 20) -> Tuple[bool, str]:
    """Check if candidate pack is within tolerance of reference pack
    
    Args:
        ref_pack: Reference pack value (e.g., 0.8 for 800g)
        cand_pack: Candidate pack value
        tolerance_pct: Tolerance percentage (default 20 for ±20%)
    
    Returns:
        (is_valid, reason)
    """
    if ref_pack is None or cand_pack is None:
        return (False, "pack_unknown")
    
    if ref_pack <= 0 or cand_pack <= 0:
        return (False, "pack_invalid")
    
    # Calculate bounds
    min_pack = ref_pack * (1 - tolerance_pct / 100)
    max_pack = ref_pack * (1 + tolerance_pct / 100)
    
    if min_pack <= cand_pack <= max_pack:
        return (True, "ok")
    elif cand_pack < min_pack:
        return (False, f"too_small_{cand_pack:.3f}<{min_pack:.3f}")
    else:
        return (False, f"too_large_{cand_pack:.3f}>{max_pack:.3f}")


# ==================== DATABASE ACCESS ====================

class V12DataLoader:
    """Loads v12 data from MongoDB (brands, aliases, seed_rules)"""
    
    def __init__(self):
        mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        self.client = MongoClient(mongo_url)
        self.db = self.client['bestprice']
        
        # Load data into memory
        self._load_brand_aliases()
        self._load_seed_rules()
    
    def _load_brand_aliases(self):
        """Load brand aliases into memory"""
        cursor = self.db.brand_aliases.find({}, {'_id': 0, 'alias_norm': 1, 'brand_id': 1})
        self.aliases = {doc['alias_norm']: doc['brand_id'] for doc in cursor if doc.get('alias_norm')}
        logger.info(f"Loaded {len(self.aliases)} brand aliases")
    
    def _load_seed_rules(self):
        """Load seed_dict_rules (product core classification)"""
        cursor = self.db.seed_dict_rules.find(
            {'action': {'$nin': ['удалить', 'skip']}},
            {'_id': 0, 'raw': 1, 'canonical': 1, 'type': 1}
        )
        self.seed_rules = {}
        self.product_cores = set()  # Core product categories
        
        for doc in cursor:
            raw = doc.get('raw', '')
            canonical = doc.get('canonical', '')
            rule_type = doc.get('type', '')
            
            if raw and canonical and canonical.lower() != 'nan':
                self.seed_rules[normalize_text(raw)] = {
                    'canonical': canonical,
                    'type': rule_type
                }
                
                # Collect core product categories (e.g., 'кетчуп', 'лосось')
                if rule_type in ['category', 'product', 'ingredient']:
                    self.product_cores.add(canonical.lower())
        
        logger.info(f"Loaded {len(self.seed_rules)} seed rules, {len(self.product_cores)} product cores")
    
    def detect_brand_id(self, product_name: str) -> Optional[str]:
        """Detect brand_id from product name using aliases"""
        if not product_name:
            return None
        
        name_norm = normalize_text(product_name)
        name_words = set(name_norm.split())
        
        # Sort aliases by length (longest first) for better matching
        sorted_aliases = sorted(self.aliases.items(), key=lambda x: len(x[0]), reverse=True)
        
        for alias_norm, brand_id in sorted_aliases:
            # For short aliases (< 4 chars), require exact word match
            if len(alias_norm) < 4:
                if alias_norm in name_words:
                    return brand_id
            else:
                # For longer aliases, check substring match at word boundary
                if alias_norm in name_norm:
                    pattern = r'(^|\s)' + re.escape(alias_norm) + r'($|\s)'
                    if re.search(pattern, name_norm):
                        return brand_id
        
        return None
    
    def get_anchor_terms(self, product_core_id: str) -> List[str]:
        """Get anchor terms (core_terms) for a product_core_id
        
        These are mandatory tokens that MUST appear in candidate products
        to prevent category jumping (e.g., кетчуп -> вода)
        """
        # For now, use the product_core_id itself as the anchor
        # In a more sophisticated system, this could be loaded from v12
        return [product_core_id.lower()] if product_core_id else []
    
    def determine_product_core_id(self, product_name: str) -> Optional[str]:
        """Determine product_core_id from product name
        
        Returns the PRIMARY category (e.g., 'кетчуп', 'лосось', 'креветки')
        """
        if not product_name:
            return None
        
        name_norm = normalize_text(product_name)
        name_words = name_norm.split()
        
        # Find matching rules
        matched_cores = []
        
        for term_norm, rule_info in self.seed_rules.items():
            canonical = rule_info['canonical']
            rule_type = rule_info['type']
            
            # Check if term appears in product name
            if term_norm in name_norm or term_norm in name_words:
                # Prioritize category/product types
                if rule_type in ['category', 'product', 'ingredient']:
                    matched_cores.append((canonical, len(term_norm)))
        
        if not matched_cores:
            return None
        
        # Return the longest match (most specific)
        matched_cores.sort(key=lambda x: x[1], reverse=True)
        return matched_cores[0][0]


# Global loader instance
_v12_loader = None

def get_v12_loader() -> V12DataLoader:
    """Get or create v12 data loader"""
    global _v12_loader
    if _v12_loader is None:
        _v12_loader = V12DataLoader()
    return _v12_loader


# ==================== SEARCH ENGINE V12 ====================

@dataclass
class SearchResultV12:
    """Result of search operation"""
    status: str  # "ok", "not_found", "insufficient_data", "error"
    failure_reason: Optional[str] = None
    
    # Selected offer (if status="ok")
    supplier_id: Optional[str] = None
    supplier_name: Optional[str] = None
    supplier_item_id: Optional[str] = None
    name_raw: Optional[str] = None
    price: Optional[float] = None
    price_per_base_unit: Optional[float] = None
    total_cost: Optional[float] = None
    need_packs: Optional[float] = None
    match_percent: Optional[float] = None
    
    # Debug info
    explanation: Dict[str, Any] = field(default_factory=dict)
    top_candidates: List[Dict[str, Any]] = field(default_factory=list)


class SearchEngineV12:
    """BestPrice Search Engine implementing full v12 specification"""
    
    def __init__(self):
        self.v12 = get_v12_loader()
        
        # Fresh categories where origin strict is allowed when brand_id is missing
        self.fresh_categories = {
            'рыба', 'морепродукты', 'seafood', 'fish',
            'мясо', 'птица', 'meat', 'poultry',
            'овощи', 'фрукты', 'vegetables', 'fruits',
            'молочка', 'сыр', 'dairy', 'cheese'
        }
    
    def search(
        self,
        reference_item: Dict[str, Any],
        candidates: List[Dict[str, Any]],
        brand_critical: bool = False,
        requested_qty: float = 1.0,
        company_map: Optional[Dict[str, str]] = None
    ) -> SearchResultV12:
        """Execute v12 search algorithm
        
        Args:
            reference_item: Reference product (from favorites)
                Required fields: name_raw, product_core_id
                Optional: brand_id, pack_value, origin_country, origin_region, origin_city
            candidates: List of supplier_item candidates (from pricelists)
                Required fields: id, name_raw, product_core_id, price, offer_status, price_status
                Optional: brand_id, pack_value, price_per_base_unit, step_qty
            brand_critical: If True, apply strict brand/origin filter
            requested_qty: Requested quantity for total_cost calculation
            company_map: supplier_id -> supplier_name mapping
        
        Returns:
            SearchResultV12 with status and selected offer (if found)
        """
        start_time = time.time()
        company_map = company_map or {}
        
        # Extract reference data
        ref_name = reference_item.get('name_raw', '')
        ref_product_core_id = reference_item.get('product_core_id')
        ref_brand_id = reference_item.get('brand_id')
        ref_pack = reference_item.get('pack_value')
        ref_pack_tolerance = reference_item.get('pack_tolerance_pct', 20)
        
        logger.info(f"🔍 V12 SEARCH: ref='{ref_name[:50]}', core={ref_product_core_id}, brand={ref_brand_id}, critical={brand_critical}")
        
        explanation = {
            'brand_critical': brand_critical,
            'filters_applied': [],
            'counts': {}
        }
        
        try:
            # ===== GUARD #0: Required data =====
            if not ref_name or not ref_product_core_id:
                return SearchResultV12(
                    status="insufficient_data",
                    failure_reason="no_product_name_or_core_id",
                    explanation=explanation
                )
            
            # ===== FILTER #1: Initial candidate query =====
            # Candidates must be: ACTIVE + VALID + same product_core_id
            initial_candidates = [
                c for c in candidates
                if c.get('offer_status') == 'ACTIVE' 
                and c.get('price_status') == 'VALID'
                and c.get('product_core_id') == ref_product_core_id
                and c.get('price', 0) > 0
            ]
            
            explanation['counts']['initial'] = len(candidates)
            explanation['counts']['after_product_core_guard'] = len(initial_candidates)
            explanation['filters_applied'].append(f"product_core_guard: {ref_product_core_id}")
            
            if not initial_candidates:
                return SearchResultV12(
                    status="not_found",
                    failure_reason="no_candidates_after_product_guard",
                    explanation=explanation
                )
            
            # ===== FILTER #2: Anchor terms guard (anti-jump) =====
            anchor_terms = self.v12.get_anchor_terms(ref_product_core_id)
            
            if anchor_terms:
                anchor_filtered = []
                for c in initial_candidates:
                    cand_tokens = extract_tokens(c.get('name_raw', ''))
                    cand_tokens_lower = {t.lower() for t in cand_tokens}
                    
                    # At least ONE anchor term must appear
                    has_anchor = any(anchor.lower() in cand_tokens_lower for anchor in anchor_terms)
                    
                    if has_anchor:
                        anchor_filtered.append(c)
                
                explanation['counts']['after_anchor_guard'] = len(anchor_filtered)
                explanation['filters_applied'].append(f"anchor_guard: {anchor_terms}")
                
                if not anchor_filtered:
                    return SearchResultV12(
                        status="not_found",
                        failure_reason="no_candidates_after_anchor_terms",
                        explanation=explanation
                    )
            else:
                anchor_filtered = initial_candidates
            
            # ===== FILTER #3: Brand Critical (if enabled) =====
            if brand_critical:
                brand_filtered = self._filter_brand_critical(
                    anchor_filtered,
                    reference_item,
                    explanation
                )
                
                if not brand_filtered:
                    return SearchResultV12(
                        status="not_found",
                        failure_reason="brand_strict_no_match",
                        explanation=explanation
                    )
            else:
                # Brand OFF: NO brand filtering at all
                brand_filtered = anchor_filtered
                explanation['filters_applied'].append("brand_filter: DISABLED (brand_critical=false)")
            
            explanation['counts']['after_brand_filter'] = len(brand_filtered)
            
            # ===== FILTER #4: Pack ±20% tolerance =====
            pack_filtered = []
            
            for c in brand_filtered:
                cand_pack = c.get('pack_value') or extract_pack_value(c.get('name_raw', ''))
                
                if ref_pack:
                    is_valid, reason = is_pack_in_tolerance(ref_pack, cand_pack, ref_pack_tolerance)
                    
                    if is_valid:
                        c['_pack_value'] = cand_pack
                        pack_filtered.append(c)
                else:
                    # If ref_pack unknown but candidate has price_per_base_unit, allow
                    if c.get('price_per_base_unit'):
                        c['_pack_value'] = cand_pack
                        pack_filtered.append(c)
            
            explanation['counts']['after_pack_filter'] = len(pack_filtered)
            if ref_pack:
                explanation['filters_applied'].append(f"pack_filter: ±{ref_pack_tolerance}%")
            else:
                explanation['filters_applied'].append("pack_filter: SKIPPED (ref_pack unknown)")
            
            if not pack_filtered:
                return SearchResultV12(
                    status="not_found",
                    failure_reason="insufficient_pack_data",
                    explanation=explanation
                )
            
            # ===== ECONOMICS: Calculate total_cost and rank =====
            scored = []
            
            for c in pack_filtered:
                item_pack = c.get('_pack_value', 1.0)
                item_price = c.get('price', 0)
                step_qty = c.get('step_qty')
                
                # Calculate required_base and need_packs
                if ref_pack and item_pack:
                    required_base = requested_qty * ref_pack
                    need_packs = math.ceil(required_base / item_pack)
                else:
                    # Fallback: use requested_qty directly
                    need_packs = requested_qty
                
                # Check step_qty (кратность)
                if step_qty and step_qty > 0:
                    if need_packs % step_qty != 0:
                        # Not кратен - skip this candidate
                        continue
                
                # Calculate total_cost
                total_cost = need_packs * item_price
                
                # Calculate price_per_base_unit
                if item_pack and item_pack > 0:
                    price_per_unit = item_price / item_pack
                else:
                    price_per_unit = item_price
                
                # Calculate simple match score (for logging)
                ref_tokens = extract_tokens(ref_name)
                cand_tokens = extract_tokens(c.get('name_raw', ''))
                common = ref_tokens & cand_tokens
                match_score = len(common) / len(ref_tokens) if len(ref_tokens) > 0 else 0
                
                scored.append({
                    'item': c,
                    'total_cost': total_cost,
                    'need_packs': need_packs,
                    'price_per_unit': price_per_unit,
                    'match_score': match_score
                })
            
            explanation['counts']['after_step_qty_filter'] = len(scored)
            
            if not scored:
                return SearchResultV12(
                    status="not_found",
                    failure_reason="step_qty_failed",
                    explanation=explanation
                )
            
            # ===== SELECT WINNER: min(total_cost) =====
            scored.sort(key=lambda x: (x['total_cost'], -x['match_score']))
            
            winner = scored[0]
            winner_item = winner['item']
            
            logger.info(f"✅ FOUND {len(scored)} candidates")
            logger.info(f"   Winner: {winner_item.get('name_raw', '')[:40]}")
            logger.info(f"   Total cost: {winner['total_cost']:.2f}₽ for {requested_qty} units")
            
            # Build response
            return SearchResultV12(
                status="ok",
                supplier_id=winner_item.get('supplierId'),
                supplier_name=company_map.get(winner_item.get('supplierId'), 'Unknown'),
                supplier_item_id=winner_item.get('id'),
                name_raw=winner_item.get('name_raw'),
                price=winner_item.get('price'),
                price_per_base_unit=winner['price_per_unit'],
                total_cost=winner['total_cost'],
                need_packs=winner['need_packs'],
                match_percent=winner['match_score'] * 100,
                explanation=explanation,
                top_candidates=[
                    {
                        'name_raw': s['item'].get('name_raw'),
                        'price': s['item'].get('price'),
                        'total_cost': s['total_cost'],
                        'supplier': company_map.get(s['item'].get('supplierId'), 'Unknown')
                    }
                    for s in scored[:5]
                ]
            )
            
        except Exception as e:
            logger.error(f"❌ SEARCH ERROR: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            
            return SearchResultV12(
                status="error",
                failure_reason=f"exception: {str(e)}",
                explanation=explanation
            )
    
    def _filter_brand_critical(
        self,
        candidates: List[Dict[str, Any]],
        reference_item: Dict[str, Any],
        explanation: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Apply brand critical filtering
        
        Logic:
        - If reference has brand_id -> strict filter by brand_id
        - If reference has NO brand but has origin -> strict filter by origin (ONLY for fresh categories)
        - Otherwise -> return empty (not_found)
        """
        brand_id = reference_item.get('brand_id')
        
        # Case 1: Has brand_id -> filter by brand
        if brand_id:
            brand_filtered = [
                c for c in candidates
                if c.get('brand_id') and c['brand_id'].lower() == brand_id.lower()
            ]
            explanation['filters_applied'].append(f"brand_filter: STRICT brand_id={brand_id}")
            return brand_filtered
        
        # Case 2: No brand, check origin (ONLY for fresh categories)
        product_core_id = reference_item.get('product_core_id', '')
        is_fresh = any(fresh in product_core_id.lower() for fresh in self.fresh_categories)
        
        if not is_fresh:
            explanation['filters_applied'].append("brand_filter: FAILED (no brand_id, not fresh category)")
            return []
        
        origin_country = reference_item.get('origin_country')
        origin_region = reference_item.get('origin_region')
        origin_city = reference_item.get('origin_city')
        
        if not origin_country:
            explanation['filters_applied'].append("brand_filter: FAILED (no brand_id, no origin)")
            return []
        
        # Filter by origin
        origin_filtered = []
        for c in candidates:
            cand_country = (c.get('origin_country') or '').lower().strip()
            cand_region = (c.get('origin_region') or '').lower().strip()
            cand_city = (c.get('origin_city') or '').lower().strip()
            
            # Country must match
            if cand_country != origin_country.lower().strip():
                continue
            
            # If reference has region, it must match
            if origin_region and cand_region != origin_region.lower().strip():
                continue
            
            # If reference has city, it must match
            if origin_city and cand_city != origin_city.lower().strip():
                continue
            
            origin_filtered.append(c)
        
        explanation['filters_applied'].append(f"origin_filter: STRICT {origin_country}/{origin_region or ''}/{origin_city or ''}")
        return origin_filtered


# ==================== MAIN ====================

if __name__ == '__main__':
    # Test v12 loader
    loader = get_v12_loader()
    print(f"✅ V12 Loader initialized")
    print(f"   Aliases: {len(loader.aliases)}")
    print(f"   Seed rules: {len(loader.seed_rules)}")
    print(f"   Product cores: {len(loader.product_cores)}")
    
    # Test brand detection
    print("\n🧪 Brand Detection Tests:")
    test_products = [
        "Кетчуп томатный 800 гр. Heinz",
        "КУКУРУЗА сладкая консервированная 425 мл. Lutik",
    ]
    
    for product in test_products:
        brand_id = loader.detect_brand_id(product)
        product_core_id = loader.determine_product_core_id(product)
        print(f"   '{product}'")
        print(f"      brand_id: {brand_id}, product_core_id: {product_core_id}")
