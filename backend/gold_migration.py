#!/usr/bin/env python3
"""
GOLD Pricelist Migration Script

This script performs the full data migration as per the Technical Specification (ТЗ):
1. Load each GOLD pricelist file
2. Find unique batch marker for the newly loaded data
3. Deactivate all old items for that supplier
4. Verify results and generate report
"""

import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List, Optional

import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment
load_dotenv(Path('/app/backend/.env'))

mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']

# GOLD file to supplier name mapping
GOLD_SUPPLIER_MAPPING = {
    'GOLD_Aifruit.xlsx': 'Айфрут',
    'GOLD_Alidi.xlsx': 'Алиди',
    'GOLD_Integrita.xlsx': 'Интегрита',
    'GOLD_PrimeFoods.xlsx': 'ПраймФудс',
    'GOLD_RBD.xlsx': 'РБД',
    'GOLD_Romanov.xlsx': 'Сладкая жизнь',  # Romanov -> Сладкая жизнь based on context
    'GOLD_Romax.xlsx': 'Ромакс',
    'GOLD_VZ.xlsx': 'Восток-Запад',
}


class GoldMigrator:
    """Handles GOLD pricelist migration"""
    
    def __init__(self):
        self.client = MongoClient(mongo_url)
        self.db = self.client[db_name]
        self.report = []
    
    def get_supplier_id(self, supplier_name: str) -> Optional[str]:
        """Get supplier company ID by name"""
        company = self.db.companies.find_one({
            '$or': [
                {'companyName': supplier_name},
                {'name': supplier_name}
            ],
            'type': 'supplier'
        })
        return company['id'] if company else None
    
    def get_active_count(self, supplier_id: str) -> int:
        """Count active items for a supplier"""
        return self.db.supplier_items.count_documents({
            'supplier_company_id': supplier_id,
            'active': True
        })
    
    def get_batch_markers(self, supplier_id: str) -> List[Dict]:
        """Get unique batch markers for a supplier's items"""
        pipeline = [
            {'$match': {'supplier_company_id': supplier_id, 'active': True}},
            {'$group': {
                '_id': {
                    'price_list_id': '$price_list_id',
                    'import_batch_id': '$import_batch_id',
                },
                'count': {'$sum': 1},
                'sample_created_at': {'$first': '$created_at'}
            }},
            {'$sort': {'sample_created_at': -1}}
        ]
        return list(self.db.supplier_items.aggregate(pipeline))
    
    def load_gold_file(self, file_path: str, supplier_id: str) -> Dict[str, Any]:
        """
        Load GOLD pricelist file into database.
        Returns import statistics.
        """
        # Generate new batch ID
        import_batch_id = f"GOLD_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}"
        pricelist_id = str(uuid.uuid4())
        
        # Read Excel file
        df = pd.read_excel(file_path)
        
        stats = {
            'total_rows': len(df),
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'import_batch_id': import_batch_id,
            'pricelist_id': pricelist_id,
        }
        
        # Process each row (skip header which is already parsed by pandas)
        for idx, row in df.iterrows():
            try:
                # Extract fields based on GOLD format
                article = str(row.get('article', '')).strip() if pd.notna(row.get('article')) else None
                product_name = str(row.get('productName', '')).strip()
                unit_type = str(row.get('unit', 'PIECE')).strip().upper()
                price = float(row.get('price', 0))
                pack_qty = int(row.get('Количество в упаковки', 1)) if pd.notna(row.get('Количество в упаковки')) else 1
                min_order_qty = int(row.get('Минимальный заказ', 1)) if pd.notna(row.get('Минимальный заказ')) else 1
                
                # Skip invalid rows
                if not product_name or product_name == 'nan' or price <= 0:
                    stats['skipped'] += 1
                    continue
                
                # Clean article
                if article and article.endswith('.0'):
                    article = article[:-2]
                if article == 'nan' or article == '':
                    article = None
                
                # Generate unique key
                if article:
                    unique_key = f"{supplier_id}:{article}"
                else:
                    norm_name = product_name.lower().strip()
                    unique_key = f"{supplier_id}:{norm_name}:{unit_type}"
                
                # Normalize unit
                unit_norm = 'kg' if unit_type == 'WEIGHT' else 'l' if unit_type == 'VOLUME' else 'pcs'
                
                # Prepare item data
                item_data = {
                    'unique_key': unique_key,
                    'supplier_company_id': supplier_id,
                    'price_list_id': pricelist_id,
                    'import_batch_id': import_batch_id,
                    'supplier_item_code': article or '',
                    'name_raw': product_name,
                    'name_norm': product_name.lower().strip(),
                    'unit_type': unit_type,
                    'unit_norm': unit_norm,
                    'unit_supplier': unit_type,
                    'price': price,
                    'pack_qty': pack_qty,
                    'min_order_qty': min_order_qty,
                    'active': True,
                    'is_gold': True,  # Mark as GOLD import
                    'updated_at': datetime.now(timezone.utc),
                }
                
                # Upsert item
                existing = self.db.supplier_items.find_one({'unique_key': unique_key})
                
                if existing:
                    self.db.supplier_items.update_one(
                        {'unique_key': unique_key},
                        {'$set': item_data}
                    )
                    stats['updated'] += 1
                else:
                    item_data['id'] = str(uuid.uuid4())
                    item_data['created_at'] = datetime.now(timezone.utc)
                    self.db.supplier_items.insert_one(item_data)
                    stats['created'] += 1
                    
            except Exception as e:
                print(f"  ⚠️ Error at row {idx}: {e}")
                stats['errors'] += 1
        
        return stats
    
    def deactivate_old_items(self, supplier_id: str, keep_batch_id: str) -> int:
        """
        Deactivate all items NOT matching the specified batch ID.
        Returns count of deactivated items.
        """
        result = self.db.supplier_items.update_many(
            {
                'supplier_company_id': supplier_id,
                'active': True,
                'import_batch_id': {'$ne': keep_batch_id}
            },
            {
                '$set': {
                    'active': False,
                    'deactivated_at': datetime.now(timezone.utc),
                    'deactivation_reason': f'Replaced by GOLD batch {keep_batch_id}'
                }
            }
        )
        return result.modified_count
    
    def migrate_supplier(self, file_name: str, supplier_name: str) -> Dict[str, Any]:
        """
        Full migration for a single supplier:
        1. Load GOLD file
        2. Deactivate old items
        3. Verify and return report
        """
        print(f"\n{'='*70}")
        print(f"📂 Миграция: {supplier_name}")
        print(f"📁 Файл: {file_name}")
        print(f"{'='*70}")
        
        # Get supplier ID
        supplier_id = self.get_supplier_id(supplier_name)
        if not supplier_id:
            error_msg = f"Supplier '{supplier_name}' not found in database"
            print(f"❌ {error_msg}")
            return {'success': False, 'error': error_msg}
        
        print(f"✅ Supplier ID: {supplier_id}")
        
        # Get before counts
        before_active = self.get_active_count(supplier_id)
        print(f"📊 Active items BEFORE: {before_active}")
        
        # Load GOLD file
        file_path = f"/app/backend/gold_pricelists/{file_name}"
        if not Path(file_path).exists():
            error_msg = f"File not found: {file_path}"
            print(f"❌ {error_msg}")
            return {'success': False, 'error': error_msg}
        
        import_stats = self.load_gold_file(file_path, supplier_id)
        print(f"✅ Import complete:")
        print(f"   Created: {import_stats['created']}")
        print(f"   Updated: {import_stats['updated']}")
        print(f"   Skipped: {import_stats['skipped']}")
        print(f"   Errors: {import_stats['errors']}")
        print(f"   Batch ID: {import_stats['import_batch_id']}")
        
        # Deactivate old items
        deactivated = self.deactivate_old_items(supplier_id, import_stats['import_batch_id'])
        print(f"🔄 Deactivated old items: {deactivated}")
        
        # Verify
        after_active = self.get_active_count(supplier_id)
        print(f"📊 Active items AFTER: {after_active}")
        
        # Get batch markers to verify only one batch is active
        markers = self.get_batch_markers(supplier_id)
        print(f"📋 Active batches: {len(markers)}")
        for m in markers:
            print(f"   - {m['_id'].get('import_batch_id', 'N/A')}: {m['count']} items")
        
        result = {
            'success': True,
            'supplier_name': supplier_name,
            'supplier_id': supplier_id,
            'file_name': file_name,
            'before_active': before_active,
            'after_active': after_active,
            'created': import_stats['created'],
            'updated': import_stats['updated'],
            'deactivated': deactivated,
            'batch_marker': import_stats['import_batch_id'],
            'active_batches': len(markers),
        }
        
        self.report.append(result)
        return result
    
    def run_full_migration(self) -> List[Dict[str, Any]]:
        """Run migration for all GOLD files"""
        print("\n" + "="*70)
        print("🚀 STARTING GOLD PRICELIST MIGRATION")
        print("="*70)
        
        results = []
        
        for file_name, supplier_name in GOLD_SUPPLIER_MAPPING.items():
            result = self.migrate_supplier(file_name, supplier_name)
            results.append(result)
        
        # Print final report
        self.print_report()
        
        return results
    
    def print_report(self):
        """Print migration report"""
        print("\n" + "="*70)
        print("📊 ИТОГОВЫЙ ОТЧЁТ МИГРАЦИИ GOLD ПРАЙС-ЛИСТОВ")
        print("="*70)
        print(f"{'Поставщик':<20} {'До':>8} {'После':>8} {'Маркер':<30}")
        print("-"*70)
        
        total_before = 0
        total_after = 0
        
        for r in self.report:
            if r.get('success'):
                supplier = r['supplier_name'][:20]
                before = r['before_active']
                after = r['after_active']
                marker = r['batch_marker'][:30]
                print(f"{supplier:<20} {before:>8} {after:>8} {marker:<30}")
                total_before += before
                total_after += after
            else:
                print(f"{r.get('supplier_name', 'Unknown'):<20} ❌ {r.get('error', 'Error')}")
        
        print("-"*70)
        print(f"{'ИТОГО':<20} {total_before:>8} {total_after:>8}")
        print("="*70)


def main():
    """Run the migration"""
    migrator = GoldMigrator()
    migrator.run_full_migration()


if __name__ == '__main__':
    main()
