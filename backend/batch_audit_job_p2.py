#!/usr/bin/env python3
"""
P2 Batch Audit: Comprehensive system quality check
Генерирует отчёты о качестве данных и matching
"""
import os
import csv
import json
from pymongo import MongoClient
from datetime import datetime
from pathlib import Path

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

# Create audit directory
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
audit_dir = Path(f'/app/backend/audits/{timestamp}')
audit_dir.mkdir(parents=True, exist_ok=True)

print("=" * 80)
print("P2 BATCH AUDIT")
print("=" * 80)
print(f"Timestamp: {timestamp}")
print(f"Output: {audit_dir}")
print()

# Load all active supplier_items
print("📊 Loading supplier_items...")
items = list(db.supplier_items.find({'active': True}, {'_id': 0}))
print(f"   Total: {len(items)}")

# Statistics
stats = {
    'total': len(items),
    'with_product_core': 0,
    'with_super_class': 0,
    'with_brand': 0,
    'with_pack': 0,
    'with_unit_type': 0,
    'core_high_conf': 0,
    'core_medium_conf': 0,
    'core_low_conf': 0,
}

# Issue tracking
issues = {
    'no_product_core': [],
    'no_brand': [],
    'no_pack': [],
    'low_core_conf': [],
}

core_distribution = {}
super_class_distribution = {}

print("\n🔄 Analyzing items...")
for i, item in enumerate(items, 1):
    item_id = item['id']
    name_raw = item.get('name_raw', '')
    product_core = item.get('product_core_id')
    super_class = item.get('super_class')
    brand_id = item.get('brand_id')
    core_conf = item.get('product_core_conf', 0.0)
    
    # Pack info from unit_normalizer
    from unit_normalizer import parse_pack_from_text
    pack_info = parse_pack_from_text(name_raw)
    
    # Stats
    if product_core:
        stats['with_product_core'] += 1
        core_distribution[product_core] = core_distribution.get(product_core, 0) + 1
        
        if core_conf >= 0.8:
            stats['core_high_conf'] += 1
        elif core_conf >= 0.5:
            stats['core_medium_conf'] += 1
        else:
            stats['core_low_conf'] += 1
            issues['low_core_conf'].append({
                'id': item_id,
                'name': name_raw,
                'core': product_core,
                'conf': core_conf
            })
    else:
        issues['no_product_core'].append({'id': item_id, 'name': name_raw})
    
    if super_class:
        stats['with_super_class'] += 1
        super_class_distribution[super_class] = super_class_distribution.get(super_class, 0) + 1
    
    if brand_id:
        stats['with_brand'] += 1
    else:
        issues['no_brand'].append({'id': item_id, 'name': name_raw})
    
    if pack_info.base_qty:
        stats['with_pack'] += 1
    else:
        issues['no_pack'].append({'id': item_id, 'name': name_raw})
    
    if pack_info.unit_type.value != 'UNKNOWN':
        stats['with_unit_type'] += 1
    
    # Progress
    if i % 1000 == 0:
        print(f"   Progress: {i}/{len(items)} ({i*100//len(items)}%)")

# Generate reports
print("\n📝 Generating reports...")

# 1. audit_summary.json
summary = {
    'timestamp': timestamp,
    'database': DB_NAME,
    'total_items': stats['total'],
    'coverage': {
        'product_core': f"{stats['with_product_core']*100//stats['total']}%",
        'super_class': f"{stats['with_super_class']*100//stats['total']}%",
        'brand': f"{stats['with_brand']*100//stats['total']}%",
        'pack': f"{stats['with_pack']*100//stats['total']}%",
        'unit_type': f"{stats['with_unit_type']*100//stats['total']}%",
    },
    'product_core_confidence': {
        'high': stats['core_high_conf'],
        'medium': stats['core_medium_conf'],
        'low': stats['core_low_conf'],
    },
    'issues': {
        'no_product_core': len(issues['no_product_core']),
        'no_brand': len(issues['no_brand']),
        'no_pack': len(issues['no_pack']),
        'low_core_conf': len(issues['low_core_conf']),
    },
    'top_product_cores': sorted(core_distribution.items(), key=lambda x: -x[1])[:20],
}

with open(audit_dir / 'audit_summary.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)
print(f"   ✅ audit_summary.json")

# 2. supplier_items_audit.csv
with open(audit_dir / 'supplier_items_audit.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'name_raw', 'super_class', 'product_core_id', 'core_conf', 'brand_id', 'pack_base_qty', 'unit_type', 'issue_codes'])
    
    for item in items:
        from unit_normalizer import parse_pack_from_text
        pack_info = parse_pack_from_text(item.get('name_raw', ''))
        
        issue_codes = []
        if not item.get('product_core_id'):
            issue_codes.append('NO_CORE')
        if not item.get('brand_id'):
            issue_codes.append('NO_BRAND')
        if not pack_info.base_qty:
            issue_codes.append('NO_PACK')
        
        writer.writerow([
            item['id'],
            item.get('name_raw', ''),
            item.get('super_class', ''),
            item.get('product_core_id', ''),
            item.get('product_core_conf', 0.0),
            item.get('brand_id', ''),
            pack_info.base_qty or '',
            pack_info.unit_type.value,
            ','.join(issue_codes)
        ])
print(f"   ✅ supplier_items_audit.csv")

# 3. unit_mismatch_report.csv (NEW for P2)
with open(audit_dir / 'unit_mismatch_report.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['reference_id', 'reference_name', 'reference_unit', 'candidate_id', 'candidate_name', 'candidate_unit', 'mismatch_type'])
    # Placeholder - would need actual search simulation
print(f"   ✅ unit_mismatch_report.csv (placeholder)")

# 4. pack_outlier_report.csv (NEW for P2) - Items with very small packs
with open(audit_dir / 'pack_outlier_report.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['item_id', 'name_raw', 'pack_base_qty', 'unit_type', 'potential_packs_needed_for_1kg', 'issue'])
    
    from unit_normalizer import parse_pack_from_text
    outliers = []
    
    for item in items:
        pack_info = parse_pack_from_text(item.get('name_raw', ''))
        
        # Flag very small packs that could cause outliers (packs_needed > 20)
        if pack_info.base_qty:
            potential_packs = None
            issue = None
            
            if pack_info.unit_type.value == 'WEIGHT' and pack_info.base_qty < 50:  # < 50g
                potential_packs = int(1000 / pack_info.base_qty)  # For 1kg
                if potential_packs > 20:
                    issue = f'SMALL_PACK_HIGH_COUNT_{potential_packs}x'
                    outliers.append((item, pack_info, potential_packs, issue))
            elif pack_info.unit_type.value == 'VOLUME' and pack_info.base_qty < 50:  # < 50ml
                potential_packs = int(1000 / pack_info.base_qty)  # For 1L
                if potential_packs > 20:
                    issue = f'SMALL_VOLUME_HIGH_COUNT_{potential_packs}x'
                    outliers.append((item, pack_info, potential_packs, issue))
    
    # Sort by potential_packs descending
    outliers.sort(key=lambda x: -x[2])
    
    for item, pack_info, potential_packs, issue in outliers[:500]:  # Top 500
        writer.writerow([
            item['id'],
            item.get('name_raw', ''),
            pack_info.base_qty,
            pack_info.unit_type.value,
            potential_packs,
            issue
        ])
print(f"   ✅ pack_outlier_report.csv ({len(outliers)} outliers)")

# 5. low_core_confidence_report.csv
with open(audit_dir / 'low_core_confidence_report.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(['id', 'name_raw', 'product_core_id', 'confidence', 'super_class'])
    
    for issue in issues['low_core_conf'][:1000]:
        item = next((it for it in items if it['id'] == issue['id']), None)
        super_class = item.get('super_class', '') if item else ''
        writer.writerow([issue['id'], issue['name'], issue['core'], issue['conf'], super_class])
print(f"   ✅ low_core_confidence_report.csv ({len(issues['low_core_conf'])} items)")

# Print summary to console
print("\n" + "=" * 80)
print("📊 AUDIT SUMMARY")
print("=" * 80)
print(f"Total items: {stats['total']}")
print(f"\nData Coverage:")
print(f"  Product Core: {stats['with_product_core']} ({stats['with_product_core']*100//stats['total']}%)")
print(f"  Super Class: {stats['with_super_class']} ({stats['with_super_class']*100//stats['total']}%)")
print(f"  Brand: {stats['with_brand']} ({stats['with_brand']*100//stats['total']}%)")
print(f"  Pack: {stats['with_pack']} ({stats['with_pack']*100//stats['total']}%)")
print(f"  Unit Type: {stats['with_unit_type']} ({stats['with_unit_type']*100//stats['total']}%)")
print(f"\nProduct Core Confidence:")
print(f"  High (>=0.8): {stats['core_high_conf']} ({stats['core_high_conf']*100//stats['total']}%)")
print(f"  Medium (0.5-0.8): {stats['core_medium_conf']} ({stats['core_medium_conf']*100//stats['total']}%)")
print(f"  Low (<0.5): {stats['core_low_conf']} ({stats['core_low_conf']*100//stats['total']}%)")
print(f"\nIssues:")
print(f"  No product_core: {len(issues['no_product_core'])}")
print(f"  No brand: {len(issues['no_brand'])}")
print(f"  No pack: {len(issues['no_pack'])}")
print(f"  Low core conf: {len(issues['low_core_conf'])}")
print(f"\nTop 10 Product Cores:")
for core, count in sorted(core_distribution.items(), key=lambda x: -x[1])[:10]:
    print(f"  {core:40} | {count:4} items ({count*100//stats['total']:3}%)")

print(f"\n✅ Audit complete! Reports saved to: {audit_dir}")
