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
    'ФРАНЦИЯ': ['франц', 'france', 'french'],
    'ИТАЛИЯ': ['итал', 'italy', 'italian'],
    'ИСПАНИЯ': ['испан', 'spain', 'spanish'],
    'НИДЕРЛАНДЫ': ['нидерланд', 'голланд', 'netherlands', 'holland', 'dutch'],
    'БЕЛЬГИЯ': ['бельги', 'belgium', 'belgian'],
    'ПОЛЬША': ['польш', 'poland', 'polish'],
    'ЧЕХИЯ': ['чехи', 'czech'],
    'АВСТРИЯ': ['австри', 'austria', 'austrian'],
    'ШВЕЙЦАРИЯ': ['швейцар', 'switzerland', 'swiss'],
    'ГРЕЦИЯ': ['греци', 'greece', 'greek'],
    'ПОРТУГАЛИЯ': ['португал', 'portugal'],
    'ДАНИЯ': ['дания', 'дании', 'датск', 'denmark', 'danish'],
    'ШВЕЦИЯ': ['швеци', 'sweden', 'swedish'],
    'НОРВЕГИЯ': ['норвег', 'norway', 'norwegian'],
    'ФИНЛЯНДИЯ': ['финлянд', 'finland', 'finnish'],
    'ИРЛАНДИЯ': ['ирланд', 'ireland', 'irish'],
    'ВЕЛИКОБРИТАНИЯ': ['великобритан', 'британ', 'англи', 'uk', 'britain', 'british', 'england'],
    'ЛИТВА': ['литва', 'литов', 'lithuania'],
    'ЛАТВИЯ': ['латви', 'latvia'],
    'ЭСТОНИЯ': ['эстони', 'estonia'],
    'ВЕНГРИЯ': ['венгр', 'hungary'],
    'РУМЫНИЯ': ['румын', 'romania'],
    'БОЛГАРИЯ': ['болгар', 'bulgaria'],
    'СЕРБИЯ': ['серби', 'serbia'],
    'ХОРВАТИЯ': ['хорват', 'croatia'],
    'СЛОВЕНИЯ': ['словени', 'slovenia'],
    'СЛОВАКИЯ': ['словак', 'slovakia'],
    
    # Азия
    'КИТАЙ': ['китай', 'china', 'chinese', 'кнр'],
    'ЯПОНИЯ': ['япони', 'japan', 'japanese'],
    'ЮЖНАЯ КОРЕЯ': ['корея', 'korea', 'korean', 'южн.корея'],
    'ВЬЕТНАМ': ['вьетнам', 'vietnam', 'vietnamese'],
    'ТАИЛАНД': ['таиланд', 'тайланд', 'thailand', 'thai'],
    'ИНДИЯ': ['инди', 'india', 'indian'],
    'ИНДОНЕЗИЯ': ['индонез', 'indonesia'],
    'МАЛАЙЗИЯ': ['малайз', 'malaysia'],
    'ФИЛИППИНЫ': ['филиппин', 'philippines'],
    'СИНГАПУР': ['сингапур', 'singapore'],
    'ТУРЦИЯ': ['турци', 'турецк', 'turkey', 'turkish'],
    'ИРАН': ['иран', 'iran', 'persian'],
    'ИЗРАИЛЬ': ['израил', 'israel'],
    'ОАЭ': ['оаэ', 'эмират', 'uae', 'emirates', 'дубай'],
    'САУДОВСКАЯ АРАВИЯ': ['саудовск', 'saudi'],
    'ПАКИСТАН': ['пакистан', 'pakistan'],
    'ШРИ-ЛАНКА': ['шри-ланка', 'цейлон', 'sri lanka', 'ceylon'],
    
    # Америка
    'США': ['сша', 'usa', 'америк', 'american', 'u.s.'],
    'КАНАДА': ['канад', 'canada', 'canadian'],
    'МЕКСИКА': ['мексик', 'mexico', 'mexican'],
    'БРАЗИЛИЯ': ['бразил', 'brazil', 'brazilian'],
    'АРГЕНТИНА': ['аргентин', 'argentina', 'argentinian'],
    'ЧИЛИ': ['чили', 'chile', 'chilean'],
    'ПЕРУ': ['перу', 'peru', 'peruvian'],
    'КОЛУМБИЯ': ['колумби', 'colombia'],
    'ЭКВАДОР': ['эквадор', 'ecuador'],
    'УРУГВАЙ': ['уругвай', 'uruguay'],
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
    
    # Extract country
    for country, patterns in COUNTRY_PATTERNS.items():
        for pattern in patterns:
            # Use word boundary matching where possible
            if re.search(rf'\b{re.escape(pattern)}\b', text_lower) or pattern in text_lower:
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
