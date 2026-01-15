#!/usr/bin/env python3
"""
Comprehensive Testing of Best Price Matching Logic in /api/favorites
Tests caliber enforcement, weight tolerance, and type matching
"""

import requests
import json
import re
from typing import Dict, List, Optional

# Backend URL
BACKEND_URL = "https://bestprice-search-ui.preview.emergentagent.com/api"

# Test credentials
EMAIL = "customer@bestprice.ru"
PASSWORD = "password123"

class MatchingTestResult:
    def __init__(self):
        self.caliber_mismatches = []
        self.weight_violations = []
        self.type_mismatches = []
        self.correct_matches = []
        self.warnings = []
        
    def add_caliber_mismatch(self, original: str, found: str, original_caliber: str, found_caliber: str):
        self.caliber_mismatches.append({
            'original': original,
            'found': found,
            'original_caliber': original_caliber,
            'found_caliber': found_caliber
        })
    
    def add_weight_violation(self, original: str, found: str, original_weight: float, found_weight: float, diff_pct: float):
        self.weight_violations.append({
            'original': original,
            'found': found,
            'original_weight': original_weight,
            'found_weight': found_weight,
            'diff_pct': diff_pct
        })
    
    def add_type_mismatch(self, original: str, found: str, original_type: str, found_type: str):
        self.type_mismatches.append({
            'original': original,
            'found': found,
            'original_type': original_type,
            'found_type': found_type
        })
    
    def add_correct_match(self, original: str, found: str, weight_diff: Optional[float] = None):
        self.correct_matches.append({
            'original': original,
            'found': found,
            'weight_diff': weight_diff
        })
    
    def add_warning(self, message: str):
        self.warnings.append(message)
    
    def print_summary(self):
        print("\n" + "="*100)
        print("BEST PRICE MATCHING LOGIC TEST RESULTS")
        print("="*100)
        
        # Critical Issues First
        if self.caliber_mismatches:
            print("\n❌ CRITICAL: CALIBER MISMATCHES FOUND")
            print("-" * 100)
            for i, mismatch in enumerate(self.caliber_mismatches, 1):
                print(f"\n{i}. Original: {mismatch['original']}")
                print(f"   Caliber: {mismatch['original_caliber']}")
                print(f"   ❌ Matched with: {mismatch['found']}")
                print(f"   Caliber: {mismatch['found_caliber']}")
                print(f"   ⚠️ SHOULD NOT MATCH - Different calibers!")
        
        if self.weight_violations:
            print("\n❌ CRITICAL: WEIGHT TOLERANCE VIOLATIONS (>20%)")
            print("-" * 100)
            for i, violation in enumerate(self.weight_violations, 1):
                print(f"\n{i}. Original: {violation['original']}")
                print(f"   Weight: {violation['original_weight']:.3f} kg")
                print(f"   ❌ Matched with: {violation['found']}")
                print(f"   Weight: {violation['found_weight']:.3f} kg")
                print(f"   Difference: {violation['diff_pct']:.1f}% (EXCEEDS 20% LIMIT)")
        
        if self.type_mismatches:
            print("\n❌ CRITICAL: TYPE MISMATCHES FOUND")
            print("-" * 100)
            for i, mismatch in enumerate(self.type_mismatches, 1):
                print(f"\n{i}. Original: {mismatch['original']}")
                print(f"   Type: {mismatch['original_type']}")
                print(f"   ❌ Matched with: {mismatch['found']}")
                print(f"   Type: {mismatch['found_type']}")
                print(f"   ⚠️ SHOULD NOT MATCH - Different types!")
        
        # Warnings
        if self.warnings:
            print("\n⚠️ WARNINGS")
            print("-" * 100)
            for i, warning in enumerate(self.warnings, 1):
                print(f"{i}. {warning}")
        
        # Correct Matches
        if self.correct_matches:
            print("\n✅ CORRECT MATCHES")
            print("-" * 100)
            for i, match in enumerate(self.correct_matches, 1):
                weight_info = f" (weight diff: {match['weight_diff']:.1f}%)" if match['weight_diff'] is not None else ""
                print(f"{i}. {match['original']} → {match['found']}{weight_info}")
        
        # Summary Statistics
        print("\n" + "="*100)
        print("SUMMARY STATISTICS")
        print("="*100)
        total_tests = len(self.caliber_mismatches) + len(self.weight_violations) + len(self.type_mismatches) + len(self.correct_matches)
        print(f"Total Favorites Tested: {total_tests}")
        print(f"✅ Correct Matches: {len(self.correct_matches)} ({len(self.correct_matches)/total_tests*100:.1f}%)")
        print(f"❌ Caliber Mismatches: {len(self.caliber_mismatches)}")
        print(f"❌ Weight Violations: {len(self.weight_violations)}")
        print(f"❌ Type Mismatches: {len(self.type_mismatches)}")
        print(f"⚠️ Warnings: {len(self.warnings)}")
        
        critical_issues = len(self.caliber_mismatches) + len(self.weight_violations) + len(self.type_mismatches)
        if critical_issues == 0:
            print("\n🎉 ALL TESTS PASSED - No critical issues found!")
        else:
            print(f"\n⚠️ {critical_issues} CRITICAL ISSUES FOUND - Matching logic needs fixes")
        
        print("="*100 + "\n")

def login() -> Optional[str]:
    """Login and return token"""
    try:
        response = requests.post(
            f"{BACKEND_URL}/auth/login",
            json={"email": EMAIL, "password": PASSWORD},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            return data.get("access_token")
        else:
            print(f"❌ Login failed: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Login error: {e}")
        return None

def extract_caliber(name: str) -> Optional[str]:
    """Extract caliber like 16/20, 31/40, 4/5, 70/30, 90/10"""
    match = re.search(r'\b(\d{1,3})\s*/\s*(\d{1,3})\s*(?:\+)?\b', name)
    if match:
        return f"{match.group(1)}/{match.group(2)}"
    return None

def extract_weight_kg(text: str) -> Optional[float]:
    """Extract weight in kg from product name"""
    if not text:
        return None
    
    # Pattern 1: Weight range (300-400 гр) or (300/400)
    range_match = re.search(r'\(?(\d+)[-/](\d+)\)?[\s]*(гр|г|g)\b', text, re.IGNORECASE)
    if range_match:
        try:
            min_val = float(range_match.group(1))
            max_val = float(range_match.group(2))
            avg_val = (min_val + max_val) / 2
            return avg_val / 1000
        except:
            pass
    
    # Pattern 2: Weight in parentheses (300 гр)
    paren_match = re.search(r'\((\d+)\s*(?:гр|г|g)\)', text, re.IGNORECASE)
    if paren_match:
        try:
            return float(paren_match.group(1)) / 1000
        except:
            pass
    
    # Pattern 3: Direct weight mention
    matches = re.findall(r'(\d+(?:[.,]\d+)?)\s*(кг|kg|г|гр|g|мл|ml|л|l)\b', text, re.IGNORECASE)
    
    if not matches:
        return None
    
    weights_kg = []
    for num_str, unit in matches:
        try:
            num = float(num_str.replace(',', '.'))
            # Convert to kg/liters
            if unit.lower() in ['г', 'гр', 'g', 'мл', 'ml']:
                num = num / 1000
            weights_kg.append(num)
        except:
            continue
    
    if not weights_kg:
        return None
    
    # Prefer smaller weights (likely product size, not package)
    small_weights = [w for w in weights_kg if w <= 2.0]
    if small_weights:
        return min(small_weights)
    
    return min(weights_kg)

def extract_product_type(name_lower: str) -> str:
    """Extract product type"""
    # Ketchup types
    if 'кетчуп' in name_lower or 'ketchup' in name_lower:
        if 'дип' in name_lower or 'порц' in name_lower or 'dip' in name_lower:
            return 'кетчуп_порционный'
        return 'кетчуп'
    
    # Mushroom types
    if 'гриб' in name_lower or 'mushroom' in name_lower:
        if ('вешенк' in name_lower or 'oyster' in name_lower) and ('шампиньон' in name_lower or 'белые' in name_lower):
            return 'грибы_микс'
        elif 'вешенк' in name_lower:
            return 'грибы_вешенки'
        elif 'шампиньон' in name_lower:
            return 'грибы_шампиньоны'
        elif 'белые' in name_lower or 'белый' in name_lower:
            return 'грибы_белые'
        return 'грибы'
    
    # Meat with fat ratio
    if 'говядин' in name_lower or 'beef' in name_lower:
        if 'фарш' in name_lower or 'ground' in name_lower:
            return 'говядина_фарш'
        return 'говядина'
    
    # Seafood
    if 'креветк' in name_lower or 'shrimp' in name_lower:
        return 'креветки'
    if 'сибас' in name_lower or 'сибасс' in name_lower:
        return 'сибас'
    if 'лосось' in name_lower or 'семга' in name_lower:
        return 'лосось'
    if 'форель' in name_lower:
        return 'форель'
    if 'мидии' in name_lower:
        return 'мидии'
    
    # Dairy
    if 'молоко' in name_lower:
        return 'молоко'
    
    return name_lower.split()[0] if name_lower.split() else "unknown"

def test_favorites_matching(token: str) -> MatchingTestResult:
    """Test all favorites with mode='cheapest'"""
    result = MatchingTestResult()
    
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    
    print("\n" + "="*100)
    print("FETCHING FAVORITES WITH mode='cheapest'")
    print("="*100)
    
    try:
        response = requests.get(f"{BACKEND_URL}/favorites", headers=headers, timeout=30)
        
        if response.status_code != 200:
            print(f"❌ Failed to get favorites: {response.status_code}")
            return result
        
        favorites = response.json()
        print(f"\nFound {len(favorites)} favorites")
        
        # Filter only those with mode='cheapest' and hasCheaperMatch=true
        cheapest_favorites = [f for f in favorites if f.get('mode') == 'cheapest']
        print(f"Favorites with mode='cheapest': {len(cheapest_favorites)}")
        
        cheaper_matches = [f for f in cheapest_favorites if f.get('hasCheaperMatch') == True]
        print(f"Favorites with hasCheaperMatch=true: {len(cheaper_matches)}")
        
        print("\n" + "-"*100)
        print("ANALYZING EACH MATCH")
        print("-"*100)
        
        for i, fav in enumerate(cheaper_matches, 1):
            original_name = fav.get('productName', '')
            found_product = fav.get('foundProduct', {})
            found_name = found_product.get('name', '')
            
            print(f"\n[{i}] Testing: {original_name}")
            print(f"    Found: {found_name}")
            
            # Extract calibers
            original_caliber = extract_caliber(original_name)
            found_caliber = extract_caliber(found_name)
            
            # Test 1: Caliber Matching
            if original_caliber:
                print(f"    Original caliber: {original_caliber}")
                if found_caliber:
                    print(f"    Found caliber: {found_caliber}")
                    if original_caliber != found_caliber:
                        print(f"    ❌ CALIBER MISMATCH!")
                        result.add_caliber_mismatch(original_name, found_name, original_caliber, found_caliber)
                        continue
                    else:
                        print(f"    ✅ Caliber matches")
                else:
                    print(f"    ❌ Found product has NO caliber (should have {original_caliber})")
                    result.add_caliber_mismatch(original_name, found_name, original_caliber, "None")
                    continue
            
            # Extract weights
            original_weight = extract_weight_kg(original_name)
            found_weight = extract_weight_kg(found_name)
            
            # Test 2: Weight Tolerance (±20%)
            if original_weight and found_weight:
                weight_diff_pct = abs(original_weight - found_weight) / original_weight * 100
                print(f"    Original weight: {original_weight:.3f} kg")
                print(f"    Found weight: {found_weight:.3f} kg")
                print(f"    Weight difference: {weight_diff_pct:.1f}%")
                
                if weight_diff_pct > 20:
                    print(f"    ❌ WEIGHT TOLERANCE VIOLATION (>{20}%)")
                    result.add_weight_violation(original_name, found_name, original_weight, found_weight, weight_diff_pct)
                    continue
                else:
                    print(f"    ✅ Weight within tolerance")
            elif original_weight or found_weight:
                print(f"    ⚠️ Weight extraction mismatch:")
                print(f"       Original: {original_weight if original_weight else 'None'}")
                print(f"       Found: {found_weight if found_weight else 'None'}")
                result.add_warning(f"Weight extraction failed for: {original_name} → {found_name}")
            
            # Test 3: Type Matching
            original_type = extract_product_type(original_name.lower())
            found_type = extract_product_type(found_name.lower())
            
            print(f"    Original type: {original_type}")
            print(f"    Found type: {found_type}")
            
            if original_type != found_type:
                print(f"    ❌ TYPE MISMATCH!")
                result.add_type_mismatch(original_name, found_name, original_type, found_type)
                continue
            else:
                print(f"    ✅ Type matches")
            
            # If we got here, it's a correct match
            weight_diff = weight_diff_pct if (original_weight and found_weight) else None
            result.add_correct_match(original_name, found_name, weight_diff)
            print(f"    ✅ CORRECT MATCH")
        
        # Test favorites without cheaper matches
        no_match_favorites = [f for f in cheapest_favorites if f.get('hasCheaperMatch') == False]
        if no_match_favorites:
            print(f"\n\nFavorites with hasCheaperMatch=false: {len(no_match_favorites)}")
            for fav in no_match_favorites[:5]:  # Show first 5
                print(f"  - {fav.get('productName', '')}")
        
    except Exception as e:
        print(f"❌ Error testing favorites: {e}")
        import traceback
        traceback.print_exc()
    
    return result

def main():
    """Run comprehensive matching tests"""
    print("\n" + "="*100)
    print("BESTPRICE MARKETPLACE - FAVORITES MATCHING LOGIC COMPREHENSIVE TEST")
    print("Testing: Caliber Enforcement, Weight Tolerance (±20%), Type Matching")
    print("="*100)
    
    # Login
    print("\n[1] Logging in...")
    token = login()
    
    if not token:
        print("❌ Cannot proceed without authentication")
        return 1
    
    print("✅ Login successful")
    
    # Test favorites matching
    print("\n[2] Testing favorites matching logic...")
    result = test_favorites_matching(token)
    
    # Print summary
    result.print_summary()
    
    # Return exit code
    critical_issues = len(result.caliber_mismatches) + len(result.weight_violations) + len(result.type_mismatches)
    return 0 if critical_issues == 0 else 1

if __name__ == "__main__":
    exit(main())
