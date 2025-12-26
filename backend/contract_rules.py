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
        
        # Load dictionary rules (NEW!)
        dict_df = pd.read_excel(CONTRACT_FILE, sheet_name='SEED_DICT_RULES')
        
        # Build product keywords by section (NEW - KEY FIX!)
        self.product_keywords = {}  # section -> {raw: canonical}
        self.section_to_category = {}  # section -> super_class prefix
        
        # Map sections to super_class categories
        section_mapping = {
            'Рыба+морепродукты': 'seafood',
            'Мясо': 'meat',
            'Молочка+яйца': 'dairy',
            'Фрукты/ягоды/заморозка/пф': 'fruits',
            'Овощи': 'vegetables',
            'Бакалея': 'staples',
            'Консервация': 'canned',
            'Напитки': 'beverages'
        }
        
        for _, row in dict_df.iterrows():
            section = row.get('РАЗДЕЛ')
            if pd.isna(section):
                continue
            
            raw = str(row['RAW']).lower()
            canonical = str(row.get('CANONICAL', raw)).lower() if pd.notna(row.get('CANONICAL')) else raw
            attr_type = str(row.get('ТИП', '')).lower()
            
            # Store product-type keywords
            if attr_type == 'product':
                if section not in self.product_keywords:
                    self.product_keywords[section] = {}
                self.product_keywords[section][raw] = canonical
                
                # Store section category mapping
                if section in section_mapping:
                    self.section_to_category[section] = section_mapping[section]
        
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
        print(f"✅ Loaded {len(self.product_keywords)} product sections with keywords")
        print(f"✅ Loaded {len(self.seafood_attributes)} seafood attribute types")
        print(f"✅ Loaded {len(self.meat_attributes)} meat attribute types")
        
        # Print product keyword counts per section
        for section, keywords in self.product_keywords.items():
            print(f"   - {section}: {len(keywords)} product types")
    
    def classify_by_dictionary(self, name: str) -> Optional[str]:
        """Classify product using dictionary rules (NEW!)
        
        Returns: super_class category or None if not found
        """
        name_lower = name.lower()
        
        # Check each section's product keywords
        for section, keywords in self.product_keywords.items():
            for raw_keyword, canonical in keywords.items():
                if raw_keyword in name_lower:
                    # Found match! Return category based on section
                    base_category = self.section_to_category.get(section, 'other')
                    
                    # Create subcategory from canonical name
                    canonical_clean = canonical.replace('_', '.')
                    return f"{base_category}.{canonical_clean}"
        
        return None
    
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
