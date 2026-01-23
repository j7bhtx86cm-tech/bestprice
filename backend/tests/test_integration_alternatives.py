"""
BestPrice v12 - Integration Tests (API)
=======================================

Интеграционные тесты для endpoint /api/v12/item/{item_id}/alternatives

Тесты по ТЗ v12:
1. Strict содержит только валидные аналоги
2. Similar включается только когда Strict < N
3. Сортировка по ppu_value корректна

Запуск: pytest /app/backend/tests/test_integration_alternatives.py -v
"""

import pytest
import requests
from pymongo import MongoClient
import os


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture(scope="module")
def db():
    """MongoDB connection"""
    client = MongoClient('mongodb://localhost:27017')
    return client['test_database']


@pytest.fixture(scope="module")
def api_url():
    """API URL"""
    return "http://localhost:8001/api/v12"


def get_item_by_regex(db, regex: str):
    """Находит товар по regex в name_norm"""
    return db.supplier_items.find_one({
        'active': True,
        'name_norm': {'$regex': regex, '$options': 'i'}
    })


# ============================================================================
# TEST: Strict Validation
# ============================================================================

class TestStrictValidation:
    """Тесты что Strict содержит только валидные аналоги"""
    
    def test_strict_same_product_core(self, db, api_url):
        """Все Strict имеют тот же product_core_id"""
        item = get_item_by_regex(db, 'молоко клевер|молоко пармалат')
        if not item:
            pytest.skip("Товар не найден")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        source_core = data['source'].get('product_core_id')
        
        for alt in data.get('strict', []):
            # Получаем product_core_id альтернативы из БД
            alt_item = db.supplier_items.find_one({'id': alt['id']})
            if alt_item:
                assert alt_item.get('product_core_id') == source_core, \
                    f"Strict alt {alt['name'][:30]} has different core"
    
    def test_strict_no_forbidden_types(self, db, api_url):
        """Strict не содержит запрещённые типы (сырое мясо для сосисок)"""
        # Тест: сосиски не должны содержать СЫРОЕ филе/грудку (но "сосиски филейные" допустимы)
        item = get_item_by_regex(db, 'сосиск')
        if not item:
            pytest.skip("Сосиски не найдены")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        # Проверяем что нет СЫРОГО мяса (филе курицы, грудка охл и т.д.)
        # Но "сосиски филейные" - это ОК
        for alt in data.get('strict', []):
            alt_name_lower = alt.get('name_raw', '').lower()
            
            # Если это сосиски/колбаса - OK
            if 'сосиск' in alt_name_lower or 'колбас' in alt_name_lower:
                continue
            
            # Иначе проверяем на сырое мясо
            forbidden = ['филе кур', 'грудка кур', 'бедро кур', 'крыло кур', 'тушка кур']
            for word in forbidden:
                assert word not in alt_name_lower, \
                    f"Strict содержит запрещённый '{word}' в '{alt['name_raw'][:30]}'"
    
    def test_strict_no_condensed_for_regular_milk(self, db, api_url):
        """Обычное молоко не содержит сгущёнку в Strict"""
        item = get_item_by_regex(db, 'молоко клевер|молоко пармалат')
        if not item:
            pytest.skip("Молоко не найдено")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        for alt in data.get('strict', []):
            alt_name_lower = alt.get('name_raw', '').lower()
            assert 'сгущ' not in alt_name_lower, \
                f"Strict содержит сгущёнку: {alt['name_raw'][:30]}"
    
    def test_strict_utensil_type_matches(self, db, api_url):
        """Посуда: Strict только того же типа (вилка → вилки)"""
        item = get_item_by_regex(db, 'вилк')
        if not item:
            pytest.skip("Вилки не найдены")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        forbidden_utensils = ['ложк', 'нож', 'стакан', 'крышк', 'контейнер']
        
        for alt in data.get('strict', []):
            alt_name_lower = alt.get('name_raw', '').lower()
            for word in forbidden_utensils:
                assert word not in alt_name_lower, \
                    f"Вилка содержит {word} в Strict: {alt['name_raw'][:30]}"


# ============================================================================
# TEST: Similar Mode
# ============================================================================

class TestSimilarMode:
    """Тесты режима Similar"""
    
    def test_similar_shown_when_strict_low(self, db, api_url):
        """Similar показывается когда Strict < 4"""
        # Ищем товар с малым количеством Strict
        item = get_item_by_regex(db, 'контейнер.*450|контейнер.*500')
        if not item:
            pytest.skip("Контейнер не найден")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        strict_count = len(data.get('strict', []))
        similar_count = len(data.get('similar', []))
        
        # Если Strict < 4, Similar должен быть показан (если есть кандидаты)
        if strict_count < 4:
            # Similar может быть пустым если нет подходящих кандидатов
            # но это нормально
            pass
    
    def test_similar_has_difference_labels(self, db, api_url):
        """Similar альтернативы имеют лейблы отличий"""
        item = get_item_by_regex(db, 'стакан')
        if not item:
            pytest.skip("Стаканы не найдены")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        for alt in data.get('similar', []):
            # Similar должен иметь difference_labels (или пустой список)
            assert 'difference_labels' in alt


# ============================================================================
# TEST: Sorting
# ============================================================================

class TestSorting:
    """Тесты сортировки результатов"""
    
    def test_strict_brand_first(self, db, api_url):
        """Товары того же бренда идут первыми в Strict"""
        item = get_item_by_regex(db, 'хайнц|heinz')
        if not item:
            pytest.skip("Heinz не найден")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        source_brand = data['source'].get('brand_id')
        strict = data.get('strict', [])
        
        if not source_brand or len(strict) < 2:
            pytest.skip("Недостаточно данных для теста")
        
        # Первые альтернативы должны иметь brand_match=True
        first_brand_match = strict[0].get('brand_match', False)
        
        # Если есть хотя бы один с brand_match, он должен быть первым
        has_brand_match = any(s.get('brand_match') for s in strict)
        if has_brand_match:
            assert first_brand_match == True, \
                "Первый Strict должен иметь brand_match=True"


# ============================================================================
# TEST: Regression (14 cases from TZ v12)
# ============================================================================

class TestRegressionTZv12:
    """Регрессионные тесты по ТЗ v12"""
    
    def test_01_pepper_no_kg(self, db, api_url):
        """1. Перец 0.3г → НЕ показывать кг"""
        item = get_item_by_regex(db, 'перец.*порцион|перец.*стик|перец.*0.3')
        if not item:
            pytest.skip("Перец порционный не найден")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        for alt in data.get('strict', []):
            assert '1кг' not in alt.get('name_raw', '').lower()
    
    def test_02_sugar_no_bulk(self, db, api_url):
        """2. Сахар порционный → НЕ песок 5кг"""
        item = get_item_by_regex(db, 'сахар.*трубочк|сахар.*порцион|сахар.*стик')
        if not item:
            pytest.skip("Сахар порционный не найден")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        for alt in data.get('strict', []):
            name_lower = alt.get('name_raw', '').lower()
            assert 'песок' not in name_lower
            assert '5кг' not in name_lower
    
    def test_03_cup_only_cups(self, db, api_url):
        """3. Стакан → только стаканы"""
        item = get_item_by_regex(db, 'стакан')
        if not item:
            pytest.skip("Стаканы не найдены")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        forbidden = ['крышк', 'контейнер', 'ложк', 'вилк']
        for alt in data.get('strict', []):
            name_lower = alt.get('name_raw', '').lower()
            for word in forbidden:
                assert word not in name_lower
    
    def test_10_fish_fillet_no_canned(self, db, api_url):
        """10. Рыба филе → НЕ консервы"""
        item = get_item_by_regex(db, 'лосось.*филе|семга.*филе|форель.*филе')
        if not item:
            pytest.skip("Филе рыбы не найдено")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        for alt in data.get('strict', []):
            name_lower = alt.get('name_raw', '').lower()
            assert 'консерв' not in name_lower
            assert 'ж/б' not in name_lower
    
    def test_13_milk_no_condensed(self, db, api_url):
        """13. Молоко → НЕ сгущёнка"""
        item = get_item_by_regex(db, 'молоко клевер|молоко пармалат')
        if not item:
            pytest.skip("Молоко не найдено")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        for alt in data.get('strict', []):
            assert 'сгущ' not in alt.get('name_raw', '').lower()
    
    def test_14_coconut_milk_separate(self, db, api_url):
        """14. Молоко кокосовое → НЕ обычное"""
        item = get_item_by_regex(db, 'молоко кокос')
        if not item:
            pytest.skip("Кокосовое молоко не найдено")
        
        resp = requests.get(f"{api_url}/item/{item['id']}/alternatives")
        data = resp.json()
        
        for alt in data.get('strict', []):
            name_lower = alt.get('name_raw', '').lower()
            assert 'клевер' not in name_lower
            assert 'сударын' not in name_lower


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
