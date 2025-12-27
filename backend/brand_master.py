"""Brand Master Dictionary - BESTPRICE_BRANDS_MASTER_EN_RU.xlsx"""
import pandas as pd
from pathlib import Path
from typing import Optional, Tuple

BRANDS_FILE = Path(__file__).parent / 'BESTPRICE_BRANDS_MASTER_EN_RU.xlsx'

class BrandMaster:
    """Singleton for brand dictionary"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_brands()
        return cls._instance
    
    def _load_brands(self):
        """Load brand dictionary"""
        print(f"📋 Loading brand master from {BRANDS_FILE}")
        
        df = pd.read_excel(BRANDS_FILE, sheet_name='BRANDS_MASTER')
        
        # Build lookups
        self.brands_by_id = {}  # brand_id -> full info
        self.ru_to_id = {}  # brand_ru (lowercase) -> brand_id
        self.en_to_id = {}  # brand_en (lowercase) -> brand_id
        
        for _, row in df.iterrows():
            brand_id = row['brand_id']
            brand_ru = str(row['brand_ru']).lower()
            brand_en = str(row['brand_en']).lower()
            default_strict = bool(row.get('default_strict', False))
            
            self.brands_by_id[brand_id] = {
                'brand_id': brand_id,
                'brand_en': brand_en.title(),
                'brand_ru': brand_ru.title(),
                'category': row.get('category', ''),
                'default_strict': default_strict,
                'notes': row.get('notes', '')
            }
            
            # Add to lookups (case-insensitive)
            self.ru_to_id[brand_ru] = brand_id
            self.en_to_id[brand_en] = brand_id
            
            # Also add variations (remove hyphens, spaces)
            ru_clean = brand_ru.replace('-', '').replace(' ', '')
            en_clean = brand_en.replace('-', '').replace(' ', '')
            
            if ru_clean != brand_ru:
                self.ru_to_id[ru_clean] = brand_id
            if en_clean != brand_en:
                self.en_to_id[en_clean] = brand_id
        
        print(f"✅ Loaded {len(self.brands_by_id)} brands")
        print(f"   RU lookups: {len(self.ru_to_id)}")
        print(f"   EN lookups: {len(self.en_to_id)}")
    
    def detect_brand(self, product_name: str) -> Tuple[Optional[str], bool]:
        """Detect brand from product name
        
        Returns: (brand_id, brand_strict) or (None, False)
        
        CRITICAL: NO heuristic guessing! Only return if found in dictionary.
        """
        name_lower = product_name.lower()
        
        # Try RU first
        for brand_ru, brand_id in self.ru_to_id.items():
            if brand_ru in name_lower:
                brand_info = self.brands_by_id[brand_id]
                return (brand_id, brand_info['default_strict'])
        
        # Try EN
        for brand_en, brand_id in self.en_to_id.items():
            if brand_en in name_lower:
                brand_info = self.brands_by_id[brand_id]
                return (brand_id, brand_info['default_strict'])
        
        # NOT FOUND - return None (DO NOT guess!)
        return (None, False)
    
    def get_brand_info(self, brand_id: str) -> Optional[dict]:
        """Get full brand info by ID"""
        return self.brands_by_id.get(brand_id)

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
    ]
    
    print("\n🧪 Testing brand detection:\n")
    for product in tests:
        brand_id, is_strict = brand_master.detect_brand(product)
        
        if brand_id:
            info = brand_master.get_brand_info(brand_id)
            status = "✅ BRANDED"
            print(f"{status} {product[:50]:50}")
            print(f"     → brand_id: {brand_id}, strict: {is_strict}, name: {info['brand_en']}")
        else:
            print(f"❌ NO BRAND {product[:50]:50}")
        print()
