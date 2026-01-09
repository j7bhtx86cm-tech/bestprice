"""
Geography Extractor - Извлечение страны, региона и города из названий товаров

Примеры:
- "Говядина БЕЛАРУСЬ охл." → origin_country: "БЕЛАРУСЬ"
- "СОУС Барбекю 1 кг. Россия Got2Eat" → origin_country: "РОССИЯ"
- "БУЛЬОН рыбный Китай 1 кг" → origin_country: "КИТАЙ"
"""
import re
import logging
from typing import Dict, Optional, Tuple

logger = logging.getLogger(__name__)

# Known countries with variations
COUNTRY_PATTERNS = {
    # Россия и СНГ
    'РОССИЯ': ['россия', 'рф', 'russian', 'russia', 'российск', 'отечествен'],
    'БЕЛАРУСЬ': ['беларус', 'белорус', 'belarus', 'белоруссия', 'бел.'],
    'КАЗАХСТАН': ['казахстан', 'kazakhstan', 'казах'],
    'УКРАИНА': ['украин', 'ukraine', 'укр.'],
    'УЗБЕКИСТАН': ['узбекистан', 'uzbekistan', 'узбек'],
    'АРМЕНИЯ': ['армения', 'armenia', 'армян'],
    'ГРУЗИЯ': ['грузия', 'georgia', 'грузин'],
    'АЗЕРБАЙДЖАН': ['азербайджан', 'azerbaijan', 'азерб'],
    'МОЛДОВА': ['молдова', 'молдавия', 'moldova', 'молдав'],
    'КИРГИЗИЯ': ['киргиз', 'кыргыз', 'kyrgyzstan'],
    'ТАДЖИКИСТАН': ['таджик', 'tajikistan'],
    'ТУРКМЕНИСТАН': ['туркмен', 'turkmenistan'],
    
    # Европа
    'ГЕРМАНИЯ': ['герман', 'germany', 'немецк', 'deutsche'],
    'ФРАНЦИЯ': ['франц', 'france', 'french', 'французск'],
    'ИТАЛИЯ': ['итал', 'italy', 'italian', 'итальянск'],
    'ИСПАНИЯ': ['испан', 'spain', 'spanish', 'испанск'],
    'НИДЕРЛАНДЫ': ['нидерланд', 'голланд', 'netherlands', 'holland', 'dutch', 'голландск'],
    'БЕЛЬГИЯ': ['бельги', 'belgium', 'belgian', 'бельгийск'],
    'ПОЛЬША': ['польш', 'poland', 'polish', 'польск'],
    'ЧЕХИЯ': ['чехи', 'czech', 'чешск'],
    'АВСТРИЯ': ['австри', 'austria', 'austrian', 'австрийск', 'штири'],  # Штирия - регион Австрии
    'ШВЕЙЦАРИЯ': ['швейцар', 'switzerland', 'swiss'],
    'ГРЕЦИЯ': ['греци', 'greece', 'greek', 'греческ'],
    'ПОРТУГАЛИЯ': ['португал', 'portugal', 'португальск'],
    'ДАНИЯ': ['дания', 'дании', 'датск', 'denmark', 'danish'],
    'ШВЕЦИЯ': ['швеци', 'sweden', 'swedish', 'шведск'],
    'НОРВЕГИЯ': ['норвег', 'norway', 'norwegian', 'норвежск'],
    'ФИНЛЯНДИЯ': ['финлянд', 'finland', 'finnish', 'финск'],
    'ИРЛАНДИЯ': ['ирланд', 'ireland', 'irish', 'ирландск'],
    'ВЕЛИКОБРИТАНИЯ': ['великобритан', 'британ', 'англи', 'uk', 'britain', 'british', 'england', 'английск'],
    'ЛИТВА': ['литва', 'литов', 'lithuania', 'литовск'],
    'ЛАТВИЯ': ['латви', 'latvia', 'латвийск'],
    'ЭСТОНИЯ': ['эстони', 'estonia', 'эстонск'],
    'ВЕНГРИЯ': ['венгр', 'hungary', 'венгерск'],
    'РУМЫНИЯ': ['румын', 'romania', 'румынск'],
    'БОЛГАРИЯ': ['болгар', 'bulgaria', 'болгарск'],
    'СЕРБИЯ': ['серби', 'serbia', 'сербск'],
    'ХОРВАТИЯ': ['хорват', 'croatia', 'хорватск'],
    'СЛОВЕНИЯ': ['словени', 'slovenia', 'словенск'],
    'СЛОВАКИЯ': ['словак', 'slovakia', 'словацк'],
    
    # Азия
    'КИТАЙ': ['китай', 'china', 'chinese', 'кнр', 'китайск'],
    'ЯПОНИЯ': ['япони', 'japan', 'japanese', 'японск'],
    'ЮЖНАЯ КОРЕЯ': ['корея', 'korea', 'korean', 'южн.корея', 'корейск'],
    'ВЬЕТНАМ': ['вьетнам', 'vietnam', 'vietnamese', 'вьетнамск'],
    'ТАИЛАНД': ['таиланд', 'тайланд', 'thailand', 'thai', 'тайск'],
    'ИНДИЯ': ['инди', 'india', 'indian', 'индийск'],
    'ИНДОНЕЗИЯ': ['индонез', 'indonesia', 'индонезийск'],
    'МАЛАЙЗИЯ': ['малайз', 'malaysia', 'малайзийск'],
    'ФИЛИППИНЫ': ['филиппин', 'philippines'],
    'СИНГАПУР': ['сингапур', 'singapore'],
    'ТУРЦИЯ': ['турци', 'турецк', 'turkey', 'turkish'],
    'ИРАН': ['иран', 'iran', 'persian', 'иранск', 'персидск'],
    'ИЗРАИЛЬ': ['израил', 'israel', 'израильск'],
    'ОАЭ': ['оаэ', 'эмират', 'uae', 'emirates', 'дубай'],
    'САУДОВСКАЯ АРАВИЯ': ['саудовск', 'saudi'],
    'ПАКИСТАН': ['пакистан', 'pakistan', 'пакистанск'],
    'ШРИ-ЛАНКА': ['шри-ланка', 'цейлон', 'sri lanka', 'ceylon', 'цейлонск'],
    
    # Америка
    'США': ['сша', 'usa', 'америк', 'american', 'u.s.'],
    'КАНАДА': ['канад', 'canada', 'canadian'],
    'МЕКСИКА': ['мексик', 'mexico', 'mexican'],
    'БРАЗИЛИЯ': ['бразил', 'brazil', 'brazilian', 'бразильск'],
    'АРГЕНТИНА': ['аргентин', 'argentina', 'argentinian'],
    'ЧИЛИ': ['чили', 'chile', 'chilean', 'чилийск'],
    'ПЕРУ': ['перу', 'peru', 'peruvian', 'перуанск'],
    'КОЛУМБИЯ': ['колумби', 'colombia', 'колумбийск'],
    'ЭКВАДОР': ['эквадор', 'ecuador', 'эквадорск'],
    'УРУГВАЙ': ['уругвай', 'uruguay', 'уругвайск'],
    'ПАРАГВАЙ': ['парагвай', 'paraguay'],
    
    # Океания
    'АВСТРАЛИЯ': ['австрали', 'australia', 'australian'],
    'НОВАЯ ЗЕЛАНДИЯ': ['новая зеланд', 'new zealand', 'зеланд'],
    
    # Африка
    'ЕГИПЕТ': ['египет', 'egypt', 'egyptian'],
    'МАРОККО': ['марокко', 'morocco'],
    'ТУНИС': ['тунис', 'tunisia'],
    'ЮАР': ['юар', 'south africa'],
    'КЕНИЯ': ['кения', 'kenya'],
    'ЭФИОПИЯ': ['эфиопи', 'ethiopia'],
}

# Russian regions (for origin_region)
REGION_PATTERNS = {
    'МОСКОВСКАЯ ОБЛ.': ['московск', 'подмосков', 'москов.обл'],
    'ЛЕНИНГРАДСКАЯ ОБЛ.': ['ленинградск', 'лен.обл', 'ленобл'],
    'КРАСНОДАРСКИЙ КРАЙ': ['краснодарск', 'кубан', 'кубань'],
    'РОСТОВСКАЯ ОБЛ.': ['ростовск', 'донск'],
    'КАЛИНИНГРАДСКАЯ ОБЛ.': ['калининградск'],
    'ВОРОНЕЖСКАЯ ОБЛ.': ['воронежск'],
    'БЕЛГОРОДСКАЯ ОБЛ.': ['белгородск'],
    'АЛТАЙСКИЙ КРАЙ': ['алтайск', 'алтай'],
    'ПРИМОРСКИЙ КРАЙ': ['приморск', 'дальневосточн'],
    'КАМЧАТКА': ['камчатк', 'камчатск'],
    'САХАЛИН': ['сахалин'],
    'МУРМАНСКАЯ ОБЛ.': ['мурманск'],
    'КАРЕЛИЯ': ['карели', 'карельск'],
    'КРЫМ': ['крым', 'крымск'],
    'ДАГЕСТАН': ['дагестан'],
    'СТАВРОПОЛЬСКИЙ КРАЙ': ['ставрополь'],
    'АСТРАХАНСКАЯ ОБЛ.': ['астраханск'],
    'ВОЛГОГРАДСКАЯ ОБЛ.': ['волгоградск'],
    'САМАРСКАЯ ОБЛ.': ['самарск'],
    'ТАТАРСТАН': ['татарстан', 'татарск'],
    'БАШКОРТОСТАН': ['башкортостан', 'башкир'],
    'СВЕРДЛОВСКАЯ ОБЛ.': ['свердловск', 'урал', 'уральск'],
    'ЧЕЛЯБИНСКАЯ ОБЛ.': ['челябинск'],
    'НОВОСИБИРСКАЯ ОБЛ.': ['новосибирск'],
    'ОМСКАЯ ОБЛ.': ['омск'],
    'ИРКУТСКАЯ ОБЛ.': ['иркутск', 'байкал'],
}

# Russian cities (for origin_city)
CITY_PATTERNS = {
    'МОСКВА': ['москва', 'москов', 'moscow'],
    'САНКТ-ПЕТЕРБУРГ': ['санкт-петербург', 'спб', 'петербург', 'питер', 'ленинград'],
    'НОВОСИБИРСК': ['новосибирск'],
    'ЕКАТЕРИНБУРГ': ['екатеринбург'],
    'КАЗАНЬ': ['казань', 'казанск'],
    'НИЖНИЙ НОВГОРОД': ['нижний новгород', 'нижегород'],
    'ЧЕЛЯБИНСК': ['челябинск'],
    'САМАРА': ['самара', 'самарск'],
    'РОСТОВ-НА-ДОНУ': ['ростов-на-дону', 'ростов'],
    'УФА': ['уфа'],
    'КРАСНОЯРСК': ['красноярск'],
    'ВОРОНЕЖ': ['воронеж'],
    'ПЕРМЬ': ['пермь', 'пермск'],
    'ВОЛГОГРАД': ['волгоград'],
    'КРАСНОДАР': ['краснодар'],
    'СОЧИ': ['сочи', 'сочинск'],
    'ВЛАДИВОСТОК': ['владивосток'],
    'МУРМАНСК': ['мурманск'],
    'КАЛИНИНГРАД': ['калининград'],
    'АРХАНГЕЛЬСК': ['архангельск'],
    'ПЕТРОПАВЛОВСК-КАМЧАТСКИЙ': ['петропавловск-камчатск', 'петропавловск'],
}

# Patterns that should NOT be matched as countries (false positives)
# These are common product words that match country patterns
FALSE_POSITIVE_EXCLUSIONS = {
    # "чили" в соусах - это перец, не страна Чили
    'чили': ['соус', 'перец', 'перца', 'острый', 'сладкий', 'chili', 'chilli', 'sweet chili', 'курицы'],
    # "голланд" может быть в названии соуса (Голландский соус)
    'голланд': ['соус', 'голландез', 'hollandaise'],
    'нидерланд': ['соус', 'голландез', 'hollandaise'],
    'holland': ['соус', 'голландез', 'hollandaise', 'sauce'],
    'dutch': ['соус', 'голландез', 'hollandaise'],
    # "америк" может быть в названии стиля блюда
    'америк': ['стиль', 'style'],
    # "мексик" может быть в названии стиля
    'мексик': ['стиль', 'style', 'микс'],
    # "грец" может быть грецкий орех
    'грец': ['орех', 'орешки'],
    # "индийск" может быть индийский рис/специи как стиль
    'инди': ['стиль', 'style', 'карри'],
}


def is_false_positive(text_lower: str, pattern: str) -> bool:
    """Check if the matched pattern is likely a false positive based on context."""
    exclusions = FALSE_POSITIVE_EXCLUSIONS.get(pattern, [])
    for excl in exclusions:
        if excl in text_lower:
            return True
    return False


def extract_geography_from_text(text: str) -> Dict[str, Optional[str]]:
    """
    Extract country, region, and city from product name.
    
    Returns:
        {
            'origin_country': 'РОССИЯ' or None,
            'origin_region': 'КРАСНОДАРСКИЙ КРАЙ' or None,
            'origin_city': 'МОСКВА' or None,
            'geo_confidence': 0.0-1.0
        }
    """
    if not text:
        return {'origin_country': None, 'origin_region': None, 'origin_city': None, 'geo_confidence': 0.0}
    
    text_lower = text.lower()
    result = {
        'origin_country': None,
        'origin_region': None,
        'origin_city': None,
        'geo_confidence': 0.0
    }
    
    # Extract country (with false positive check)
    for country, patterns in COUNTRY_PATTERNS.items():
        for pattern in patterns:
            # Use word boundary matching where possible
            if re.search(rf'\b{re.escape(pattern)}\b', text_lower) or pattern in text_lower:
                # Check for false positives (e.g., "чили" in "соус чили")
                if is_false_positive(text_lower, pattern):
                    continue
                result['origin_country'] = country
                result['geo_confidence'] = 0.9
                break
        if result['origin_country']:
            break
    
    # Extract region (only if country is Russia or not set)
    if result['origin_country'] in ['РОССИЯ', None]:
        for region, patterns in REGION_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    result['origin_region'] = region
                    if not result['origin_country']:
                        result['origin_country'] = 'РОССИЯ'  # Assume Russia if region found
                    result['geo_confidence'] = max(result['geo_confidence'], 0.85)
                    break
            if result['origin_region']:
                break
    
    # Extract city (only if country is Russia or not set)
    if result['origin_country'] in ['РОССИЯ', None]:
        for city, patterns in CITY_PATTERNS.items():
            for pattern in patterns:
                if pattern in text_lower:
                    result['origin_city'] = city
                    if not result['origin_country']:
                        result['origin_country'] = 'РОССИЯ'  # Assume Russia if city found
                    result['geo_confidence'] = max(result['geo_confidence'], 0.8)
                    break
            if result['origin_city']:
                break
    
    return result


def get_geo_filter_value(favorite: dict) -> Tuple[Optional[str], str, str]:
    """
    Get the geographic filter value based on cascade priority: City > Region > Country.
    
    Returns:
        (filter_value, filter_field, filter_type)
        e.g., ('МОСКВА', 'origin_city', 'city') or ('РОССИЯ', 'origin_country', 'country')
    """
    # Priority: City > Region > Country
    origin_city = favorite.get('origin_city')
    if origin_city and str(origin_city).strip():
        return origin_city.strip().upper(), 'origin_city', 'city'
    
    origin_region = favorite.get('origin_region')
    if origin_region and str(origin_region).strip():
        return origin_region.strip().upper(), 'origin_region', 'region'
    
    origin_country = favorite.get('origin_country')
    if origin_country and str(origin_country).strip():
        return origin_country.strip().upper(), 'origin_country', 'country'
    
    return None, '', ''


if __name__ == "__main__":
    # Test extraction
    test_names = [
        "Говядина БЕЛАРУСЬ охл. 1 кг",
        "СОУС Барбекю 1 кг. Россия Got2Eat",
        "БУЛЬОН рыбный Китай 1 кг",
        "ЛАПША рисовая Вьетнам 500 гр",
        "Сыр Московский 45%",
        "Краб Камчатка свежий",
        "Рыба Мурманск охл.",
        "Креветки Аргентина 16/20",
        "Говядина Алтайский край",
        "Молоко Краснодарский край 3.2%",
    ]
    
    print("=== Geography Extraction Test ===\n")
    for name in test_names:
        result = extract_geography_from_text(name)
        print(f"'{name[:50]}'")
        print(f"  → country={result['origin_country']}, region={result['origin_region']}, city={result['origin_city']}, conf={result['geo_confidence']:.2f}")
        print()
