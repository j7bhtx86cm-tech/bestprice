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
