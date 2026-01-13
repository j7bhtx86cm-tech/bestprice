"""
BestPrice - Массовая переклассификация товаров
Исправляет все найденные проблемы классификации
"""

import os
import re
import logging
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv('/app/backend/.env')
client = MongoClient(os.environ.get('MONGO_URL'))
db = client[os.environ.get('DB_NAME')]


# === ПРАВИЛА ПЕРЕИМЕНОВАНИЯ КАТЕГОРИЙ ===
CATEGORY_RENAME = {
    # Русские -> Английские
    'staples.мука': 'staples.flour',
    'staples.сахар': 'staples.sugar',
    'canned.огурцы': 'canned.pickles',
    'canned.томаты.консервированные': 'canned.tomatoes',
    'canned.тунец.консервированный': 'canned.tuna',
    'staples.масло.оливковое': 'oils.olive',
    'staples.рис': 'staples.rice',
    'canned.каперсы': 'canned.capers',
    'staples.рис.жасмин': 'staples.rice.jasmine',
    'vegetables.тыква': 'vegetables.pumpkin',
    'staples.рис.басмати': 'staples.rice.basmati',
    'canned.оливки': 'canned.olives',
}


# === ПРАВИЛА КЛАССИФИКАЦИИ ПО КЛЮЧЕВЫМ СЛОВАМ ===
CLASSIFICATION_RULES = [
    # Морепродукты - высший приоритет
    {'pattern': r'креветк|shrimp|prawn|лангустин|langoustine', 'super_class': 'seafood.shrimp', 'priority': 100},
    {'pattern': r'кальмар|squid|calamari', 'super_class': 'seafood.squid', 'priority': 100},
    {'pattern': r'лосось|salmon|сёмга|семга|форель|trout', 'super_class': 'seafood.salmon', 'priority': 100},
    {'pattern': r'тунец|tuna', 'super_class': 'seafood.tuna', 'priority': 100},
    {'pattern': r'краб|crab|камчат', 'super_class': 'seafood.crab', 'priority': 100},
    {'pattern': r'гребеш|scallop', 'super_class': 'seafood.scallop', 'priority': 100},
    {'pattern': r'мидии|mussel', 'super_class': 'seafood.shellfish.mussels', 'priority': 100},
    {'pattern': r'устриц|oyster', 'super_class': 'seafood.shellfish.oysters', 'priority': 100},
    {'pattern': r'осьминог|octopus', 'super_class': 'seafood.octopus', 'priority': 100},
    {'pattern': r'угорь|eel|унаги', 'super_class': 'seafood.eel', 'priority': 100},
    {'pattern': r'треска|cod|минтай|pollock', 'super_class': 'seafood.cod', 'priority': 100},
    {'pattern': r'сельд|herring', 'super_class': 'seafood.herring', 'priority': 100},
    {'pattern': r'икра|caviar|tobiko|masago', 'super_class': 'seafood.caviar', 'priority': 100},
    {'pattern': r'водорос|seaweed|nori|вакаме|wakame|чука', 'super_class': 'seafood.seaweed', 'priority': 100},
    {'pattern': r'судак|pike.?perch|zander', 'super_class': 'seafood.pike_perch', 'priority': 100},
    {'pattern': r'щука(?!.*перч)|pike(?!.*perch)', 'super_class': 'seafood.pike', 'priority': 100},
    {'pattern': r'сайда|saithe|pollock', 'super_class': 'seafood.pollock', 'priority': 100},
    {'pattern': r'горбуша|pink.?salmon', 'super_class': 'seafood.pink_salmon', 'priority': 100},
    {'pattern': r'кета|chum|keta', 'super_class': 'seafood.chum_salmon', 'priority': 100},
    {'pattern': r'тилапия|tilapia|изумидай', 'super_class': 'seafood.tilapia', 'priority': 100},
    {'pattern': r'окунь|perch|seabass|сибас', 'super_class': 'seafood.seabass', 'priority': 100},
    {'pattern': r'дорадо|dorado|seabream|дорада', 'super_class': 'seafood.seabream', 'priority': 100},
    {'pattern': r'палтус|halibut', 'super_class': 'seafood.halibut', 'priority': 100},
    {'pattern': r'камбала|flounder|flatfish', 'super_class': 'seafood.flatfish', 'priority': 100},
    {'pattern': r'тюрбо|turbot', 'super_class': 'seafood.turbot', 'priority': 100},
    {'pattern': r'морепродукт|seafood|морской коктейль', 'super_class': 'seafood.mix', 'priority': 90},
    {'pattern': r'масляная рыба|butterfish|эсколар', 'super_class': 'seafood.butterfish', 'priority': 100},
    {'pattern': r'скумбрия|mackerel', 'super_class': 'seafood.mackerel', 'priority': 100},
    {'pattern': r'анчоус|anchov', 'super_class': 'seafood.anchovy', 'priority': 100},
    {'pattern': r'сардин|sardine', 'super_class': 'seafood.sardine', 'priority': 100},
    {'pattern': r'навага|navaga', 'super_class': 'seafood.navaga', 'priority': 100},
    {'pattern': r'зубатка|wolffish|catfish', 'super_class': 'seafood.wolffish', 'priority': 100},
    {'pattern': r'пангасиус|pangasius|баса', 'super_class': 'seafood.pangasius', 'priority': 100},
    {'pattern': r'\bрыб[аыу]|\bfish\b|филе.*(с/м|свежемор|охлажд)', 'super_class': 'seafood.fish', 'priority': 80},
    
    # Мясо
    {'pattern': r'курица|куриц|chicken|цыплён|цыпл|бройлер', 'super_class': 'meat.chicken', 'priority': 95},
    {'pattern': r'говядин|beef|телятин|veal|мраморн.*(говяд|beef)', 'super_class': 'meat.beef', 'priority': 95},
    {'pattern': r'свинин|pork|поросён', 'super_class': 'meat.pork', 'priority': 95},
    {'pattern': r'баранин|lamb|ягнёнок|ягнятин', 'super_class': 'meat.lamb', 'priority': 95},
    {'pattern': r'утка|утин|duck', 'super_class': 'meat.duck', 'priority': 95},
    {'pattern': r'индейк|turkey', 'super_class': 'meat.turkey', 'priority': 95},
    {'pattern': r'кролик|rabbit', 'super_class': 'meat.rabbit', 'priority': 95},
    {'pattern': r'оленин|venison|deer', 'super_class': 'meat.venison', 'priority': 95},
    {'pattern': r'колбас|sausage|сосиск|сардельк', 'super_class': 'meat.sausage', 'priority': 90},
    {'pattern': r'бекон|bacon|грудинк', 'super_class': 'meat.bacon', 'priority': 90},
    {'pattern': r'ветчин|ham|хамон|прошутто|prosciutto', 'super_class': 'meat.ham', 'priority': 90},
    {'pattern': r'фарш|ground|minced', 'super_class': 'meat.ground', 'priority': 90},
    {'pattern': r'котлет|cutlet|patty', 'super_class': 'meat.cutlets', 'priority': 90},
    {'pattern': r'пельмен|dumpling', 'super_class': 'ready_meals.pelmeni', 'priority': 90},
    
    # Молочные
    {'pattern': r'сыр|cheese|пармезан|parmesan|моцарел|mozzarella|чеддер|cheddar|горгонзол|gorgonzola|бри|camembert|рикотта|ricotta|маскарпоне|mascarpone', 'super_class': 'dairy.cheese', 'priority': 90},
    {'pattern': r'молоко|milk', 'super_class': 'dairy.milk', 'priority': 90},
    {'pattern': r'сливк|cream(?!.*сыр)', 'super_class': 'dairy.cream', 'priority': 90},
    {'pattern': r'масло.*сливочн|butter(?!.*fish)', 'super_class': 'dairy.butter', 'priority': 90},
    {'pattern': r'сметан|sour.?cream', 'super_class': 'dairy.sour_cream', 'priority': 90},
    {'pattern': r'йогурт|yogurt', 'super_class': 'dairy.yogurt', 'priority': 90},
    {'pattern': r'творог|cottage.?cheese', 'super_class': 'dairy.cottage_cheese', 'priority': 90},
    {'pattern': r'кефир|kefir', 'super_class': 'dairy.kefir', 'priority': 90},
    
    # Овощи
    {'pattern': r'помидор|томат|tomato', 'super_class': 'vegetables.tomato', 'priority': 85},
    {'pattern': r'картофел|картошк|potato', 'super_class': 'vegetables.potato', 'priority': 85},
    {'pattern': r'лук(?!.*овин)|onion', 'super_class': 'vegetables.onion', 'priority': 85},
    {'pattern': r'чеснок|garlic', 'super_class': 'vegetables.garlic', 'priority': 85},
    {'pattern': r'морковь|carrot', 'super_class': 'vegetables.carrot', 'priority': 85},
    {'pattern': r'капуст|cabbage', 'super_class': 'vegetables.cabbage', 'priority': 85},
    {'pattern': r'огурец|cucumber', 'super_class': 'vegetables.cucumber', 'priority': 85},
    {'pattern': r'перец.*болгар|bell.?pepper|паприка|paprika', 'super_class': 'vegetables.bell_pepper', 'priority': 85},
    {'pattern': r'баклажан|eggplant|aubergine', 'super_class': 'vegetables.eggplant', 'priority': 85},
    {'pattern': r'грибы|гриб|mushroom|шампиньон|champignon|шиитаке|shiitake', 'super_class': 'vegetables.mushrooms', 'priority': 85},
    {'pattern': r'шпинат|spinach', 'super_class': 'vegetables.spinach', 'priority': 85},
    {'pattern': r'спаржа|asparagus', 'super_class': 'vegetables.asparagus', 'priority': 85},
    {'pattern': r'артишок|artichoke', 'super_class': 'vegetables.artichoke', 'priority': 85},
    {'pattern': r'тыква|pumpkin|squash', 'super_class': 'vegetables.pumpkin', 'priority': 85},
    {'pattern': r'кабачок|zucchini|courgette', 'super_class': 'vegetables.zucchini', 'priority': 85},
    {'pattern': r'свекла|beet', 'super_class': 'vegetables.beet', 'priority': 85},
    {'pattern': r'горох|pea(?!nut)', 'super_class': 'vegetables.peas', 'priority': 85},
    {'pattern': r'фасоль|bean(?!.*кофе|coffee)', 'super_class': 'vegetables.beans', 'priority': 85},
    
    # Фрукты и ягоды
    {'pattern': r'яблок|apple', 'super_class': 'fruits.apple', 'priority': 85},
    {'pattern': r'груша|pear', 'super_class': 'fruits.pear', 'priority': 85},
    {'pattern': r'апельсин|orange', 'super_class': 'fruits.orange', 'priority': 85},
    {'pattern': r'лимон|lemon', 'super_class': 'fruits.lemon', 'priority': 85},
    {'pattern': r'лайм|lime', 'super_class': 'fruits.lime', 'priority': 85},
    {'pattern': r'банан|banana', 'super_class': 'fruits.banana', 'priority': 85},
    {'pattern': r'манго|mango', 'super_class': 'fruits.mango', 'priority': 85},
    {'pattern': r'ананас|pineapple', 'super_class': 'fruits.pineapple', 'priority': 85},
    {'pattern': r'клубник|strawberry|земляник', 'super_class': 'fruits.strawberry', 'priority': 85},
    {'pattern': r'малин|raspberry', 'super_class': 'fruits.raspberry', 'priority': 85},
    {'pattern': r'черник|blueberry|голубик', 'super_class': 'fruits.blueberry', 'priority': 85},
    {'pattern': r'вишн|cherry', 'super_class': 'fruits.cherry', 'priority': 85},
    {'pattern': r'слив|plum', 'super_class': 'fruits.plum', 'priority': 85},
    {'pattern': r'персик|peach', 'super_class': 'fruits.peach', 'priority': 85},
    {'pattern': r'абрикос|apricot', 'super_class': 'fruits.apricot', 'priority': 85},
    {'pattern': r'виноград|grape(?!fruit)', 'super_class': 'fruits.grape', 'priority': 85},
    {'pattern': r'киви|kiwi', 'super_class': 'fruits.kiwi', 'priority': 85},
    {'pattern': r'смородин|currant', 'super_class': 'fruits.currant', 'priority': 85},
    {'pattern': r'грейпфрут|grapefruit', 'super_class': 'fruits.grapefruit', 'priority': 85},
    
    # Напитки
    {'pattern': r'сок(?!.*кокос)|juice', 'super_class': 'beverages.juice', 'priority': 85},
    {'pattern': r'кола|cola|pepsi|пепси', 'super_class': 'beverages.cola', 'priority': 85},
    {'pattern': r'сироп|syrup', 'super_class': 'beverages.syrup', 'priority': 85},
    {'pattern': r'чай|tea(?!.*масло)', 'super_class': 'beverages.tea', 'priority': 85},
    {'pattern': r'кофе|coffee', 'super_class': 'beverages.coffee', 'priority': 85},
    {'pattern': r'какао|cocoa|горячий шоколад', 'super_class': 'beverages.cocoa', 'priority': 85},
    {'pattern': r'вода.*мин|mineral.?water|газир.*вода', 'super_class': 'beverages.water', 'priority': 85},
    {'pattern': r'лимонад|lemonade', 'super_class': 'beverages.lemonade', 'priority': 85},
    {'pattern': r'нектар|nectar', 'super_class': 'beverages.nectar', 'priority': 85},
    {'pattern': r'напиток|drink|beverage', 'super_class': 'beverages.soft_drinks', 'priority': 70},
    
    # Макароны
    {'pattern': r'спагетти|spaghetti', 'super_class': 'pasta.spaghetti', 'priority': 85},
    {'pattern': r'пенне|penne', 'super_class': 'pasta.penne', 'priority': 85},
    {'pattern': r'фузилли|fusilli', 'super_class': 'pasta.fusilli', 'priority': 85},
    {'pattern': r'тальятелле|tagliatelle', 'super_class': 'pasta.tagliatelle', 'priority': 85},
    {'pattern': r'фетучини|fettuccine', 'super_class': 'pasta.fettuccine', 'priority': 85},
    {'pattern': r'лазанья|lasagne|lasagna', 'super_class': 'pasta.lasagna', 'priority': 85},
    {'pattern': r'ригатони|rigatoni', 'super_class': 'pasta.rigatoni', 'priority': 85},
    {'pattern': r'лапша|noodle|удон|udon|рамен|ramen|соба|soba', 'super_class': 'pasta.noodles', 'priority': 85},
    {'pattern': r'вермишель|vermicelli', 'super_class': 'pasta.vermicelli', 'priority': 85},
    {'pattern': r'макарон|pasta|macaroni', 'super_class': 'pasta.macaroni', 'priority': 75},
    
    # Крупы и бакалея
    {'pattern': r'\bрис\b|rice', 'super_class': 'staples.rice', 'priority': 85},
    {'pattern': r'гречк|buckwheat', 'super_class': 'staples.buckwheat', 'priority': 85},
    {'pattern': r'овсян|oat|овёс', 'super_class': 'staples.oats', 'priority': 85},
    {'pattern': r'мука|flour', 'super_class': 'staples.flour', 'priority': 85},
    {'pattern': r'сахар|sugar', 'super_class': 'staples.sugar', 'priority': 85},
    {'pattern': r'соль(?!.*ин)|salt', 'super_class': 'condiments.salt', 'priority': 85},
    {'pattern': r'кускус|couscous', 'super_class': 'staples.couscous', 'priority': 85},
    {'pattern': r'булгур|bulgur', 'super_class': 'staples.bulgur', 'priority': 85},
    {'pattern': r'киноа|quinoa', 'super_class': 'staples.quinoa', 'priority': 85},
    {'pattern': r'крупа|cereal|каша', 'super_class': 'staples.cereals', 'priority': 75},
    
    # Соусы и приправы
    {'pattern': r'соус|sauce', 'super_class': 'condiments.sauce', 'priority': 80},
    {'pattern': r'майонез|mayo', 'super_class': 'condiments.mayo', 'priority': 85},
    {'pattern': r'кетчуп|ketchup', 'super_class': 'condiments.ketchup', 'priority': 85},
    {'pattern': r'горчиц|mustard', 'super_class': 'condiments.mustard', 'priority': 85},
    {'pattern': r'уксус|vinegar', 'super_class': 'condiments.vinegar', 'priority': 85},
    {'pattern': r'васаби|wasabi', 'super_class': 'condiments.wasabi', 'priority': 85},
    {'pattern': r'имбир|ginger', 'super_class': 'condiments.ginger', 'priority': 85},
    {'pattern': r'мёд|мед|honey', 'super_class': 'condiments.honey', 'priority': 85},
    {'pattern': r'специ|spice|пряност', 'super_class': 'condiments.spice', 'priority': 80},
    {'pattern': r'приправ|seasoning', 'super_class': 'condiments.seasoning', 'priority': 80},
    
    # Масла
    {'pattern': r'масло.*оливков|olive.?oil', 'super_class': 'oils.olive', 'priority': 85},
    {'pattern': r'масло.*подсолнечн|sunflower.?oil', 'super_class': 'oils.sunflower', 'priority': 85},
    {'pattern': r'масло.*кунжутн|sesame.?oil', 'super_class': 'oils.sesame', 'priority': 85},
    {'pattern': r'масло.*тыквенн|pumpkin.?oil', 'super_class': 'oils.pumpkin', 'priority': 85},
    {'pattern': r'масло.*фритюр|frying.?oil', 'super_class': 'oils.frying', 'priority': 85},
    
    # Консервы
    {'pattern': r'консерв|canned|preserve', 'super_class': 'canned.vegetables', 'priority': 70},
    {'pattern': r'огурц.*марин|pickle', 'super_class': 'canned.pickles', 'priority': 85},
    {'pattern': r'оливк|olive(?!.*oil)', 'super_class': 'canned.olives', 'priority': 85},
    {'pattern': r'капер|caper', 'super_class': 'canned.capers', 'priority': 85},
    
    # Выпечка
    {'pattern': r'хлеб|bread|батон|baguette', 'super_class': 'bakery.bread', 'priority': 85},
    {'pattern': r'булочка|bun|круассан|croissant', 'super_class': 'bakery.bun', 'priority': 85},
    {'pattern': r'пицц|pizza', 'super_class': 'bakery.pizza', 'priority': 85},
    {'pattern': r'торт|cake', 'super_class': 'bakery.cake', 'priority': 85},
    {'pattern': r'тесто|dough', 'super_class': 'bakery.dough', 'priority': 85},
    {'pattern': r'сухар|breadcrumb', 'super_class': 'bakery.breadcrumbs', 'priority': 85},
    
    # Замороженные продукты
    {'pattern': r'мороженое|ice.?cream', 'super_class': 'frozen.ice_cream', 'priority': 85},
    {'pattern': r'заморож|frozen|с/м|свежеморож', 'super_class': 'frozen.products', 'priority': 60},
    
    # Готовые блюда
    {'pattern': r'пюре|puree', 'super_class': 'ready_meals.puree', 'priority': 85},
    {'pattern': r'бульон|broth|stock', 'super_class': 'ready_meals.broth', 'priority': 85},
    {'pattern': r'суп|soup', 'super_class': 'ready_meals.soup', 'priority': 85},
    
    # Упаковка
    {'pattern': r'упаков|packag|пакет|bag|контейнер|container', 'super_class': 'packaging', 'priority': 70},
    {'pattern': r'перчатк|glove', 'super_class': 'disposables.gloves', 'priority': 85},
    {'pattern': r'салфетк|napkin', 'super_class': 'disposables.napkins', 'priority': 85},
    {'pattern': r'стакан|cup', 'super_class': 'disposables.cups', 'priority': 85},
]


def classify_product(name):
    """Классифицирует продукт по названию"""
    if not name:
        return None, 0
    
    name_lower = name.lower()
    best_match = None
    best_priority = 0
    
    for rule in CLASSIFICATION_RULES:
        if re.search(rule['pattern'], name_lower, re.IGNORECASE):
            if rule['priority'] > best_priority:
                best_priority = rule['priority']
                best_match = rule['super_class']
    
    return best_match, best_priority


def run_reclassification():
    """Запускает переклассификацию всех товаров"""
    logger.info("=" * 60)
    logger.info("ЗАПУСК МАССОВОЙ ПЕРЕКЛАССИФИКАЦИИ")
    logger.info("=" * 60)
    
    # 1. Переименование русских категорий
    logger.info("\n1️⃣ Переименование русских категорий...")
    renamed = 0
    for old_cat, new_cat in CATEGORY_RENAME.items():
        result = db.supplier_items.update_many(
            {'super_class': old_cat},
            {'$set': {'super_class': new_cat, 'reclassified_at': datetime.now(timezone.utc).isoformat()}}
        )
        if result.modified_count > 0:
            logger.info(f"   {old_cat} -> {new_cat}: {result.modified_count}")
            renamed += result.modified_count
    logger.info(f"   Итого переименовано: {renamed}")
    
    # 2. Исправление неверных классификаций (морепродукты как meat)
    logger.info("\n2️⃣ Исправление морепродуктов классифицированных как meat...")
    fixed_seafood = 0
    
    # Найти товары meat которые на самом деле seafood
    meat_items = list(db.supplier_items.find(
        {'active': True, 'super_class': {'$regex': '^meat'}},
        {'_id': 1, 'name_raw': 1, 'super_class': 1}
    ))
    
    for item in meat_items:
        new_class, priority = classify_product(item['name_raw'])
        if new_class and new_class.startswith('seafood') and priority >= 80:
            db.supplier_items.update_one(
                {'_id': item['_id']},
                {'$set': {
                    'super_class': new_class,
                    'product_core_id': new_class,
                    'reclassified_at': datetime.now(timezone.utc).isoformat(),
                    'reclassified_from': item['super_class']
                }}
            )
            fixed_seafood += 1
            if fixed_seafood <= 20:
                logger.info(f"   ✅ {item['name_raw'][:50]} : {item['super_class']} -> {new_class}")
    
    logger.info(f"   Итого исправлено seafood: {fixed_seafood}")
    
    # 3. Исправление мяса классифицированного как seafood
    logger.info("\n3️⃣ Исправление мяса классифицированного как seafood...")
    fixed_meat = 0
    
    seafood_items = list(db.supplier_items.find(
        {'active': True, 'super_class': {'$regex': '^seafood'}},
        {'_id': 1, 'name_raw': 1, 'super_class': 1}
    ))
    
    for item in seafood_items:
        new_class, priority = classify_product(item['name_raw'])
        if new_class and new_class.startswith('meat') and priority >= 90:
            db.supplier_items.update_one(
                {'_id': item['_id']},
                {'$set': {
                    'super_class': new_class,
                    'product_core_id': new_class,
                    'reclassified_at': datetime.now(timezone.utc).isoformat(),
                    'reclassified_from': item['super_class']
                }}
            )
            fixed_meat += 1
            if fixed_meat <= 20:
                logger.info(f"   ✅ {item['name_raw'][:50]} : {item['super_class']} -> {new_class}")
    
    logger.info(f"   Итого исправлено meat: {fixed_meat}")
    
    # 4. Детализация generic категории "meat"
    logger.info("\n4️⃣ Детализация generic категории 'meat'...")
    generic_meat = list(db.supplier_items.find(
        {'active': True, 'super_class': 'meat'},
        {'_id': 1, 'name_raw': 1}
    ))
    
    detailed_meat = 0
    for item in generic_meat:
        new_class, priority = classify_product(item['name_raw'])
        if new_class and priority >= 70:
            db.supplier_items.update_one(
                {'_id': item['_id']},
                {'$set': {
                    'super_class': new_class,
                    'product_core_id': new_class,
                    'reclassified_at': datetime.now(timezone.utc).isoformat()
                }}
            )
            detailed_meat += 1
    
    logger.info(f"   Итого детализировано: {detailed_meat}")
    
    # 5. Детализация других generic категорий
    logger.info("\n5️⃣ Детализация других generic категорий...")
    generic_cats = ['beverages', 'frozen', 'fruits', 'vegetables', 'dairy', 'seafood', 'pasta']
    
    for cat in generic_cats:
        items = list(db.supplier_items.find(
            {'active': True, 'super_class': cat},
            {'_id': 1, 'name_raw': 1}
        ))
        
        detailed = 0
        for item in items:
            new_class, priority = classify_product(item['name_raw'])
            if new_class and new_class != cat and priority >= 70:
                db.supplier_items.update_one(
                    {'_id': item['_id']},
                    {'$set': {
                        'super_class': new_class,
                        'product_core_id': new_class,
                        'reclassified_at': datetime.now(timezone.utc).isoformat()
                    }}
                )
                detailed += 1
        
        if detailed > 0:
            logger.info(f"   {cat}: детализировано {detailed}")
    
    # 6. Синхронизация product_core_id с super_class
    logger.info("\n6️⃣ Синхронизация product_core_id...")
    result = db.supplier_items.update_many(
        {'active': True, 'super_class': {'$ne': None}},
        [{'$set': {'product_core_id': {'$ifNull': ['$product_core_id', '$super_class']}}}]
    )
    logger.info(f"   Синхронизировано: {result.modified_count}")
    
    # Итоговая статистика
    logger.info("\n" + "=" * 60)
    logger.info("ИТОГОВАЯ СТАТИСТИКА")
    logger.info("=" * 60)
    
    pipeline = [
        {'$match': {'active': True}},
        {'$group': {'_id': {'$substr': ['$super_class', 0, 15]}, 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}},
        {'$limit': 25}
    ]
    
    final_stats = list(db.supplier_items.aggregate(pipeline))
    for s in final_stats:
        logger.info(f"   {s['_id']:20} : {s['count']:5}")
    
    return {
        'renamed': renamed,
        'fixed_seafood': fixed_seafood,
        'fixed_meat': fixed_meat,
        'detailed_meat': detailed_meat
    }


if __name__ == '__main__':
    run_reclassification()
