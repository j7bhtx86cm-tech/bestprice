"""Scoring System (0-100, MIN_SCORE=70)"""
from typing import Dict, List
import difflib

MIN_SCORE = 50  # Lowered from 70 for better recall

def calculate_name_similarity(query_tokens: set, item_name_norm: str) -> float:
    """Name similarity score (0-60)"""
    item_tokens = set(item_name_norm.split())
    
    if not query_tokens or not item_tokens:
        return 0
    
    # Jaccard similarity on tokens
    intersection = query_tokens & item_tokens
    union = query_tokens | item_tokens
    
    if not union:
        return 0
    
    jaccard = len(intersection) / len(union)
    
    # Boost if all query tokens are present
    if query_tokens.issubset(item_tokens):
        jaccard = min(1.0, jaccard + 0.2)
    
    return jaccard * 60

def calculate_packaging_score(query: Dict, item: Dict) -> float:
    """Packaging similarity score (0-15)"""
    score = 0
    
    query_weight = query.get('target_weight_kg')
    item_weight = item.get('net_weight_kg')
    
    if query_weight and item_weight:
        diff = abs(query_weight - item_weight) / max(query_weight, item_weight)
        if diff <= 0.05:  # Within 5%
            score += 15
        elif diff <= 0.10:  # Within 10%
            score += 10
        elif diff <= 0.20:  # Within 20%
            score += 5
    
    return score

def calculate_brand_score(query: Dict, item: Dict) -> float:
    """Brand matching score (0-10)"""
    query_brand = query.get('brand')
    item_brand = item.get('brand')
    
    if not query_brand or not item_brand:
        return 0
    
    if query_brand.lower() == item_brand.lower():
        return 10
    
    # Partial match
    if query_brand.lower() in item_brand.lower() or item_brand.lower() in query_brand.lower():
        return 5
    
    return 0

def calculate_attributes_score(query: Dict, item: Dict) -> float:
    """Attributes score (0-15): caliber, fat%, processing flags"""
    score = 0
    
    # Caliber (critical - worth 10 points)
    query_cal = query.get('caliber')
    item_cal = item.get('caliber')
    
    if query_cal and item_cal:
        if query_cal == item_cal:
            score += 10
        else:
            score -= 20  # Heavy penalty for caliber mismatch
    
    # Fat percentage (worth 3 points)
    query_fat = query.get('fat_pct')
    item_fat = item.get('fat_pct')
    
    if query_fat and item_fat:
        diff = abs(query_fat - item_fat)
        if diff == 0:
            score += 3
        elif diff <= 5:
            score += 1
    
    # Processing flags (worth 2 points)
    query_flags = set(query.get('processing_flags', []))
    item_flags = set(item.get('processing_flags', []))
    
    if query_flags and item_flags:
        matching_flags = query_flags & item_flags
        if matching_flags:
            score += 2
    
    return score

def score_candidate(query: Dict, item: Dict) -> float:
    """Calculate total score (0-100)
    
    Breakdown:
    - Name similarity: 0-60
    - Packaging: 0-15
    - Brand: 0-10
    - Attributes: 0-15
    Total: 100
    """
    name_score = calculate_name_similarity(query['name_tokens'], item.get('name_norm', ''))
    pack_score = calculate_packaging_score(query, item)
    brand_score = calculate_brand_score(query, item)
    attr_score = calculate_attributes_score(query, item)
    
    total = name_score + pack_score + brand_score + attr_score
    return min(100, max(0, total))

def find_matches(query: Dict, candidates: List[Dict], top_n: int = 20) -> List[Dict]:
    """Score all candidates and return top matches
    
    Returns list of candidates with 'score' field added, sorted by score DESC
    """
    scored = []
    
    for item in candidates:
        score = score_candidate(query, item)
        
        if score >= MIN_SCORE:
            scored.append({
                **item,
                'match_score': score
            })
    
    # Sort by score descending
    scored.sort(key=lambda x: x['match_score'], reverse=True)
    
    return scored[:top_n]
