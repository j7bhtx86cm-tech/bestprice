"""Order Optimizer - Implements MVP logic for minimum orders, +10% top-up, and redistribution"""
from typing import Dict, List, Optional, Tuple
from collections import defaultdict
import logging

logger = logging.getLogger(__name__)

# Supplier minimum order amounts (per MVP requirements)
SUPPLIER_MIN_ORDERS = {
    'Интегрита': 7000,
    'default': 10000  # All other suppliers
}

def get_supplier_min_order(supplier_name: str) -> float:
    """Get minimum order amount for supplier"""
    return SUPPLIER_MIN_ORDERS.get(supplier_name, SUPPLIER_MIN_ORDERS['default'])


def optimize_order_with_minimums(
    orders_by_supplier: Dict[str, Dict],
    all_items_data: List[Dict],
    supplier_names: Dict[str, str]
) -> Tuple[Dict, Dict]:
    """Optimize order to meet supplier minimums
    
    Args:
        orders_by_supplier: {supplier_id: {'items': [...], 'total': float}}
        all_items_data: List of all available items with prices
        supplier_names: {supplier_id: supplier_name}
    
    Returns:
        (optimized_orders, stats)
    
    Per MVP logic:
    1. If supplier below minimum:
       - Try +10% top-up (increase qty or select larger packs)
       - If still below, try redistribution
       - If no benefit, exclude supplier
    """
    
    optimized = {}
    excluded_suppliers = []
    stats = {
        'topup_used': [],
        'redistributed': [],
        'excluded': []
    }
    
    # First pass: Check which suppliers are below minimum
    for supplier_id, order_data in orders_by_supplier.items():
        supplier_name = supplier_names.get(supplier_id, 'Unknown')
        min_order = get_supplier_min_order(supplier_name)
        current_total = order_data['total']
        
        if current_total >= min_order:
            # Already meets minimum
            optimized[supplier_id] = order_data
            continue
        
        # Below minimum - try +10% top-up
        max_topup_allowed = current_total * 0.10
        shortage = min_order - current_total
        
        if shortage <= max_topup_allowed:
            # Can reach minimum with +10% top-up
            # Try to increase quantities proportionally
            topup_items = []
            remaining_topup = max_topup_allowed
            
            for item in order_data['items']:
                if remaining_topup <= 0:
                    break
                
                # Increase quantity by 1 unit
                additional_cost = item['price']
                if additional_cost <= remaining_topup:
                    item['quantity'] += 1
                    remaining_topup -= additional_cost
                    topup_items.append(item['productName'])
            
            new_total = sum(i['price'] * i['quantity'] for i in order_data['items'])
            
            if new_total >= min_order:
                # Success with top-up!
                order_data['total'] = new_total
                optimized[supplier_id] = order_data
                stats['topup_used'].append({
                    'supplier': supplier_name,
                    'original': current_total,
                    'after_topup': new_total,
                    'added_items': topup_items
                })
                logger.info(f"✅ {supplier_name}: минималка достигнута через +10% ({current_total}₽ → {new_total}₽)")
                continue
        
        # +10% didn't work - try redistribution (TODO: complex logic)
        # For MVP, we'll just exclude the supplier
        excluded_suppliers.append(supplier_id)
        stats['excluded'].append({
            'supplier': supplier_name,
            'total': current_total,
            'minimum': min_order,
            'shortage': shortage
        })
        logger.warning(f"❌ {supplier_name}: исключен (сумма {current_total}₽ < минималки {min_order}₽)")
    
    return optimized, stats


def calculate_baseline_price(all_suppliers_prices: List[float]) -> float:
    """Calculate baseline for savings calculation
    
    Per MVP: 50% best + 50% third-best
    If no third supplier, use fallback
    """
    if not all_suppliers_prices:
        return 0
    
    sorted_prices = sorted(all_suppliers_prices)
    
    if len(sorted_prices) == 1:
        return sorted_prices[0]
    
    if len(sorted_prices) == 2:
        # Use average of two
        return (sorted_prices[0] + sorted_prices[1]) / 2
    
    # 50% best + 50% third
    best = sorted_prices[0]
    third = sorted_prices[2]
    
    return (best * 0.5) + (third * 0.5)
