"""
BestPrice - NPC Matching SHRIMP v1 (Zero-Trash)
===============================================

Тесты по ТЗ · NPC-Matching · SHRIMP · v1 (Zero-Trash)

ACCEPTANCE CRITERIA:
1. Strict не содержит мусора ни при каких входных данных
2. Калибр ВСЕГДА совпадает
3. Нет гёдза/пельменей/соусов/лапши
4. Короба не лезут наверх
5. Пустая выдача допустима и считается корректной
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from bestprice_v12.npc_matching_v9 import (
    extract_npc_signature, check_npc_strict, check_npc_similar,
    explain_npc_match, apply_npc_filter, load_npc_data,
)


@pytest.fixture(scope="module")
def npc_data():
    load_npc_data()
    return True


# =============================================================================
# 3.1 ВИД ПРОДУКТА — запрещены п/ф, гёдза, пельмени, соусы
# =============================================================================

class TestShrimpProductType:
    """Strict = только креветки. Запрещено всё остальное."""
    
    @pytest.mark.parametrize("ref,candidate,desc", [
        ('Креветки ваннамей 21/25 с/м', 'Гёдза с креветкой 1кг', 'gyoza'),
        ('Креветки 21/25', 'Пельмени с креветкой', 'pelmeni'),
        ('Креветки 16/20 с/м', 'Креветки в панировке', 'breaded'),
        ('Креветки 21/25', 'Соус с креветкой', 'sauce'),
        ('Креветки 21/25', 'Лапша с креветкой', 'noodles'),
        ('Креветки 21/25', 'Чипсы со вкусом креветки', 'chips'),
        ('Креветки 21/25', 'Котлеты из креветок', 'cutlets'),
        ('Креветки 21/25', 'Наггетсы креветочные', 'nuggets'),
    ])
    def test_junk_blocked(self, npc_data, ref, candidate, desc):
        """Мусор блокируется в Strict."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False, f"{desc} should be blocked"


# =============================================================================
# 3.2 АТРИБУТЫ КРЕВЕТОК — строго 1-к-1
# =============================================================================

class TestShrimpAttributes:
    """Все атрибуты должны совпадать строго."""
    
    # --- species ---
    @pytest.mark.parametrize("ref,candidate,should_pass", [
        ('Креветки ваннамей 21/25 с/м', 'Креветки тигровые 21/25 с/м', False),
        ('Креветки ваннамей 21/25 с/м', 'Креветки ваннамей 21/25 с/м 1кг', True),
        ('Креветки северные 90/120 с/м', 'Креветки ваннамей 90/120 с/м', False),
    ])
    def test_species(self, npc_data, ref, candidate, should_pass):
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == should_pass
    
    # --- shrimp_state (с/м vs в/м) ---
    @pytest.mark.parametrize("ref,candidate,should_pass", [
        ('Креветки с/м 21/25', 'Креветки в/м 21/25', False),
        ('Креветки сыромор 21/25', 'Креветки варёно-мор 21/25', False),
        ('Креветки с/м 21/25', 'Креветки бланш 21/25', False),
        ('Креветки с/м 21/25', 'Креветки с/м 21/25 1кг', True),
    ])
    def test_state(self, npc_data, ref, candidate, should_pass):
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == should_pass
    
    # --- shrimp_form (очищ/неочищ/хвост) ---
    @pytest.mark.parametrize("ref,candidate,should_pass", [
        ('Креветки очищ б/г 21/25 с/м', 'Креветки неочищ б/г 21/25 с/м', False),
        ('Креветки б/г 21/25 с/м', 'Креветки с/г 21/25 с/м', False),
    ])
    def test_form(self, npc_data, ref, candidate, should_pass):
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == should_pass
    
    # --- caliber (НИКОГДА не ослабляется) ---
    @pytest.mark.parametrize("ref,candidate,should_pass", [
        ('Креветки 16/20 с/м', 'Креветки 21/25 с/м', False),
        ('Креветки 21/25 с/м', 'Креветки 31/40 с/м', False),
        ('Креветки 31/40 с/м', 'Креветки 41/50 с/м', False),
        ('Креветки 41/50 с/м', 'Креветки 51/60 с/м', False),
        ('Креветки 16/20 с/м', 'Креветки 16/20 с/м 1кг', True),
        ('Креветки 21/25', 'Креветки без калибра', False),
    ])
    def test_caliber_strict(self, npc_data, ref, candidate, should_pass):
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == should_pass


# =============================================================================
# 4. УПАКОВКА И ОБЪЁМ
# =============================================================================

class TestShrimpPackaging:
    """Box-rule и граммовка."""
    
    @pytest.mark.parametrize("ref,candidate,should_pass", [
        ('Креветки 21/25 500г', 'Креветки 21/25 10кг/кор', False),
        ('Креветки 21/25 10кг/кор', 'Креветки 21/25 500г', False),
        ('Креветки 21/25 1кг', 'Креветки 21/25 20кг ящик', False),
        ('Креветки 21/25 10кг/кор', 'Креветки 21/25 10кг/кор', True),
    ])
    def test_box_rule(self, npc_data, ref, candidate, should_pass):
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == should_pass


# =============================================================================
# 5. БРЕНД И СТРАНА
# =============================================================================

class TestShrimpBrandCountry:
    """Brand gate и Country ranking — v11: только ранжирование, НЕ hard gates."""
    
    def test_brand_same_higher_rank(self, npc_data):
        """Тот же бренд = выше rank."""
        source = {'name_raw': 'Креветки VICI 21/25 с/м', 'brand_id': 'vici'}
        candidate = {'name_raw': 'Креветки VICI 21/25 с/м 1кг', 'brand_id': 'vici'}
        
        sig_s = extract_npc_signature(source)
        sig_c = extract_npc_signature(candidate)
        result = check_npc_strict(sig_s, sig_c)
        
        assert result.passed_strict == True
        assert result.same_brand == True
        assert result.brand_score > 0  # Brand влияет на score
    
    def test_brand_different_passes_lower_rank(self, npc_data):
        """v11: Другой бренд НЕ блокирует, но rank ниже."""
        source = {'name_raw': 'Креветки VICI 21/25 с/м', 'brand_id': 'vici'}
        candidate = {'name_raw': 'Креветки AGAMA 21/25 с/м', 'brand_id': 'agama'}
        
        sig_s = extract_npc_signature(source)
        sig_c = extract_npc_signature(candidate)
        result = check_npc_strict(sig_s, sig_c)
        
        # v11: Brand не блокирует
        assert result.passed_strict == True
        assert result.same_brand == False
        assert result.brand_score == 0  # No brand bonus
    
    def test_brand_missing_passes_lower_rank(self, npc_data):
        """v11: Candidate без бренда НЕ блокируется, но rank ниже."""
        source = {'name_raw': 'Креветки VICI 21/25 с/м', 'brand_id': 'vici'}
        candidate = {'name_raw': 'Креветки 21/25 с/м'}
        
        sig_s = extract_npc_signature(source)
        sig_c = extract_npc_signature(candidate)
        result = check_npc_strict(sig_s, sig_c)
        
        # v11: Brand не блокирует
        assert result.passed_strict == True
        assert result.same_brand == False
    
    def test_country_does_not_block(self, npc_data):
        """Разные страны НЕ блокируют (только ранжирование)."""
        result = explain_npc_match(
            'Креветки Вьетнам 21/25 с/м',
            'Креветки Индия 21/25 с/м'
        )
        assert result['strict_result']['passed'] == True
    
    def test_same_country_higher_score(self, npc_data):
        """Та же страна = выше score."""
        source = {'name_raw': 'Креветки Вьетнам 21/25 с/м'}
        cand_same = {'name_raw': 'Креветки Вьетнам 21/25 с/м 1кг'}
        cand_diff = {'name_raw': 'Креветки Индия 21/25 с/м'}
        
        sig_s = extract_npc_signature(source)
        sig_same = extract_npc_signature(cand_same)
        sig_diff = extract_npc_signature(cand_diff)
        
        r_same = check_npc_strict(sig_s, sig_same)
        r_diff = check_npc_strict(sig_s, sig_diff)
        
        assert r_same.same_country == True
        assert r_same.country_score > 0
        assert r_diff.same_country == False


# =============================================================================
# 6. ЗАПРЕТЫ (консервы, копчёные)
# =============================================================================

class TestShrimpProhibitions:
    """Глобальные запреты для SHRIMP."""
    
    @pytest.mark.parametrize("ref,candidate,should_pass", [
        ('Креветки 21/25 с/м', 'Креветки консервы ж/б', False),
        ('Креветки 21/25 с/м', 'Креветки х/к', False),
        ('Креветки 21/25 с/м', 'Креветки г/к', False),
    ])
    def test_canned_smoked_blocked(self, npc_data, ref, candidate, should_pass):
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == should_pass


# =============================================================================
# 7. ACCEPTANCE CRITERIA — полный тест
# =============================================================================

class TestAcceptanceCriteria:
    """Финальная приёмка по ТЗ."""
    
    def test_strict_no_junk(self, npc_data):
        """Strict не содержит мусора."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        
        junk_candidates = [
            {'name_raw': 'Гёдза с креветкой'},
            {'name_raw': 'Пельмени морские'},
            {'name_raw': 'Соус креветочный'},
            {'name_raw': 'Лапша с креветкой'},
            {'name_raw': 'Креветки в панировке'},
            {'name_raw': 'Наггетсы креветочные'},
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, junk_candidates, mode='strict')
        
        # Strict должен быть пустым
        assert len(strict) == 0
    
    def test_caliber_always_matches(self, npc_data):
        """Калибр всегда совпадает."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        
        wrong_caliber = [
            {'name_raw': 'Креветки ваннамей б/г с/м 16/20 1кг'},
            {'name_raw': 'Креветки ваннамей б/г с/м 31/40 1кг'},
            {'name_raw': 'Креветки ваннамей б/г с/м 41/50 1кг'},
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, wrong_caliber, mode='strict')
        
        # Все должны быть отклонены
        assert len(strict) == 0
        # rejected может быть пустой если фильтрация работает через другой механизм
        # главное — strict пустой
    
    def test_empty_result_is_valid(self, npc_data):
        """Пустая выдача допустима и корректна."""
        ref = {'name_raw': 'Креветки редкий вид 99/100 с/м'}
        candidates = []
        
        strict, similar, rejected = apply_npc_filter(ref, candidates, mode='strict')
        
        # Пустой результат — OK
        assert strict == []
        assert similar == []


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


# =============================================================================
# v11: NEW TESTS FOR SHRIMP Zero-Trash
# =============================================================================

class TestGlobalBlacklist:
    """v11: Global NEVER blacklist (Strict + Similar)."""
    
    @pytest.mark.parametrize("name,expected_blocked", [
        ('Гёдза с креветкой', True),
        ('Пельмени морские', True),
        ('Вареники с креветкой', True),
        ('Хинкали с креветкой', True),
        ('Суп с креветками', True),
        ('Салат с креветками', True),
        ('Набор морепродуктов', True),
        ('Ассорти креветок', True),
        ('Котлеты из креветок', True),
        ('Наггетсы креветочные', True),
        ('Лапша удон с креветкой', True),
        ('Креветки 21/25 с/м', False),  # Normal product
    ])
    def test_blacklist(self, npc_data, name, expected_blocked):
        from bestprice_v12.npc_matching_v9 import check_blacklist
        is_blocked, _ = check_blacklist(name.lower())
        assert is_blocked == expected_blocked


class TestShrimpOnlyGate:
    """v11: SHRIMP-only gate."""
    
    def test_non_shrimp_rejected(self, npc_data):
        result = explain_npc_match('Креветки 21/25 с/м', 'Лосось филе с/м')
        assert result['strict_result']['passed'] == False
        assert 'NOT_SHRIMP' in result['strict_result']['block_reason']
    
    def test_shrimp_to_shrimp_passes(self, npc_data):
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки 21/25 с/м 1кг')
        assert result['strict_result']['passed'] == True


class TestTailState:
    """v11: tail_state hard gate."""
    
    def test_tail_on_vs_tail_off_blocked(self, npc_data):
        result = explain_npc_match('Креветки с хвостом 21/25 с/м', 'Креветки без хвоста 21/25 с/м')
        assert result['strict_result']['passed'] == False
        assert 'TAIL_STATE_MISMATCH' in result['strict_result']['block_reason']
    
    def test_same_tail_passes(self, npc_data):
        result = explain_npc_match('Креветки с хвостом 21/25 с/м', 'Креветки с хвостом 21/25 с/м 1кг')
        assert result['strict_result']['passed'] == True


class TestBreadedFlag:
    """v11: breaded_flag hard gate."""
    
    def test_breaded_vs_plain_blocked(self, npc_data):
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки в панировке 21/25')
        assert result['strict_result']['passed'] == False
        assert 'BREADED_MISMATCH' in result['strict_result']['block_reason']
    
    def test_tempura_vs_plain_blocked(self, npc_data):
        result = explain_npc_match('Креветки в темпуре 21/25', 'Креветки 21/25 с/м')
        assert result['strict_result']['passed'] == False


class TestUOMGate:
    """v11: UOM gate (шт vs кг)."""
    
    def test_kg_vs_pcs_blocked(self, npc_data):
        result = explain_npc_match('Креветки 21/25 1кг', 'Креветки 21/25 10шт')
        assert result['strict_result']['passed'] == False
        assert 'UOM_MISMATCH' in result['strict_result']['block_reason']
    
    def test_same_uom_passes(self, npc_data):
        result = explain_npc_match('Креветки 21/25 1кг', 'Креветки 21/25 500г')
        assert result['strict_result']['passed'] == True


class TestDebugOutput:
    """v11: Debug output в ответе."""
    
    def test_passed_gates_present(self, npc_data):
        result = explain_npc_match('Креветки ваннамей 21/25 с/м', 'Креветки ваннамей 21/25 с/м 1кг')
        assert 'passed_gates' in result['strict_result']
        assert len(result['strict_result']['passed_gates']) > 0
    
    def test_rank_features_present(self, npc_data):
        result = explain_npc_match('Креветки ваннамей 21/25 с/м', 'Креветки ваннамей 21/25 с/м 1кг')
        assert 'rank_features' in result['strict_result']
        rf = result['strict_result']['rank_features']
        assert 'brand_match' in rf
        assert 'country_match' in rf
        assert 'text_similarity' in rf


class TestRankingOrder:
    """v11: Ранжирование brand_match → country_match → text_similarity."""
    
    def test_brand_higher_than_country(self, npc_data):
        """Тот же бренд выше чем та же страна."""
        source = {'name_raw': 'Креветки VICI Вьетнам 21/25 с/м', 'brand_id': 'vici'}
        cand_brand = {'name_raw': 'Креветки VICI Индия 21/25 с/м', 'brand_id': 'vici'}  # Same brand, diff country
        cand_country = {'name_raw': 'Креветки AGAMA Вьетнам 21/25 с/м', 'brand_id': 'agama'}  # Diff brand, same country
        
        sig_s = extract_npc_signature(source)
        sig_brand = extract_npc_signature(cand_brand)
        sig_country = extract_npc_signature(cand_country)
        
        r_brand = check_npc_strict(sig_s, sig_brand)
        r_country = check_npc_strict(sig_s, sig_country)
        
        # Both should pass
        assert r_brand.passed_strict == True
        assert r_country.passed_strict == True
        
        # Brand match should have higher score
        assert r_brand.brand_score > r_country.brand_score
