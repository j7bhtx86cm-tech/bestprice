"""Brand Master Dictionary - BESTPRICE_BRANDS_MASTER_EN_RU_SITE_STYLE_FINAL.xlsx

NEW VERSION with:
- BRANDS_MASTER sheet (brand_id, brand_en, brand_ru, category, default_strict)
- BRAND_ALIASES sheet (alias, brand_id, comment)
- Normalized aliases (lower, ё→е, trim, remove special chars)
"""
import pandas as pd
import re
from pathlib import Path
from typing import Optional, Tuple, Dict

# NEW FILE
BRANDS_FILE = Path(__file__).parent / 'BESTPRICE_BRANDS_MASTER_EN_RU_SITE_STYLE_FINAL.xlsx'


def normalize_alias(text: str) -> str:
    """Normalize alias for matching:
    - lowercase
    - ё → е
    - trim whitespace
    - remove special chars (except letters, numbers, spaces)
    """
    if not text or pd.isna(text):
        return ""
    
    text = str(text).lower().strip()
    text = text.replace('ё', 'е')  # ё → е
    
    # Remove special chars except letters (RU/EN), numbers, spaces
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
        """Load brand dictionary from Excel"""
        print(f"📋 Loading brand master from {BRANDS_FILE}")
        
        # Load BRANDS_MASTER sheet
        df_brands = pd.read_excel(BRANDS_FILE, sheet_name='BRANDS_MASTER')
        
        # Load BRAND_ALIASES sheet
        try:
            df_aliases = pd.read_excel(BRANDS_FILE, sheet_name='BRAND_ALIASES')
            print(f"   Found {len(df_aliases)} brand aliases")
        except Exception as e:
            print(f"   No BRAND_ALIASES sheet found: {e}")
            df_aliases = pd.DataFrame(columns=['alias', 'brand_id', 'comment'])
        
        # Build lookups
        self.brands_by_id: Dict[str, dict] = {}  # brand_id -> full info
        self.alias_to_id: Dict[str, str] = {}    # normalized alias -> brand_id
        
        # Process BRANDS_MASTER
        for _, row in df_brands.iterrows():
            brand_id = str(row['brand_id']).strip().lower()
            brand_ru = str(row['brand_ru']) if pd.notna(row.get('brand_ru')) else None
            brand_en = str(row['brand_en']) if pd.notna(row.get('brand_en')) else None
            default_strict = bool(row.get('default_strict', False))
            
            # Skip empty brand_id
            if not brand_id or brand_id == 'nan':
                continue
            
            self.brands_by_id[brand_id] = {
                'brand_id': brand_id,
                'brand_en': brand_en,
                'brand_ru': brand_ru,
                'category': row.get('category', 'unknown'),
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
            
            # Also add brand_id itself as alias
            norm_id = normalize_alias(brand_id)
            if norm_id:
                self.alias_to_id[norm_id] = brand_id
        
        # Process BRAND_ALIASES (explicit aliases like BG → barco)
        for _, row in df_aliases.iterrows():
            alias = str(row['alias']) if pd.notna(row.get('alias')) else ''
            target_brand_id = str(row['brand_id']).strip().lower() if pd.notna(row.get('brand_id')) else ''
            
            if not alias or not target_brand_id:
                continue
            
            # Normalize and add alias
            norm = normalize_alias(alias)
            if norm and target_brand_id in self.brands_by_id:
                self.alias_to_id[norm] = target_brand_id
                print(f"   ➕ Alias: '{alias}' → {target_brand_id}")
        
        print(f"✅ Loaded {len(self.brands_by_id)} brands")
        print(f"   Total aliases: {len(self.alias_to_id)}")
    
    def detect_brand(self, product_name: str) -> Tuple[Optional[str], bool]:
        """Detect brand from product name
        
        Returns: (brand_id, brand_strict) or (None, False)
        
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
                    pattern = r'(^|\\s)' + re.escape(alias) + r'($|\\s)'
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


# Global instance
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
        "BG масло оливковое 500мл",  # Alias for barco
        "БГ оливки 250г",  # Cyrillic alias for barco
        "Barko оливки каламата",  # Typo alias for barco
    ]
    
    print("\n🧪 Testing brand detection:\n")
    for product in tests:
        brand_id, is_strict = brand_master.detect_brand(product)
        
        if brand_id:
            info = brand_master.get_brand_info(brand_id)
            status = "✅ BRANDED"
            print(f"{status} {product[:50]:50}")
            print(f"     → brand_id: {brand_id}, strict: {is_strict}")
            if info:
                print(f"        EN: {info['brand_en']}, RU: {info['brand_ru']}")
        else:
            print(f"❌ NO BRAND {product[:50]:50}")
        print()
