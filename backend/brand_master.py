"""Brand Master Dictionary - BESTPRICE_BRANDS_MASTER_UNIFIED_RF_HORECA_ULTRA_SAFE.xlsx

NEW VERSION (December 2025) with:
- BRANDS_MASTER sheet (brand_id, brand_ru, brand_en, category, default_strict, notes)
- BRAND_ALIASES sheet (alias, alias_norm, brand_id, source, comment)
- Normalized aliases (lower, ё→е, trim, remove special chars)
"""
import pandas as pd
import re
from pathlib import Path
from typing import Optional, Tuple, Dict

# NEW FILE - UNIFIED ULTRA SAFE VERSION
BRANDS_FILE = Path(__file__).parent / 'BESTPRICE_BRANDS_MASTER_UNIFIED_RF_HORECA_ULTRA_SAFE.xlsx'


def normalize_alias(text: str) -> str:
    """Normalize alias for matching:
    - lowercase
    - ё → е
    - trim whitespace
    - remove/replace special chars
    """
    if not text or pd.isna(text):
        return ""
    
    text = str(text).lower().strip()
    text = text.replace('ё', 'е')  # ё → е
    
    # Replace quotes and punctuation with spaces (to separate words)
    text = text.replace('"', ' ').replace("'", ' ').replace('«', ' ').replace('»', ' ')
    text = text.replace('.', ' ').replace(',', ' ').replace(';', ' ').replace(':', ' ')
    text = text.replace('/', ' ').replace('\\', ' ').replace('-', ' ').replace('_', ' ')
    
    # Remove other special chars
    text = re.sub(r'[^\w\s]', '', text, flags=re.UNICODE)
    
    # Collapse multiple spaces
    text = re.sub(r'\s+', ' ', text).strip()
    
    return text


class BrandMaster:
    """Singleton for brand dictionary with aliases"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_brands()
        return cls._instance
    
    @classmethod
    def reload(cls):
        """Force reload brand dictionary (clear cache)"""
        cls._instance = None
        return cls()
    
    def _load_brands(self):
        """Load brand dictionary from Excel (UNIFIED RF HORECA ULTRA SAFE)"""
        print(f"📋 Loading brand master from {BRANDS_FILE}")
        
        if not BRANDS_FILE.exists():
            print(f"❌ Brand file not found: {BRANDS_FILE}")
            self.brands_by_id = {}
            self.alias_to_id = {}
            return
        
        # Load BRANDS_MASTER sheet
        try:
            df_brands = pd.read_excel(BRANDS_FILE, sheet_name='BRANDS_MASTER')
            print(f"   Found {len(df_brands)} brands in BRANDS_MASTER")
        except Exception as e:
            print(f"❌ Error loading BRANDS_MASTER: {e}")
            df_brands = pd.DataFrame()
        
        # Load BRAND_ALIASES sheet
        try:
            df_aliases = pd.read_excel(BRANDS_FILE, sheet_name='BRAND_ALIASES')
            print(f"   Found {len(df_aliases)} aliases in BRAND_ALIASES")
        except Exception as e:
            print(f"   No BRAND_ALIASES sheet found: {e}")
            df_aliases = pd.DataFrame(columns=['alias', 'alias_norm', 'brand_id', 'source', 'comment'])
        
        # Build lookups
        self.brands_by_id: Dict[str, dict] = {}  # brand_id -> full info
        self.alias_to_id: Dict[str, str] = {}    # normalized alias -> brand_id
        
        # Process BRANDS_MASTER
        for _, row in df_brands.iterrows():
            brand_id = str(row.get('brand_id', '')).strip().lower()
            brand_ru = str(row['brand_ru']) if pd.notna(row.get('brand_ru')) else None
            brand_en = str(row['brand_en']) if pd.notna(row.get('brand_en')) else None
            
            # Parse default_strict (can be 1, True, "1", etc.)
            default_strict_raw = row.get('default_strict', 0)
            default_strict = bool(default_strict_raw) if pd.notna(default_strict_raw) else False
            
            # Skip empty brand_id
            if not brand_id or brand_id == 'nan':
                continue
            
            self.brands_by_id[brand_id] = {
                'brand_id': brand_id,
                'brand_en': brand_en,
                'brand_ru': brand_ru,
                'category': str(row.get('category', 'unknown')) if pd.notna(row.get('category')) else 'unknown',
                'default_strict': default_strict,
                'notes': str(row.get('notes', '')) if pd.notna(row.get('notes')) else ''
            }
            
            # Add brand_ru and brand_en as aliases
            if brand_ru and brand_ru.lower() != 'nan':
                norm = normalize_alias(brand_ru)
                if norm:
                    self.alias_to_id[norm] = brand_id
            
            if brand_en and brand_en.lower() != 'nan':
                norm = normalize_alias(brand_en)
                if norm:
                    self.alias_to_id[norm] = brand_id
            
            # Also add brand_id itself as alias (normalized)
            norm_id = normalize_alias(brand_id)
            if norm_id:
                self.alias_to_id[norm_id] = brand_id
        
        # Process BRAND_ALIASES (explicit aliases)
        for _, row in df_aliases.iterrows():
            alias = str(row.get('alias', '')) if pd.notna(row.get('alias')) else ''
            # Use pre-normalized alias if available
            alias_norm = str(row.get('alias_norm', '')) if pd.notna(row.get('alias_norm')) else ''
            target_brand_id = str(row.get('brand_id', '')).strip().lower() if pd.notna(row.get('brand_id')) else ''
            
            if not alias and not alias_norm:
                continue
            if not target_brand_id:
                continue
            
            # Use alias_norm if available, otherwise normalize alias
            norm = alias_norm.strip().lower() if alias_norm else normalize_alias(alias)
            
            if norm and target_brand_id in self.brands_by_id:
                self.alias_to_id[norm] = target_brand_id
        
        print(f"✅ Loaded {len(self.brands_by_id)} brands")
        print(f"   Total aliases: {len(self.alias_to_id)}")
    
    def detect_brand(self, product_name: str) -> Tuple[Optional[str], bool]:
        """Detect brand from product name
        
        Returns: (brand_id, default_strict) or (None, False)
        
        Algorithm:
        1. Normalize product name
        2. Check each alias (sorted by length, longest first)
        3. If found, return brand_id and default_strict
        
        CRITICAL: NO heuristic guessing! Only return if found in dictionary.
        """
        if not product_name:
            return (None, False)
        
        name_norm = normalize_alias(product_name)
        name_words = set(name_norm.split())
        
        # Sort aliases by length (longest first) for better matching
        sorted_aliases = sorted(self.alias_to_id.keys(), key=len, reverse=True)
        
        for alias in sorted_aliases:
            # For short aliases (< 4 chars), require exact word match
            if len(alias) < 4:
                if alias in name_words:
                    brand_id = self.alias_to_id[alias]
                    brand_info = self.brands_by_id.get(brand_id, {})
                    return (brand_id, brand_info.get('default_strict', False))
            else:
                # For longer aliases, check substring match
                # But ensure it's at word boundary
                if alias in name_norm:
                    # Check it's not part of another word
                    # Pattern: alias at start/end of string or surrounded by spaces
                    pattern = r'(^|\s)' + re.escape(alias) + r'($|\s)'
                    if re.search(pattern, name_norm) or alias in name_words:
                        brand_id = self.alias_to_id[alias]
                        brand_info = self.brands_by_id.get(brand_id, {})
                        return (brand_id, brand_info.get('default_strict', False))
        
        # NOT FOUND - return None (DO NOT guess!)
        return (None, False)
    
    def get_brand_info(self, brand_id: str) -> Optional[dict]:
        """Get full brand info by ID"""
        return self.brands_by_id.get(brand_id.lower() if brand_id else '')
    
    def get_all_brands(self) -> list:
        """Get all brands as list"""
        return list(self.brands_by_id.values())
    
    def get_all_aliases(self) -> Dict[str, str]:
        """Get all aliases (normalized -> brand_id)"""
        return self.alias_to_id.copy()
    
    def get_stats(self) -> dict:
        """Get statistics about brand dictionary"""
        return {
            'total_brands': len(self.brands_by_id),
            'total_aliases': len(self.alias_to_id),
            'strict_brands': sum(1 for b in self.brands_by_id.values() if b.get('default_strict')),
            'categories': list(set(b.get('category', 'unknown') for b in self.brands_by_id.values()))
        }


# Global instance - lazy load to avoid import errors
brand_master = None

def get_brand_master() -> BrandMaster:
    """Get or create brand master instance"""
    global brand_master
    if brand_master is None:
        try:
            brand_master = BrandMaster()
        except Exception as e:
            print(f"⚠️ Warning: Could not load brand master: {e}")
            brand_master = BrandMaster()  # Empty instance
    return brand_master


# For backward compatibility
try:
    brand_master = BrandMaster()
except Exception as e:
    print(f"⚠️ Warning: Could not load brand master: {e}")
    brand_master = None


# Testing
if __name__ == '__main__':
    tests = [
        "БУЛЬОН грибной 2 кг. Knorr professional",
        "Кетчуп томатный 800 гр. Heinz",
        "Соус терияки 1л Aroy-D",
        "СУХАРИ панировочные 1кг",  # No brand
        "ЛОСОСЬ филе 1.5кг",  # No brand
        "Паста Barilla спагетти 500г",
        "Мясо Мираторг говядина 1кг",  # Russian brand
        "Ahmad Tea чай черный 100г",  # Ahmad alias
        "Acqua Panna вода 500мл",  # Acqua Panna brand
        "Табаско соус острый 60мл",  # Tabasco
    ]
    
    bm = get_brand_master()
    stats = bm.get_stats()
    print(f"\n📊 Brand Dictionary Stats:")
    print(f"   Total brands: {stats['total_brands']}")
    print(f"   Total aliases: {stats['total_aliases']}")
    print(f"   Strict brands: {stats['strict_brands']}")
    print(f"   Categories: {len(stats['categories'])}")
    
    print("\n🧪 Testing brand detection:\n")
    for product in tests:
        brand_id, is_strict = bm.detect_brand(product)
        
        if brand_id:
            info = bm.get_brand_info(brand_id)
            status = "✅ BRANDED"
            print(f"{status} {product[:50]:50}")
            print(f"     → brand_id: {brand_id}, strict: {is_strict}")
            if info:
                print(f"        EN: {info['brand_en']}, RU: {info['brand_ru']}")
        else:
            print(f"❌ NO BRAND {product[:50]:50}")
        print()
