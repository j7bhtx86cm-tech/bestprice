"""Main Processing Pipeline: Parse → Normalize → Enrich → Calculate → Publish"""
import logging
from typing import Dict, List, Optional
from datetime import datetime, timezone
from uuid import uuid4

from .normalizer import normalize_name, normalize_unit, extract_item_code
from .enricher import (
    extract_weights, extract_volumes, extract_packaging,
    extract_caliber, extract_fat_pct, extract_brand,
    extract_super_class, extract_processing_flags,
    extract_seafood_head_status, extract_cooking_state, extract_trim_grade
)
from .calculator import determine_base_unit, calculate_price_per_base_unit, calculate_calc_confidence

# Import brand master
try:
    from brand_master import brand_master
    BRAND_MASTER_LOADED = brand_master is not None
except:
    BRAND_MASTER_LOADED = False
    brand_master = None

logger = logging.getLogger(__name__)

def process_price_list_item(raw_item: Dict, supplier_company_id: str, price_list_id: str) -> Dict:
    """Process single price list row through full pipeline
    
    Args:
        raw_item: {
            'productName': str,
            'price': float,
            'unit': str,
            'article': str (optional),
            ...
        }
        supplier_company_id: str
        price_list_id: str
    
    Returns:
        Processed item ready for supplier_items collection
    """
    
    # STAGE 1: Parse (already done - we receive structured data)
    name_raw = raw_item.get('productName', '').strip()
    price = raw_item.get('price', 0)
    unit_supplier = raw_item.get('unit', 'pcs')
    article_supplier = raw_item.get('article', '')
    
    if not name_raw or price <= 0:
        logger.warning(f"Invalid item: name='{name_raw}', price={price}")
        return None
    
    # STAGE 2: Normalize
    name_cleaned, extracted_code = extract_item_code(name_raw)
    supplier_item_code = article_supplier or extracted_code
    
    name_norm = normalize_name(name_raw)
    unit_norm = normalize_unit(unit_supplier)
    
    # STAGE 3: Enrich (Feature Extraction)
    weight_data = extract_weights(name_raw)
    volume_data = extract_volumes(name_raw)
    pack_data = extract_packaging(name_raw)
    
    caliber = extract_caliber(name_raw)
    fat_pct = extract_fat_pct(name_raw)
    
    # NEW: Brand detection using BRAND MASTER (not heuristic!)
    brand = None
    brand_id = None
    brand_strict = False
    
    if BRAND_MASTER_LOADED:
        brand_id, brand_strict = brand_master.detect_brand(name_raw)
        if brand_id:
            brand_info = brand_master.get_brand_info(brand_id)
            brand = brand_info.get('brand_en') if brand_info else None
    
    # Fallback to old method only if brand_master not loaded
    if not brand and not BRAND_MASTER_LOADED:
        brand = extract_brand(name_raw)
    
    super_class = extract_super_class(name_norm)
    processing_flags = extract_processing_flags(name_norm)
    
    # NEW: Seafood-specific attributes (STRICT matching per MVP)
    seafood_head_status = extract_seafood_head_status(name_raw)
    cooking_state = extract_cooking_state(name_raw)
    trim_grade = extract_trim_grade(name_raw)
    
    # STAGE 4: Determine base_unit
    base_unit = determine_base_unit(
        unit_norm,
        weight_data.get('net_weight_kg'),
        volume_data.get('net_volume_l')
    )
    
    # Build intermediate item
    item = {
        'unit_norm': unit_norm,
        'base_unit': base_unit,
        'net_weight_kg': weight_data.get('net_weight_kg'),
        'net_volume_l': volume_data.get('net_volume_l'),
        'piece_weight_kg': weight_data.get('piece_weight_kg'),
        'variable_weight': weight_data.get('variable_weight', False),
        'pack_qty': pack_data.get('pack_qty'),
        'price': price
    }
    
    # STAGE 5: Calculate price_per_base_unit
    price_per_base, calc_route, base_price_unknown = calculate_price_per_base_unit(item)
    calc_confidence = calculate_calc_confidence(calc_route, item)
    
    # STAGE 6: Build final supplier_item
    supplier_item = {
        'id': str(uuid4()),
        'supplier_company_id': supplier_company_id,
        'price_list_id': price_list_id,
        'supplier_item_code': supplier_item_code,
        
        # Names
        'name_raw': name_raw,
        'name_norm': name_norm,
        
        # Units & Pricing
        'unit_supplier': unit_supplier,
        'unit_norm': unit_norm,
        'base_unit': base_unit,
        'price': price,
        'price_per_base_unit': price_per_base,
        'base_price_unknown': base_price_unknown,
        
        # Packaging & Weight
        'pack_qty': pack_data.get('pack_qty'),
        'net_weight_kg': weight_data.get('net_weight_kg'),
        'package_weight_kg': weight_data.get('package_weight_kg'),
        'net_volume_l': volume_data.get('net_volume_l'),
        'piece_weight_kg': weight_data.get('piece_weight_kg'),
        'variable_weight': weight_data.get('variable_weight', False),
        'bulk_package': weight_data.get('bulk_package', False),
        
        # Classification
        'super_class': super_class,
        'brand': brand,
        'fat_pct': fat_pct,
        'caliber': caliber,
        'processing_flags': processing_flags,
        
        # NEW: Seafood STRICT attributes (per MVP requirements)
        'seafood_head_status': seafood_head_status,
        'cooking_state': cooking_state,
        'trim_grade': trim_grade,
        
        # Technical
        'calc_route': calc_route,
        'calc_confidence': calc_confidence,
        'active': True,
        'updated_at': datetime.now(timezone.utc)
    }
    
    return supplier_item

def process_price_list(price_list_items: List[Dict], supplier_company_id: str, price_list_id: str) -> List[Dict]:
    """Process entire price list through pipeline
    
    Returns list of processed supplier_items ready for MongoDB
    """
    processed = []
    
    for i, raw_item in enumerate(price_list_items):
        try:
            item = process_price_list_item(raw_item, supplier_company_id, price_list_id)
            if item:
                processed.append(item)
        except Exception as e:
            logger.error(f"Error processing item {i}: {raw_item.get('productName', 'UNKNOWN')[:50]} - {e}")
            continue
    
    logger.info(f"Processed {len(processed)}/{len(price_list_items)} items")
    return processed
