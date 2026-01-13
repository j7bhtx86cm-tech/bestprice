"""
BestPrice - Массовая переклассификация товаров v2
Исправляет все найденные проблемы классификации

ПРОБЛЕМЫ:
1. packaging (277) - содержит специи, соусы, приправы (слова "пакет", "банка" в названии)
2. canned.vegetables (263) - содержит оливковое масло, перец горошек (специя)
3. frozen.ready_meals (68) - содержит ветчину, креветки (не готовые блюда)
4. Слабо детализированные категории (meat, seafood, frozen без подкатегорий)
"""

import os
import re
import logging
from datetime import datetime, timezone
from pymongo import MongoClient
from dotenv import load_dotenv

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

load_dotenv('/app/backend/.env')
client = MongoClient(os.environ.get('MONGO_URL'))
db = client[os.environ.get('DB_NAME')]


# === ПРАВИЛА КЛАССИФИКАЦИИ ПО КЛЮЧЕВЫМ СЛОВАМ ===
# Приоритет: чем выше priority, тем важнее правило

CLASSIFICATION_RULES = [
    # ===============================
    # ВЫСШИЙ ПРИОРИТЕТ (100) - МОРЕПРОДУКТЫ
    # ===============================
    {'pattern': r'креветк|shrimp|prawn', 'super_class': 'seafood.shrimp', 'priority': 100},
    {'pattern': r'лангустин|langoustine', 'super_class': 'seafood.langoustine', 'priority': 100},
    {'pattern': r'кальмар|squid|calamari', 'super_class': 'seafood.squid', 'priority': 100},
    {'pattern': r'лосось|salmon|сёмга|семга', 'super_class': 'seafood.salmon', 'priority': 100},
    {'pattern': r'форель|trout', 'super_class': 'seafood.trout', 'priority': 100},
    {'pattern': r'тунец|tuna', 'super_class': 'seafood.tuna', 'priority': 100},
    {'pattern': r'краб(?!.*палочк)|crab(?!.*stick)', 'super_class': 'seafood.crab', 'priority': 100},
    {'pattern': r'краб.*палочк|crab.*stick|крабов.*палочк', 'super_class': 'seafood.crab_sticks', 'priority': 100},
    {'pattern': r'гребеш|scallop', 'super_class': 'seafood.scallop', 'priority': 100},
    {'pattern': r'мидии|mussel', 'super_class': 'seafood.shellfish.mussels', 'priority': 100},
    {'pattern': r'устриц|oyster', 'super_class': 'seafood.shellfish.oysters', 'priority': 100},
    {'pattern': r'осьминог|octopus', 'super_class': 'seafood.octopus', 'priority': 100},
    {'pattern': r'угорь|\beel\b|унаги', 'super_class': 'seafood.eel', 'priority': 100},
    {'pattern': r'треска|cod(?!.*liver)', 'super_class': 'seafood.cod', 'priority': 100},
    {'pattern': r'печень треск|cod liver', 'super_class': 'seafood.cod_liver', 'priority': 100},
    {'pattern': r'минтай|pollock', 'super_class': 'seafood.pollock', 'priority': 100},
    {'pattern': r'сельд|herring', 'super_class': 'seafood.herring', 'priority': 100},
    {'pattern': r'икра|caviar|tobiko|masago', 'super_class': 'seafood.caviar', 'priority': 100},
    {'pattern': r'водорос|seaweed|nori|вакаме|wakame|чука', 'super_class': 'seafood.seaweed', 'priority': 100},
    {'pattern': r'судак|pike.?perch|zander', 'super_class': 'seafood.pike_perch', 'priority': 100},
    {'pattern': r'щука(?!.*перч)|pike(?!.*perch)', 'super_class': 'seafood.pike', 'priority': 100},
    {'pattern': r'горбуша|pink.?salmon', 'super_class': 'seafood.pink_salmon', 'priority': 100},
    {'pattern': r'кета(?!.*чуп)|chum|keta', 'super_class': 'seafood.chum_salmon', 'priority': 100},
    {'pattern': r'тилапия|tilapia|изумидай', 'super_class': 'seafood.tilapia', 'priority': 100},
    {'pattern': r'окунь.*морск|seabass|сибас', 'super_class': 'seafood.seabass', 'priority': 100},
    {'pattern': r'дорадо|dorado|seabream|дорада', 'super_class': 'seafood.seabream', 'priority': 100},
    {'pattern': r'палтус|halibut', 'super_class': 'seafood.halibut', 'priority': 100},
    {'pattern': r'камбала|flounder|flatfish', 'super_class': 'seafood.flatfish', 'priority': 100},
    {'pattern': r'тюрбо|turbot', 'super_class': 'seafood.turbot', 'priority': 100},
    {'pattern': r'масляная рыба|butterfish|эсколар', 'super_class': 'seafood.butterfish', 'priority': 100},
    {'pattern': r'скумбрия|mackerel', 'super_class': 'seafood.mackerel', 'priority': 100},
    {'pattern': r'анчоус|anchov', 'super_class': 'seafood.anchovy', 'priority': 100},
    {'pattern': r'сардин|sardine', 'super_class': 'seafood.sardine', 'priority': 100},
    {'pattern': r'навага|navaga', 'super_class': 'seafood.navaga', 'priority': 100},
    {'pattern': r'зубатка|wolffish', 'super_class': 'seafood.wolffish', 'priority': 100},
    {'pattern': r'пангасиус|pangasius|баса', 'super_class': 'seafood.pangasius', 'priority': 100},
    {'pattern': r'шпрот|sprat', 'super_class': 'seafood.sprat', 'priority': 100},
    {'pattern': r'морской язык|sole', 'super_class': 'seafood.sole', 'priority': 100},
    {'pattern': r'\bрыб[аыу]|\bfish\b|филе.*(с/м|свежемор|охлажд)', 'super_class': 'seafood.fish', 'priority': 80},
    {'pattern': r'морепродукт|seafood|морской коктейль', 'super_class': 'seafood.mix', 'priority': 90},
    
    # ===============================
    # ВЫСШИЙ ПРИОРИТЕТ (95-100) - МЯСО
    # ===============================
    {'pattern': r'курица|куриц|chicken|цыплён|цыпл|бройлер', 'super_class': 'meat.chicken', 'priority': 95},
    {'pattern': r'говядин|beef|телятин|veal|мраморн.*(говяд|beef)', 'super_class': 'meat.beef', 'priority': 95},
    {'pattern': r'свинин|pork|поросён', 'super_class': 'meat.pork', 'priority': 95},
    {'pattern': r'баранин|lamb|ягнёнок|ягнятин', 'super_class': 'meat.lamb', 'priority': 95},
    {'pattern': r'утка|утин|\bduck\b|\bутки\b', 'super_class': 'meat.duck', 'priority': 95},
    {'pattern': r'индейк|turkey', 'super_class': 'meat.turkey', 'priority': 95},
    {'pattern': r'кролик|rabbit', 'super_class': 'meat.rabbit', 'priority': 95},
    {'pattern': r'оленин|venison|deer', 'super_class': 'meat.venison', 'priority': 95},
    {'pattern': r'гусь|гуся|гусин|goose', 'super_class': 'meat.goose', 'priority': 95},
    {'pattern': r'перепел|quail', 'super_class': 'meat.quail', 'priority': 95},
    {'pattern': r'колбас|sausage|сосиск|сардельк', 'super_class': 'meat.sausage', 'priority': 90},
    {'pattern': r'бекон|bacon|грудинк', 'super_class': 'meat.bacon', 'priority': 90},
    {'pattern': r'ветчин|ham(?!.*бург)|хамон|прошутто|prosciutto', 'super_class': 'meat.ham', 'priority': 95},
    {'pattern': r'фарш|ground|minced', 'super_class': 'meat.ground', 'priority': 90},
    {'pattern': r'котлет(?!.*рыб)|cutlet|patty', 'super_class': 'meat.cutlets', 'priority': 90},
    {'pattern': r'пельмен', 'super_class': 'frozen.pelmeni', 'priority': 90},
    {'pattern': r'варени', 'super_class': 'frozen.vareniki', 'priority': 90},
    
    # ===============================
    # ВЫСОКИЙ ПРИОРИТЕТ (90) - СПЕЦИИ И ПРИПРАВЫ (FIX: packaging problem)
    # ===============================
    {'pattern': r'перец.*горошек|перец.*черн.*горош|pepper.*corn', 'super_class': 'condiments.spice.pepper', 'priority': 95},
    {'pattern': r'перец.*молот|перец.*черн.*молот|pepper.*ground', 'super_class': 'condiments.spice.pepper', 'priority': 95},
    {'pattern': r'перец.*чили|chili.*pepper|чили.*перец', 'super_class': 'condiments.spice.chili', 'priority': 95},
    {'pattern': r'перец.*розов|pink.*pepper', 'super_class': 'condiments.spice.pepper', 'priority': 95},
    {'pattern': r'корица|cinnamon', 'super_class': 'condiments.spice.cinnamon', 'priority': 95},
    {'pattern': r'гвоздика|cloves', 'super_class': 'condiments.spice.cloves', 'priority': 95},
    {'pattern': r'кориандр|coriander', 'super_class': 'condiments.spice.coriander', 'priority': 95},
    {'pattern': r'ванил|vanilla', 'super_class': 'condiments.spice.vanilla', 'priority': 95},
    {'pattern': r'бадьян|star.*anise', 'super_class': 'condiments.spice.anise', 'priority': 95},
    {'pattern': r'куркума|turmeric', 'super_class': 'condiments.spice.turmeric', 'priority': 95},
    {'pattern': r'паприка|paprika', 'super_class': 'condiments.spice.paprika', 'priority': 95},
    {'pattern': r'кардамон|cardamom', 'super_class': 'condiments.spice.cardamom', 'priority': 95},
    {'pattern': r'орегано|oregano', 'super_class': 'condiments.spice.oregano', 'priority': 95},
    {'pattern': r'базилик|basil', 'super_class': 'condiments.spice.basil', 'priority': 95},
    {'pattern': r'тимьян|thyme|чабрец', 'super_class': 'condiments.spice.thyme', 'priority': 95},
    {'pattern': r'розмарин|rosemary', 'super_class': 'condiments.spice.rosemary', 'priority': 95},
    {'pattern': r'мускатн.*орех|nutmeg', 'super_class': 'condiments.spice.nutmeg', 'priority': 95},
    {'pattern': r'кумин|зира|cumin', 'super_class': 'condiments.spice.cumin', 'priority': 95},
    {'pattern': r'карри(?!.*паст)|curry(?!.*paste)', 'super_class': 'condiments.curry', 'priority': 95},
    {'pattern': r'карри.*паст|curry.*paste', 'super_class': 'condiments.curry_paste', 'priority': 95},
    {'pattern': r'лавр.*лист|bay.*leaf', 'super_class': 'condiments.spice.bay_leaf', 'priority': 95},
    {'pattern': r'майоран|marjoram', 'super_class': 'condiments.spice.marjoram', 'priority': 95},
    {'pattern': r'эстрагон|tarragon', 'super_class': 'condiments.spice.tarragon', 'priority': 95},
    {'pattern': r'укроп|dill', 'super_class': 'condiments.spice.dill', 'priority': 95},
    {'pattern': r'петрушка|parsley', 'super_class': 'condiments.spice.parsley', 'priority': 95},
    {'pattern': r'кинза|cilantro', 'super_class': 'condiments.spice.cilantro', 'priority': 95},
    {'pattern': r'пажитник|fenugreek', 'super_class': 'condiments.spice.fenugreek', 'priority': 95},
    {'pattern': r'сумах|sumac', 'super_class': 'condiments.spice.sumac', 'priority': 95},
    {'pattern': r'барбарис|barberry', 'super_class': 'condiments.spice.barberry', 'priority': 95},
    {'pattern': r'можжевел|juniper', 'super_class': 'condiments.spice.juniper', 'priority': 95},
    {'pattern': r'тмин(?!.*кумин)|caraway', 'super_class': 'condiments.spice.caraway', 'priority': 95},
    {'pattern': r'фенхель|fennel', 'super_class': 'condiments.spice.fennel', 'priority': 95},
    {'pattern': r'шафран|saffron', 'super_class': 'condiments.spice.saffron', 'priority': 95},
    {'pattern': r'хмели.*сунели', 'super_class': 'condiments.spice_mix.khmeli_suneli', 'priority': 95},
    {'pattern': r'уцхо.*сунели', 'super_class': 'condiments.spice_mix.utskho_suneli', 'priority': 95},
    {'pattern': r'прован.*трав|provenc.*herbs', 'super_class': 'condiments.spice_mix.provence', 'priority': 95},
    {'pattern': r'итальян.*трав|italian.*herbs', 'super_class': 'condiments.spice_mix.italian', 'priority': 95},
    {'pattern': r'приправ.*для|seasoning.*for', 'super_class': 'condiments.seasoning', 'priority': 85},
    {'pattern': r'смесь.*специй|spice.*mix', 'super_class': 'condiments.spice_mix', 'priority': 85},
    {'pattern': r'пастернак', 'super_class': 'vegetables.parsnip', 'priority': 90},
    
    # ===============================
    # ВЫСОКИЙ ПРИОРИТЕТ (90) - ДОБАВКИ
    # ===============================
    {'pattern': r'желатин|gelatin', 'super_class': 'additives.gelatin', 'priority': 95},
    {'pattern': r'агар|agar', 'super_class': 'additives.agar', 'priority': 95},
    {'pattern': r'пектин|pectin', 'super_class': 'additives.pectin', 'priority': 95},
    {'pattern': r'разрыхлит|baking.*powder', 'super_class': 'additives.baking_powder', 'priority': 95},
    {'pattern': r'дрожж|yeast', 'super_class': 'additives.yeast', 'priority': 95},
    {'pattern': r'глюкоза|glucose', 'super_class': 'additives.glucose', 'priority': 95},
    {'pattern': r'фруктоза|fructose', 'super_class': 'additives.fructose', 'priority': 95},
    {'pattern': r'глутамат|msg|усилитель вкуса', 'super_class': 'additives.msg', 'priority': 95},
    {'pattern': r'краситель|colorant|пищев.*красит', 'super_class': 'additives.colorant', 'priority': 95},
    
    # ===============================
    # ВЫСОКИЙ ПРИОРИТЕТ (90) - СОУСЫ
    # ===============================
    {'pattern': r'соус|sauce', 'super_class': 'condiments.sauce', 'priority': 85},
    {'pattern': r'соус.*барбекю|bbq.*sauce|barbecue', 'super_class': 'condiments.sauce.bbq', 'priority': 90},
    {'pattern': r'соус.*терияки|teriyaki', 'super_class': 'condiments.sauce.teriyaki', 'priority': 90},
    {'pattern': r'соус.*соев|soy.*sauce', 'super_class': 'condiments.sauce.soy', 'priority': 90},
    {'pattern': r'соус.*сырн|cheese.*sauce', 'super_class': 'condiments.sauce.cheese', 'priority': 90},
    {'pattern': r'соус.*чесноч|garlic.*sauce', 'super_class': 'condiments.sauce.garlic', 'priority': 90},
    {'pattern': r'соус.*горчичн|mustard.*sauce', 'super_class': 'condiments.sauce.mustard', 'priority': 90},
    {'pattern': r'бешамель|bechamel', 'super_class': 'condiments.sauce.bechamel', 'priority': 90},
    {'pattern': r'песто|pesto', 'super_class': 'condiments.sauce.pesto', 'priority': 90},
    {'pattern': r'гуакамоле|guacamole', 'super_class': 'condiments.sauce.guacamole', 'priority': 90},
    {'pattern': r'том.*кха|tom.*kha', 'super_class': 'condiments.paste.tom_kha', 'priority': 90},
    {'pattern': r'майонез|mayo', 'super_class': 'condiments.mayo', 'priority': 90},
    {'pattern': r'кетчуп|ketchup', 'super_class': 'condiments.ketchup', 'priority': 90},
    {'pattern': r'горчиц(?!.*порош)|mustard(?!.*powder)', 'super_class': 'condiments.mustard', 'priority': 90},
    {'pattern': r'горчичн.*порош|mustard.*powder', 'super_class': 'condiments.spice.mustard_powder', 'priority': 90},
    {'pattern': r'уксус|vinegar', 'super_class': 'condiments.vinegar', 'priority': 90},
    {'pattern': r'васаби|wasabi', 'super_class': 'condiments.wasabi', 'priority': 90},
    {'pattern': r'имбир|ginger', 'super_class': 'condiments.ginger', 'priority': 90},
    {'pattern': r'мёд|мед|honey', 'super_class': 'condiments.honey', 'priority': 90},
    
    # ===============================
    # ВЫСОКИЙ ПРИОРИТЕТ (90) - МАСЛА
    # ===============================
    {'pattern': r'масло.*оливков|olive.*oil', 'super_class': 'oils.olive', 'priority': 95},
    {'pattern': r'масло.*подсолнечн|sunflower.*oil', 'super_class': 'oils.sunflower', 'priority': 95},
    {'pattern': r'масло.*кунжутн|sesame.*oil', 'super_class': 'oils.sesame', 'priority': 95},
    {'pattern': r'масло.*тыквенн|pumpkin.*oil', 'super_class': 'oils.pumpkin', 'priority': 95},
    {'pattern': r'масло.*фритюр|frying.*oil', 'super_class': 'oils.frying', 'priority': 95},
    {'pattern': r'масло.*трюфел|truffle.*oil', 'super_class': 'oils.truffle', 'priority': 95},
    {'pattern': r'масло.*авокадо|avocado.*oil', 'super_class': 'oils.avocado', 'priority': 95},
    {'pattern': r'масло.*раст|vegetable.*oil', 'super_class': 'oils.vegetable', 'priority': 85},
    
    # ===============================
    # МОЛОЧНЫЕ ПРОДУКТЫ (90)
    # ===============================
    {'pattern': r'сыр|cheese|пармезан|parmesan|моцарел|mozzarella|чеддер|cheddar|горгонзол|gorgonzola|бри(?!.*крем)|camembert|рикотта|ricotta|маскарпоне|mascarpone', 'super_class': 'dairy.cheese', 'priority': 90},
    {'pattern': r'молоко|milk', 'super_class': 'dairy.milk', 'priority': 90},
    {'pattern': r'сливк|cream(?!.*сыр)', 'super_class': 'dairy.cream', 'priority': 90},
    {'pattern': r'масло.*сливочн|butter(?!.*fish)', 'super_class': 'dairy.butter', 'priority': 95},
    {'pattern': r'сметан|sour.?cream', 'super_class': 'dairy.sour_cream', 'priority': 90},
    {'pattern': r'йогурт|yogurt', 'super_class': 'dairy.yogurt', 'priority': 90},
    {'pattern': r'творог|cottage.?cheese', 'super_class': 'dairy.cottage_cheese', 'priority': 90},
    {'pattern': r'кефир|kefir', 'super_class': 'dairy.kefir', 'priority': 90},
    
    # ===============================
    # ОВОЩИ (85)
    # ===============================
    {'pattern': r'помидор|томат(?!.*сок|.*паст)|tomato(?!.*juice|.*paste)', 'super_class': 'vegetables.tomato', 'priority': 85},
    {'pattern': r'картофел|картошк|potato', 'super_class': 'vegetables.potato', 'priority': 85},
    {'pattern': r'\bлук\b(?!.*овин)|onion', 'super_class': 'vegetables.onion', 'priority': 85},
    {'pattern': r'чеснок|garlic', 'super_class': 'vegetables.garlic', 'priority': 85},
    {'pattern': r'морковь|carrot', 'super_class': 'vegetables.carrot', 'priority': 85},
    {'pattern': r'капуст|cabbage', 'super_class': 'vegetables.cabbage', 'priority': 85},
    {'pattern': r'огурец|cucumber', 'super_class': 'vegetables.cucumber', 'priority': 85},
    {'pattern': r'перец.*болгар|bell.?pepper', 'super_class': 'vegetables.bell_pepper', 'priority': 85},
    {'pattern': r'баклажан|eggplant|aubergine', 'super_class': 'vegetables.eggplant', 'priority': 85},
    {'pattern': r'грибы|гриб|mushroom|шампиньон|champignon|шиитаке|shiitake', 'super_class': 'vegetables.mushrooms', 'priority': 85},
    {'pattern': r'шпинат|spinach', 'super_class': 'vegetables.spinach', 'priority': 85},
    {'pattern': r'спаржа|asparagus', 'super_class': 'vegetables.asparagus', 'priority': 85},
    {'pattern': r'артишок|artichoke', 'super_class': 'vegetables.artichoke', 'priority': 85},
    {'pattern': r'тыква|pumpkin|squash', 'super_class': 'vegetables.pumpkin', 'priority': 85},
    {'pattern': r'кабачок|zucchini|courgette', 'super_class': 'vegetables.zucchini', 'priority': 85},
    {'pattern': r'свекла|beet', 'super_class': 'vegetables.beet', 'priority': 85},
    {'pattern': r'\bгорох(?!.*зелен)|pea(?!nut|.*green)', 'super_class': 'vegetables.peas', 'priority': 85},
    {'pattern': r'горошек.*зелен|green.*pea', 'super_class': 'canned.green_peas', 'priority': 90},
    {'pattern': r'фасоль|bean(?!.*кофе|coffee)', 'super_class': 'vegetables.beans', 'priority': 85},
    {'pattern': r'кукуруз|corn(?!.*beef)', 'super_class': 'canned.corn', 'priority': 90},
    
    # ===============================
    # КОНСЕРВЫ (88)
    # ===============================
    {'pattern': r'огурц.*марин|pickle', 'super_class': 'canned.pickles', 'priority': 88},
    {'pattern': r'оливк|olive(?!.*oil)', 'super_class': 'canned.olives', 'priority': 88},
    {'pattern': r'капер|caper', 'super_class': 'canned.capers', 'priority': 88},
    {'pattern': r'томат.*консерв|tomato.*canned|томат.*паст|tomato.*paste', 'super_class': 'canned.tomatoes', 'priority': 88},
    
    # ===============================
    # МАКАРОНЫ И ЛАПША (85)
    # ===============================
    {'pattern': r'спагетти|spaghetti', 'super_class': 'pasta.spaghetti', 'priority': 85},
    {'pattern': r'пенне|penne', 'super_class': 'pasta.penne', 'priority': 85},
    {'pattern': r'фузилли|fusilli', 'super_class': 'pasta.fusilli', 'priority': 85},
    {'pattern': r'тальятелле|tagliatelle', 'super_class': 'pasta.tagliatelle', 'priority': 85},
    {'pattern': r'фетучини|fettuccine', 'super_class': 'pasta.fettuccine', 'priority': 85},
    {'pattern': r'лазанья|lasagne|lasagna', 'super_class': 'pasta.lasagna', 'priority': 85},
    {'pattern': r'ригатони|rigatoni', 'super_class': 'pasta.rigatoni', 'priority': 85},
    {'pattern': r'лапша|noodle', 'super_class': 'pasta.noodles', 'priority': 85},
    {'pattern': r'удон|udon', 'super_class': 'pasta.udon', 'priority': 85},
    {'pattern': r'рамен|ramen', 'super_class': 'pasta.ramen', 'priority': 85},
    {'pattern': r'соба|soba', 'super_class': 'pasta.soba', 'priority': 85},
    {'pattern': r'вермишель|vermicelli', 'super_class': 'pasta.vermicelli', 'priority': 85},
    {'pattern': r'макарон(?!.*мак)|pasta|macaroni|макфа', 'super_class': 'pasta.macaroni', 'priority': 88},
    
    # ===============================
    # КРУПЫ И БАКАЛЕЯ (85)
    # ===============================
    {'pattern': r'\bрис\b(?!.*бумаг)|rice(?!.*paper)', 'super_class': 'staples.rice', 'priority': 85},
    {'pattern': r'рис.*басмати|basmati', 'super_class': 'staples.rice.basmati', 'priority': 90},
    {'pattern': r'рис.*жасмин|jasmine.*rice', 'super_class': 'staples.rice.jasmine', 'priority': 90},
    {'pattern': r'рис.*для.*суши|sushi.*rice', 'super_class': 'staples.rice.sushi', 'priority': 90},
    {'pattern': r'гречк|buckwheat|греча', 'super_class': 'staples.buckwheat', 'priority': 85},
    {'pattern': r'овсян|oat|овёс', 'super_class': 'staples.oats', 'priority': 85},
    {'pattern': r'мука|flour', 'super_class': 'staples.flour', 'priority': 85},
    {'pattern': r'сахар(?!.*пудр)|sugar(?!.*powder)', 'super_class': 'staples.sugar', 'priority': 85},
    {'pattern': r'сахарн.*пудр|sugar.*powder|powdered.*sugar', 'super_class': 'staples.sugar_powder', 'priority': 90},
    {'pattern': r'соль(?!.*ин)|salt', 'super_class': 'condiments.salt', 'priority': 85},
    {'pattern': r'кускус|couscous', 'super_class': 'staples.couscous', 'priority': 85},
    {'pattern': r'булгур|bulgur', 'super_class': 'staples.bulgur', 'priority': 85},
    {'pattern': r'киноа|quinoa', 'super_class': 'staples.quinoa', 'priority': 85},
    {'pattern': r'манка|semolina', 'super_class': 'staples.semolina', 'priority': 85},
    {'pattern': r'пшено|millet', 'super_class': 'staples.millet', 'priority': 85},
    {'pattern': r'крупа|cereal|каша', 'super_class': 'staples.cereals', 'priority': 75},
    
    # ===============================
    # ФРУКТЫ И ЯГОДЫ (92) - выше чем sugar для "манго"
    # ===============================
    {'pattern': r'манго|mango', 'super_class': 'fruits.mango', 'priority': 92},
    {'pattern': r'яблок|apple', 'super_class': 'fruits.apple', 'priority': 85},
    {'pattern': r'груша|pear', 'super_class': 'fruits.pear', 'priority': 85},
    {'pattern': r'апельсин|orange(?!.*juice)', 'super_class': 'fruits.orange', 'priority': 85},
    {'pattern': r'лимон|lemon', 'super_class': 'fruits.lemon', 'priority': 85},
    {'pattern': r'лайм|lime', 'super_class': 'fruits.lime', 'priority': 85},
    {'pattern': r'банан|banana', 'super_class': 'fruits.banana', 'priority': 85},
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
    {'pattern': r'черносл|prune', 'super_class': 'dried_fruits.prunes', 'priority': 88},
    
    # ===============================
    # НАПИТКИ (85)
    # ===============================
    {'pattern': r'\bсок\b(?!.*кокос)|juice', 'super_class': 'beverages.juice', 'priority': 85},
    {'pattern': r'кола|cola|pepsi|пепси', 'super_class': 'beverages.cola', 'priority': 85},
    {'pattern': r'сироп|syrup', 'super_class': 'beverages.syrup', 'priority': 85},
    {'pattern': r'\bчай\b|tea(?!.*масло)', 'super_class': 'beverages.tea', 'priority': 85},
    {'pattern': r'кофе|coffee', 'super_class': 'beverages.coffee', 'priority': 85},
    {'pattern': r'какао|cocoa|горячий шоколад', 'super_class': 'beverages.cocoa', 'priority': 85},
    {'pattern': r'вода.*мин|mineral.?water|газир.*вода', 'super_class': 'beverages.water', 'priority': 85},
    {'pattern': r'лимонад|lemonade', 'super_class': 'beverages.lemonade', 'priority': 85},
    {'pattern': r'нектар|nectar', 'super_class': 'beverages.nectar', 'priority': 85},
    
    # ===============================
    # ВЫПЕЧКА (85)
    # ===============================
    {'pattern': r'хлеб|bread|батон', 'super_class': 'bakery.bread', 'priority': 85},
    {'pattern': r'багет|baguette', 'super_class': 'bakery.baguette', 'priority': 85},
    {'pattern': r'булочка|bun', 'super_class': 'bakery.bun', 'priority': 85},
    {'pattern': r'круассан|croissant', 'super_class': 'bakery.croissant', 'priority': 90},
    {'pattern': r'пицц|pizza', 'super_class': 'bakery.pizza', 'priority': 85},
    {'pattern': r'торт|cake', 'super_class': 'bakery.cake', 'priority': 85},
    {'pattern': r'тесто|dough', 'super_class': 'bakery.dough', 'priority': 85},
    {'pattern': r'сухар.*панир|breadcrumb|панко|panko', 'super_class': 'bakery.breadcrumbs', 'priority': 85},
    
    # ===============================
    # ШОКОЛАД И КОНДИТЕРКА (85)
    # ===============================
    {'pattern': r'шоколад|chocolate', 'super_class': 'confectionery.chocolate', 'priority': 85},
    {'pattern': r'какао.*масло|cocoa.*butter', 'super_class': 'confectionery.cocoa_butter', 'priority': 90},
    
    # ===============================
    # КРАХМАЛ (88)
    # ===============================
    {'pattern': r'крахмал|starch', 'super_class': 'staples.starch', 'priority': 88},
    
    # ===============================
    # ЗАМОРОЖЕННЫЕ (80)
    # ===============================
    {'pattern': r'мороженое|ice.?cream', 'super_class': 'frozen.ice_cream', 'priority': 85},
    
    # ===============================
    # ОРЕХИ И СЕМЕНА (85)
    # ===============================
    {'pattern': r'кунжут|sesame', 'super_class': 'seeds.sesame', 'priority': 90},
    {'pattern': r'семена.*чиа|chia', 'super_class': 'seeds.chia', 'priority': 90},
    {'pattern': r'семена.*льна|flax|лён', 'super_class': 'seeds.flax', 'priority': 90},
    {'pattern': r'\bмак\b(?!.*арон|.*фа)|poppy', 'super_class': 'seeds.poppy', 'priority': 90},
    {'pattern': r'миндал|almond', 'super_class': 'nuts.almonds', 'priority': 85},
    {'pattern': r'фисташ|pistachio', 'super_class': 'nuts.pistachios', 'priority': 85},
    {'pattern': r'грецк.*орех|walnut', 'super_class': 'nuts.walnuts', 'priority': 85},
    {'pattern': r'кешью|cashew', 'super_class': 'nuts.cashews', 'priority': 85},
    {'pattern': r'фундук|hazelnut', 'super_class': 'nuts.hazelnuts', 'priority': 85},
    {'pattern': r'арахис|peanut', 'super_class': 'nuts.peanuts', 'priority': 85},
    {'pattern': r'кедров.*орех|pine.*nut', 'super_class': 'nuts.pine_nuts', 'priority': 85},
    
    # ===============================
    # ГОТОВЫЕ БЛЮДА (80)
    # ===============================
    {'pattern': r'пюре|puree', 'super_class': 'ready_meals.puree', 'priority': 80},
    {'pattern': r'бульон|broth|stock', 'super_class': 'ready_meals.broth', 'priority': 80},
    {'pattern': r'суп(?!.*пюре)|soup', 'super_class': 'ready_meals.soup', 'priority': 80},
    
    # ===============================
    # РЕАЛЬНАЯ УПАКОВКА (75) - после всех продуктов!
    # ===============================
    {'pattern': r'лоток(?!.*утк|.*курин)|tray', 'super_class': 'packaging.tray', 'priority': 75},
    {'pattern': r'контейнер|container', 'super_class': 'packaging.container', 'priority': 75},
    {'pattern': r'вакуум.*пакет|vacuum.*bag', 'super_class': 'packaging.vacuum_bags', 'priority': 75},
    {'pattern': r'пакет.*майка', 'super_class': 'packaging.bags', 'priority': 75},
    {'pattern': r'пакет.*фасов', 'super_class': 'packaging.bags', 'priority': 75},
    {'pattern': r'пакет.*крафт', 'super_class': 'packaging.bags', 'priority': 75},
    {'pattern': r'пакет.*бумаж', 'super_class': 'packaging.bags', 'priority': 75},
    {'pattern': r'упаков.*для.*бургер', 'super_class': 'packaging.burger_boxes', 'priority': 75},
    {'pattern': r'форма.*алюмин|aluminum.*form', 'super_class': 'packaging.aluminum', 'priority': 75},
    {'pattern': r'банка.*прозрач|jar.*clear', 'super_class': 'packaging.jars', 'priority': 75},
    {'pattern': r'тарелка.*одноразов|disposable.*plate', 'super_class': 'disposables.plates', 'priority': 75},
    {'pattern': r'уголок.*бел', 'super_class': 'packaging.corner', 'priority': 75},
    {'pattern': r'зубочист|toothpick', 'super_class': 'disposables.toothpicks', 'priority': 75},
    {'pattern': r'размешиват|stirrer', 'super_class': 'disposables.stirrers', 'priority': 75},
    {'pattern': r'трубочк|straw', 'super_class': 'disposables.straws', 'priority': 75},
    {'pattern': r'палочк.*для.*суши|chopstick', 'super_class': 'disposables.chopsticks', 'priority': 75},
    {'pattern': r'палочк.*бамбук', 'super_class': 'disposables.bamboo_sticks', 'priority': 75},
    {'pattern': r'перчатк|glove', 'super_class': 'disposables.gloves', 'priority': 75},
    {'pattern': r'салфетк|napkin', 'super_class': 'disposables.napkins', 'priority': 75},
    {'pattern': r'стакан|cup', 'super_class': 'disposables.cups', 'priority': 75},
    {'pattern': r'крышк|lid', 'super_class': 'disposables.lids', 'priority': 75},
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


def run_reclassification(dry_run=False):
    """
    Запускает переклассификацию всех товаров
    
    Args:
        dry_run: если True, только показывает что будет изменено, без записи в БД
    """
    logger.info("=" * 70)
    logger.info("ЗАПУСК МАССОВОЙ ПЕРЕКЛАССИФИКАЦИИ v2")
    logger.info(f"Режим: {'DRY RUN (без записи)' if dry_run else 'ПОЛНЫЙ ЗАПУСК'}")
    logger.info("=" * 70)
    
    stats = {
        'total_processed': 0,
        'reclassified': 0,
        'unchanged': 0,
        'categories_fixed': {}
    }
    
    # Получаем все активные товары
    items = list(db.supplier_items.find(
        {'active': True},
        {'_id': 1, 'name_raw': 1, 'super_class': 1, 'product_core_id': 1}
    ))
    
    total = len(items)
    logger.info(f"Всего товаров для обработки: {total}")
    
    for i, item in enumerate(items):
        if i > 0 and i % 1000 == 0:
            logger.info(f"Обработано: {i}/{total} ({100*i/total:.1f}%)")
        
        stats['total_processed'] += 1
        name = item.get('name_raw', '')
        old_class = item.get('super_class', '')
        
        new_class, priority = classify_product(name)
        
        # Если нашли лучшую классификацию
        if new_class and priority >= 75:
            # Проверяем, что это реально улучшение
            if new_class != old_class:
                stats['reclassified'] += 1
                
                # Подсчет по старым категориям
                if old_class not in stats['categories_fixed']:
                    stats['categories_fixed'][old_class] = {'count': 0, 'examples': []}
                stats['categories_fixed'][old_class]['count'] += 1
                if len(stats['categories_fixed'][old_class]['examples']) < 5:
                    stats['categories_fixed'][old_class]['examples'].append({
                        'name': name[:60],
                        'old': old_class,
                        'new': new_class
                    })
                
                if not dry_run:
                    db.supplier_items.update_one(
                        {'_id': item['_id']},
                        {'$set': {
                            'super_class': new_class,
                            'product_core_id': new_class,
                            'reclassified_at': datetime.now(timezone.utc).isoformat(),
                            'reclassified_from': old_class
                        }}
                    )
            else:
                stats['unchanged'] += 1
        else:
            stats['unchanged'] += 1
    
    # Выводим статистику
    logger.info("\n" + "=" * 70)
    logger.info("РЕЗУЛЬТАТЫ ПЕРЕКЛАССИФИКАЦИИ")
    logger.info("=" * 70)
    logger.info(f"Всего обработано: {stats['total_processed']}")
    logger.info(f"Переклассифицировано: {stats['reclassified']}")
    logger.info(f"Без изменений: {stats['unchanged']}")
    
    logger.info("\n--- ИСПРАВЛЕННЫЕ КАТЕГОРИИ ---")
    for old_cat, data in sorted(stats['categories_fixed'].items(), key=lambda x: -x[1]['count']):
        logger.info(f"\n{old_cat}: {data['count']} товаров исправлено")
        for ex in data['examples']:
            logger.info(f"   {ex['name']} -> {ex['new']}")
    
    return stats


def verify_classification():
    """Самопроверка классификации после переклассификации"""
    logger.info("\n" + "=" * 70)
    logger.info("САМОПРОВЕРКА КЛАССИФИКАЦИИ")
    logger.info("=" * 70)
    
    issues = []
    
    # 1. Проверка packaging - не должно содержать продукты
    logger.info("\n1. Проверка packaging...")
    packaging_items = list(db.supplier_items.find(
        {'active': True, 'super_class': {'$regex': '^packaging'}},
        {'_id': 0, 'name_raw': 1, 'super_class': 1}
    ))
    
    product_keywords = ['соус', 'кетчуп', 'майонез', 'перец', 'корица', 'специ', 
                       'приправ', 'желатин', 'курица', 'говядин', 'рыб', 'масло.*олив']
    
    packaging_issues = []
    for item in packaging_items:
        name = item.get('name_raw', '').lower()
        for kw in product_keywords:
            if re.search(kw, name):
                packaging_issues.append(item)
                break
    
    if packaging_issues:
        logger.warning(f"   ❌ Найдено {len(packaging_issues)} продуктов в packaging:")
        for item in packaging_issues[:10]:
            logger.warning(f"      {item['name_raw'][:60]}")
        issues.extend(packaging_issues)
    else:
        logger.info(f"   ✅ packaging чистый ({len(packaging_items)} товаров)")
    
    # 2. Проверка кросс-категорий seafood <-> meat
    logger.info("\n2. Проверка seafood vs meat...")
    
    seafood_keywords = ['креветк', 'кальмар', 'рыб', 'fish', 'лосось', 'salmon', 'тунец', 'треск']
    meat_keywords = ['курица', 'куриц', 'говядин', 'beef', 'свинин', 'pork']
    
    # Seafood с мясными ключевыми словами
    seafood_items = list(db.supplier_items.find(
        {'active': True, 'super_class': {'$regex': '^seafood'}},
        {'_id': 0, 'name_raw': 1, 'super_class': 1}
    ))
    seafood_issues = []
    for item in seafood_items:
        name = item.get('name_raw', '').lower()
        for kw in meat_keywords:
            if kw in name:
                seafood_issues.append(item)
                break
    
    if seafood_issues:
        logger.warning(f"   ❌ Найдено {len(seafood_issues)} мясных товаров в seafood:")
        for item in seafood_issues[:5]:
            logger.warning(f"      {item['name_raw'][:60]}")
        issues.extend(seafood_issues)
    else:
        logger.info(f"   ✅ seafood без мясных товаров ({len(seafood_items)} товаров)")
    
    # Meat с seafood ключевыми словами
    meat_items = list(db.supplier_items.find(
        {'active': True, 'super_class': {'$regex': '^meat'}},
        {'_id': 0, 'name_raw': 1, 'super_class': 1}
    ))
    meat_issues = []
    for item in meat_items:
        name = item.get('name_raw', '').lower()
        for kw in seafood_keywords:
            if kw in name:
                meat_issues.append(item)
                break
    
    if meat_issues:
        logger.warning(f"   ❌ Найдено {len(meat_issues)} seafood товаров в meat:")
        for item in meat_issues[:5]:
            logger.warning(f"      {item['name_raw'][:60]}")
        issues.extend(meat_issues)
    else:
        logger.info(f"   ✅ meat без seafood товаров ({len(meat_items)} товаров)")
    
    # 3. Финальная статистика
    logger.info("\n3. Финальное распределение по категориям...")
    pipeline = [
        {'$match': {'active': True}},
        {'$group': {'_id': {'$arrayElemAt': [{'$split': ['$super_class', '.']}, 0]}, 'count': {'$sum': 1}}},
        {'$sort': {'count': -1}}
    ]
    
    for cat in db.supplier_items.aggregate(pipeline):
        logger.info(f"   {cat['_id']}: {cat['count']}")
    
    logger.info("\n" + "=" * 70)
    if issues:
        logger.warning(f"ИТОГО: {len(issues)} проблем требуют внимания")
    else:
        logger.info("ИТОГО: Все проверки пройдены успешно! ✅")
    logger.info("=" * 70)
    
    return issues


if __name__ == '__main__':
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == '--dry-run':
        run_reclassification(dry_run=True)
    elif len(sys.argv) > 1 and sys.argv[1] == '--verify':
        verify_classification()
    else:
        # Полный запуск
        stats = run_reclassification(dry_run=False)
        verify_classification()
