#!/usr/bin/env python3
"""
Detailed Test of Best Price Matching Logic
Analyzes existing favorites to verify weight tolerance and type matching
"""

import requests
import json

BACKEND_URL = "https://orderflow-fix-5.preview.emergentagent.com/api"
EMAIL = "customer@bestprice.ru"
PASSWORD = "password123"

def login():
    response = requests.post(
        f"{BACKEND_URL}/auth/login",
        json={"email": EMAIL, "password": PASSWORD},
        timeout=10
    )
    if response.status_code == 200:
        return response.json()["access_token"]
    return None

def get_favorites(token):
    headers = {"Authorization": f"Bearer {token}"}
    response = requests.get(f"{BACKEND_URL}/favorites", headers=headers, timeout=10)
    if response.status_code == 200:
        return response.json()
    return []

def extract_weight_from_name(name):
    """Extract weight in kg from product name"""
    import re
    
    # Pattern 1: Range (300-400 гр)
    range_match = re.search(r'\(?(\d+)[-/](\d+)\)?[\s]*(гр|г|g)\b', name, re.IGNORECASE)
    if range_match:
        min_val = float(range_match.group(1))
        max_val = float(range_match.group(2))
        avg_val = (min_val + max_val) / 2
        return avg_val / 1000
    
    # Pattern 2: Direct weight
    matches = re.findall(r'(\d+(?:[.,]\d+)?)\s*(кг|kg|г|гр|g|мл|ml)\b', name, re.IGNORECASE)
    
    if not matches:
        return None
    
    weights_kg = []
    for num_str, unit in matches:
        num = float(num_str.replace(',', '.'))
        if unit.lower() in ['г', 'гр', 'g', 'мл', 'ml']:
            num = num / 1000
        weights_kg.append(num)
    
    if not weights_kg:
        return None
    
    # Prefer smaller weights (likely product size, not package)
    small_weights = [w for w in weights_kg if w <= 2.0]
    if small_weights:
        return min(small_weights)
    
    return min(weights_kg)

def calculate_weight_diff(weight1, weight2):
    """Calculate weight difference percentage"""
    if not weight1 or not weight2:
        return None
    return abs(weight1 - weight2) / weight1

def main():
    print("="*80)
    print("DETAILED BEST PRICE MATCHING ANALYSIS")
    print("="*80)
    
    token = login()
    if not token:
        print("❌ Login failed")
        return 1
    
    print("✅ Logged in successfully\n")
    
    favorites = get_favorites(token)
    print(f"Found {len(favorites)} favorites\n")
    
    passed = []
    failed = []
    
    # Analyze each favorite
    for i, fav in enumerate(favorites, 1):
        product_name = fav.get('productName', 'N/A')
        mode = fav.get('mode', 'N/A')
        original_price = fav.get('originalPrice', 0)
        best_price = fav.get('bestPrice', 0)
        has_cheaper = fav.get('hasCheaperMatch', False)
        
        print(f"\n{'='*80}")
        print(f"FAVORITE #{i}: {product_name}")
        print(f"{'='*80}")
        print(f"Mode: {mode}")
        print(f"Original Price: {original_price} ₽")
        print(f"Best Price: {best_price} ₽")
        print(f"Has Cheaper Match: {has_cheaper}")
        
        if mode != 'cheapest':
            print("⚠️ SKIPPED: Not in cheapest mode")
            continue
        
        if has_cheaper:
            found_product = fav.get('foundProduct', {})
            found_name = found_product.get('name', 'N/A')
            found_price = found_product.get('price', 0)
            found_weight = found_product.get('weight')
            
            print(f"\nFound Product: {found_name}")
            print(f"Found Price: {found_price} ₽")
            print(f"Found Weight (from API): {found_weight} kg")
            
            # Extract weights from names
            original_weight = extract_weight_from_name(product_name)
            found_weight_extracted = extract_weight_from_name(found_name)
            
            print(f"\nWeight Analysis:")
            print(f"  Original Weight (extracted): {original_weight} kg")
            print(f"  Found Weight (extracted): {found_weight_extracted} kg")
            
            if original_weight and found_weight_extracted:
                weight_diff = calculate_weight_diff(original_weight, found_weight_extracted)
                weight_diff_pct = weight_diff * 100 if weight_diff else 0
                print(f"  Weight Difference: {weight_diff_pct:.1f}%")
                
                # Check if weight difference is within 20% tolerance
                if weight_diff and weight_diff > 0.20:
                    print(f"\n❌ CRITICAL BUG: Weight difference {weight_diff_pct:.1f}% exceeds 20% tolerance!")
                    print(f"   Should NOT match these products:")
                    print(f"   - Original: {product_name} ({original_weight} kg)")
                    print(f"   - Found: {found_name} ({found_weight_extracted} kg)")
                    failed.append({
                        'favorite': i,
                        'issue': f'Weight difference {weight_diff_pct:.1f}% > 20%',
                        'original': product_name,
                        'found': found_name
                    })
                else:
                    print(f"\n✅ CORRECT: Weight difference {weight_diff_pct:.1f}% is within 20% tolerance")
                    passed.append({
                        'favorite': i,
                        'original': product_name,
                        'found': found_name,
                        'weight_diff': weight_diff_pct
                    })
            else:
                print(f"\n⚠️ WARNING: Could not extract weights for comparison")
                print(f"   Original weight: {original_weight}")
                print(f"   Found weight: {found_weight_extracted}")
            
            # Check price
            if found_price >= original_price:
                print(f"\n❌ CRITICAL BUG: Found price ({found_price} ₽) is NOT cheaper than original ({original_price} ₽)")
                failed.append({
                    'favorite': i,
                    'issue': f'Found price {found_price} ₽ >= original {original_price} ₽',
                    'original': product_name,
                    'found': found_name
                })
            else:
                savings = original_price - found_price
                savings_pct = (savings / original_price) * 100
                print(f"\n✅ CORRECT: Found cheaper price - savings: {savings:.2f} ₽ ({savings_pct:.1f}%)")
        
        else:
            fallback = fav.get('fallbackMessage', '')
            print(f"\nNo cheaper match found")
            if fallback:
                print(f"Fallback Message: {fallback}")
            print(f"\n✅ CORRECT: No cheaper alternatives available or current price is best")
    
    # Print summary
    print("\n" + "="*80)
    print("SUMMARY")
    print("="*80)
    
    if failed:
        print(f"\n❌ CRITICAL BUGS FOUND: {len(failed)}")
        for bug in failed:
            print(f"\n  Favorite #{bug['favorite']}: {bug['issue']}")
            print(f"    Original: {bug['original']}")
            print(f"    Found: {bug['found']}")
    
    if passed:
        print(f"\n✅ CORRECT MATCHES: {len(passed)}")
        for match in passed:
            print(f"\n  Favorite #{match['favorite']}: Weight diff {match['weight_diff']:.1f}%")
            print(f"    Original: {match['original']}")
            print(f"    Found: {match['found']}")
    
    print("\n" + "="*80)
    print(f"Total: {len(passed)} correct, {len(failed)} bugs")
    print("="*80)
    
    return 0 if len(failed) == 0 else 1

if __name__ == "__main__":
    exit(main())
