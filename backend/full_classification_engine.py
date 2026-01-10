"""
ДВОЙНОЙ АЛГОРИТМ КЛАССИФИКАЦИИ ТОВАРОВ
======================================

Алгоритм 1 (Rule-based): Детерминистические правила по ключевым словам
Алгоритм 2 (Fuzzy-matching): Нечёткое сопоставление + контекстный анализ

Автор: AI Agent
Дата: 2026-01-10
"""

import re
from typing import Tuple, Dict, List, Optional
from collections import defaultdict

# ============================================================================
# АЛГОРИТМ 1: RULE-BASED КЛАССИФИКАЦИЯ
# ============================================================================

# Иерархическая структура категорий с приоритетами
CLASSIFICATION_RULES = {
    # УРОВЕНЬ 1: Самый высокий приоритет (специфичные товары)
    'priority_1': {
        # Упаковка и посуда
        'packaging.cutlery': ['нож пластик', 'вилка пластик', 'ложка пластик', 'столов прибор', 
                              'нож 180', 'нож 165', 'вилка 165', 'ложка 165'],
        'packaging.container': ['ланч-бокс', 'lunchbox', 'контейнер пищев', 'контейнер с крышк',
                                'лоток пищев', 'ёмкость пищев', 'судок'],
        'packaging.skewer': ['шампур', 'шпажк', 'палочк бамбук', 'палочк дерев'],
        'packaging.wrap': ['плёнка пищев', 'фольга алюмин', 'пакет вакуум', 'пакет zip'],
        'packaging.napkin': ['салфетк', 'napkin', 'бумажн полотенц'],
        'packaging.cup': ['стакан пластик', 'стакан бумаж', 'стаканчик'],
        'packaging.plate': ['тарелка однораз', 'тарелка пластик', 'тарелка бумаж'],
        'packaging.bag': ['пакет фасов', 'пакет майка', 'мешок мусор'],
        
        # Морепродукты - специфичные
        'seafood.fish_sticks': ['палочки рыбн', 'fish stick', 'рыбн палочк'],
        'seafood.langoustine': ['лангустин', 'langoustine', 'креветки аргентин'],
        'seafood.crab_sticks': ['крабов палочк', 'сурими', 'имитац краб'],
        
        # Готовые блюда - специфичные
        'ready_meals.cheburek': ['чебурек', 'чебурёк'],
        'ready_meals.pelmeni': ['пельмен', 'хинкал', 'манты', 'позы'],
        'ready_meals.pierogi': ['вареник', 'галушк'],
        
        # Мясопродукты специфичные
        'meat.prosciutto': ['прошутто', 'prosciutto', 'ломбо', 'lombo', 'хамон', 'jamon'],
        'meat.bacon': ['бекон', 'bacon', 'грудинк копчён'],
        'meat.sausage': ['колбас', 'sausage', 'сосиск', 'сардельк'],
        
        # Десертные пасты и соусы
        'condiments.paste': ['паста десертн', 'паста концентрир', 'joypaste', 'паста вкусов'],
        'condiments.miso': ['мисо паста', 'miso', 'shiro miso', 'паста соев'],
        'condiments.curry_paste': ['паста том ям', 'tom yam', 'карри паста', 'curry paste'],
    },
    
    # УРОВЕНЬ 2: Высокий приоритет (категории продуктов)
    'priority_2': {
        # Молочные продукты
        'dairy.butter': ['масло сливоч', 'butter', 'масло крестьян', 'масло традиц'],
        'dairy.cheese': ['сыр ', 'cheese', 'моцарелл', 'пармезан', 'чеддер', 'гауда', 'бри'],
        'dairy.milk': ['молоко', 'milk', 'молоч коктейл'],
        'dairy.cream': ['сливки', 'cream', 'сметан'],
        'dairy.yogurt': ['йогурт', 'yogurt', 'кефир', 'ряженк', 'простоваш'],
        
        # Мясо
        'meat.chicken': ['курин', 'кура ', 'курица', 'куриц', 'chicken', 'цыплён', 'бройлер',
                        'филе куриц', 'грудка куриц', 'бедро куриц', 'крыл куриц'],
        'meat.beef': ['говядин', 'beef', 'говяж', 'телятин', 'veal', 'стейк говяж'],
        'meat.pork': ['свинин', 'pork', 'свиной', 'свиная', 'карбонад', 'корейк свин'],
        'meat.lamb': ['баранин', 'lamb', 'mutton', 'ягнятин', 'каре ягнёнк'],
        'meat.turkey': ['индейк', 'turkey', 'индюш'],
        'meat.duck': ['утка', 'утин', 'duck', 'утиц'],
        
        # Морепродукты
        'seafood.shrimp': ['креветк', 'shrimp', 'prawn', 'гамбас'],
        'seafood.squid': ['кальмар', 'squid', 'calamari'],
        'seafood.salmon': ['лосос', 'salmon', 'сёмг', 'семг', 'форел', 'trout'],
        'seafood.tuna': ['тунец', 'tuna'],
        'seafood.crab': ['краб натур', 'crab', 'камчатск краб'],
        'seafood.pollock': ['минтай', 'pollock'],
        'seafood.cod': ['треска', 'cod'],
        'seafood.seabass': ['сибас', 'seabass', 'лавран'],
        'seafood.octopus': ['осьминог', 'octopus'],
        'seafood.mussel': ['мидии', 'mussel'],
        'seafood.oyster': ['устриц', 'oyster'],
        
        # Овощи
        'vegetables.tomato': ['помидор', 'томат', 'tomato', 'черри'],
        'vegetables.potato': ['картофел', 'potato', 'картошк'],
        'vegetables.onion': ['лук репч', 'onion', 'лук крас'],
        'vegetables.carrot': ['морков', 'carrot'],
        'vegetables.cucumber': ['огурц', 'cucumber', 'корнишон'],
        'vegetables.pepper': ['перец болгар', 'bell pepper', 'паприка свеж'],
        'vegetables.cabbage': ['капуст', 'cabbage', 'брокколи', 'цветн капуст'],
        'vegetables.mushroom': ['гриб', 'mushroom', 'шампиньон', 'вёшенк'],
        'vegetables.greens': ['салат лист', 'рукол', 'шпинат', 'петрушк', 'укроп', 'кинз'],
        
        # Фрукты
        'fruits.apple': ['яблок', 'apple'],
        'fruits.orange': ['апельсин', 'orange', 'мандарин'],
        'fruits.lemon': ['лимон', 'lemon', 'лайм', 'lime'],
        'fruits.banana': ['банан', 'banana'],
        'fruits.berry': ['клубник', 'малин', 'черник', 'ежевик', 'голубик', 'смородин'],
        
        # Напитки
        'beverages.water': ['вода минерал', 'вода газиров', 'вода питьев', 'mineral water'],
        'beverages.juice': ['сок ', 'juice', 'нектар'],
        'beverages.cola': ['кола', 'cola', 'пепси', 'pepsi', 'sprite', 'fanta'],
        'beverages.tea': ['чай ', 'tea', 'чай чёрн', 'чай зелён'],
        'beverages.coffee': ['кофе', 'coffee', 'эспрессо', 'капучино'],
        'beverages.syrup': ['сироп', 'syrup'],
        'beverages.energy': ['энергетик', 'energy drink', 'red bull', 'monster'],
        
        # Консервы
        'canned.vegetables': ['консерв овощ', 'горошек консерв', 'кукуруза консерв', 'оливк'],
        'canned.fish': ['консерв рыб', 'шпрот', 'сардин', 'тунец консерв'],
        'canned.fruits': ['консерв фрукт', 'ананас консерв', 'персик консерв'],
        
        # Крупы и макароны
        'staples.rice': ['рис ', 'rice', 'рис басмат', 'рис жасмин'],
        'staples.buckwheat': ['гречк', 'buckwheat', 'гречих'],
        'staples.oats': ['овсянк', 'oats', 'геркулес'],
        'pasta': ['макарон', 'pasta', 'спагетти', 'пенне', 'фузилл', 'лазань', 'лингвин'],
        
        # Мука и выпечка
        'staples.flour': ['мука', 'flour', 'мука пшенич', 'мука ржан'],
        'bakery.bread': ['хлеб', 'bread', 'батон', 'багет', 'булк'],
        'bakery.pastry': ['выпечк', 'pastry', 'круассан', 'пирожок', 'слойк'],
        
        # Соусы и приправы
        'condiments.sauce': ['соус', 'sauce', 'кетчуп', 'майонез', 'горчиц'],
        'condiments.oil': ['масло растит', 'масло подсолн', 'масло оливк', 'olive oil'],
        'condiments.vinegar': ['уксус', 'vinegar', 'бальзамик'],
        'condiments.spice': ['специ', 'spice', 'приправ', 'перец молот', 'корица', 'имбир'],
        'condiments.salt': ['соль ', 'salt', 'соль морск', 'соль йодир'],
        'condiments.sugar': ['сахар', 'sugar'],
    },
    
    # УРОВЕНЬ 3: Средний приоритет (общие категории)
    'priority_3': {
        'meat': ['мясо', 'meat', 'фарш', 'котлет', 'стейк'],
        'seafood': ['морепродукт', 'seafood', 'рыба', 'fish', 'филе рыб'],
        'vegetables': ['овощ', 'vegetable', 'зелень'],
        'fruits': ['фрукт', 'fruit', 'ягод'],
        'dairy': ['молочн', 'dairy'],
        'beverages': ['напиток', 'beverage', 'питьё'],
        'canned': ['консерв', 'canned'],
        'frozen': ['заморож', 'frozen', 'с/м'],
        'ready_meals': ['готов блюд', 'ready meal', 'полуфабрикат'],
    }
}

# Негативные слова для исключения ложных срабатываний
NEGATIVE_CONTEXT = {
    'dairy.butter': ['арахис', 'какао', 'кокос', 'ши '],  # Не сливочное масло
    'pasta': ['зубн', 'паста томатн', 'паста десерт', 'паста соев'],  # Не макароны
    'meat.chicken': ['грибы курин'],  # Курник - не курица
}


def classify_rule_based(name: str) -> Tuple[str, float, str]:
    """
    Алгоритм 1: Rule-based классификация
    
    Returns:
        (category, confidence, matched_rule)
    """
    name_lower = name.lower()
    
    # Проверяем по приоритетам
    for priority_level in ['priority_1', 'priority_2', 'priority_3']:
        rules = CLASSIFICATION_RULES.get(priority_level, {})
        
        for category, keywords in rules.items():
            for keyword in keywords:
                if keyword in name_lower:
                    # Проверяем негативный контекст
                    neg_words = NEGATIVE_CONTEXT.get(category, [])
                    if any(neg in name_lower for neg in neg_words):
                        continue
                    
                    # Определяем confidence по уровню приоритета
                    conf_map = {'priority_1': 0.95, 'priority_2': 0.85, 'priority_3': 0.70}
                    confidence = conf_map.get(priority_level, 0.50)
                    
                    return category, confidence, keyword
    
    return 'other', 0.30, 'no_match'


# ============================================================================
# АЛГОРИТМ 2: FUZZY MATCHING + КОНТЕКСТНЫЙ АНАЛИЗ
# ============================================================================

# Словарь синонимов и вариаций написания
SYNONYMS = {
    # Форматы
    'с/м': ['свежемороженый', 'замороженный', 'frozen'],
    'с/г': ['свежий', 'охлаждённый', 'fresh'],
    'б/к': ['без кости', 'boneless', 'бескостный'],
    'б/ш': ['без шкуры', 'skinless', 'без кожи'],
    'о/х': ['охлаждённый', 'chilled'],
    'в/с': ['высший сорт', 'premium'],
    'в/у': ['в упаковке', 'packed'],
    
    # Единицы
    'кг': ['килограмм', 'kg', 'килогр'],
    'г': ['грамм', 'гр', 'gr'],
    'л': ['литр', 'liter', 'л.'],
    'мл': ['миллилитр', 'ml'],
    'шт': ['штука', 'штук', 'pcs', 'pc'],
    
    # Бренды-страны
    'россия': ['российск', 'отечествен', 'рф'],
    'испания': ['испанск', 'spain'],
    'италия': ['итальянск', 'italy'],
    'китай': ['китайск', 'china'],
    'таиланд': ['тайск', 'thai', 'thailand'],
}

# Токены для контекстного анализа
CONTEXT_TOKENS = {
    'packaging': ['упак', 'короб', 'блок', 'пач', 'набор', 'комплект'],
    'frozen': ['с/м', 'зам', 'мороз', 'frozen'],
    'fresh': ['свеж', 'охл', 'chilled', 'fresh'],
    'organic': ['органик', 'bio', 'эко', 'organic'],
    'premium': ['премиум', 'premium', 'элит', 'высш сорт'],
}


def tokenize(text: str) -> List[str]:
    """Разбиение текста на токены с нормализацией"""
    # Удаляем специальные символы, оставляем буквы и цифры
    text = re.sub(r'[^\w\s]', ' ', text.lower())
    tokens = text.split()
    
    # Нормализация синонимов
    normalized = []
    for token in tokens:
        found_syn = False
        for canonical, synonyms in SYNONYMS.items():
            if token in synonyms or token == canonical:
                normalized.append(canonical)
                found_syn = True
                break
        if not found_syn:
            normalized.append(token)
    
    return normalized


def extract_context(name: str) -> Dict[str, bool]:
    """Извлечение контекстных признаков"""
    name_lower = name.lower()
    context = {}
    
    for ctx_type, tokens in CONTEXT_TOKENS.items():
        context[ctx_type] = any(t in name_lower for t in tokens)
    
    return context


def classify_fuzzy(name: str, existing_items: List[dict] = None) -> Tuple[str, float, str]:
    """
    Алгоритм 2: Fuzzy matching с контекстным анализом
    
    Returns:
        (category, confidence, reason)
    """
    try:
        from rapidfuzz import fuzz, process
    except ImportError:
        return 'other', 0.30, 'rapidfuzz_not_installed'
    
    tokens = tokenize(name)
    context = extract_context(name)
    
    # Если есть существующие классифицированные товары - ищем похожие
    if existing_items:
        # Создаём список для сравнения
        choices = [(item.get('name_raw', ''), item.get('super_class', '')) 
                   for item in existing_items if item.get('super_class')]
        
        if choices:
            # Ищем лучшее совпадение
            best_match = process.extractOne(
                name, 
                [c[0] for c in choices],
                scorer=fuzz.token_set_ratio,
                score_cutoff=70
            )
            
            if best_match:
                matched_name, score, idx = best_match
                matched_category = choices[idx][1]
                
                # Корректируем confidence на основе контекста
                confidence = score / 100
                
                # Бонус за совпадение контекста (frozen/fresh)
                if context.get('frozen') and 'frozen' in matched_name.lower():
                    confidence = min(1.0, confidence + 0.05)
                
                return matched_category, confidence, f"fuzzy_match:{matched_name[:30]}"
    
    return 'other', 0.30, 'no_fuzzy_match'


# ============================================================================
# ДВОЙНАЯ КЛАССИФИКАЦИЯ (ENSEMBLE)
# ============================================================================

def classify_double(name: str, existing_items: List[dict] = None) -> Dict:
    """
    Двойной алгоритм: комбинирует rule-based и fuzzy matching
    
    Returns:
        {
            'category': str,
            'confidence': float,
            'algorithm': str,  # 'rule_based', 'fuzzy', 'ensemble'
            'rule_result': {...},
            'fuzzy_result': {...}
        }
    """
    # Алгоритм 1
    rule_cat, rule_conf, rule_match = classify_rule_based(name)
    
    # Алгоритм 2
    fuzzy_cat, fuzzy_conf, fuzzy_reason = classify_fuzzy(name, existing_items)
    
    result = {
        'name': name[:60],
        'rule_based': {'category': rule_cat, 'confidence': rule_conf, 'match': rule_match},
        'fuzzy': {'category': fuzzy_cat, 'confidence': fuzzy_conf, 'reason': fuzzy_reason},
    }
    
    # Решающая логика
    if rule_conf >= 0.85:
        # Rule-based уверен
        result['final_category'] = rule_cat
        result['final_confidence'] = rule_conf
        result['algorithm'] = 'rule_based'
    elif fuzzy_conf >= 0.85 and rule_cat == 'other':
        # Fuzzy нашёл хорошее совпадение, rule-based не нашёл
        result['final_category'] = fuzzy_cat
        result['final_confidence'] = fuzzy_conf
        result['algorithm'] = 'fuzzy'
    elif rule_cat == fuzzy_cat and rule_cat != 'other':
        # Оба алгоритма согласны
        result['final_category'] = rule_cat
        result['final_confidence'] = max(rule_conf, fuzzy_conf) + 0.05  # Бонус за согласие
        result['algorithm'] = 'ensemble'
    elif rule_conf > fuzzy_conf:
        result['final_category'] = rule_cat
        result['final_confidence'] = rule_conf
        result['algorithm'] = 'rule_based'
    else:
        result['final_category'] = fuzzy_cat
        result['final_confidence'] = fuzzy_conf
        result['algorithm'] = 'fuzzy'
    
    return result


# ============================================================================
# ПАКЕТНАЯ КЛАССИФИКАЦИЯ
# ============================================================================

def classify_batch(items: List[dict], use_existing: bool = True) -> List[Dict]:
    """
    Пакетная классификация с использованием уже классифицированных товаров
    """
    results = []
    
    # Получаем уже классифицированные товары для fuzzy matching
    existing = [item for item in items if item.get('super_class')] if use_existing else []
    
    for item in items:
        name = item.get('name_raw', '')
        current_class = item.get('super_class')
        
        if current_class:
            # Уже классифицирован - проверяем корректность
            check_result = classify_double(name, existing)
            check_result['original_category'] = current_class
            check_result['status'] = 'verified' if check_result['final_category'] == current_class else 'mismatch'
            results.append(check_result)
        else:
            # Не классифицирован - классифицируем
            class_result = classify_double(name, existing)
            class_result['original_category'] = None
            class_result['status'] = 'new_classification'
            results.append(class_result)
    
    return results


if __name__ == '__main__':
    # Тестирование
    test_names = [
        "НОЖ 180 мм прозрачный 1 упак/50 шт. ВЗЛП",
        "ЛАНЧ-БОКС 1 секция черный LBS",
        "ШАМПУРЫ для шашлыка 3мм*20 см бамбук 100 штук/уп",
        "ПАЛОЧКИ рыбные в панировке 5 кг, РОССИЯ",
        "ЧЕБУРЕКИ с курицей замороженные 5 кг, РОССИЯ",
        "Паста Том Ям 1кг",
        "ПАСТА соевая светлая Shiro Miso 1 кг",
        "Продукт из свинины цельно куск.с/в кат.А «Lombo»",
    ]
    
    print("=" * 70)
    print("ТЕСТ ДВОЙНОГО АЛГОРИТМА КЛАССИФИКАЦИИ")
    print("=" * 70)
    
    for name in test_names:
        result = classify_double(name)
        print(f"\n{name[:50]}...")
        print(f"  Rule-based: {result['rule_based']['category']} ({result['rule_based']['confidence']:.0%})")
        print(f"  Fuzzy:      {result['fuzzy']['category']} ({result['fuzzy']['confidence']:.0%})")
        print(f"  FINAL:      {result['final_category']} ({result['final_confidence']:.0%}) [{result['algorithm']}]")
