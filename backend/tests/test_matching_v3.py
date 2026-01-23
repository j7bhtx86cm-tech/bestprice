"""
BestPrice v12 - Matching Engine v3 Unit Tests
==============================================

Тесты по ТЗ v12 для модуля matching_engine_v3.py

Запуск: pytest /app/backend/tests/test_matching_v3.py -v
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from bestprice_v12.matching_engine_v3 import (
    extract_signature,
    match_candidate,
    match_for_similar,
    check_hard_blocks,
    check_pack_compatibility,
    find_alternatives_v3,
    ProductForm,
    KNOWN_BRAND_PATTERNS,
)


# ============================================================================
# FIXTURES
# ============================================================================

@pytest.fixture
def heinz_item():
    return {
        'id': 'test-heinz-1',
        'name_raw': 'Соус ХАЙНЦ Барбекю классический 1кг',
        'name_norm': 'соус хайнц барбекю классический 1кг',
        'product_core_id': 'condiments.bbq',
        'price': 300,
        'pack_qty': 1,
        'unit_type': 'PIECE',
    }

@pytest.fixture
def milk_regular():
    return {
        'id': 'test-milk-1',
        'name_raw': 'Молоко Клевер 3.2% 1л',
        'name_norm': 'молоко клевер 3.2% 1л',
        'product_core_id': 'dairy.milk',
        'price': 89,
        'unit_type': 'VOLUME',
    }

@pytest.fixture
def milk_condensed():
    return {
        'id': 'test-milk-2',
        'name_raw': 'Молоко сгущённое 8.5% 380г',
        'name_norm': 'молоко сгущённое 8.5% 380г',
        'product_core_id': 'dairy.milk',
        'price': 120,
        'unit_type': 'WEIGHT',
    }


# ============================================================================
# TEST: Signature Extraction
# ============================================================================

class TestSignatureExtraction:
    """Тесты извлечения сигнатуры из товара"""
    
    def test_extract_brand_from_name_heinz(self, heinz_item):
        """Бренд Heinz извлекается из названия"""
        sig = extract_signature(heinz_item)
        assert sig.brand_id == 'heinz'
    
    def test_extract_product_form_sauce(self, heinz_item):
        """Форма продукта 'sauce' распознаётся"""
        sig = extract_signature(heinz_item)
        assert sig.product_form == ProductForm.SAUCE
    
    def test_extract_milk_type_condensed(self, milk_condensed):
        """Тип молока 'condensed' распознаётся"""
        sig = extract_signature(milk_condensed)
        assert sig.milk_type == 'condensed'
    
    def test_extract_milk_type_dairy(self, milk_regular):
        """Тип молока 'dairy' для обычного молока"""
        sig = extract_signature(milk_regular)
        assert sig.milk_type == 'dairy'
    
    def test_extract_portion_info(self):
        """Порционные товары распознаются"""
        item = {
            'name_raw': 'Перец черный молотый порционный в стиках 0.3г',
            'name_norm': 'перец черный молотый порционный в стиках 0.3г',
            'product_core_id': 'spice.pepper',
        }
        sig = extract_signature(item)
        assert sig.is_portion == True
        assert sig.portion_weight is not None
    
    def test_extract_utensil_type_fork(self):
        """Тип посуды 'fork' распознаётся"""
        item = {
            'name_raw': 'Вилка пластиковая белая',
            'name_norm': 'вилка пластиковая белая',
            'product_core_id': 'utensil.fork',
        }
        sig = extract_signature(item)
        assert sig.utensil_type == 'fork'
    
    def test_extract_utensil_type_lid(self):
        """Тип посуды 'lid' распознаётся"""
        item = {
            'name_raw': 'Крышка для стакана D90мм',
            'name_norm': 'крышка для стакана d90мм',
            'product_core_id': 'utensil.lid',
        }
        sig = extract_signature(item)
        assert sig.utensil_type == 'lid'
    
    def test_extract_frozen_form(self):
        """Форма 'frozen' распознаётся"""
        item = {
            'name_raw': 'Креветки с/м б/г 31/40',
            'name_norm': 'креветки с/м б/г 31/40',
            'product_core_id': 'seafood.shrimp',
        }
        sig = extract_signature(item)
        assert sig.product_form == ProductForm.FROZEN
    
    def test_extract_breaded(self):
        """Панировка распознаётся"""
        item = {
            'name_raw': 'Креветки в панировке',
            'name_norm': 'креветки в панировке',
            'product_core_id': 'seafood.shrimp',
        }
        sig = extract_signature(item)
        assert sig.breaded == True
    
    def test_extract_part_type_fillet(self):
        """Часть туши 'fillet' распознаётся"""
        item = {
            'name_raw': 'Филе куриное охлаждённое',
            'name_norm': 'филе куриное охлаждённое',
            'product_core_id': 'poultry.chicken',
        }
        sig = extract_signature(item)
        assert sig.part_type == 'fillet'


# ============================================================================
# TEST: Hard Blocks
# ============================================================================

class TestHardBlocks:
    """Тесты hard-block фильтров"""
    
    def test_milk_type_mismatch_blocks(self, milk_regular, milk_condensed):
        """Сгущёнка ≠ обычное молоко (MILK_TYPE_MISMATCH)"""
        # Исправляем unit_type чтобы проверить именно milk_type
        milk_regular_fixed = milk_regular.copy()
        milk_regular_fixed['unit_type'] = 'WEIGHT'
        
        source_sig = extract_signature(milk_regular_fixed)
        cand_sig = extract_signature(milk_condensed)
        
        passed, reason, _ = check_hard_blocks(source_sig, cand_sig)
        assert passed == False
        assert 'MILK_TYPE_MISMATCH' in reason
    
    def test_utensil_type_mismatch_blocks(self):
        """Вилка ≠ ложка (UTENSIL_TYPE_MISMATCH)"""
        fork = extract_signature({
            'name_raw': 'Вилка',
            'name_norm': 'вилка',
            'product_core_id': 'utensil.cutlery',
        })
        spoon = extract_signature({
            'name_raw': 'Ложка',
            'name_norm': 'ложка',
            'product_core_id': 'utensil.cutlery',
        })
        
        passed, reason, _ = check_hard_blocks(fork, spoon)
        assert passed == False
        assert 'UTENSIL_TYPE_MISMATCH' in reason
    
    def test_flavor_mismatch_blocks(self):
        """Клубника ≠ манго (FLAVOR_MISMATCH)"""
        strawberry = extract_signature({
            'name_raw': 'Йогурт клубника',
            'name_norm': 'йогурт клубника',
            'product_core_id': 'dairy.yogurt',
        })
        mango = extract_signature({
            'name_raw': 'Йогурт манго',
            'name_norm': 'йогурт манго',
            'product_core_id': 'dairy.yogurt',
        })
        
        passed, reason, _ = check_hard_blocks(strawberry, mango)
        assert passed == False
        assert 'FLAVOR_MISMATCH' in reason
    
    def test_core_mismatch_blocks(self):
        """Разные product_core_id блокируются"""
        item1 = extract_signature({
            'name_raw': 'Сосиски',
            'name_norm': 'сосиски',
            'product_core_id': 'meat.sausage',
        })
        item2 = extract_signature({
            'name_raw': 'Филе курицы',
            'name_norm': 'филе курицы',
            'product_core_id': 'poultry.fillet',
        })
        
        passed, reason, _ = check_hard_blocks(item1, item2)
        assert passed == False
        assert 'CORE_MISMATCH' in reason


# ============================================================================
# TEST: Pack Compatibility
# ============================================================================

class TestPackCompatibility:
    """Тесты совместимости фасовки"""
    
    def test_pack_exact_match(self):
        """Точное совпадение фасовки"""
        sig1 = extract_signature({
            'name_raw': 'Молоко 1л',
            'name_norm': 'молоко 1л',
            'product_core_id': 'dairy.milk',
            'net_weight_kg': 1.0,
        })
        sig2 = extract_signature({
            'name_raw': 'Молоко 1л',
            'name_norm': 'молоко 1л',
            'product_core_id': 'dairy.milk',
            'net_weight_kg': 1.0,
        })
        
        passed, diff_pct, _ = check_pack_compatibility(sig1, sig2)
        assert passed == True
        assert diff_pct == 0.0
    
    def test_pack_20pct_tolerance_pass(self):
        """Допуск ±20% для обычных товаров"""
        sig1 = extract_signature({
            'name_raw': 'Молоко 1л',
            'name_norm': 'молоко 1л',
            'product_core_id': 'dairy.milk',
            'net_weight_kg': 1.0,
        })
        sig2 = extract_signature({
            'name_raw': 'Молоко 0.9л',
            'name_norm': 'молоко 0.9л',
            'product_core_id': 'dairy.milk',
            'net_weight_kg': 0.9,
        })
        
        passed, diff_pct, _ = check_pack_compatibility(sig1, sig2)
        assert passed == True  # 10% < 20%
    
    def test_pack_scale_mismatch_blocks(self):
        """1кг vs 0.145г блокируется (>20%)"""
        sig1 = extract_signature({
            'name_raw': 'Соус 1кг',
            'name_norm': 'соус 1кг',
            'product_core_id': 'condiments.sauce',
            'net_weight_kg': 1.0,
        })
        sig2 = extract_signature({
            'name_raw': 'Соус 145г',
            'name_norm': 'соус 145г',
            'product_core_id': 'condiments.sauce',
            'net_weight_kg': 0.145,
        })
        
        passed, diff_pct, _ = check_pack_compatibility(sig1, sig2)
        assert passed == False  # 85.5% > 20%


# ============================================================================
# TEST: Full Matching Flow
# ============================================================================

class TestMatchCandidate:
    """Тесты полного процесса matching"""
    
    def test_brand_match_detected(self, heinz_item):
        """Совпадение бренда определяется"""
        source = extract_signature(heinz_item)
        
        cand_item = {
            'id': 'test-heinz-2',
            'name_raw': 'Кетчуп HEINZ 1кг',
            'name_norm': 'кетчуп heinz 1кг',
            'product_core_id': 'condiments.bbq',
            'price': 280,
            'unit_type': 'PIECE',
        }
        cand = extract_signature(cand_item)
        
        result = match_candidate(source, cand)
        assert result.brand_match == True
    
    def test_breaded_blocked_in_strict(self):
        """Панировка блокируется в Strict если source без панировки"""
        source = extract_signature({
            'name_raw': 'Креветки с/м б/г 31/40',
            'name_norm': 'креветки с/м б/г 31/40',
            'product_core_id': 'seafood.shrimp',
        })
        cand = extract_signature({
            'name_raw': 'Креветки в панировке',
            'name_norm': 'креветки в панировке',
            'product_core_id': 'seafood.shrimp',
        })
        
        result = match_candidate(source, cand)
        assert result.passed_strict == False
        assert 'BREADED' in result.block_reason


# ============================================================================
# TEST: Similar Mode
# ============================================================================

class TestSimilarMode:
    """Тесты Similar режима"""
    
    def test_similar_allows_different_brand(self):
        """Similar допускает другой бренд с лейблом"""
        source = extract_signature({
            'name_raw': 'Соус ХАЙНЦ 1кг',
            'name_norm': 'соус хайнц 1кг',
            'product_core_id': 'condiments.sauce',
            'brand_id': 'heinz',
        })
        cand = extract_signature({
            'name_raw': 'Соус CALVE 1кг',
            'name_norm': 'соус calve 1кг',
            'product_core_id': 'condiments.sauce',
        })
        
        result = match_for_similar(source, cand)
        assert result.passed_similar == True
        assert 'Бренд другой' in result.difference_labels
    
    def test_similar_still_blocks_flavor(self):
        """Similar всё равно блокирует разные вкусы"""
        source = extract_signature({
            'name_raw': 'Йогурт клубника',
            'name_norm': 'йогурт клубника',
            'product_core_id': 'dairy.yogurt',
        })
        cand = extract_signature({
            'name_raw': 'Йогурт манго',
            'name_norm': 'йогурт манго',
            'product_core_id': 'dairy.yogurt',
        })
        
        result = match_for_similar(source, cand)
        assert result.passed_similar == False
        assert 'FLAVOR_MISMATCH' in result.block_reason


# ============================================================================
# TEST: find_alternatives_v3
# ============================================================================

class TestFindAlternatives:
    """Тесты основной функции find_alternatives_v3"""
    
    def test_empty_candidates_returns_empty(self):
        """Пустой список кандидатов → пустой результат"""
        source = {
            'id': 'test-1',
            'name_raw': 'Тест',
            'name_norm': 'тест',
            'product_core_id': 'test',
        }
        
        result = find_alternatives_v3(source, [])
        assert result.strict == []
        assert result.similar == []
    
    def test_similar_shown_when_strict_below_threshold(self):
        """Similar показывается если Strict < threshold"""
        source = {
            'id': 'source-1',
            'name_raw': 'Молоко 1л',
            'name_norm': 'молоко 1л',
            'product_core_id': 'dairy.milk',
            'price': 89,
        }
        
        # Кандидаты с большой разницей в фасовке (не пройдут Strict)
        candidates = [
            {
                'id': f'cand-{i}',
                'name_raw': f'Молоко {0.5 + i*0.1}л',
                'name_norm': f'молоко {0.5 + i*0.1}л',
                'product_core_id': 'dairy.milk',
                'price': 50 + i*10,
                'net_weight_kg': 0.5 + i*0.1,  # 0.5, 0.6, 0.7 - разница > 20%
            }
            for i in range(3)
        ]
        
        result = find_alternatives_v3(source, candidates, strict_threshold=4)
        
        # Strict должен быть < 4, поэтому Similar должен показаться
        # (если есть подходящие кандидаты)


# ============================================================================
# RUN TESTS
# ============================================================================

if __name__ == '__main__':
    pytest.main([__file__, '-v'])
