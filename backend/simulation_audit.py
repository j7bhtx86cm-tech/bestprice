#!/usr/bin/env python3
"""
Batch Audit Simulation: 500-1000 favorites
Симулирует поиск для всех favorites и собирает статистику
"""
import os
import csv
import json
from pymongo import MongoClient
from datetime import datetime
from pathlib import Path
from collections import Counter
import sys

# Add backend to path
sys.path.insert(0, '/app/backend')

from universal_super_class_mapper import detect_super_class
from product_core_classifier import detect_product_core
from unit_normalizer import parse_pack_from_text, calculate_packs_needed, UnitType

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

# Create audit directory
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
audit_dir = Path(f'/app/backend/audits/simulation_{timestamp}')
audit_dir.mkdir(parents=True, exist_ok=True)

print("=" * 80)
print("BATCH AUDIT SIMULATION: 500-1000 Favorites")
print("=" * 80)
print(f"Timestamp: {timestamp}")
print(f"Output: {audit_dir}")
print()

# Load favorites
print("📊 Loading favorites...")
favorites = list(db.favorites.find({}, {'_id': 0}).limit(1000))
print(f"   Total favorites: {len(favorites)}")

# Load all active supplier_items
print("📊 Loading supplier_items...")
supplier_items = list(db.supplier_items.find({'active': True}, {'_id': 0}))
print(f"   Total supplier_items: {len(supplier_items)}")

# Statistics
stats = {
    'total_favorites': len(favorites),
    'processed': 0,
    'found': 0,
    'not_found': 0,
    'core_not_detected': 0,
    'core_no_candidates': 0,
    'core_mismatch': 0,
    'unit_mismatch': 0,
    'pack_outlier': 0,
    'brand_not_found': 0,
    'other_not_found': 0,
}

# Detailed results
results = []
score_distribution = Counter()
packs_needed_distribution = Counter()

print("\n🔄 Simulating searches...")

for i, fav in enumerate(favorites[:500], 1):  # Limit to 500 for performance
    fav_id = fav.get('id', f'unknown_{i}')
    ref_name = fav.get('reference_name') or fav.get('productName', '')
    
    if not ref_name:
        stats['not_found'] += 1
        stats['other_not_found'] += 1
        continue
    
    # Step 1: Classify reference
    ref_super_class, conf_super = detect_super_class(ref_name)
    ref_product_core, conf_core = detect_product_core(ref_name, ref_super_class)
    ref_pack_info = parse_pack_from_text(ref_name)
    
    # Check if core is detectable
    if not ref_product_core or conf_core < 0.5:
        stats['not_found'] += 1
        stats['core_not_detected'] += 1
        results.append({
            'fav_id': fav_id,
            'ref_name': ref_name,
            'status': 'NOT_FOUND',
            'reason': 'CORE_NOT_DETECTED',
            'ref_product_core': ref_product_core,
            'ref_core_conf': conf_core,
        })
        continue
    
    # Step 2: Find candidates by product_core
    candidates = [
        item for item in supplier_items
        if item.get('product_core_id') == ref_product_core
        and item.get('price', 0) > 0
    ]
    
    if len(candidates) == 0:
        stats['not_found'] += 1
        stats['core_no_candidates'] += 1
        results.append({
            'fav_id': fav_id,
            'ref_name': ref_name,
            'status': 'NOT_FOUND',
            'reason': 'CORE_NO_CANDIDATES',
            'ref_product_core': ref_product_core,
        })
        continue
    
    # Step 3: Unit filtering + pack outlier
    compatible = []
    unit_mismatch_count = 0
    pack_outlier_count = 0
    
    for cand in candidates:
        cand_pack_info = parse_pack_from_text(cand.get('name_raw', ''))
        packs_needed, total_cost_mult, calc_reason = calculate_packs_needed(
            ref_pack_info, cand_pack_info
        )
        
        # Unit mismatch
        if "UNIT_MISMATCH" in calc_reason:
            unit_mismatch_count += 1
            continue
        
        # Pack outlier
        if packs_needed and packs_needed > 20:
            pack_outlier_count += 1
            continue
        
        compatible.append({
            'item': cand,
            'packs_needed': packs_needed,
            'total_cost_mult': total_cost_mult,
            'total_cost': cand.get('price', 0) * total_cost_mult if total_cost_mult else 999999
        })
    
    if len(compatible) == 0:
        stats['not_found'] += 1
        if unit_mismatch_count > 0:
            stats['unit_mismatch'] += 1
            reason = 'UNIT_MISMATCH_ALL_REJECTED'
        else:
            stats['pack_outlier'] += 1
            reason = 'PACK_OUTLIER_ALL_REJECTED'
        
        results.append({
            'fav_id': fav_id,
            'ref_name': ref_name,
            'status': 'NOT_FOUND',
            'reason': reason,
            'ref_product_core': ref_product_core,
            'candidates_before_filter': len(candidates),
            'unit_mismatch_count': unit_mismatch_count,
            'pack_outlier_count': pack_outlier_count,
        })
        continue
    
    # Step 4: Ranking by total_cost
    compatible.sort(key=lambda x: x['total_cost'])
    winner_data = compatible[0]
    winner = winner_data['item']
    packs_needed = winner_data['packs_needed']
    
    # Step 5: CORE_MISMATCH check
    winner_core = winner.get('product_core_id')
    if winner_core != ref_product_core:
        stats['not_found'] += 1
        stats['core_mismatch'] += 1
        results.append({
            'fav_id': fav_id,
            'ref_name': ref_name,
            'status': 'NOT_FOUND',
            'reason': 'CORE_MISMATCH',
            'ref_product_core': ref_product_core,
            'winner_product_core': winner_core,
            'winner_name': winner.get('name_raw', ''),
        })
        continue
    
    # SUCCESS
    stats['found'] += 1
    stats['processed'] += 1
    
    # Calculate score (simplified)
    base_score = 60 + 20 + 10  # core + guards + base
    if packs_needed == 1:
        pack_penalty = 0
    elif packs_needed <= 5:
        pack_penalty = 10
    elif packs_needed <= 10:
        pack_penalty = 15
    else:
        pack_penalty = 25
    
    final_score = max(0, min(100, base_score - pack_penalty))
    score_distribution[final_score] += 1
    
    if packs_needed:
        packs_needed_distribution[min(packs_needed, 21)] += 1  # Cap at 21 for display
    
    results.append({
        'fav_id': fav_id,
        'ref_name': ref_name,
        'status': 'FOUND',
        'ref_product_core': ref_product_core,
        'winner_name': winner.get('name_raw', ''),
        'winner_core': winner_core,
        'price': winner.get('price'),
        'packs_needed': packs_needed,
        'total_cost': winner_data['total_cost'],
        'score': final_score,
        'candidates_count': len(candidates),
        'after_filter_count': len(compatible),
    })
    
    # Progress
    if i % 50 == 0:
        print(f"   Progress: {i}/500 ({i*2}%)")

stats['processed'] = len(results)

# Generate reports
print("\n📝 Generating reports...")

# 1. simulation_summary.json
summary = {
    'timestamp': timestamp,
    'total_favorites': stats['total_favorites'],
    'processed': stats['processed'],
    'success_rate': f"{stats['found']*100//stats['processed']:.1f}%" if stats['processed'] > 0 else "0%",
    'found': stats['found'],
    'not_found': stats['not_found'],
    'not_found_breakdown': {
        'core_not_detected': stats['core_not_detected'],
        'core_no_candidates': stats['core_no_candidates'],
        'core_mismatch': stats['core_mismatch'],
        'unit_mismatch': stats['unit_mismatch'],
        'pack_outlier': stats['pack_outlier'],
        'other': stats['other_not_found'],
    },
    'score_distribution': dict(sorted(score_distribution.items())),
    'packs_needed_distribution': dict(sorted(packs_needed_distribution.items())),
}

with open(audit_dir / 'simulation_summary.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"   ✅ simulation_summary.json")

# 2. simulation_results.csv
with open(audit_dir / 'simulation_results.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=[
        'fav_id', 'ref_name', 'status', 'reason', 'ref_product_core', 
        'winner_name', 'winner_core', 'price', 'packs_needed', 'total_cost', 
        'score', 'candidates_count', 'after_filter_count'
    ])
    writer.writeheader()
    for result in results:
        writer.writerow({k: result.get(k, '') for k in writer.fieldnames})
print(f"   ✅ simulation_results.csv")

# Print summary
print("\n" + "=" * 80)
print("📊 SIMULATION SUMMARY")
print("=" * 80)
print(f"Total favorites: {stats['total_favorites']}")
print(f"Processed: {stats['processed']}")
print(f"\nResults:")
print(f"  Found: {stats['found']} ({stats['found']*100//stats['processed']:.1f}%)" if stats['processed'] > 0 else "  Found: 0")
print(f"  Not Found: {stats['not_found']} ({stats['not_found']*100//stats['processed']:.1f}%)" if stats['processed'] > 0 else "  Not Found: 0")
print(f"\nNOT_FOUND Breakdown:")
print(f"  CORE_NOT_DETECTED: {stats['core_not_detected']}")
print(f"  CORE_NO_CANDIDATES: {stats['core_no_candidates']}")
print(f"  CORE_MISMATCH: {stats['core_mismatch']}")
print(f"  UNIT_MISMATCH: {stats['unit_mismatch']}")
print(f"  PACK_OUTLIER: {stats['pack_outlier']}")
print(f"  Other: {stats['other_not_found']}")

print(f"\nScore Distribution (FOUND only):")
for score in sorted(score_distribution.keys(), reverse=True):
    count = score_distribution[score]
    bar = '█' * (count * 50 // max(score_distribution.values()))
    print(f"  {score:3d}: {count:3d} {bar}")

print(f"\nPacks Needed Distribution (FOUND only):")
for packs in sorted(packs_needed_distribution.keys()):
    count = packs_needed_distribution[packs]
    bar = '█' * (count * 50 // max(packs_needed_distribution.values()))
    display_packs = f"{packs}+" if packs == 21 else str(packs)
    print(f"  {display_packs:3s}: {count:3d} {bar}")

print(f"\n✅ Simulation complete! Reports saved to: {audit_dir}")
