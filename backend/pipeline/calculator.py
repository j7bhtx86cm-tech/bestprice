"""Price Per Base Unit Calculator (Routes A-E)"""
from typing import Dict, Optional, Tuple

def determine_base_unit(unit_norm: str, net_weight_kg: Optional[float], net_volume_l: Optional[float]) -> str:
    """Determine base unit for price comparison
    
    Rules:
    1. Weight exists → kg
    2. Volume exists → l
    3. Otherwise → pcs
    """
    if net_weight_kg and net_weight_kg > 0:
        return 'kg'
    if net_volume_l and net_volume_l > 0:
        return 'l'
    return 'pcs'

def calculate_price_per_base_unit(item: Dict) -> Tuple[Optional[float], str, bool]:
    """Calculate price_per_base_unit using Routes A-E
    
    Returns:
        (price_per_base_unit, calc_route, base_price_unknown)
    """
    price = item.get('price', 0)
    unit_norm = item.get('unit_norm', 'pcs')
    net_weight_kg = item.get('net_weight_kg')
    net_volume_l = item.get('net_volume_l')
    pack_qty = item.get('pack_qty')
    piece_weight_kg = item.get('piece_weight_kg')
    base_unit = item.get('base_unit', 'pcs')
    
    if price <= 0:
        return (None, '0', True)
    
    # Route A: unit = kg, direct price
    if unit_norm == 'kg':
        return (price, 'A', False)
    
    # Route B: unit = l, direct price
    if unit_norm == 'l':
        return (price, 'B', False)
    
    # Route A1: unit = g, convert to kg
    if unit_norm == 'g' and net_weight_kg:
        return (price / net_weight_kg, 'A1', False)
    
    # Route B1: unit = ml, convert to l
    if unit_norm == 'ml' and net_volume_l:
        return (price / net_volume_l, 'B1', False)
    
    # Route C: pcs + net_weight → price/kg
    if unit_norm in ['pcs', 'box'] and net_weight_kg and net_weight_kg > 0:
        if base_unit == 'kg':
            return (price / net_weight_kg, 'C', False)
        else:
            return (price, 'C_pcs', False)  # Price per piece
    
    # Route D: pcs + net_volume → price/l
    if unit_norm in ['pcs', 'box'] and net_volume_l and net_volume_l > 0:
        if base_unit == 'l':
            return (price / net_volume_l, 'D', False)
        else:
            return (price, 'D_pcs', False)
    
    # Route E: piece_weight × pack_qty
    if piece_weight_kg and pack_qty and pack_qty > 0:
        total_weight = piece_weight_kg * pack_qty
        if base_unit == 'kg' and total_weight > 0:
            return (price / total_weight, 'E', False)
    
    # Route 0: Insufficient data
    # For pcs without weight → can still be used for pcs-to-pcs comparison
    if unit_norm in ['pcs', 'box'] and base_unit == 'pcs':
        return (price, '0_pcs', False)  # Valid for pcs comparison
    
    return (None, '0', True)  # Unknown - cannot participate in kg/l comparison

def calculate_calc_confidence(calc_route: str, item: Dict) -> float:
    """Calculate confidence in price_per_base_unit (0..1)"""
    if calc_route in ['A', 'B']:
        return 1.0  # Direct unit match
    
    if calc_route in ['A1', 'B1']:
        return 0.95  # Simple conversion
    
    if calc_route == 'C':
        # pcs + weight
        if item.get('variable_weight'):
            return 0.7  # Variable weight reduces confidence
        return 0.9
    
    if calc_route in ['D', 'E']:
        return 0.85
    
    if calc_route in ['0_pcs', 'C_pcs', 'D_pcs']:
        return 0.8  # Pcs-to-pcs is valid but less confident
    
    return 0.0  # Route 0 - unknown
