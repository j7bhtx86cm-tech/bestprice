"""
BestPrice v12 - Matching Rules v2.0
===================================

Модуль сопоставления товаров согласно ТЗ v1.0.

Ключевые принципы:
1. Жёсткие фильтры ДО ранжирования (product_class, variant, special_type)
2. Бренд — приоритет №1 при ранжировании (если определён)
3. Универсальная логика для любой номенклатуры
4. "Слова-ловушки" — распознавание когда слово выглядит как название, а не тип
5. Quality tier — премиум товары показывают премиум альтернативы
6. Порог релевантности — не показываем мусор

Атрибуты для извлечения:
- product_class: жёсткий тип товара
- brand: торговая марка
- variant: вкус/начинка/аромат
- special_type: растительное/безлактозное/кокосовое/сгущённое/ЗМЖ/UHT
- fat_percent: жирность
- net_qty, unit: масса/объём
- pack_info: упаковка
- form_factor: готовое блюдо/ингредиент/полуфабрикат
- quality_tier: премиум/экстра/стандарт

Author: BestPrice v12
Version: 2.0
"""

import json
import re
import os
import logging
from typing import Dict, List, Optional, Tuple, Any, Set
from pathlib import Path
from dataclasses import dataclass, field
from functools import lru_cache

logger = logging.getLogger(__name__)

# === LEXICON AND TAXONOMY ===

_LEXICON_CACHE: Optional[Dict] = None
_TAXONOMY_CACHE: Optional[Dict] = None


def get_lexicon_path() -> Path:
    return Path(__file__).parent / "lexicon_ru_v1_3.json"


def load_lexicon() -> Dict:
    global _LEXICON_CACHE
    if _LEXICON_CACHE is not None:
        return _LEXICON_CACHE
    
    lexicon_path = get_lexicon_path()
    if not lexicon_path.exists():
        raise FileNotFoundError(f"Lexicon not found: {lexicon_path}")
    
    with open(lexicon_path, 'r', encoding='utf-8') as f:
        _LEXICON_CACHE = json.load(f)
    
    logger.info(f"Lexicon v2 loaded: {lexicon_path}")
    return _LEXICON_CACHE


def get_lexicon() -> Dict:
    return load_lexicon()


# === PRODUCT CLASS TAXONOMY (расширенная для ТЗ v1.0) ===

PRODUCT_CLASS_TAXONOMY = {
    # Молочка - разные классы
    'milk_drinking': ['молоко питьевое', 'молоко пастеризованное', 'молоко ультрапастеризованное', 'молоко топлёное', 'молоко цельное'],
    'milk_condensed': ['молоко сгущённое', 'сгущёнка', 'сгущенка', 'молоко сгущ', 'сгущенное молоко'],
    'milk_plant_based': ['растительное молоко', 'овсяное молоко', 'миндальное молоко', 'кокосовое молоко', 'соевое молоко', 'рисовое молоко', 'фундуковое молоко'],
    'kefir': ['кефир'],
    'yogurt': ['йогурт', 'йогу|рт', 'биойогурт'],
    'ryazhenka': ['ряженка'],
    'smetana': ['сметана'],
    'cream': ['сливки', 'сливок'],
    'cottage_cheese': ['творог', 'творожок', 'творожный'],
    'syrniki': ['сырники', 'сырник'],
    'cheese_hard': ['сыр твёрдый', 'сыр полутвёрдый', 'пармезан', 'маасдам', 'гауда', 'эдам', 'чеддер', 'голландский сыр'],
    'cheese_soft': ['сыр мягкий', 'бри', 'камамбер', 'фета', 'рикотта', 'маскарпоне'],
    'cheese_curd': ['сыр творожный', 'сырок', 'творожный сыр'],
    'cheese_mozzarella': ['моцарелла', 'мацарелла', 'буррата'],
    'cheese_processed': ['сыр плавленый', 'плавленый сыр', 'сырный продукт'],
    'butter': ['масло сливочное', 'масло крестьянское', 'масло традиционное'],
    
    # Сосиски и колбасы - разные классы
    'sausages': ['сосиски', 'сосиска', 'сарделька', 'сардельки', 'шпикачки'],
    'sausage_boiled': ['колбаса варёная', 'колбаса вареная', 'докторская', 'молочная колбаса', 'любительская'],
    'sausage_smoked': ['колбаса копчёная', 'колбаса копченая', 'салями', 'сервелат', 'колбаса сырокопчёная', 'колбаса полукопчёная'],
    'ham': ['ветчина', 'окорок', 'буженина'],
    'bacon': ['бекон', 'грудинка', 'корейка'],
    'pate': ['паштет'],
    
    # Мясо сырое - разные формы
    'meat_fillet': ['филе', 'вырезка'],
    'meat_breast': ['грудка', 'грудинка сырая'],
    'meat_thigh': ['бедро', 'окорочок', 'голень'],
    'meat_wing': ['крыло', 'крылышки', 'крылья'],
    'meat_carcass': ['тушка', 'цыплёнок', 'курица целая', 'утка целая'],
    'meat_minced': ['фарш'],
    'meat_steak': ['стейк', 'антрекот', 'рибай', 'тибон'],
    'meat_ribs': ['рёбра', 'ребрышки', 'рёбрышки'],
    'meat_neck': ['шея', 'шейка'],
    'meat_liver': ['печень', 'печёнка'],
    'meat_heart': ['сердце', 'сердечки'],
    
    # Рыба - разные формы
    'fish_fillet': ['филе рыбы', 'филе лосося', 'филе трески', 'филе горбуши'],
    'fish_carcass': ['тушка рыбы', 'рыба целая', 'тушка лосося'],
    'fish_steak': ['стейк рыбы', 'стейк лосося', 'стейк семги'],
    'fish_canned': ['консервы рыбные', 'шпроты', 'сайра консервы', 'тунец консервы'],
    'fish_smoked': ['рыба копчёная', 'лосось копчёный', 'горбуша копчёная', 'скумбрия копчёная'],
    'fish_salted': ['рыба солёная', 'сёмга солёная', 'лосось слабосолёный', 'селёдка'],
    'caviar': ['икра', 'икра красная', 'икра чёрная', 'икра лососёвая'],
    
    # Полуфабрикаты
    'dumplings': ['пельмени'],
    'vareniki': ['вареники'],
    'khinkali': ['хинкали'],
    'manti': ['манты'],
    'cutlets': ['котлеты', 'котлета', 'биточки'],
    'nuggets': ['наггетсы', 'нагетсы'],
    'pancakes': ['блины', 'блинчики', 'оладьи'],
    'chebureki': ['чебуреки', 'беляши'],
    
    # Готовые блюда
    'casserole': ['запеканка', 'творожная запеканка'],
    'salad_ready': ['салат готовый', 'оливье', 'винегрет'],
    'soup_ready': ['суп готовый', 'борщ готовый', 'щи готовые'],
    
    # Хлеб и выпечка
    'bread': ['хлеб', 'батон', 'багет', 'буханка'],
    'buns': ['булочка', 'плюшка', 'слойка'],
    'cookies': ['печенье', 'крекер'],
    'cakes': ['торт', 'пирожное', 'эклер'],
    'croissant': ['круассан', 'круассаны'],
    
    # Сладости
    'chocolate': ['шоколад', 'шоколадка', 'плитка шоколада'],
    'candy': ['конфеты', 'конфета', 'карамель', 'ирис'],
    'bars': ['батончик', 'сникерс', 'марс', 'твикс', 'баунти'],
    'donut': ['донат', 'пончик', 'берлинер'],
    'ice_cream': ['мороженое', 'пломбир', 'эскимо'],
    
    # Напитки
    'juice': ['сок', 'нектар', 'морс'],
    'water': ['вода', 'минералка', 'минеральная вода'],
    'soda': ['газировка', 'кола', 'лимонад', 'фанта', 'спрайт'],
    'tea': ['чай', 'чай чёрный', 'чай зелёный'],
    'coffee': ['кофе', 'кофейный напиток'],
    
    # Овощи и фрукты
    'vegetables': ['овощи', 'огурцы', 'помидоры', 'томаты', 'картофель', 'морковь', 'лук', 'капуста'],
    'fruits': ['фрукты', 'яблоки', 'груши', 'бананы', 'апельсины', 'мандарины'],
    'berries': ['ягоды', 'клубника', 'малина', 'черника', 'смородина'],
    'mushrooms': ['грибы', 'шампиньоны', 'вешенки', 'лисички'],
    
    # Яйца
    'eggs': ['яйца', 'яйцо', 'яйца куриные', 'яйца перепелиные'],
    
    # Масла и соусы
    'oil_vegetable': ['масло подсолнечное', 'масло растительное', 'масло оливковое', 'масло рапсовое'],
    'mayonnaise': ['майонез', 'майонезный соус'],
    'ketchup': ['кетчуп', 'томатный соус'],
    'mustard': ['горчица'],
    'soy_sauce': ['соевый соус', 'соус соевый'],
    
    # Крупы и макароны
    'pasta': ['макароны', 'спагетти', 'пенне', 'фузилли', 'лапша'],
    'rice': ['рис', 'рис длиннозёрный', 'рис круглозёрный'],
    'buckwheat': ['гречка', 'гречневая крупа'],
    'oatmeal': ['овсянка', 'овсяные хлопья', 'геркулес'],
    
    # Консервы
    'canned_vegetables': ['консервы овощные', 'горошек', 'кукуруза консервированная', 'фасоль консервированная'],
    'canned_meat': ['тушёнка', 'консервы мясные'],
}

# Обратный индекс: keyword -> product_class
_PRODUCT_CLASS_INDEX: Dict[str, str] = {}


def _build_product_class_index():
    """Строит обратный индекс для быстрого поиска product_class."""
    global _PRODUCT_CLASS_INDEX
    if _PRODUCT_CLASS_INDEX:
        return
    
    for pclass, keywords in PRODUCT_CLASS_TAXONOMY.items():
        for kw in keywords:
            kw_lower = kw.lower()
            # Более длинные ключевые слова имеют приоритет
            if kw_lower not in _PRODUCT_CLASS_INDEX or len(kw) > len(_PRODUCT_CLASS_INDEX.get(kw_lower, '')):
                _PRODUCT_CLASS_INDEX[kw_lower] = pclass


_build_product_class_index()


# === VARIANTS (вкусы/начинки) ===

VARIANT_KEYWORDS = {
    # Фруктовые вкусы
    'strawberry': ['клубника', 'клубничный', 'клубничная', 'земляника', 'земляничный'],
    'peach': ['персик', 'персиковый', 'персиковая'],
    'cherry': ['вишня', 'вишнёвый', 'вишневый', 'черешня'],
    'apple': ['яблоко', 'яблочный', 'яблочная'],
    'banana': ['банан', 'банановый', 'банановая'],
    'mango': ['манго', 'манговый'],
    'pineapple': ['ананас', 'ананасовый'],
    'orange': ['апельсин', 'апельсиновый', 'цитрус'],
    'lemon': ['лимон', 'лимонный'],
    'raspberry': ['малина', 'малиновый', 'малиновая'],
    'blueberry': ['черника', 'черничный', 'черничная', 'голубика'],
    'cranberry': ['клюква', 'клюквенный'],
    'currant': ['смородина', 'смородиновый'],
    'grape': ['виноград', 'виноградный'],
    'melon': ['дыня', 'дынный'],
    'watermelon': ['арбуз', 'арбузный'],
    'pear': ['груша', 'грушевый'],
    'plum': ['слива', 'сливовый'],
    'apricot': ['абрикос', 'абрикосовый'],
    'pomegranate': ['гранат', 'гранатовый'],
    'tropical': ['тропический', 'тропик', 'мультифрукт', 'экзотик'],
    
    # Ореховые и другие
    'chocolate': ['шоколад', 'шоколадный', 'какао'],
    'vanilla': ['ваниль', 'ванильный'],
    'caramel': ['карамель', 'карамельный', 'ириска'],
    'hazelnut': ['фундук', 'фундуковый', 'лесной орех'],
    'almond': ['миндаль', 'миндальный'],
    'coconut': ['кокос', 'кокосовый'],
    'pistachio': ['фисташка', 'фисташковый'],
    'walnut': ['грецкий орех', 'орех'],
    'honey': ['мёд', 'медовый', 'медовая'],
    'maple': ['клён', 'кленовый', 'maple'],
    
    # Молочные начинки
    'cream_filling': ['со сливками', 'сливочный', 'крем'],
    'cottage_filling': ['с творогом', 'творожный', 'творожная'],
    
    # Мясные/другие начинки
    'meat_filling': ['с мясом', 'мясной', 'мясная'],
    'chicken_filling': ['с курицей', 'куриный', 'куриная'],
    'mushroom_filling': ['с грибами', 'грибной', 'грибная'],
    'cheese_filling': ['с сыром', 'сырный', 'сырная'],
    'potato_filling': ['с картошкой', 'картофельный', 'картофельная'],
    'cabbage_filling': ['с капустой', 'капустный'],
    'berry_filling': ['с ягодами', 'ягодный', 'ягодная'],
    
    # Без добавок
    'natural': ['натуральный', 'классический', 'без добавок', 'original', 'plain'],
}


# === SPECIAL TYPES ===

SPECIAL_TYPE_KEYWORDS = {
    'plant_based': ['растительный', 'растительное', 'веган', 'vegan', 'на растительной основе'],
    'lactose_free': ['безлактозный', 'безлактозное', 'без лактозы', 'lactose free'],
    'coconut': ['кокосовый', 'кокосовое', 'на кокосе', 'coconut'],
    'oat': ['овсяный', 'овсяное', 'на овсе', 'oat'],
    'soy': ['соевый', 'соевое', 'на сое', 'soy'],
    'almond': ['миндальный', 'миндальное', 'на миндале', 'almond'],
    'rice': ['рисовый', 'рисовое', 'на рисе', 'rice milk'],
    'condensed': ['сгущённый', 'сгущенный', 'сгущённое', 'сгущенное', 'сгущёнка'],
    'zmzh': ['с змж', 'змж', 'заменитель молочного жира', 'сырный продукт', 'молокосодержащий'],
    'uht': ['ультрапастеризованный', 'ультрапастеризованное', 'uht', 'ультрапаст'],
    'pasteurized': ['пастеризованный', 'пастеризованное'],
    'sterilized': ['стерилизованный', 'стерилизованное'],
    'bio': ['био', 'bio', 'органик', 'organic'],
    'diet': ['диетический', 'диетическое', 'низкокалорийный', 'lite', 'light'],
    'protein': ['протеин', 'protein', 'высокобелковый', 'с повышенным содержанием белка'],
}


# === QUALITY TIERS ===

QUALITY_TIER_KEYWORDS = {
    'premium': ['премиум', 'premium', 'экстра', 'extra', 'prime', 'люкс', 'lux', 'luxury', 
                'элитный', 'элитное', 'высший сорт', 'отборный', 'отборное', 'высшей категории',
                'деликатес', 'gourmet'],
    'standard': [],  # default
}


# === TRAP WORDS (слова-ловушки) ===
# Слова, которые выглядят как тип продукта, но являются названием/брендом

TRAP_WORDS = {
    'форель': {
        'in_context': ['груша', 'фрукт', 'яблоко'],  # Если есть эти слова - "форель" это название
        'is_type': ['рыба', 'филе', 'стейк', 'копчёная', 'солёная'],  # Если есть эти - это рыба
    },
    'белуга': {
        'in_context': ['машина', 'авто', 'автомобиль'],
        'is_type': ['рыба', 'икра', 'осетр'],
    },
}


# === BRAND EXTRACTION ===

KNOWN_BRANDS = [
    # Молочные бренды
    'простоквашино', 'домик в деревне', 'вкуснотеево', 'parmalat', 'danone', 'данон',
    'активиа', 'чудо', 'агуша', 'тёма', 'фрутоняня', 'валио', 'valio', 'president',
    'президент', 'экомилк', 'эконива', 'савушкин', 'савушкин продукт', 'молком',
    'белый город', 'село зелёное', 'village', 'alpro', 'nemoloko', 'не молоко',
    
    # Мясные бренды
    'мираторг', 'miratorg', 'черкизово', 'дымов', 'рублёвский', 'останкино',
    'велком', 'велком', 'клинский', 'ремит', 'микоян', 'окраина', 'атяшево',
    'индилайт', 'петелинка', 'петруха', 'приосколье',
    
    # Рыбные бренды
    'санта бремор', 'русское море', 'baltica', 'балтика', 'fish house',
    
    # Кондитерские бренды
    'fazer', 'фацер', 'красный октябрь', 'бабаевский', 'рот фронт', 'коркунов',
    'lindt', 'milka', 'alpen gold', 'snickers', 'mars', 'twix', 'bounty', 'kitkat',
    'nestle', 'нестле', 'ferrero', 'raffaello', 'oreo', 'tuc',
    
    # Напитки
    'coca-cola', 'pepsi', 'fanta', 'sprite', 'добрый', 'j7', 'rich', 'рич',
    'моя семья', 'фруктовый сад', 'любимый', 'santal', 'сантал',
    
    # Другие
    'maggi', 'магги', 'knorr', 'кнорр', 'heinz', 'хайнц', 'bonduelle', 'бондюэль',
    'barilla', 'макфа', 'makfa', 'шебекинские', 'увелка',
]


# === DATA CLASSES ===

@dataclass
class ProductSignature:
    """Сигнатура товара для matching."""
    # Обязательные
    product_class: Optional[str] = None
    
    # Брендинг
    brand: Optional[str] = None
    
    # Характеристики
    variant: Optional[str] = None  # вкус/начинка
    special_type: Optional[str] = None  # растительное/безлактозное/etc
    
    # Числовые
    fat_percent: Optional[float] = None
    net_qty: Optional[float] = None
    unit: Optional[str] = None  # кг/л/шт/г/мл
    
    # Качество
    quality_tier: str = 'standard'  # premium/standard
    
    # Форм-фактор
    form_factor: Optional[str] = None  # ready_meal/ingredient/semi_finished
    
    # Исходные данные
    raw_name: str = ""
    normalized_name: str = ""
    
    # Диагностика
    extraction_log: List[str] = field(default_factory=list)
    
    def to_dict(self) -> Dict:
        return {
            'product_class': self.product_class,
            'brand': self.brand,
            'variant': self.variant,
            'special_type': self.special_type,
            'fat_percent': self.fat_percent,
            'net_qty': self.net_qty,
            'unit': self.unit,
            'quality_tier': self.quality_tier,
            'form_factor': self.form_factor,
        }


@dataclass
class MatchResult:
    """Результат сопоставления кандидата."""
    candidate: Dict
    signature: ProductSignature
    passed_filters: bool
    filter_reasons: List[str]
    score: int
    score_breakdown: Dict[str, int]
    tier: Optional[str]  # A/B/C or None


# === EXTRACTION FUNCTIONS ===

def normalize_text(text: str) -> str:
    """Нормализация текста."""
    if not text:
        return ""
    text = text.lower().strip()
    text = re.sub(r'\s+', ' ', text)
    # Замена ё на е для унификации
    text = text.replace('ё', 'е')
    return text


def extract_brand(text: str) -> Optional[str]:
    """Извлечение бренда из названия."""
    text_lower = text.lower()
    
    # Сортируем бренды по длине (длинные первыми)
    sorted_brands = sorted(KNOWN_BRANDS, key=len, reverse=True)
    
    for brand in sorted_brands:
        if brand in text_lower:
            return brand
    
    # Попытка извлечь бренд из кавычек
    quoted = re.findall(r'["\']([^"\']+)["\']', text)
    for q in quoted:
        if len(q) >= 3 and len(q) <= 30:
            # Проверяем что это не описание
            if not any(kw in q.lower() for kw in ['охл', 'зам', 'с/м', 'вес', 'кг', 'шт']):
                return q
    
    return None


def extract_variant(text: str) -> Optional[str]:
    """Извлечение вкуса/начинки."""
    text_lower = normalize_text(text)
    
    # Сортируем по длине ключевых слов (длинные первыми)
    for variant, keywords in sorted(VARIANT_KEYWORDS.items(), key=lambda x: -max(len(k) for k in x[1])):
        for kw in keywords:
            if kw in text_lower:
                return variant
    
    return None


def extract_special_type(text: str) -> Optional[str]:
    """Извлечение специального типа."""
    text_lower = normalize_text(text)
    
    for special_type, keywords in SPECIAL_TYPE_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return special_type
    
    return None


def extract_fat_percent(text: str) -> Optional[float]:
    """Извлечение жирности."""
    # Паттерн: число + % или "жирность X"
    patterns = [
        r'(\d{1,2}(?:[.,]\d)?)\s*%',  # 3.2%
        r'жирн[а-я]*\s*(\d{1,2}(?:[.,]\d)?)',  # жирность 3.2
        r'м\.?д\.?ж\.?\s*(\d{1,2}(?:[.,]\d)?)',  # м.д.ж. 3.2
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text.lower())
        if match:
            try:
                return float(match.group(1).replace(',', '.'))
            except ValueError:
                continue
    
    return None


def extract_quantity(text: str) -> Tuple[Optional[float], Optional[str]]:
    """Извлечение количества и единицы измерения."""
    patterns = [
        (r'(\d+(?:[.,]\d+)?)\s*(кг|kg)', 'kg'),
        (r'(\d+(?:[.,]\d+)?)\s*(г|гр|g)', 'g'),
        (r'(\d+(?:[.,]\d+)?)\s*(л|l|литр)', 'l'),
        (r'(\d+(?:[.,]\d+)?)\s*(мл|ml)', 'ml'),
        (r'(\d+)\s*(шт|штук|pcs)', 'pcs'),
    ]
    
    text_lower = text.lower()
    
    for pattern, unit in patterns:
        match = re.search(pattern, text_lower)
        if match:
            try:
                qty = float(match.group(1).replace(',', '.'))
                return qty, unit
            except ValueError:
                continue
    
    return None, None


def extract_quality_tier(text: str) -> str:
    """Извлечение класса качества."""
    text_lower = normalize_text(text)
    
    for tier, keywords in QUALITY_TIER_KEYWORDS.items():
        for kw in keywords:
            if kw in text_lower:
                return tier
    
    return 'standard'


def detect_product_class(text: str) -> Optional[str]:
    """Определение класса товара."""
    text_lower = normalize_text(text)
    
    # Проверяем trap words сначала
    for trap_word, contexts in TRAP_WORDS.items():
        if trap_word in text_lower:
            # Проверяем контекст
            has_trap_context = any(ctx in text_lower for ctx in contexts.get('in_context', []))
            has_type_context = any(ctx in text_lower for ctx in contexts.get('is_type', []))
            
            if has_trap_context and not has_type_context:
                # Это trap word (название), пропускаем поиск по этому слову
                text_lower = text_lower.replace(trap_word, '')
    
    # Ищем product_class по таксономии
    # Сначала более длинные совпадения (более специфичные)
    matches = []
    for pclass, keywords in PRODUCT_CLASS_TAXONOMY.items():
        for kw in keywords:
            kw_lower = kw.lower()
            if kw_lower in text_lower:
                matches.append((pclass, len(kw), kw))
    
    if matches:
        # Выбираем наиболее специфичное совпадение
        matches.sort(key=lambda x: -x[1])
        return matches[0][0]
    
    # Fallback: используем lexicon product_kind
    lexicon = get_lexicon()
    product_kind = lexicon.get('product_kind', {})
    
    for kind, tokens in product_kind.items():
        for token in tokens:
            if token.lower() in text_lower:
                return kind
    
    return None


def extract_signature(name: str, brand_hint: Optional[str] = None) -> ProductSignature:
    """
    Извлечение полной сигнатуры товара.
    
    Args:
        name: Название товара
        brand_hint: Подсказка бренда (если известен)
    
    Returns:
        ProductSignature
    """
    sig = ProductSignature()
    sig.raw_name = name
    sig.normalized_name = normalize_text(name)
    
    # 1. Product class (самое важное)
    sig.product_class = detect_product_class(name)
    sig.extraction_log.append(f"product_class: {sig.product_class}")
    
    # 2. Brand
    sig.brand = brand_hint or extract_brand(name)
    sig.extraction_log.append(f"brand: {sig.brand}")
    
    # 3. Variant (вкус/начинка)
    sig.variant = extract_variant(name)
    sig.extraction_log.append(f"variant: {sig.variant}")
    
    # 4. Special type
    sig.special_type = extract_special_type(name)
    sig.extraction_log.append(f"special_type: {sig.special_type}")
    
    # 5. Fat percent
    sig.fat_percent = extract_fat_percent(name)
    sig.extraction_log.append(f"fat_percent: {sig.fat_percent}")
    
    # 6. Quantity
    sig.net_qty, sig.unit = extract_quantity(name)
    sig.extraction_log.append(f"net_qty: {sig.net_qty} {sig.unit}")
    
    # 7. Quality tier
    sig.quality_tier = extract_quality_tier(name)
    sig.extraction_log.append(f"quality_tier: {sig.quality_tier}")
    
    return sig


# === HARD FILTERS ===

def apply_hard_filters(source: ProductSignature, candidate: ProductSignature) -> Tuple[bool, List[str]]:
    """
    Применение жёстких фильтров.
    Кандидат исключается, если не проходит хотя бы один фильтр.
    
    Returns:
        (passed, reasons)
    """
    reasons = []
    
    # HF1: Product class must match
    if source.product_class and candidate.product_class:
        if source.product_class != candidate.product_class:
            reasons.append(f"HF1_CLASS_MISMATCH: {source.product_class} != {candidate.product_class}")
    elif source.product_class and not candidate.product_class:
        # Кандидат без класса - пропускаем мягко
        pass
    
    # HF2: Variant must match if specified in source
    if source.variant:
        if candidate.variant and source.variant != candidate.variant:
            reasons.append(f"HF2_VARIANT_MISMATCH: {source.variant} != {candidate.variant}")
    
    # HF3: Special type must match if specified in source
    if source.special_type:
        if candidate.special_type and source.special_type != candidate.special_type:
            reasons.append(f"HF3_SPECIAL_TYPE_MISMATCH: {source.special_type} != {candidate.special_type}")
        elif not candidate.special_type:
            # У source есть спецтип, у candidate нет - это может быть проблемой
            # Например: растительное молоко vs обычное молоко
            if source.special_type in ['plant_based', 'lactose_free', 'coconut', 'oat', 'soy', 'almond']:
                reasons.append(f"HF3_SPECIAL_TYPE_MISSING: source={source.special_type}, candidate=None")
    
    # HF4: Fat percent tolerance (±2%)
    if source.fat_percent is not None:
        if candidate.fat_percent is not None:
            diff = abs(source.fat_percent - candidate.fat_percent)
            if diff > 2.0:
                reasons.append(f"HF4_FAT_MISMATCH: {source.fat_percent}% vs {candidate.fat_percent}% (diff={diff}%)")
    
    passed = len(reasons) == 0
    return passed, reasons


# === RANKING ===

def calculate_score(source: ProductSignature, candidate: ProductSignature) -> Tuple[int, Dict[str, int]]:
    """
    Вычисление score для ранжирования.
    
    Приоритеты:
    1. Brand match (если у source есть бренд)
    2. Quantity/package match
    3. Fat percent proximity
    4. Special type match
    5. Quality tier match
    """
    score = 0
    breakdown = {}
    
    # 1. BRAND MATCH - высший приоритет (если бренд определён)
    if source.brand:
        if candidate.brand and source.brand.lower() == candidate.brand.lower():
            score += 500
            breakdown['brand_match'] = 500
        else:
            # Штраф за отсутствие бренда когда у source он есть
            breakdown['brand_match'] = 0
    
    # 2. CLASS MATCH
    if source.product_class == candidate.product_class:
        score += 200
        breakdown['class_match'] = 200
    
    # 3. VARIANT MATCH
    if source.variant:
        if source.variant == candidate.variant:
            score += 100
            breakdown['variant_match'] = 100
        elif not candidate.variant:
            # Neutral
            breakdown['variant_match'] = 0
    else:
        breakdown['variant_match'] = 50  # Bonus if no variant specified
    
    # 4. SPECIAL TYPE MATCH
    if source.special_type:
        if source.special_type == candidate.special_type:
            score += 80
            breakdown['special_type_match'] = 80
    else:
        if not candidate.special_type:
            score += 40
            breakdown['special_type_match'] = 40
    
    # 5. FAT PERCENT PROXIMITY
    if source.fat_percent is not None and candidate.fat_percent is not None:
        diff = abs(source.fat_percent - candidate.fat_percent)
        if diff == 0:
            score += 60
            breakdown['fat_match'] = 60
        elif diff <= 1:
            score += 40
            breakdown['fat_match'] = 40
        elif diff <= 2:
            score += 20
            breakdown['fat_match'] = 20
    
    # 6. QUANTITY PROXIMITY
    if source.net_qty and candidate.net_qty and source.unit == candidate.unit:
        ratio = min(source.net_qty, candidate.net_qty) / max(source.net_qty, candidate.net_qty)
        if ratio >= 0.9:
            score += 50
            breakdown['qty_match'] = 50
        elif ratio >= 0.7:
            score += 30
            breakdown['qty_match'] = 30
    
    # 7. QUALITY TIER MATCH
    if source.quality_tier == candidate.quality_tier:
        score += 40
        breakdown['quality_match'] = 40
    elif source.quality_tier == 'premium' and candidate.quality_tier != 'premium':
        # Штраф за несовпадение премиум
        score -= 30
        breakdown['quality_match'] = -30
    
    return score, breakdown


# === MAIN MATCHING FUNCTION ===

MIN_RELEVANCE_SCORE = 100  # Порог релевантности


def find_alternatives_v2(
    source_item: Dict,
    candidates: List[Dict],
    limit: int = 10,
    include_low_relevance: bool = False
) -> Dict:
    """
    Поиск альтернатив согласно ТЗ v1.0.
    
    Args:
        source_item: Исходный товар
        candidates: Список кандидатов
        limit: Максимум в выдаче
        include_low_relevance: Показывать низкорелевантные
    
    Returns:
        {
            'source': {...},
            'alternatives': [...],
            'diagnostics': {...}
        }
    """
    # Extract source signature
    source_name = source_item.get('name_raw', source_item.get('name', ''))
    source_brand = source_item.get('brand')
    source_sig = extract_signature(source_name, source_brand)
    
    results = []
    filtered_out = []
    
    for cand in candidates:
        cand_name = cand.get('name_raw', cand.get('name', ''))
        cand_brand = cand.get('brand')
        cand_sig = extract_signature(cand_name, cand_brand)
        
        # Apply hard filters
        passed, filter_reasons = apply_hard_filters(source_sig, cand_sig)
        
        if not passed:
            filtered_out.append({
                'name': cand_name[:50],
                'reasons': filter_reasons,
            })
            continue
        
        # Calculate score
        score, breakdown = calculate_score(source_sig, cand_sig)
        
        # Check minimum threshold
        if score < MIN_RELEVANCE_SCORE and not include_low_relevance:
            filtered_out.append({
                'name': cand_name[:50],
                'reasons': [f"BELOW_THRESHOLD: score={score} < {MIN_RELEVANCE_SCORE}"],
            })
            continue
        
        result = MatchResult(
            candidate=cand,
            signature=cand_sig,
            passed_filters=True,
            filter_reasons=[],
            score=score,
            score_breakdown=breakdown,
            tier='A' if score >= 500 else 'B' if score >= 200 else 'C'
        )
        results.append(result)
    
    # Sort by score DESC, then by price ASC
    results.sort(key=lambda x: (-x.score, x.candidate.get('price', 0)))
    
    # Apply quality tier boosting for premium sources
    if source_sig.quality_tier == 'premium':
        # Ensure top 2-3 are also premium if available
        premium_results = [r for r in results if r.signature.quality_tier == 'premium']
        other_results = [r for r in results if r.signature.quality_tier != 'premium']
        
        # Take up to 3 premium first, then others
        boosted = premium_results[:3] + other_results
        results = boosted[:limit * 2]  # Keep more for final filtering
    
    # Limit results
    results = results[:limit]
    
    # Build response
    alternatives = []
    for r in results:
        alternatives.append({
            **r.candidate,
            'match_score': r.score,
            'match_tier': r.tier,
            'match_breakdown': r.score_breakdown,
            'match_signature': r.signature.to_dict(),
        })
    
    return {
        'source': {
            **source_item,
            'match_signature': source_sig.to_dict(),
        },
        'alternatives': alternatives,
        'total': len(alternatives),
        'diagnostics': {
            'candidates_checked': len(candidates),
            'filtered_out_count': len(filtered_out),
            'filtered_out_sample': filtered_out[:5],
        },
        # Backward compatibility
        'tiers': {
            'A': [a for a in alternatives if a.get('match_tier') == 'A'],
            'B': [a for a in alternatives if a.get('match_tier') == 'B'],
            'C': [a for a in alternatives if a.get('match_tier') == 'C'],
        }
    }


def explain_match_v2(source_name: str, candidate_name: str) -> Dict:
    """
    Объяснение решения matching для отладки.
    """
    source_sig = extract_signature(source_name)
    cand_sig = extract_signature(candidate_name)
    
    passed, filter_reasons = apply_hard_filters(source_sig, cand_sig)
    score, breakdown = calculate_score(source_sig, cand_sig)
    
    return {
        'source': {
            'name': source_name,
            'signature': source_sig.to_dict(),
            'extraction_log': source_sig.extraction_log,
        },
        'candidate': {
            'name': candidate_name,
            'signature': cand_sig.to_dict(),
            'extraction_log': cand_sig.extraction_log,
        },
        'filters': {
            'passed': passed,
            'reasons': filter_reasons,
        },
        'score': {
            'total': score,
            'breakdown': breakdown,
        },
        'tier': 'A' if passed and score >= 500 else 'B' if passed and score >= 200 else 'C' if passed else None,
    }


# === INITIALIZATION ===

def init_matching_rules_v2():
    """Initialize matching rules v2."""
    try:
        load_lexicon()
        _build_product_class_index()
        logger.info("Matching rules v2 initialized")
        return True
    except Exception as e:
        logger.error(f"Failed to initialize matching rules v2: {e}")
        return False


# Pre-initialize on module import
try:
    load_lexicon()
except Exception as e:
    logger.warning(f"Could not pre-load lexicon: {e}")
