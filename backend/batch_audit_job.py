"""
BATCH AUDIT JOB - Complete Analysis of 8,218 supplier_items

Performs comprehensive audit:
1. Data Quality Audit - checks each item
2. Matching Audit - simulates search
3. Bad Matches Detection - автовыявление проблем

Output: CSV и JSON отчёты в /app/backend/audits/<timestamp>/
"""
import os
import sys
import csv
import json
from pymongo import MongoClient
from collections import Counter
from datetime import datetime
import re

# Create audit directory
timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
AUDIT_DIR = f'/app/backend/audits/{timestamp}'
os.makedirs(AUDIT_DIR, exist_ok=True)

DB_NAME = os.environ.get('DB_NAME', 'test_database')
db = MongoClient(os.environ.get('MONGO_URL'))[DB_NAME]

print("="*120)
print(f"🔍 BATCH AUDIT JOB - Full Analysis")
print("="*120)
print(f"Output directory: {AUDIT_DIR}\n")

# Load data
all_items = list(db.supplier_items.find({'active': True}, {'_id': 0}))
total = len(all_items)

print(f"Loaded {total} ACTIVE supplier_items")

# Import audit functions
from universal_super_class_mapper import detect_super_class
from p0_hotfix_stabilization import (
    parse_pack_value,
    has_negative_keywords,
    load_brand_aliases,
    extract_brand_from_text
)

brand_aliases = load_brand_aliases()

# ==================== 1) DATA QUALITY AUDIT ====================
print(f"\n{'='*120}")
print("1️⃣ DATA QUALITY AUDIT (каждый supplier_item)")
print("="*120)

data_quality_results = []
issue_codes_counter = Counter()

for i, item in enumerate(all_items):
    if (i + 1) % 1000 == 0:
        print(f"   Progress: {i + 1}/{total}")
    
    item_id = item.get('id')
    name_raw = item.get('name_raw', '')
    name_norm = item.get('name_norm', '')
    super_class_db = item.get('super_class')
    brand_id_db = item.get('brand_id')
    price = item.get('price', 0)
    
    # Detect super_class at runtime
    super_class_runtime, sc_conf = detect_super_class(name_raw)
    
    # Parse pack
    pack_runtime = parse_pack_value(name_raw)
    pack_db = item.get('net_weight_kg') or item.get('net_volume_l')
    
    # Extract brand from text
    brand_from_text = extract_brand_from_text(name_raw, brand_aliases)
    
    # Collect data issues
    data_issues = []
    
    if super_class_db == 'other':
        data_issues.append('SUPER_CLASS_OTHER')
        issue_codes_counter['SUPER_CLASS_OTHER'] += 1
    
    if not super_class_db:
        data_issues.append('NO_SUPER_CLASS')
        issue_codes_counter['NO_SUPER_CLASS'] += 1
    
    if not pack_db:
        data_issues.append('NO_PACK')
        issue_codes_counter['NO_PACK'] += 1
    
    if not brand_id_db and not brand_from_text:
        data_issues.append('NO_BRAND')
        issue_codes_counter['NO_BRAND'] += 1
    
    if price <= 0:
        data_issues.append('INVALID_PRICE')
        issue_codes_counter['INVALID_PRICE'] += 1
    
    # Check negative keywords
    if super_class_db:
        has_neg, neg_kw = has_negative_keywords(name_raw, super_class_db)
        if has_neg:
            data_issues.append(f'NEGATIVE_KEYWORD_{neg_kw}')
            issue_codes_counter[f'NEGATIVE_KEYWORD'] += 1
    
    data_quality_results.append({
        'supplier_item_id': item_id,
        'supplier_id': item.get('supplier_company_id'),
        'name_raw': name_raw[:100],
        'name_norm': name_norm[:100],
        'super_class_db': super_class_db,
        'super_class_runtime': super_class_runtime,
        'sc_confidence': round(sc_conf, 2) if sc_conf else 0,
        'brand_id_db': brand_id_db or '',
        'brand_from_text': brand_from_text or '',
        'pack_db': pack_db or '',
        'pack_runtime': pack_runtime or '',
        'price': price,
        'data_issues': '|'.join(data_issues) if data_issues else 'OK'
    })

# Save data quality audit
print(f"\n   Saving supplier_items_audit.csv...")
with open(f'{AUDIT_DIR}/supplier_items_audit.csv', 'w', newline='', encoding='utf-8') as f:
    writer = csv.DictWriter(f, fieldnames=data_quality_results[0].keys())
    writer.writeheader()
    writer.writerows(data_quality_results)

print(f"   ✅ Saved {len(data_quality_results)} records")

# ==================== 2) MATCHING AUDIT ====================
print(f"\n{'='*120}")
print("2️⃣ MATCHING AUDIT (симуляция поиска)")
print("="*120)

matching_results = []
not_found_reasons = Counter()

# Sample 1000 items for matching (full 8800 would be slow)
sample_items = all_items[::8]  # Every 8th item
print(f"Sampling {len(sample_items)} items for matching simulation...")

for i, ref_item in enumerate(sample_items):
    if (i + 1) % 100 == 0:
        print(f"   Progress: {i + 1}/{len(sample_items)}")
    
    ref_name = ref_item.get('name_raw', '')
    ref_super_class, conf = detect_super_class(ref_name)
    
    if not ref_super_class:
        matching_results.append({
            'reference_name': ref_name[:100],
            'status': 'not_found',
            'reason_code': 'INSUFFICIENT_CLASSIFICATION',
            'candidates_total': len(all_items),
            'after_super_class': 0
        })
        not_found_reasons['INSUFFICIENT_CLASSIFICATION'] += 1
        continue
    
    # Filter by super_class
    candidates = [c for c in all_items 
                 if c.get('super_class') == ref_super_class 
                 and c.get('price', 0) > 0
                 and c.get('id') != ref_item.get('id')]  # Exclude self
    
    # Fallback to 'other'
    if len(candidates) == 0 and ref_super_class != 'other':
        ref_keywords = {w for w in re.findall(r'\w+', ref_name.lower()) if len(w) >= 4}
        candidates = [c for c in all_items 
                     if c.get('super_class') == 'other'
                     and c.get('id') != ref_item.get('id')
                     and len({w for w in re.findall(r'\w+', (c.get('name_raw') or '').lower())} & ref_keywords) >= 2]
    
    if len(candidates) == 0:
        matching_results.append({
            'reference_name': ref_name[:100],
            'status': 'not_found',
            'reason_code': 'NO_CANDIDATES_AFTER_SUPER_CLASS',
            'ref_super_class': ref_super_class,
            'candidates_total': len(all_items),
            'after_super_class': 0
        })
        not_found_reasons['NO_CANDIDATES_AFTER_SUPER_CLASS'] += 1
        continue
    
    # Sort by price
    candidates.sort(key=lambda x: x.get('price', 999999))
    winner = candidates[0]
    
    # Check if bad match
    winner_name = winner.get('name_raw', '').lower()
    ref_name_lower = ref_name.lower()
    
    is_bad_match = False
    bad_match_reason = ""
    
    # Heuristics for bad matches
    if 'сыр' in ref_name_lower and 'сырник' in winner_name:
        is_bad_match = True
        bad_match_reason = "сыр→сырники"
    elif 'говядина' in ref_name_lower and 'растительн' in winner_name:
        is_bad_match = True
        bad_match_reason = "говядина→растительные"
    elif 'креветк' in ref_name_lower and 'креветк' not in winner_name:
        is_bad_match = True
        bad_match_reason = "креветки→без_креветок"
    
    matching_results.append({
        'reference_name': ref_name[:100],
        'ref_super_class': ref_super_class,
        'status': 'ok',
        'selected_name': winner.get('name_raw', '')[:100],
        'selected_super_class': winner.get('super_class'),
        'price': winner.get('price'),
        'match_percent': min(100, int(conf * 100)),
        'candidates_after_super_class': len(candidates),
        'is_bad_match': is_bad_match,
        'bad_match_reason': bad_match_reason
    })
    
    if is_bad_match:
        not_found_reasons[f'BAD_MATCH_{bad_match_reason}'] += 1

# Save matching audit
print(f"\n   Saving matching_audit.csv...")
with open(f'{AUDIT_DIR}/matching_audit.csv', 'w', newline='', encoding='utf-8') as f:
    if matching_results:
        # Get all unique keys
        all_keys = set()
        for m in matching_results:
            all_keys.update(m.keys())
        
        writer = csv.DictWriter(f, fieldnames=sorted(all_keys))
        writer.writeheader()
        writer.writerows(matching_results)

print(f"   ✅ Saved {len(matching_results)} matching simulations")

# ==================== 3) BAD MATCHES TOP 500 ====================
bad_matches = [m for m in matching_results if m.get('is_bad_match')]

if bad_matches:
    print(f"\n   Saving bad_matches_top500.csv...")
    with open(f'{AUDIT_DIR}/bad_matches_top500.csv', 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=bad_matches[0].keys())
        writer.writeheader()
        writer.writerows(bad_matches[:500])
    
    print(f"   ✅ Saved {len(bad_matches)} bad matches")

# ==================== 4) SUMMARY ====================
summary = {
    'timestamp': timestamp,
    'total_items': total,
    'sampled_for_matching': len(sample_items),
    'data_quality': {
        'super_class_other': sum(1 for r in data_quality_results if r['super_class_db'] == 'other'),
        'no_pack': sum(1 for r in data_quality_results if not r['pack_db']),
        'no_brand': sum(1 for r in data_quality_results if not r['brand_id_db'] and not r['brand_from_text']),
        'top_issues': dict(issue_codes_counter.most_common(20))
    },
    'matching_quality': {
        'ok': sum(1 for m in matching_results if m.get('status') == 'ok'),
        'not_found': sum(1 for m in matching_results if m.get('status') == 'not_found'),
        'bad_matches': len(bad_matches),
        'not_found_reasons': dict(not_found_reasons.most_common(20))
    }
}

with open(f'{AUDIT_DIR}/audit_summary.json', 'w', encoding='utf-8') as f:
    json.dump(summary, f, ensure_ascii=False, indent=2)

# ==================== REPORT ====================
print(f"\n{'='*120}")
print("📊 AUDIT SUMMARY")
print("="*120)

print(f"\n📋 Data Quality:")
print(f"   super_class='other': {summary['data_quality']['super_class_other']} ({summary['data_quality']['super_class_other']/total*100:.1f}%)")
print(f"   No pack:             {summary['data_quality']['no_pack']} ({summary['data_quality']['no_pack']/total*100:.1f}%)")
print(f"   No brand:            {summary['data_quality']['no_brand']} ({summary['data_quality']['no_brand']/total*100:.1f}%)")

print(f"\n🔍 Matching Quality ({len(sample_items)} sampled):")
print(f"   OK:                  {summary['matching_quality']['ok']} ({summary['matching_quality']['ok']/len(sample_items)*100:.1f}%)")
print(f"   NOT FOUND:           {summary['matching_quality']['not_found']} ({summary['matching_quality']['not_found']/len(sample_items)*100:.1f}%)")
print(f"   Bad matches:         {summary['matching_quality']['bad_matches']} ({summary['matching_quality']['bad_matches']/len(sample_items)*100:.1f}%)")

print(f"\n📋 Top NOT FOUND reasons:")
for reason, count in not_found_reasons.most_common(10):
    print(f"   {reason:50} : {count}")

print(f"\n📋 Top Data Issues:")
for issue, count in issue_codes_counter.most_common(10):
    print(f"   {issue:50} : {count}")

print(f"\n{'='*120}")
print(f"✅ AUDIT COMPLETE")
print("="*120)
print(f"\n📁 Output files:")
print(f"   1. {AUDIT_DIR}/audit_summary.json")
print(f"   2. {AUDIT_DIR}/supplier_items_audit.csv ({len(data_quality_results)} rows)")
print(f"   3. {AUDIT_DIR}/matching_audit.csv ({len(matching_results)} rows)")
if bad_matches:
    print(f"   4. {AUDIT_DIR}/bad_matches_top500.csv ({len(bad_matches)} rows)")

print(f"\n✅ Done!")
