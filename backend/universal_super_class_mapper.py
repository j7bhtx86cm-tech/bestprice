"""
UNIVERSAL Product Name → super_class Mapper

Использует базу данных supplier_items для автоматического определения super_class
на основе текстового сходства с name_norm.

Логика:
1. Нормализация имени продукта
2. Поиск в supplier_items с текстовым совпадением
3. Извлечение наиболее частого super_class среди matches
4. Fallback на 'other' если не найдено
"""
import os
import re
from pymongo import MongoClient
from collections import Counter

# Global cache
_super_class_cache = None
_db_connection = None

def get_db():
    """Get MongoDB connection"""
    global _db_connection
    if _db_connection is None:
        mongo_url = os.environ.get('MONGO_URL', 'mongodb://localhost:27017')
        db_name = os.environ.get('DB_NAME', 'test_database')
        _db_connection = MongoClient(mongo_url)[db_name]
    return _db_connection

def normalize_text(text):
    """Normalize text for matching"""
    if not text:
        return ""
    text = str(text).lower().strip().replace('ё', 'е')
    text = re.sub(r'[^\w\s]', ' ', text, flags=re.UNICODE)
    return re.sub(r'\s+', ' ', text).strip()

def extract_key_terms(text):
    """Extract key terms from product name"""
    if not text:
        return set()
    
    norm = normalize_text(text)
    words = norm.split()
    
    # Remove stop words and very short words
    stop_words = {'и', 'в', 'на', 'с', 'из', 'для', 'по', 'до', 'от', 'за', 'со', 'под'}
    key_terms = {w for w in words if len(w) >= 3 and w not in stop_words}
    
    return key_terms

def build_super_class_index():
    """Build index of keywords → super_class from supplier_items
    
    Returns dict: {keyword: {super_class: count}}
    """
    db = get_db()
    
    print("📚 Building super_class index from supplier_items...")
    
    # Get all active supplier_items
    items = list(db.supplier_items.find(
        {'active': True, 'super_class': {'$ne': None, '$ne': 'other'}},
        {'_id': 0, 'name_norm': 1, 'super_class': 1}
    ))
    
    print(f"   Loaded {len(items)} items")
    
    # Build keyword → super_class mapping
    keyword_to_classes = {}
    
    for item in items:
        name_norm = item.get('name_norm', '')
        super_class = item.get('super_class')
        
        if not super_class or super_class == 'other':
            continue
        
        # Extract keywords
        keywords = extract_key_terms(name_norm)
        
        for keyword in keywords:
            if keyword not in keyword_to_classes:
                keyword_to_classes[keyword] = Counter()
            keyword_to_classes[keyword][super_class] += 1
    
    print(f"   ✅ Built index: {len(keyword_to_classes)} keywords")
    
    return keyword_to_classes

def get_super_class_index():
    """Get or build super_class index"""
    global _super_class_cache
    if _super_class_cache is None:
        _super_class_cache = build_super_class_index()
    return _super_class_cache

def detect_super_class(product_name, min_confidence=0.3):
    """Detect super_class from product name
    
    Args:
        product_name: Product name (Russian)
        min_confidence: Minimum confidence threshold (0..1), default 0.3
    
    Returns:
        (super_class, confidence) or (None, 0.0)
    """
    if not product_name:
        return None, 0.0
    
    name_norm = normalize_text(product_name)
    
    # DIRECT MAPPINGS (high priority, confidence=1.0)
    # Расширенный набор для снижения 'other' с 29% до <10%
    direct_map = {
        # Condiments & Sauces
        'кетчуп': 'condiments.ketchup',
        'майонез': 'condiments.mayo',
        'соус': 'condiments.sauce',
        'горчиц': 'condiments.mustard',
        'хрен': 'condiments.horseradish',
        'аджик': 'condiments.adjika',
        
        # Spices & Seasonings
        'васаби': 'condiments.spice',
        'бадьян': 'condiments.spice',
        'кардамон': 'condiments.spice',
        'корица': 'condiments.spice',
        'анис': 'condiments.spice',
        'гвоздик': 'condiments.spice',
        'кориандр': 'condiments.spice',
        'куркум': 'condiments.spice',
        'паприк': 'condiments.spice',
        'перец': 'condiments.spice',
        'пряност': 'condiments.spice',
        'специ': 'condiments.spice',
        'приправ': 'condiments.seasoning',
        'заправк': 'condiments.seasoning',
        
        # Oils
        'кунжут': 'oils.sesame',
        'тыквен': 'oils.pumpkin',
        'фритюр': 'oils.frying',
        'оливков': 'staples.масло.оливковое',
        'подсолнеч': 'oils.sunflower',
        'рапсов': 'oils.rapeseed',
        
        # Seafood
        'сибас': 'seafood.seabass',
        'сибасс': 'seafood.seabass',
        'лосось': 'seafood.salmon',
        'сёмга': 'seafood.salmon',
        'форель': 'seafood.trout',
        'креветк': 'seafood.shrimp',
        'дорадо': 'seafood.seabream',
        'дорада': 'seafood.seabream',
        'тунец': 'canned.тунец.консервированный',
        'минтай': 'seafood.pollock',
        'треска': 'seafood.cod',
        'камбал': 'seafood.flounder',
        'палтус': 'seafood.halibut',
        'скумбр': 'seafood.mackerel',
        'сельд': 'seafood.herring',
        'анчоус': 'seafood.anchovy',
        'кальмар': 'seafood.squid',
        'осьминог': 'seafood.octopus',
        'мидии': 'seafood.mussels',
        'гребешок': 'seafood.scallop',
        'икра': 'seafood.caviar',
        
        # Meat
        'говядина': 'meat.beef',
        'свинина': 'meat.pork',
        'курица': 'meat.chicken',
        'индейка': 'meat.turkey',
        'ягнятина': 'meat.lamb',
        'утка': 'meat.duck',
        'фарш': 'meat.ground',
        'колбас': 'meat.kolbasa',
        'сосиск': 'meat.sausage',
        'ветчин': 'meat.ham',
        
        # Additives
        'желатин': 'additives.gelatin',
        'глутамат': 'additives.msg',
        'кокосов': 'additives.coconut',
        'крахмал': 'additives.starch',
        'разрыхлител': 'additives.baking_powder',
        'сода': 'additives.baking_soda',
        'уксус': 'condiments.vinegar',
        'лимонн': 'additives.citric_acid',
        
        # Pickles & Preserves
        'релиш': 'condiments.relish',
        'огурц': 'canned.огурцы',
        'помидор': 'canned.томаты.консервированные',
        'томат': 'canned.томаты.консервированные',
        'оливк': 'canned.оливки',
        'каперс': 'canned.каперсы',
        'корнишон': 'canned.огурцы'
    }
    
    # Check direct mappings first
    for key, super_class in direct_map.items():
        if key in name_norm:
            return super_class, 1.0
    
    # Fallback to keyword-based detection
    index = get_super_class_index()
    
    # Extract keywords from product name
    keywords = extract_key_terms(product_name)
    
    if not keywords:
        return None, 0.0
    
    # Collect all super_class candidates from keywords
    class_votes = Counter()
    
    for keyword in keywords:
        if keyword in index:
            # Add votes from this keyword
            for super_class, count in index[keyword].items():
                class_votes[super_class] += count
    
    if not class_votes:
        return None, 0.0
    
    # Get top candidate
    top_class, top_votes = class_votes.most_common(1)[0]
    
    # Calculate confidence
    total_votes = sum(class_votes.values())
    confidence = top_votes / total_votes if total_votes > 0 else 0.0
    
    if confidence < min_confidence:
        return None, confidence
    
    return top_class, confidence

# For backward compatibility
def detect_product_core(product_name):
    """Legacy interface - returns super_class for compatibility"""
    super_class, confidence = detect_super_class(product_name)
    return super_class

# Test if run directly
if __name__ == '__main__':
    test_products = [
        "Кетчуп томатный 800 гр. Heinz",
        "Говядина фарш 80/20 5 кг",
        "ЛОСОСЬ филе трим D Чили с/м вес 1.5 кг",
        "Креветки 16/20 варено-мороженые 1 кг",
        "СИБАС целый 300-400 гр",
        "Масло оливковое Extra Virgin 1 л",
        "Мука пшеничная высший сорт 2 кг"
    ]
    
    print("\n🧪 Testing super_class detection:\n")
    for product in test_products:
        super_class, confidence = detect_super_class(product)
        status = "✅" if super_class else "❌"
        print(f"{status} {product[:50]:50} → {super_class or 'NONE':30} (conf: {confidence:.2f})")
