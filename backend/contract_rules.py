"""BestPrice Contract Rules - Integration with BESTPRICE_IDEAL_CONTRACT_v8.xlsx"""
import pandas as pd
from pathlib import Path
from typing import Dict, Set, Optional

# Load contract file
CONTRACT_FILE = Path(__file__).parent / 'BESTPRICE_IDEAL_CONTRACT_v8.xlsx'

class ContractRules:
    """Singleton for accessing contract rules"""
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._load_rules()
        return cls._instance
    
    def _load_rules(self):
        """Load all rules from contract file"""
        print(f"📋 Loading contract rules from {CONTRACT_FILE}")
        
        # Load brands
        brands_df = pd.read_excel(CONTRACT_FILE, sheet_name='BRANDS')
        self.strict_brands = set()
        for _, row in brands_df.iterrows():
            brand = row['canonical_brand']
            is_strict = row.get('brand_strict_default', False)
            if is_strict or is_strict == 1 or str(is_strict).lower() == 'true':
                self.strict_brands.add(brand.lower())
        
        # Load brand aliases
        aliases_df = pd.read_excel(CONTRACT_FILE, sheet_name='BRAND_ALIASES')
        self.brand_aliases = {}  # alias -> canonical
        for _, row in aliases_df.iterrows():
            canonical = row['canonical_brand'].lower()
            alias = row['alias'].lower()
            self.brand_aliases[alias] = canonical
        
        # Load dictionary rules
        dict_df = pd.read_excel(CONTRACT_FILE, sheet_name='SEED_DICT_RULES')
        
        # Build seafood attributes map
        self.seafood_attributes = {}
        for _, row in dict_df.iterrows():
            if row.get('РАЗДЕЛ') == 'Рыба+морепродукты':
                raw = str(row['RAW']).lower()
                canonical = str(row['CANONICAL']).lower() if pd.notna(row['CANONICAL']) else raw
                attr_type = str(row['ТИП']).lower()
                
                if attr_type not in self.seafood_attributes:
                    self.seafood_attributes[attr_type] = {}
                
                self.seafood_attributes[attr_type][raw] = canonical
        
        # Build meat attributes
        self.meat_attributes = {}
        for _, row in dict_df.iterrows():
            if row.get('РАЗДЕЛ') == 'Мясо':
                raw = str(row['RAW']).lower()
                canonical = str(row['CANONICAL']).lower() if pd.notna(row['CANONICAL']) else raw
                attr_type = str(row['ТИП']).lower()
                
                if attr_type not in self.meat_attributes:
                    self.meat_attributes[attr_type] = {}
                
                self.meat_attributes[attr_type][raw] = canonical
        
        print(f"✅ Loaded {len(self.strict_brands)} strict brands")
        print(f"✅ Loaded {len(self.brand_aliases)} brand aliases")
        print(f"✅ Loaded {len(self.seafood_attributes)} seafood attribute types")
        print(f"✅ Loaded {len(self.meat_attributes)} meat attribute types")
    
    def is_strict_brand(self, brand_name: str) -> bool:
        """Check if brand requires strict matching"""
        if not brand_name:
            return False
        
        brand_lower = brand_name.lower()
        
        # Check canonical name
        if brand_lower in self.strict_brands:
            return True
        
        # Check aliases
        canonical = self.brand_aliases.get(brand_lower)
        if canonical and canonical in self.strict_brands:
            return True
        
        return False
    
    def get_canonical_brand(self, brand_name: str) -> Optional[str]:
        """Get canonical brand name from alias"""
        if not brand_name:
            return None
        
        brand_lower = brand_name.lower()
        return self.brand_aliases.get(brand_lower, brand_lower)
    
    def extract_seafood_form(self, name: str) -> Optional[str]:
        """Extract seafood form (с головой, без головы, etc.)"""
        name_lower = name.lower()
        
        form_attrs = self.seafood_attributes.get('form', {})
        for raw, canonical in form_attrs.items():
            if raw in name_lower:
                return canonical
        
        return None
    
    def extract_trim_grade(self, name: str) -> Optional[str]:
        """Extract trim grade (trim A, trim C, trim D)"""
        name_lower = name.lower()
        
        grade_attrs = self.seafood_attributes.get('grade', {})
        for raw, canonical in grade_attrs.items():
            if raw in name_lower:
                return canonical
        
        return None

# Global instance
try:
    contract_rules = ContractRules()
except Exception as e:
    print(f"⚠️ Warning: Could not load contract rules: {e}")
    contract_rules = None
