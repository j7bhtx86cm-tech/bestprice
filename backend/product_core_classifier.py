"""
Product Core Classification for BestPrice v12
Узкая классификация товаров для точного матчинга
"""
import re
from typing import Tuple, Optional


# Product Core Mapping: super_class → [(keywords, product_core)]
PRODUCT_CORE_RULES = {
    # Meat - Мясо
    'meat.beef': [
        (['фарш', 'minced', 'ground'], 'meat.beef.ground'),
        (['стейк', 'steak'], 'meat.beef.steak'),
        (['рибай', 'ribeye', 'rib-eye', 'рибей'], 'meat.beef.ribeye'),  # P1: Added ribeye
        (['рёбр', 'ribs', 'ребра'], 'meat.beef.ribs'),
        (['филе', 'fillet', 'вырезка'], 'meat.beef.fillet'),
        (['грудк', 'brisket'], 'meat.beef.brisket'),
        (['суповой', 'soup', 'набор'], 'meat.beef.soup_set'),
        (['гуляш', 'stew'], 'meat.beef.stew'),
        (['котлет', 'burger', 'patty'], 'meat.beef.patty'),
    ],
    
    'meat.pork': [
        (['фарш', 'minced', 'ground'], 'meat.pork.ground'),
        (['ребр', 'ribs'], 'meat.pork.ribs'),
        (['шейк', 'neck'], 'meat.pork.neck'),
        (['корейк', 'loin'], 'meat.pork.loin'),
        (['грудинк', 'belly'], 'meat.pork.belly'),
    ],
    
    'meat.chicken': [
        (['фарш', 'minced', 'ground'], 'meat.chicken.ground'),
        (['грудк', 'breast'], 'meat.chicken.breast'),
        (['бедр', 'thigh'], 'meat.chicken.thigh'),
        (['крыл', 'wing'], 'meat.chicken.wing'),
        (['голен', 'drumstick'], 'meat.chicken.drumstick'),
        (['целая', 'whole'], 'meat.chicken.whole'),
    ],
    
    # Flour - Мука
    'staples.мука': [
        (['пшенич', 'wheat'], 'staples.flour.wheat'),
        (['ржан', 'rye'], 'staples.flour.rye'),
        (['кукуруз', 'corn'], 'staples.flour.corn'),
        (['рисов', 'rice'], 'staples.flour.rice'),
        (['гречнев', 'buckwheat'], 'staples.flour.buckwheat'),
        (['овсян', 'oat'], 'staples.flour.oat'),
        (['макарон', 'pasta', 'дурум'], 'staples.flour.durum'),
    ],
    
    'staples.flour': [
        (['пшенич', 'wheat'], 'staples.flour.wheat'),
        (['ржан', 'rye'], 'staples.flour.rye'),
        (['кукуруз', 'corn'], 'staples.flour.corn'),
        (['рисов', 'rice'], 'staples.flour.rice'),
    ],
    
    # Grains/Cereals - Крупы
    'staples.cereals': [
        (['рис', 'rice'], 'staples.cereals.rice'),
        (['гречк', 'грече', 'греч', 'buckwheat'], 'staples.cereals.buckwheat'),
        (['пшен', 'millet'], 'staples.cereals.millet'),
        (['манк', 'semolina', 'манн'], 'staples.cereals.semolina'),
        (['булгур', 'bulgur'], 'staples.cereals.bulgur'),
        (['кускус', 'couscous'], 'staples.cereals.couscous'),
        (['овсян', 'oat', 'геркулес'], 'staples.cereals.oat'),
        (['перловк', 'barley', 'ячмен', 'ячневая'], 'staples.cereals.barley'),
        (['кукуруз', 'corn', 'полент'], 'staples.cereals.corn'),
        (['горох', 'pea'], 'staples.cereals.peas'),
        (['чечевиц', 'lentil'], 'staples.cereals.lentils'),
        (['фасоль', 'bean', 'бобы'], 'staples.cereals.beans'),
        (['нут', 'chickpea'], 'staples.cereals.chickpeas'),
        (['киноа', 'quinoa'], 'staples.cereals.quinoa'),
    ],
    
    # Condiments - Приправы/Соусы
    'condiments.spice': [
        (['васаби', 'wasabi'], 'condiments.wasabi'),
        (['соль', 'salt'], 'condiments.salt'),
        (['перец', 'pepper'], 'condiments.pepper'),
        (['паприк', 'paprika'], 'condiments.paprika'),
        (['куркум', 'turmeric'], 'condiments.turmeric'),
        (['имбир', 'ginger'], 'condiments.ginger'),
        (['кориандр', 'coriander'], 'condiments.coriander'),
        (['базилик', 'basil'], 'condiments.basil'),
        (['орегано', 'oregano'], 'condiments.oregano'),
    ],
    
    'condiments.wasabi': [
        (['васаби', 'wasabi'], 'condiments.wasabi'),
    ],
    
    'condiments.sauce': [
        (['кетчуп', 'ketchup'], 'condiments.ketchup'),
        (['майонез', 'mayo'], 'condiments.mayo'),
        (['соев', 'soy'], 'condiments.soy_sauce'),
        (['томат', 'tomato'], 'condiments.tomato_sauce'),
        (['горчиц', 'mustard'], 'condiments.mustard'),
        # New: More specific sauce types to reduce low confidence
        (['барбекю', 'bbq', 'barbecue'], 'condiments.sauce.bbq'),
        (['терияки', 'teriyaki'], 'condiments.sauce.teriyaki'),
        (['кимчи', 'kimchi'], 'condiments.sauce.kimchi'),
        (['кисло-сладк', 'sweet.*sour'], 'condiments.sauce.sweet_sour'),
        (['цезар', 'caesar'], 'condiments.sauce.caesar'),
        (['карри', 'curry'], 'condiments.sauce.curry'),
        (['бальзамич', 'balsamic'], 'condiments.sauce.balsamic'),
        (['чили', 'chili'], 'condiments.sauce.chili'),
        (['шашлыч', 'marinade'], 'condiments.sauce.marinade'),
        (['бешамель', 'bechamel'], 'condiments.sauce.bechamel'),
        (['голландез', 'hollandaise'], 'condiments.sauce.hollandaise'),
    ],
    
    # Seafood - Морепродукты
    'seafood.salmon': [
        (['филе', 'fillet'], 'seafood.salmon.fillet'),
        (['стейк', 'steak'], 'seafood.salmon.steak'),
        (['брюшк', 'belly'], 'seafood.salmon.belly'),
        (['икр', 'caviar'], 'seafood.salmon.caviar'),
    ],
    
    'seafood.shrimp': [
        (['креветк', 'shrimp', 'prawn'], 'seafood.shrimp'),
    ],
    
    # Crab - CRITICAL: Separate natural from imitation
    'seafood.crab': [
        (['камчат', 'kamchatka'], 'seafood.crab.kamchatka'),
        (['king crab', 'королевск'], 'seafood.crab.king'),
        (['натур'], 'seafood.crab.natural'),
        (['снежн', 'vici', 'вичи'], 'seafood.crab_sticks'),  # Snow crab = imitation in RU
        (['палочк', 'сурими', 'surimi', 'имит'], 'seafood.crab_sticks'),
    ],
    
    'seafood.crab_sticks': [
        (['палочк', 'stick'], 'seafood.crab_sticks'),
        (['сурими', 'surimi'], 'seafood.crab_sticks'),
        (['снежн', 'vici'], 'seafood.crab_sticks'),
    ],
    
    # Squid - кальмар
    'seafood.squid': [
        (['кальмар', 'squid', 'calamari'], 'seafood.squid'),
        (['тушк', 'body'], 'seafood.squid.body'),
        (['филе', 'fillet'], 'seafood.squid.fillet'),
        (['кольц', 'ring'], 'seafood.squid.rings'),
    ],
    
    # Dairy - Молочные продукты
    'dairy.сыр': [
        (['моцарелл', 'mozzarella'], 'dairy.cheese.mozzarella'),
        (['пармезан', 'parmesan'], 'dairy.cheese.parmesan'),
        (['чеддер', 'cheddar'], 'dairy.cheese.cheddar'),
        (['фета', 'feta'], 'dairy.cheese.feta'),
        (['брынз', 'brynza'], 'dairy.cheese.brynza'),
        (['сулугун', 'suluguni'], 'dairy.cheese.suluguni'),
        (['голланд', 'gouda', 'dutch'], 'dairy.cheese.dutch'),
        (['плавлен', 'processed'], 'dairy.cheese.processed'),
    ],
    
    'dairy.cheese': [
        (['моцарелл', 'mozzarella'], 'dairy.cheese.mozzarella'),
        (['пармезан', 'parmesan'], 'dairy.cheese.parmesan'),
        (['чеддер', 'cheddar'], 'dairy.cheese.cheddar'),
    ],
    
    # Vegetables - Овощи/Бобовые
    'vegetables.beans': [
        (['бобы', 'beans', 'эдамаме'], 'vegetables.beans'),
    ],
    'vegetables.peas': [
        (['горох', 'peas'], 'vegetables.peas'),
    ],
    'vegetables.lentils': [
        (['чечевиц', 'lentils'], 'vegetables.lentils'),
    ],
    
    # Disposables - Расходники
    'disposables.paper': [
        (['бумага', 'paper', 'пергамент'], 'disposables.paper'),
    ],
    'disposables.napkins': [
        (['салфетк', 'полотенц', 'napkin', 'towel'], 'disposables.napkins'),
    ],
    
    # Canned goods
    'canned.фрукты': [
        (['персик', 'peach'], 'canned.peaches'),
        (['ананас', 'pineapple'], 'canned.pineapple'),
        (['груш', 'pear'], 'canned.pears'),
    ],
    
    # Seaweed - Морские водоросли
    'seafood.seaweed': [
        (['чука', 'вакаме', 'нори', 'водоросл'], 'seafood.seaweed'),
    ],
    
    # === NEW: Categories for "other" reduction ===
    # Beverages - Syrups
    'beverages.syrup': [
        (['сироп', 'syrup'], 'beverages.syrup'),
    ],
    
    # Broths/Stocks - Бульоны
    'ready_meals.broth': [
        (['бульон', 'broth', 'stock'], 'ready_meals.broth'),
        (['грибн', 'mushroom'], 'ready_meals.broth.mushroom'),
        (['куриц', 'chicken'], 'ready_meals.broth.chicken'),
        (['говяж', 'beef'], 'ready_meals.broth.beef'),
        (['овощн', 'vegetable'], 'ready_meals.broth.vegetable'),
        (['рыбн', 'fish'], 'ready_meals.broth.fish'),
        (['баран', 'lamb'], 'ready_meals.broth.lamb'),
    ],
    
    # Canned vegetables - Консервированные овощи
    'canned.vegetables': [
        (['кукуруз', 'corn'], 'canned.vegetables.corn'),
        (['маслин', 'olives', 'olive'], 'canned.vegetables.olives'),
        (['горош', 'peas'], 'canned.vegetables.peas'),
        (['фасоль', 'beans'], 'canned.vegetables.beans'),
        (['огурц', 'cucumber', 'pickle'], 'canned.vegetables.pickles'),
        (['капуст', 'cabbage'], 'canned.vegetables.cabbage'),
        (['грибы', 'mushroom'], 'canned.vegetables.mushrooms'),
        (['редис', 'редьк', 'radish'], 'canned.vegetables.radish'),
    ],
    
    # Frozen foods - Замороженные продукты
    'frozen.vegetables': [
        (['картофел', 'potato', 'фри'], 'frozen.vegetables.potatoes'),
        (['овощ', 'vegetable'], 'frozen.vegetables'),
    ],
    'frozen.ready_meals': [
        (['пельмен', 'dumpling'], 'frozen.ready_meals.dumplings'),
        (['варен', 'vareniki'], 'frozen.ready_meals.vareniki'),
        (['котлет', 'cutlet'], 'frozen.ready_meals.cutlets'),
        (['гуляш', 'goulash'], 'frozen.ready_meals.goulash'),
        (['борщ', 'borscht'], 'frozen.ready_meals.borscht'),
        (['уха', 'soup'], 'frozen.ready_meals.soup'),
        (['каша', 'porridge'], 'frozen.ready_meals.porridge'),
    ],
    
    # Pasta - expanded
    'pasta.spaghetti': [
        (['спагетти', 'spaghetti'], 'pasta.spaghetti'),
    ],
    'pasta.penne': [
        (['пенне', 'penne', 'рожки'], 'pasta.penne'),
    ],
    'pasta.tagliatelle': [
        (['тальятелле', 'tagliatelle', 'гнезда'], 'pasta.tagliatelle'),
    ],
    'pasta.vermicelli': [
        (['вермишель', 'vermicelli'], 'pasta.vermicelli'),
    ],
    
    # Asian noodles
    'pasta.noodles': [
        (['лапша', 'noodle'], 'pasta.noodles'),
    ],
    'pasta.soba': [
        (['соба', 'soba'], 'pasta.soba'),
    ],
    'pasta.udon': [
        (['удон', 'udon'], 'pasta.udon'),
    ],
    'pasta.ramen': [
        (['рамен', 'ramen'], 'pasta.ramen'),
    ],
    'pasta.glass_noodles': [
        (['фунчоза', 'glass noodle', 'стеклян'], 'pasta.glass_noodles'),
    ],
    
    # Nuts
    'nuts.almonds': [(['миндал', 'almond'], 'nuts.almonds')],
    'nuts.hazelnuts': [(['фундук', 'hazelnut'], 'nuts.hazelnuts')],
    'nuts.cashews': [(['кешью', 'cashew'], 'nuts.cashews')],
    'nuts.pistachios': [(['фисташ', 'pistachio'], 'nuts.pistachios')],
    'nuts.walnuts': [(['грецк', 'walnut'], 'nuts.walnuts')],
    'nuts.peanuts': [(['арахис', 'peanut'], 'nuts.peanuts')],
    'nuts.pine_nuts': [(['кедров', 'pine nut'], 'nuts.pine_nuts')],
    
    # Dried fruits
    'dried_fruits.prunes': [(['чернослив', 'prune'], 'dried_fruits.prunes')],
    'dried_fruits.apricots': [(['курага', 'dried apricot'], 'dried_fruits.apricots')],
    'dried_fruits.raisins': [(['изюм', 'raisin'], 'dried_fruits.raisins')],
    'dried_fruits.figs': [(['инжир', 'fig'], 'dried_fruits.figs')],
    'dried_fruits.dates': [(['финик', 'date'], 'dried_fruits.dates')],
    
    # Soft drinks
    'beverages.cola': [(['кола', 'cola', 'пепси', 'pepsi'], 'beverages.cola')],
    
    # === DOUGH - ТЕСТО ===
    'bakery.dough': [
        (['слоен', 'puff'], 'bakery.dough.puff'),
        (['дрожжев', 'yeast'], 'bakery.dough.yeast'),
        (['песочн', 'shortcrust'], 'bakery.dough.shortcrust'),
        (['фило', 'filo', 'phyllo'], 'bakery.dough.filo'),
        (['тесто'], 'bakery.dough'),
    ],
    
    # === DAIRY - МОЛОЧНЫЕ ===
    'dairy.cheese': [
        (['пармезан', 'parmesan'], 'dairy.cheese.parmesan'),
        (['моцарел', 'mozzarella'], 'dairy.cheese.mozzarella'),
        (['гауда', 'gouda'], 'dairy.cheese.gouda'),
        (['чеддер', 'cheddar'], 'dairy.cheese.cheddar'),
        (['российск', 'russian'], 'dairy.cheese.russian'),
        (['маасдам', 'maasdam'], 'dairy.cheese.maasdam'),
        (['бри', 'brie'], 'dairy.cheese.brie'),
        (['камамбер', 'camembert'], 'dairy.cheese.camembert'),
        (['горгонзол', 'gorgonzola'], 'dairy.cheese.gorgonzola'),
        (['фета', 'feta'], 'dairy.cheese.feta'),
        (['рикотт', 'ricotta'], 'dairy.cheese.ricotta'),
        (['маскарпон', 'mascarpone'], 'dairy.cheese.mascarpone'),
        (['филадельф', 'philadelphia'], 'dairy.cheese.cream_cheese'),
        (['плавлен', 'processed'], 'dairy.cheese.processed'),
        (['сыр'], 'dairy.cheese'),
    ],
    'dairy.cream': [
        (['сливки'], 'dairy.cream'),
        (['взбит', 'whipped'], 'dairy.cream.whipped'),
        (['кулинарн', 'cooking'], 'dairy.cream.cooking'),
    ],
    'dairy.milk': [
        (['молоко'], 'dairy.milk'),
        (['молокосодерж', 'milk_product'], 'dairy.milk_product'),
    ],
    'dairy.sour_cream': [
        (['сметан'], 'dairy.sour_cream'),
    ],
    'dairy.butter': [
        (['масло сливочн', 'butter'], 'dairy.butter'),
        (['маргарин', 'margarine'], 'dairy.margarine'),
    ],
    
    # === VEGETABLES - ОВОЩИ ===
    'vegetables.potato': [
        (['картофел', 'potato'], 'vegetables.potato'),
        (['фри', 'fries'], 'frozen.vegetables.fries'),
    ],
    'vegetables.cabbage': [
        (['капуст', 'cabbage'], 'vegetables.cabbage'),
        (['квашен', 'sauerkraut'], 'vegetables.cabbage.sauerkraut'),
    ],
    'vegetables.onion': [
        (['лук ', 'onion'], 'vegetables.onion'),
        (['жарен', 'fried'], 'vegetables.onion.fried'),
    ],
    
    # === FRUITS & BERRIES - ФРУКТЫ ===
    'fruits.currant': [(['смородин', 'currant'], 'fruits.currant')],
    'fruits.strawberry': [(['клубник', 'strawberry'], 'fruits.strawberry')],
    'fruits.raspberry': [(['малин', 'raspberry'], 'fruits.raspberry')],
    'fruits.blueberry': [(['черник', 'голубик', 'blueberry'], 'fruits.blueberry')],
    'fruits.cherry': [(['вишн', 'cherry'], 'fruits.cherry')],
    
    # === BAKERY - ВЫПЕЧКА ===
    'bakery.bread': [(['хлеб', 'bread'], 'bakery.bread')],
    'bakery.bun': [(['булочк', 'bun'], 'bakery.bun')],
    'bakery.cake': [
        (['торт', 'cake'], 'bakery.cake'),
        (['кекс', 'cupcake'], 'bakery.cake.cupcake'),
    ],
    'bakery.pizza': [(['пицц', 'pizza'], 'bakery.pizza')],
    
    # === BEVERAGES - НАПИТКИ ===
    'beverages.tea': [
        (['чай', 'tea'], 'beverages.tea'),
        (['черн', 'black'], 'beverages.tea.black'),
        (['зелен', 'green'], 'beverages.tea.green'),
        (['травян', 'herbal'], 'beverages.tea.herbal'),
    ],
    'beverages.coffee': [
        (['кофе', 'coffee'], 'beverages.coffee'),
        (['эспрессо', 'espresso'], 'beverages.coffee.espresso'),
        (['капучино', 'cappuccino'], 'beverages.coffee.cappuccino'),
    ],
    'beverages.cocoa': [(['какао', 'cocoa'], 'beverages.cocoa')],
    
    # === SNACKS - СНЕКИ ===
    'snacks.chips': [(['чипс', 'chips'], 'snacks.chips')],
    'snacks.crackers': [(['сухар', 'крекер', 'cracker'], 'snacks.crackers')],
    
    # === HONEY - МЁД ===
    'condiments.honey': [(['мед', 'мёд', 'honey'], 'condiments.honey')],
    
    # === MIXES - СМЕСИ ===
    'ready_meals.mix': [
        (['смесь'], 'ready_meals.mix'),
        (['овощн', 'vegetable'], 'frozen.vegetables.mix'),
        (['специй', 'spice'], 'condiments.spice_mix'),
    ],
    
    # === PASTA (extended) ===
    'pasta': [
        (['макарон', 'macaroni'], 'pasta.macaroni'),
        (['спагетти', 'spaghetti'], 'pasta.spaghetti'),
        (['пенне', 'penne'], 'pasta.penne'),
        (['фузилли', 'fusilli'], 'pasta.fusilli'),
        (['фарфалле', 'farfalle'], 'pasta.farfalle'),
        (['ригатони', 'rigatoni'], 'pasta.rigatoni'),
        (['лазанья', 'lasagna'], 'pasta.lasagna'),
        (['каннеллони', 'cannelloni'], 'pasta.cannelloni'),
    ],
    
    # JUICES - Соки (CRITICAL FIX)
    'beverages.juice': [
        (['юдзу', 'yuzu'], 'beverages.juice.yuzu'),
        (['апельсин', 'orange'], 'beverages.juice.orange'),
        (['яблок', 'apple'], 'beverages.juice.apple'),
        (['томат', 'tomato'], 'beverages.juice.tomato'),
        (['ананас', 'pineapple'], 'beverages.juice.pineapple'),
        (['грейпфрут', 'grapefruit'], 'beverages.juice.grapefruit'),
        (['виноград', 'grape'], 'beverages.juice.grape'),
        (['гранат', 'pomegranate'], 'beverages.juice.pomegranate'),
        (['лимон', 'lemon'], 'beverages.juice.lemon'),
        (['лайм', 'lime'], 'beverages.juice.lime'),
        (['манго', 'mango'], 'beverages.juice.mango'),
        (['вишн', 'cherry'], 'beverages.juice.cherry'),
        (['персик', 'peach'], 'beverages.juice.peach'),
        (['груш', 'pear'], 'beverages.juice.pear'),
        (['мультифрукт', 'multifruit'], 'beverages.juice'),
    ],
    'beverages.juice.yuzu': [
        (['юдзу', 'yuzu'], 'beverages.juice.yuzu'),
    ],
    'beverages.juice.orange': [
        (['апельсин', 'orange'], 'beverages.juice.orange'),
    ],
    'beverages.juice.apple': [
        (['яблок', 'apple'], 'beverages.juice.apple'),
    ],
    'beverages.soft_drinks': [(['эвервесс', 'спрайт', 'фанта', 'sprite', 'fanta'], 'beverages.soft_drinks')],
    'beverages.lemonade': [(['лимонад', 'lemonade'], 'beverages.lemonade')],
    'beverages.carbonated': [(['газиров', 'carbonated'], 'beverages.carbonated')],
    
    # Concentrates
    'beverages.concentrate': [(['концентрат', 'concentrate'], 'beverages.concentrate')],
}


def detect_product_core(product_name: str, super_class: str) -> Tuple[Optional[str], float]:
    """
    Определяет узкую категорию (product_core) для товара
    
    Args:
        product_name: Название товара
        super_class: Широкая категория (из universal_super_class_mapper)
    
    Returns:
        (product_core, confidence)
        - product_core: Узкая категория или None
        - confidence: Уверенность 0.0-1.0
    """
    if not product_name or not super_class:
        return (None, 0.0)
    
    name_lower = product_name.lower()
    
    # Check if we have rules for this super_class
    if super_class not in PRODUCT_CORE_RULES:
        # No rules - return super_class as core (fallback)
        return (super_class, 0.5)
    
    rules = PRODUCT_CORE_RULES[super_class]
    
    # Try to match keywords
    for keywords, product_core in rules:
        for keyword in keywords:
            if keyword in name_lower:
                return (product_core, 0.9)
    
    # No match - return super_class as fallback with low confidence
    return (super_class, 0.3)


def get_all_product_cores():
    """Возвращает список всех возможных product_core"""
    cores = set()
    for super_class, rules in PRODUCT_CORE_RULES.items():
        for keywords, product_core in rules:
            cores.add(product_core)
    return sorted(cores)


# Tests
if __name__ == "__main__":
    test_cases = [
        ("ГОВЯДИНА фарш охлажденный 1кг", "meat.beef"),
        ("Суповой набор из говядины вес", "meat.beef"),
        ("МУКА пшеничная высший сорт 1кг", "staples.мука"),
        ("МУКА ржаная обдирная 1кг", "staples.мука"),
        ("ВАСАБИ порошок 1кг", "condiments.wasabi"),
        ("Соль нитритная 1кг", "condiments.spice"),
        ("Кетчуп томатный 500г", "condiments.sauce"),
        ("Креветки 1кг", "seafood.shrimp"),
    ]
    
    print("=" * 80)
    print("PRODUCT CORE CLASSIFICATION TESTS")
    print("=" * 80)
    
    for name, super_class in test_cases:
        core, conf = detect_product_core(name, super_class)
        print(f"\n📦 {name[:50]:50}")
        print(f"   Super: {super_class:25} → Core: {core:30} (conf={conf:.2f})")
    
    print(f"\n\n📊 Total product cores defined: {len(get_all_product_cores())}")
    print("Examples:")
    for core in get_all_product_cores()[:20]:
        print(f"  - {core}")
