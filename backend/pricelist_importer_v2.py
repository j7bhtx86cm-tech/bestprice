#!/usr/bin/env python3
"""
P0 Compliant Price List Importer v2

Implements all P0 requirements:
- P0.1: Upsert on import (no duplicates)
- P0.2: One active pricelist per supplier
- P0.3: Import min_order_qty
- P0.4: Unit priority (file > parsed)
- P0.6: Safe pricelist deactivation
"""

import os
import re
import uuid
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

import pandas as pd
from pymongo import MongoClient
from dotenv import load_dotenv

# Load environment
load_dotenv(Path('/app/backend/.env'))

mongo_url = os.environ['MONGO_URL']
db_name = os.environ['DB_NAME']

# Unit type mapping
UNIT_TYPE_MAP = {
    'шт': 'PIECE', 'шт.': 'PIECE', 'штук': 'PIECE', 'штука': 'PIECE', 'pcs': 'PIECE',
    'кг': 'WEIGHT', 'кг.': 'WEIGHT', 'kg': 'WEIGHT', 'г': 'WEIGHT', 'гр': 'WEIGHT', 'г.': 'WEIGHT',
    'л': 'VOLUME', 'л.': 'VOLUME', 'мл': 'VOLUME', 'мл.': 'VOLUME', 'l': 'VOLUME', 'ml': 'VOLUME',
}

UNIT_NORM_MAP = {
    'шт': 'pcs', 'шт.': 'pcs', 'штук': 'pcs', 'штука': 'pcs', 'pcs': 'pcs',
    'кг': 'kg', 'кг.': 'kg', 'kg': 'kg',
    'г': 'kg', 'гр': 'kg', 'г.': 'kg',  # Convert to kg
    'л': 'l', 'л.': 'l', 'l': 'l',
    'мл': 'l', 'мл.': 'l', 'ml': 'l',  # Convert to l
}


def normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, remove extra spaces"""
    if not text or pd.isna(text):
        return ""
    text = str(text).lower().strip()
    # Remove extra whitespace
    text = re.sub(r'\s+', ' ', text)
    # Normalize unicode
    text = unicodedata.normalize('NFKC', text)
    return text


def generate_unique_key(supplier_id: str, article: Optional[str], product_name: str, unit_type: str) -> str:
    """
    Generate unique key for upsert (P0.1):
    - If article exists: supplier_id:article
    - Otherwise: supplier_id:normalize(productName):unitType
    """
    if article and str(article).strip() and str(article).strip() != 'nan':
        return f"{supplier_id}:{str(article).strip()}"
    else:
        norm_name = normalize_text(product_name)
        return f"{supplier_id}:{norm_name}:{unit_type}"


def get_unit_type(unit_str: str) -> str:
    """Get unit type (WEIGHT, VOLUME, PIECE) from unit string"""
    unit_lower = str(unit_str).lower().strip()
    return UNIT_TYPE_MAP.get(unit_lower, 'PIECE')


def get_unit_norm(unit_str: str) -> str:
    """Get normalized unit (kg, l, pcs) from unit string"""
    unit_lower = str(unit_str).lower().strip()
    return UNIT_NORM_MAP.get(unit_lower, 'pcs')


def parse_file_columns(df: pd.DataFrame) -> Dict[str, int]:
    """
    Parse Excel file and detect column mapping.
    Returns dict mapping field names to column indices.
    """
    columns = {}
    
    # Standard column names (case-insensitive) - ordered by specificity
    # More specific patterns first to avoid false matches
    column_patterns = {
        'article': ['код товара поставщика', 'код товара', 'артикул', 'article', 'code'],
        'name': ['название', 'наименование', 'товар', 'name', 'product'],
        'supplier': ['поставщик', 'supplier'],
        'unit': ['единица', 'ед. изм.', 'ед.', 'unit'],
        'pack_qty': ['количество в упаковки', 'количество в упаковке', 'кол-во в месте', 'pack_qty'],
        'min_order': ['минимальный заказ', 'мин. заказ', 'min_order'],
        'price': ['цена за единицу', 'цена', 'price', 'стоимость'],
    }
    
    # Check each row for headers (first 5 rows)
    for row_idx in range(min(5, len(df))):
        row = df.iloc[row_idx]
        row_str = [str(x).lower().strip() for x in row.values]
        
        # Check if this row contains headers
        found_headers = 0
        temp_columns = {}
        used_cols = set()  # Track which columns are already assigned
        
        for col_idx, cell in enumerate(row_str):
            if col_idx in used_cols:
                continue
            for field, patterns in column_patterns.items():
                if field not in temp_columns:
                    for pattern in patterns:
                        if pattern in cell:
                            temp_columns[field] = col_idx
                            used_cols.add(col_idx)
                            found_headers += 1
                            break
                    if field in temp_columns:
                        break  # Move to next column after finding match
        
        # If we found at least name and price, this is the header row
        if 'name' in temp_columns and 'price' in temp_columns:
            columns = temp_columns
            columns['header_row'] = row_idx
            break
    
    return columns


class PricelistImporter:
    """P0-compliant pricelist importer"""
    
    def __init__(self, client: Optional[MongoClient] = None):
        if client:
            self.client = client
            self.db = client[db_name]
        else:
            self.client = MongoClient(mongo_url)
            self.db = self.client[db_name]
    
    def get_supplier_id(self, supplier_name: str) -> Optional[str]:
        """Get supplier company ID by name"""
        company = self.db.companies.find_one({'companyName': supplier_name, 'type': 'supplier'})
        if not company:
            company = self.db.companies.find_one({'name': supplier_name, 'type': 'supplier'})
        if not company:
            # Try case-insensitive search
            company = self.db.companies.find_one({
                'companyName': {'$regex': f'^{re.escape(supplier_name)}$', '$options': 'i'},
                'type': 'supplier'
            })
        
        return company['id'] if company else None
    
    def deactivate_supplier_items(self, supplier_id: str, exclude_pricelist_id: Optional[str] = None) -> int:
        """
        P0.2: Deactivate all supplier items except for the specified pricelist.
        Returns count of deactivated items.
        """
        query = {'supplier_company_id': supplier_id, 'active': True}
        if exclude_pricelist_id:
            query['price_list_id'] = {'$ne': exclude_pricelist_id}
        
        result = self.db.supplier_items.update_many(
            query,
            {'$set': {'active': False, 'deactivated_at': datetime.now(timezone.utc)}}
        )
        return result.modified_count
    
    def delete_old_pricelists(self, supplier_id: str, keep_pricelist_id: Optional[str] = None) -> Tuple[int, int]:
        """
        P0.6: Delete old pricelist items and metadata.
        Returns (items_deleted, pricelists_deleted)
        """
        items_query = {'supplier_company_id': supplier_id, 'active': False}
        if keep_pricelist_id:
            items_query['price_list_id'] = {'$ne': keep_pricelist_id}
        
        items_result = self.db.supplier_items.delete_many(items_query)
        
        pricelists_query = {'supplierId': supplier_id}
        if keep_pricelist_id:
            pricelists_query['id'] = {'$ne': keep_pricelist_id}
        
        pricelists_result = self.db.pricelists.delete_many(pricelists_query)
        
        return items_result.deleted_count, pricelists_result.deleted_count
    
    def upsert_supplier_item(self, item_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        P0.1: Upsert supplier item using unique key.
        Returns (is_new, item_id)
        """
        unique_key = item_data['unique_key']
        
        # Try to find existing item
        existing = self.db.supplier_items.find_one({'unique_key': unique_key})
        
        if existing:
            # Update existing
            item_data['updated_at'] = datetime.now(timezone.utc)
            self.db.supplier_items.update_one(
                {'unique_key': unique_key},
                {'$set': item_data}
            )
            return False, existing['id']
        else:
            # Insert new
            item_data['id'] = str(uuid.uuid4())
            item_data['created_at'] = datetime.now(timezone.utc)
            item_data['updated_at'] = datetime.now(timezone.utc)
            self.db.supplier_items.insert_one(item_data)
            return True, item_data['id']
    
    def import_file(
        self,
        file_path: str,
        supplier_name: str,
        deactivate_old: bool = True,
        delete_old: bool = False
    ) -> Dict[str, Any]:
        """
        Import pricelist file with P0 compliance.
        
        Args:
            file_path: Path to Excel file
            supplier_name: Name of supplier company
            deactivate_old: If True, deactivate old items (P0.2)
            delete_old: If True, delete old items (P0.6)
        
        Returns:
            Import statistics
        """
        print(f"\n{'='*70}")
        print(f"📂 Импорт: {supplier_name}")
        print(f"📁 Файл: {file_path}")
        print(f"{'='*70}")
        
        # Get supplier ID
        supplier_id = self.get_supplier_id(supplier_name)
        if not supplier_id:
            print(f"❌ Поставщик '{supplier_name}' не найден в базе данных")
            return {'error': f"Supplier '{supplier_name}' not found", 'success': False}
        
        print(f"✅ Supplier ID: {supplier_id}")
        
        # Generate new pricelist ID
        pricelist_id = str(uuid.uuid4())
        print(f"📋 New Pricelist ID: {pricelist_id}")
        
        # Read Excel file
        try:
            df = pd.read_excel(file_path, header=None)
        except Exception as e:
            print(f"❌ Ошибка чтения файла: {e}")
            return {'error': str(e), 'success': False}
        
        print(f"📊 Строк в файле: {len(df)}")
        
        # Detect column mapping
        col_map = parse_file_columns(df)
        if 'name' not in col_map or 'price' not in col_map:
            print(f"❌ Не найдены обязательные колонки (название, цена)")
            print(f"   Обнаруженные колонки: {col_map}")
            return {'error': 'Required columns not found', 'success': False}
        
        header_row = col_map.get('header_row', 0)
        print(f"✅ Обнаружен заголовок на строке {header_row}")
        print(f"   Маппинг колонок: {col_map}")
        
        # Statistics
        stats = {
            'created': 0,
            'updated': 0,
            'skipped': 0,
            'errors': 0,
            'deactivated': 0,
            'deleted_items': 0,
            'deleted_pricelists': 0,
        }
        
        # Process rows
        for idx in range(header_row + 1, len(df)):
            row = df.iloc[idx]
            
            try:
                # Extract fields
                product_name = str(row.iloc[col_map['name']]).strip() if 'name' in col_map else None
                price_raw = row.iloc[col_map['price']] if 'price' in col_map else None
                
                # Skip invalid rows
                if not product_name or product_name == 'nan' or pd.isna(product_name):
                    stats['skipped'] += 1
                    continue
                
                # Parse price
                try:
                    price = float(price_raw)
                except (ValueError, TypeError):
                    stats['skipped'] += 1
                    continue
                
                if price <= 0:
                    stats['skipped'] += 1
                    continue
                
                # Extract optional fields
                article = None
                if 'article' in col_map:
                    art_val = row.iloc[col_map['article']]
                    if pd.notna(art_val) and str(art_val).strip() != 'nan':
                        article = str(art_val).strip()
                
                unit_str = 'шт'
                if 'unit' in col_map:
                    unit_val = row.iloc[col_map['unit']]
                    if pd.notna(unit_val) and str(unit_val).strip() != 'nan':
                        unit_str = str(unit_val).strip()
                
                # P0.3: Import min_order_qty
                pack_qty = 1
                if 'pack_qty' in col_map:
                    pq_val = row.iloc[col_map['pack_qty']]
                    if pd.notna(pq_val):
                        try:
                            pack_qty = max(1, int(float(pq_val)))
                        except (ValueError, TypeError):
                            pass
                
                min_order_qty = 1
                if 'min_order' in col_map:
                    mo_val = row.iloc[col_map['min_order']]
                    if pd.notna(mo_val):
                        try:
                            min_order_qty = max(1, int(float(mo_val)))
                        except (ValueError, TypeError):
                            pass
                
                # P0.4: Unit priority (file > parsed)
                unit_type = get_unit_type(unit_str)
                unit_norm = get_unit_norm(unit_str)
                
                # Generate unique key (P0.1)
                unique_key = generate_unique_key(supplier_id, article, product_name, unit_type)
                
                # Prepare item data
                item_data = {
                    'unique_key': unique_key,
                    'supplier_company_id': supplier_id,
                    'price_list_id': pricelist_id,
                    'supplier_item_code': article or '',
                    'name_raw': product_name,
                    'name_norm': normalize_text(product_name),
                    'unit_supplier': unit_str,
                    'unit_norm': unit_norm,
                    'unit_type': unit_type,  # P0.4: Explicit unit type
                    'price': price,
                    'pack_qty': pack_qty,  # P0.3
                    'min_order_qty': min_order_qty,  # P0.3: Critical for P0.5
                    'active': True,
                }
                
                # Upsert (P0.1)
                is_new, item_id = self.upsert_supplier_item(item_data)
                
                if is_new:
                    stats['created'] += 1
                else:
                    stats['updated'] += 1
                    
            except Exception as e:
                print(f"⚠️  Ошибка в строке {idx}: {e}")
                stats['errors'] += 1
                continue
        
        # P0.2: Deactivate old items
        if deactivate_old:
            deactivated = self.deactivate_supplier_items(supplier_id, exclude_pricelist_id=pricelist_id)
            stats['deactivated'] = deactivated
            print(f"🔄 Деактивировано старых позиций: {deactivated}")
        
        # P0.6: Delete old items (optional)
        if delete_old:
            items_del, pl_del = self.delete_old_pricelists(supplier_id, keep_pricelist_id=pricelist_id)
            stats['deleted_items'] = items_del
            stats['deleted_pricelists'] = pl_del
            print(f"🗑️  Удалено старых позиций: {items_del}, прайс-листов: {pl_del}")
        
        # Create pricelist metadata
        pricelist_meta = {
            'id': pricelist_id,
            'supplierId': supplier_id,
            'supplierName': supplier_name,
            'fileName': Path(file_path).name,
            'itemsCount': stats['created'] + stats['updated'],
            'createdAt': datetime.now(timezone.utc).isoformat(),
            'active': True,
        }
        self.db.pricelists.insert_one(pricelist_meta)
        
        # Print summary
        print(f"\n✅ Результат импорта:")
        print(f"   Создано: {stats['created']}")
        print(f"   Обновлено: {stats['updated']}")
        print(f"   Пропущено: {stats['skipped']}")
        print(f"   Ошибок: {stats['errors']}")
        
        stats['success'] = True
        stats['pricelist_id'] = pricelist_id
        return stats
    
    def import_all_new_catalogs(self, catalogs_dir: str = '/app/backend/new_catalogs') -> Dict[str, Any]:
        """Import all catalogs from the new_catalogs directory"""
        
        # Map filenames to supplier names
        supplier_mapping = {
            'Алиди.xlsx': 'Алиди',
            'Айфрут.xlsx': 'Айфрут',
            'Восток-Запад.xlsx': 'Восток-Запад',
            'Интегрита.xlsx': 'Интегрита',
            'Нордико.xlsx': 'Нордико',
            'ПраймФудс.xlsx': 'ПраймФудс',
            'РБД.xlsx': 'РБД',
            'Ромакс.xlsx': 'Ромакс',
            'Сладкая_жизнь.xlsx': 'Сладкая жизнь',
        }
        
        results = {}
        total_created = 0
        total_updated = 0
        
        for filename, supplier_name in supplier_mapping.items():
            file_path = Path(catalogs_dir) / filename
            
            if not file_path.exists():
                print(f"⚠️  Файл {filename} не найден, пропуск...")
                results[supplier_name] = {'error': 'File not found'}
                continue
            
            result = self.import_file(str(file_path), supplier_name)
            results[supplier_name] = result
            
            if result.get('success'):
                total_created += result.get('created', 0)
                total_updated += result.get('updated', 0)
        
        print(f"\n{'='*70}")
        print(f"📊 ИТОГОВАЯ СТАТИСТИКА ИМПОРТА")
        print(f"{'='*70}")
        print(f"Всего создано: {total_created}")
        print(f"Всего обновлено: {total_updated}")
        
        return {
            'results': results,
            'total_created': total_created,
            'total_updated': total_updated,
        }


def main():
    """CLI entry point"""
    import argparse
    
    parser = argparse.ArgumentParser(description='P0 Compliant Pricelist Importer')
    parser.add_argument('--file', help='Path to Excel file')
    parser.add_argument('--supplier', help='Supplier name')
    parser.add_argument('--all', action='store_true', help='Import all catalogs from new_catalogs')
    parser.add_argument('--delete-old', action='store_true', help='Delete old pricelists (P0.6)')
    
    args = parser.parse_args()
    
    importer = PricelistImporter()
    
    if args.all:
        importer.import_all_new_catalogs()
    elif args.file and args.supplier:
        importer.import_file(args.file, args.supplier, delete_old=args.delete_old)
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
