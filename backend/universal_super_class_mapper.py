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
    
    # GUARD RULES: Hard negative filters to prevent false positives
    # These keywords EXCLUDE certain super_classes regardless of other matches
    # NOTE: Guard rules should be specific enough to avoid false positives
    guard_rules = {
        # Vegetables/Legumes - NOT seafood
        'бобы': {'exclude': ['seafood'], 'assign': 'vegetables.beans'},
        'эдамаме': {'exclude': ['seafood'], 'assign': 'vegetables.beans'},
        'горох': {'exclude': ['seafood'], 'assign': 'vegetables.peas'},
        'фасоль': {'exclude': ['seafood'], 'assign': 'vegetables.beans'},
        'чечевиц': {'exclude': ['seafood'], 'assign': 'vegetables.lentils'},
        'нут': {'exclude': ['seafood'], 'assign': 'vegetables.chickpeas'},
        
        # Canned fruits - NOT seafood
        'персик': {'exclude': ['seafood'], 'assign': 'canned.фрукты'},
        'ананас': {'exclude': ['seafood'], 'assign': 'canned.фрукты'},
        'груша': {'exclude': ['seafood'], 'assign': 'canned.фрукты'},
        'абрикос': {'exclude': ['seafood'], 'assign': 'canned.фрукты'},
        
        # CRITICAL: Meat cuts should NOT be classified as vegetables
        # "внутренняя часть" contains "нут" but it's MEAT, not chickpeas
        'внутренняя часть': {'exclude': ['vegetables', 'staples'], 'assign': 'meat.beef.round'},
        'тазобедренн': {'exclude': ['vegetables', 'staples', 'chicken'], 'assign': 'meat.beef.round'},
        
        # Paper/Disposables - NOT staples/food
        # NOTE: Removed 'пакет' - too generic, appears in product descriptions like "желатин пакет 1кг"
        # NOTE: 'бумага рисовая' is food (rice paper), not disposables
        'бумага для выпечки': {'exclude': ['staples', 'seafood', 'meat'], 'assign': 'disposables.paper'},
        'бумага туалетная': {'exclude': ['staples', 'seafood', 'meat'], 'assign': 'disposables.paper'},
        'бумага рисов': {'exclude': ['disposables'], 'assign': 'staples.rice_paper'},  # Rice paper is food
        'полотенц': {'exclude': ['staples', 'seafood', 'meat'], 'assign': 'disposables.napkins'},
        'салфетк': {'exclude': ['staples', 'seafood', 'meat'], 'assign': 'disposables.napkins'},
        'перчатк': {'exclude': ['staples', 'seafood', 'meat'], 'assign': 'disposables.gloves'},
        'пленк пищев': {'exclude': ['staples', 'seafood', 'meat'], 'assign': 'disposables.film'},
        'фольг': {'exclude': ['staples', 'seafood', 'meat'], 'assign': 'disposables.foil'},
        
        # Seaweed salads - special category, not shrimp
        'чука': {'exclude': ['seafood.shrimp'], 'assign': 'seafood.seaweed'},
        'вакаме': {'exclude': ['seafood.shrimp'], 'assign': 'seafood.seaweed'},
        'нори': {'exclude': ['seafood.shrimp'], 'assign': 'seafood.seaweed'},
        'водоросл': {'exclude': ['seafood.shrimp'], 'assign': 'seafood.seaweed'},
        
        # Fish - not shrimp (горбуша, семга, etc.)
        'горбуша': {'exclude': ['seafood.shrimp'], 'assign': 'seafood.salmon'},
        'тилапия': {'exclude': ['seafood.shrimp'], 'assign': 'seafood.tilapia'},
        'пангасиус': {'exclude': ['seafood.shrimp'], 'assign': 'seafood.pangasius'},
    }
    
    # DIRECT MAPPINGS - Check these FIRST before guard rules
    # These have highest priority for specific product types
    direct_map_priority = {
        # === MEAT CUTS (HIGHEST PRIORITY - prevent false matches) ===
        # "внутренняя часть" contains "нут" which triggers chickpeas - WRONG!
        'говядина внутрен': 'meat.beef.round',
        'говядина тазобедр': 'meat.beef.round',
        'свинина тазобедр': 'meat.pork.leg',
        'тазобедренн': 'meat.beef.round',  # Default to beef
        'тазобедр': 'meat.beef.round',  # Abbreviated form
        'внутренняя часть': 'meat.beef.round',
        'внутр.': 'meat.beef.round',  # Short form like "внутр. б/к"
        
        # === PUREE - Пюре (HIGHEST PRIORITY to avoid sugar conflicts) ===
        'пюре': 'ready_meals.puree',
        'пюре юдзу': 'ready_meals.puree.yuzu',
        'пюре манго': 'ready_meals.puree.mango',
        'пюре малин': 'ready_meals.puree.raspberry',
        'пюре клубник': 'ready_meals.puree.strawberry',
        'пюре маракуй': 'ready_meals.puree.passionfruit',
        'пюре персик': 'ready_meals.puree.peach',
        
        # === JUICES - Соки (HIGHEST PRIORITY to avoid salt/sugar conflicts) ===
        'сок томат': 'beverages.juice.tomato',  # Must be before 'соль' 
        'сок юдзу': 'beverages.juice.yuzu',
        'сок yuzu': 'beverages.juice.yuzu',
        'сок апельсин': 'beverages.juice.orange',
        'сок яблок': 'beverages.juice.apple',
        'сок ананас': 'beverages.juice.pineapple',
        'сок грейпфрут': 'beverages.juice.grapefruit',
        'сок виноград': 'beverages.juice.grape',
        'сок гранат': 'beverages.juice.pomegranate',
        'сок лимон': 'beverages.juice.lemon',
        'сок лайм': 'beverages.juice.lime',
        'сок манго': 'beverages.juice.mango',
        'сок': 'beverages.juice',  # Generic juice after specific types
        'фреш': 'beverages.juice',
        'нектар': 'beverages.nectar',
        
        # Additives that may contain "пакет" in name
        'желатин': 'additives.gelatin',
        'агар': 'additives.agar',
        'пектин': 'additives.pectin',
        # Salt - often comes in "пакет" packaging
        'соль': 'condiments.salt',
        # Rice-specific to avoid false matches
        'рис басмати': 'staples.рис.басмати',
        'рис жасмин': 'staples.рис.жасмин',
        'рис круглозерн': 'staples.рис',
        'рис длиннозерн': 'staples.рис',
        # Vegetables that may incorrectly get staples.рис
        'тыква': 'vegetables.тыква',
        'кабачок': 'vegetables.кабачок',
        # Crab - CRITICAL: Distinguish natural crab from imitation
        'краб камчат': 'seafood.crab.kamchatka',  # Натуральный камчатский краб
        'краб натур': 'seafood.crab.natural',     # Натуральный краб
        'king crab': 'seafood.crab.king',          # King crab
        'крабов палочк': 'seafood.crab_sticks',    # Крабовые палочки (имитация)
        'сурими': 'seafood.crab_sticks',           # Сурими (имитация)
        'снежный краб': 'seafood.crab_sticks',     # Снежный краб VICI = имитация
        'краб': 'seafood.crab',                    # Generic crab (will be refined)
        # Sugar
        'сахар': 'staples.сахар',
        
        # === FLOUR - МУКА (CRITICAL FIX) ===
        'мука': 'staples.мука',
        'мука пшеничная': 'staples.мука.пшеничная',
        'мука ржаная': 'staples.мука.ржаная',
        'мука кукурузная': 'staples.мука.кукурузная',
        'мука рисовая': 'staples.мука.рисовая',
        'мука гречневая': 'staples.мука.гречневая',
        'макфа': 'staples.мука',  # Brand often indicates flour
        
        # === CEREALS/GRAINS - КРУПЫ ===
        'гречк': 'staples.cereals',
        'греча': 'staples.cereals',
        'гречих': 'staples.cereals',
        'манк': 'staples.cereals',
        'манн': 'staples.cereals',
        'пшено': 'staples.cereals',
        'пшен': 'staples.cereals',
        'булгур': 'staples.cereals',
        'кускус': 'staples.cereals',
        'перловк': 'staples.cereals',
        'ячмен': 'staples.cereals',
        'ячнев': 'staples.cereals',
        'овсян': 'staples.cereals',
        'геркулес': 'staples.cereals',
        'горох': 'staples.cereals',
        'чечевиц': 'staples.cereals',
        'фасоль': 'staples.cereals',
        'нут': 'staples.cereals',
        'киноа': 'staples.cereals',
        
        # === BROTHS - БУЛЬОНЫ ===
        'бульон': 'ready_meals.broth',
        
        # === CANNED VEGETABLES - КОНСЕРВЫ ОВОЩНЫЕ ===
        'кукуруза ж': 'canned.vegetables',
        'кукуруза консерв': 'canned.vegetables',
        'маслин': 'canned.vegetables',
        'олив': 'canned.vegetables',
        'горошек': 'canned.vegetables',
        'горох консерв': 'canned.vegetables',
        'грибы маринов': 'canned.vegetables',
        'редис маринов': 'canned.vegetables',
        'редька маринов': 'canned.vegetables',
        
        # === FROZEN FOODS - ЗАМОРОЖЕННЫЕ ===
        'картофел фри': 'frozen.vegetables',
        'хэшбраун': 'frozen.vegetables',
        'пельмен': 'frozen.ready_meals',
        'варен': 'frozen.ready_meals',
        'котлет с/м': 'frozen.ready_meals',
        'гуляш с/м': 'frozen.ready_meals',
        'борщ с/м': 'frozen.ready_meals',
        'каша с/м': 'frozen.ready_meals',
        'уха с/м': 'frozen.ready_meals',
        
        # === PASTA - МАКАРОННЫЕ ИЗДЕЛИЯ ===
        'спагетти': 'pasta.spaghetti',
        'пенне': 'pasta.penne',
        'рожки': 'pasta.penne',
        'тальятелле': 'pasta.tagliatelle',
        'гнезда': 'pasta.tagliatelle',
        'вермишель': 'pasta.vermicelli',
        
        # === Categories from "other" analysis ===
        # Syrups (110 items)
        'сироп': 'beverages.syrup',
        
        # Asian noodles (9 items)
        'лапша': 'pasta.noodles',
        'соба': 'pasta.soba',
        'удон': 'pasta.udon',
        'рамен': 'pasta.ramen',
        'фунчоза': 'pasta.glass_noodles',
        
        # Nuts (12 items)
        'миндал': 'nuts.almonds',
        'фундук': 'nuts.hazelnuts',
        'кешью': 'nuts.cashews',
        'фисташ': 'nuts.pistachios',
        'грецк': 'nuts.walnuts',
        'арахис': 'nuts.peanuts',
        'кедров': 'nuts.pine_nuts',
        
        # Dried fruits (3 items)
        'чернослив': 'dried_fruits.prunes',
        'курага': 'dried_fruits.apricots',
        'изюм': 'dried_fruits.raisins',
        'инжир': 'dried_fruits.figs',
        'финик': 'dried_fruits.dates',
        
        # Soft drinks (31 items)
        'кола': 'beverages.cola',
        'эвервесс': 'beverages.soft_drinks',
        'спрайт': 'beverages.soft_drinks',
        'фанта': 'beverages.soft_drinks',
        'лимонад': 'beverages.lemonade',
        'газиров': 'beverages.carbonated',
        
        # Note: Juices are defined in direct_map_priority at the top
        
        # Concentrates (10 items)
        'концентрат': 'beverages.concentrate',
        
        # Exotic spices
        'галангал': 'condiments.spice',
        'имбирь': 'condiments.ginger',
        
        # Fish & Seafood (detailed)
        'угорь': 'seafood.eel',
        'судак': 'seafood.pike_perch',
        'окунь': 'seafood.perch',
        'гребеш': 'seafood.scallop',
        'краб': 'seafood.crab',
        
        # Meat products
        'бекон': 'meat.bacon',
        'стрипс': 'meat.strips',
        'фрикадельк': 'meat.meatballs',
        
        # Vegetables
        'шпинат': 'vegetables.spinach',
        'вишн': 'canned.cherries',
        
        # Desserts/Bakery
        'мороженое': 'frozen.ice_cream',
        'пирожное': 'bakery.pastry',
        'чизкейк': 'bakery.cheesecake',
        
        # Disposables
        'мешки': 'disposables.bags',
        'стакан': 'disposables.cups',
        'бутылка': 'disposables.bottles',
        'коробка': 'disposables.boxes',
        'крышк': 'disposables.lids',
        
        # Colorants/Additives
        'краситель': 'additives.colorant',
        'дрожжи': 'additives.yeast',
        
        # Fish - more specific
        'щука': 'seafood.pike',
        'сайда': 'seafood.pollock',
        'кета': 'seafood.chum_salmon',
        'изумидай': 'seafood.tilapia',
        # NOTE: 'филе' is too generic - use with meat type
        
        # Berries
        'брусника': 'frozen.berries',
        'облепиха': 'frozen.berries',
        'клюква': 'frozen.berries',
        'черника': 'frozen.berries',
        'малина': 'frozen.berries',
        'клубника': 'frozen.berries',
        
        # Vegetables
        'шампиньон': 'vegetables.mushrooms',
        'грибы': 'vegetables.mushrooms',
        
        # === CRITICAL FIX: MEAT CUTS (Generic cuts that need meat type context) ===
        # These are meat cuts that should be classified based on the meat type
        # NOT as chicken by default!
        
        # Pork cuts (свинина)
        'свинина корейка': 'meat.pork.loin',
        'свинина карбонад': 'meat.pork.loin',
        'свинина окорок': 'meat.pork.leg',
        'свинина лопатк': 'meat.pork.shoulder',
        'свинина грудинк': 'meat.pork.belly',
        'свинина шея': 'meat.pork.neck',
        'свинина ребр': 'meat.pork.ribs',
        'свинина вырезк': 'meat.pork.tenderloin',
        'свинина голяшк': 'meat.pork.shank',
        'свиной': 'meat.pork',
        'свиная': 'meat.pork',
        
        # Beef cuts (говядина)
        'говядина корейка': 'meat.beef.loin',
        'говядина окорок': 'meat.beef.round',
        'говядина лопатк': 'meat.beef.shoulder',
        'говядина грудинк': 'meat.beef.brisket',
        'говядина шея': 'meat.beef.neck',
        'говядина ребр': 'meat.beef.ribs',
        'говядина вырезк': 'meat.beef.tenderloin',
        'говядина голяшк': 'meat.beef.shank',
        'говядина тазобедр': 'meat.beef.round',
        'говяжий': 'meat.beef',
        'говяжья': 'meat.beef',
        
        # Lamb/Mutton cuts (баранина/ягнятина)
        'баранина корейка': 'meat.lamb.rack',
        'баранина окорок': 'meat.lamb.leg',
        'баранина лопатк': 'meat.lamb.shoulder',
        'баранина ребр': 'meat.lamb.ribs',
        'баранина шея': 'meat.lamb.neck',
        'баранина голяшк': 'meat.lamb.shank',
        'ягнятина корейка': 'meat.lamb.rack',
        'ягнятина окорок': 'meat.lamb.leg',
        'ягнятина лопатк': 'meat.lamb.shoulder',
        'ягнятина ребр': 'meat.lamb.ribs',
        'баранина': 'meat.lamb',
        'ягнятина': 'meat.lamb',
        
        # Venison (оленина)
        'оленина': 'meat.venison',
        'оленина филей': 'meat.venison.loin',
        'оленина корейка': 'meat.venison.rack',
        
        # Duck (утка)
        'утка': 'meat.duck',
        'утиная': 'meat.duck',
        'утиный': 'meat.duck',
        
        # Generic meat cuts (MUST come AFTER specific meat types!)
        # These will be used as fallback
        'корейка': 'meat.pork.loin',  # Default to pork if no meat type specified
        'окорок': 'meat.pork.leg',
        'лопатка': 'meat.pork.shoulder',
        'грудинка': 'meat.pork.belly',
        'шея': 'meat.pork.neck',
        'вырезка': 'meat.pork.tenderloin',
        'голяшка': 'meat.pork.shank',
        'карбонад': 'meat.pork.loin',
        'ребра': 'meat.pork.ribs',
        'тазобедренный': 'meat.beef.round',  # Usually beef
        'филей': 'meat.beef.loin',  # NOT seafood!
        
        # Meat products - more specific
        'пепперони': 'meat.pepperoni',
        'паштет': 'meat.pate',
        'байтс': 'meat.bites',
        'голубц': 'frozen.golubcy',
        
        # Chicken parts (only with chicken context!)
        'куриная грудка': 'meat.chicken.breast',
        'куриное бедро': 'meat.chicken.thigh',
        'куриные крылья': 'meat.chicken.wings',
        'куриная': 'meat.chicken',
        'кура': 'meat.chicken',
        'курин': 'meat.chicken',
        'цыпл': 'meat.chicken',
        'бройлер': 'meat.chicken',
        
        # Bakery
        'круассан': 'bakery.croissant',
        'багет': 'bakery.baguette',
        'панини': 'bakery.panini',
        'тарталетк': 'bakery.tartlet',
        'сухар': 'bakery.breadcrumbs',
        'маршмеллоу': 'confectionery.marshmallow',
        
        # Ready meals
        'суп': 'ready_meals.soup',
        'запеканк': 'ready_meals.casserole',
        'пюре': 'ready_meals.puree',
        
        # Beverages
        'пепси': 'beverages.pepsi',
        
        # === NEW: Fix misclassifications ===
        # Syrniki are NOT cheese
        'сырник': 'frozen.syrniki',
        
        # Ready dishes with meat - not meat category
        'плов': 'ready_meals.pilaf',
        'гёдза': 'frozen.gyoza',
        'блины': 'frozen.bliny',
        
        # Decor/confectionery - not beverages
        'глазурь': 'confectionery.glaze',
        'декор': 'confectionery.decor',
        
        # Spices - specific
        'анис': 'condiments.spice.anise',
        'бадьян': 'condiments.spice.star_anise',
        'кориандр': 'condiments.spice.coriander',
        'тмин': 'condiments.spice.cumin',
        'зира': 'condiments.spice.cumin',
        'орегано': 'condiments.spice.oregano',
        'базилик': 'condiments.spice.basil',
        'розмарин': 'condiments.spice.rosemary',
        'тимьян': 'condiments.spice.thyme',
        'мускат': 'condiments.spice.nutmeg',
        
        # Sauces - more specific
        'соус бонито': 'condiments.sauce.bonito',
        'бургер': 'condiments.sauce.burger',
        'ворчестер': 'condiments.sauce.worcester',
        'гриль': 'condiments.sauce.grill',
        'луков': 'condiments.sauce.onion',
        'сырн': 'condiments.sauce.cheese',
        'наполи': 'condiments.sauce.napoli',
        'деми глас': 'condiments.sauce.demi_glace',
        'песто': 'condiments.sauce.pesto',
        
        # Seafood cocktail
        'коктейль морск': 'seafood.cocktail',
        'лангустин': 'seafood.langoustine',
    }
    
    # Check priority direct mappings FIRST
    for key, super_class in direct_map_priority.items():
        if key in name_norm:
            return super_class, 1.0
    
    # Check GUARD RULES second
    for guard_key, guard_rule in guard_rules.items():
        if guard_key in name_norm:
            # This keyword triggers a guard rule
            assigned_class = guard_rule.get('assign')
            if assigned_class:
                return assigned_class, 1.0
    
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
        'васаби': 'condiments.wasabi',  # Специфичная категория для васаби
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
