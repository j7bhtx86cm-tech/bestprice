"""Brand Master Dictionary - BESTPRICE_BRANDS_MASTER_UNIFIED_RF_HORECA_ULTRA_SAFE.xlsx

VERSION 2.0 (December 2025):
- BRANDS_MASTER sheet (brand_id, brand_ru, brand_en, category, default_strict, notes)
- BRAND_ALIASES sheet (alias, alias_norm, brand_id, source, comment)
- NEW: brand_family_id support for brand lineages (Chef, Professional, HoReCa variants)
- Normalized aliases (lower, ё→е, trim, remove special chars)
"""
import pandas as pd
import re
from pathlib import Path
from typing import Optional, Tuple, Dict, List

# NEW FILE - UNIFIED ULTRA SAFE VERSION
BRANDS_FILE = Path(__file__).parent / 'BESTPRICE_BRANDS_MASTER_UNIFIED_RF_HORECA_ULTRA_SAFE.xlsx'

# Brand family mappings: sub_brand_id -> parent_brand_id
# These are brands that are variants/lineages of a parent brand
BRAND_FAMILY_MAPPINGS = {
    # Miraторг variants
    'miratorg_chef': 'miratorg',
    'miratorg chef': 'miratorg',
    'мираторг chef': 'miratorg',
    
    # Hochland variants
    'hochland professional': 'hochland',
    'hochland_professional': 'hochland',
    
    # Mission variants
    'mission professional': 'mission',
    'mission_professional': 'mission',
    
    # Tamaki variants
    'tamaki pro': 'tamaki',
    'tamaki_pro': 'tamaki',
    
    # Pechagin variants
    'pechagin professional': 'pechagin',
    'pechagin_professional': 'pechagin',
    
    # Smart Chef variants
    'smart chef': 'smart_chef',
    'smart chef triumph': 'smart_chef',
    
    # Granoro variants
    'granoro classic': 'granoro',
    'granoro classici': 'granoro',
    
    # Pikador variants
    'pikador pro': 'pikador',
    'pikador_pro': 'pikador',
    
    # Svezhe Zavtra variants
    'свежее завтра professional': 'свежее завтра',
    'свежее завтра professional,': 'свежее завтра',
    
    # Pro Astoria variants
    'pro astoria': 'astoria',
    
    # Ангстрем variants
    'ангстрем премиум': 'ангстрем',
    
    # Add more mappings as needed...
}


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


def extract_base_brand(brand_id: str) -> Optional[str]:
    """Extract base brand from sub-brand by removing common suffixes
    
    Examples:
    - miratorg_chef -> miratorg
    - hochland professional -> hochland
    - tamaki pro -> tamaki
    """
    if not brand_id:
        return None
    
    brand_lower = brand_id.lower().strip()
    
    # Check explicit mapping first
    if brand_lower in BRAND_FAMILY_MAPPINGS:
        return BRAND_FAMILY_MAPPINGS[brand_lower]
    
    # Try to extract base brand by removing common suffixes
    suffixes = [
        ' professional', '_professional', ' pro', '_pro',
        ' chef', '_chef', ' horeca', '_horeca',
        ' premium', '_premium', ' премиум', '_премиум',
        ' gold', '_gold', ' classic', '_classic',
        ' classici', '_classici', ' triumph', '_triumph',
        ' profi', '_profi'
    ]
    
    for suffix in suffixes:
        if brand_lower.endswith(suffix):
            base = brand_lower[:-len(suffix)].strip()
            if len(base) >= 3:  # Minimum length for valid brand
                return base
    
    return None


class BrandMaster:
    """Singleton for brand dictionary with aliases and family support"""
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
            self.family_to_members = {}
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
        self.family_to_members: Dict[str, List[str]] = {}  # family_id -> list of brand_ids
        
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
            
            # Determine brand_family_id
            brand_family_id = extract_base_brand(brand_id)
            
            self.brands_by_id[brand_id] = {
                'brand_id': brand_id,
                'brand_en': brand_en,
                'brand_ru': brand_ru,
                'category': str(row.get('category', 'unknown')) if pd.notna(row.get('category')) else 'unknown',
                'default_strict': default_strict,
                'notes': str(row.get('notes', '')) if pd.notna(row.get('notes')) else '',
                'brand_family_id': brand_family_id  # NEW: family reference
            }
            
            # Build family -> members mapping
            if brand_family_id:
                if brand_family_id not in self.family_to_members:
                    self.family_to_members[brand_family_id] = []
                self.family_to_members[brand_family_id].append(brand_id)
            
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
            alias_norm = str(row.get('alias_norm', '')) if pd.notna(row.get('alias_norm')) else ''
            target_brand_id = str(row.get('brand_id', '')).strip().lower() if pd.notna(row.get('brand_id')) else ''
            
            if not alias and not alias_norm:
                continue
            if not target_brand_id:
                continue
            
            norm = alias_norm.strip().lower() if alias_norm else normalize_alias(alias)
            
            if norm and target_brand_id in self.brands_by_id:
                self.alias_to_id[norm] = target_brand_id
        
        print(f"✅ Loaded {len(self.brands_by_id)} brands")
        print(f"   Total aliases: {len(self.alias_to_id)}")
        print(f"   Brand families: {len(self.family_to_members)}")
    
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
    
    def get_brand_family_id(self, brand_id: str) -> Optional[str]:
        """Get the family ID for a brand (returns parent brand if exists)"""
        if not brand_id:
            return None
        
        brand_info = self.get_brand_info(brand_id)
        if brand_info:
            return brand_info.get('brand_family_id')
        
        # Try to extract from brand_id directly
        return extract_base_brand(brand_id)
    
    def get_family_members(self, family_id: str) -> List[str]:
        """Get all brand_ids belonging to a family"""
        if not family_id:
            return []
        
        family_lower = family_id.lower()
        
        # Direct members from mapping
        members = self.family_to_members.get(family_lower, []).copy()
        
        # Also include the family_id itself if it's a valid brand
        if family_lower in self.brands_by_id and family_lower not in members:
            members.append(family_lower)
        
        return members
    
    def is_brand_in_family(self, brand_id: str, family_id: str) -> bool:
        """Check if brand_id belongs to the brand family"""
        if not brand_id or not family_id:
            return False
        
        brand_lower = brand_id.lower()
        family_lower = family_id.lower()
        
        # Direct match
        if brand_lower == family_lower:
            return True
        
        # Check if brand has this family
        brand_info = self.get_brand_info(brand_id)
        if brand_info and brand_info.get('brand_family_id') == family_lower:
            return True
        
        # Check family members
        return brand_lower in self.get_family_members(family_lower)
    
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
            'brand_families': len(self.family_to_members),
            'brands_with_family': sum(1 for b in self.brands_by_id.values() if b.get('brand_family_id')),
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
    bm = get_brand_master()
    stats = bm.get_stats()
    print(f"\n📊 Brand Dictionary Stats:")
    print(f"   Total brands: {stats['total_brands']}")
    print(f"   Total aliases: {stats['total_aliases']}")
    print(f"   Strict brands: {stats['strict_brands']}")
    print(f"   Brand families: {stats['brand_families']}")
    print(f"   Brands with family: {stats['brands_with_family']}")
    
    # Test family detection
    print("\n🔗 Brand Family Tests:")
    test_brands = ['miratorg_chef', 'miratorg', 'hochland professional', 'hochland', 'heinz']
    for brand in test_brands:
        family = bm.get_brand_family_id(brand)
        members = bm.get_family_members(family) if family else []
        print(f"   {brand} -> family={family}, members={members}")
    
    # Test detection
    print("\n🧪 Brand Detection Tests:")
    tests = [
        "БУЛЬОН грибной 2 кг. Knorr professional",
        "Кетчуп томатный 800 гр. Heinz",
        "Говядина Мираторг Chef 500г",
        "Сыр Hochland Professional плавленый",
        "ЛОСОСЬ филе 1.5кг",  # No brand
    ]
    
    for product in tests:
        brand_id, is_strict = bm.detect_brand(product)
        family = bm.get_brand_family_id(brand_id) if brand_id else None
        
        if brand_id:
            print(f"✅ {product[:45]:45}")
            print(f"     → brand={brand_id}, family={family}, strict={is_strict}")
        else:
            print(f"❌ {product[:45]:45}")
