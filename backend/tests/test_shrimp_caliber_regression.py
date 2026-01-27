"""
BestPrice - NPC Matching SHRIMP v12 - Caliber Regression Suite
==============================================================

КРИТИЧЕСКИЙ ТЕСТ: REF 16/20 не должен матчиться с 31/40, 26/30, 21/25, гёдзой.

30+ регрессионных кейсов для проверки:
1. Калибр ВСЕГДА hard gate (16/20 vs 31/40/26/30/21/25)
2. FORBIDDEN_CLASS (гёдза, суп, набор и т.д.)
3. Все остальные hard gates
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from bestprice_v12.npc_matching_v9 import (
    extract_npc_signature, check_npc_strict,
    explain_npc_match, apply_npc_filter, load_npc_data,
    check_blacklist, extract_shrimp_caliber,
)


@pytest.fixture(scope="module")
def npc_data():
    load_npc_data()
    return True


# =============================================================================
# CRITICAL: КАЛИБР 16/20 vs ДРУГИЕ КАЛИБРЫ
# =============================================================================

class TestCaliber1620VsOthers:
    """КРИТИЧЕСКИЙ ТЕСТ: 16/20 не должен матчиться с другими калибрами."""
    
    REF_16_20 = 'Креветки ваннамей б/г с/м 16/20 1кг'
    
    @pytest.mark.parametrize("candidate,expected_reject", [
        ('Креветки ваннамей б/г с/м 31/40 1кг', 'CALIBER_MISMATCH'),
        ('Креветки ваннамей б/г с/м 26/30 1кг', 'CALIBER_MISMATCH'),
        ('Креветки ваннамей б/г с/м 21/25 1кг', 'CALIBER_MISMATCH'),
        ('Креветки ваннамей б/г с/м 41/50 1кг', 'CALIBER_MISMATCH'),
        ('Креветки ваннамей б/г с/м 51/60 1кг', 'CALIBER_MISMATCH'),
        ('Креветки ваннамей б/г с/м 61/70 1кг', 'CALIBER_MISMATCH'),
        ('Креветки ваннамей б/г с/м 71/90 1кг', 'CALIBER_MISMATCH'),
        ('Креветки ваннамей б/г с/м 90/120 1кг', 'CALIBER_MISMATCH'),
        ('Гёдза с креветкой 1кг', 'FORBIDDEN_CLASS'),
        ('Пельмени с креветкой', 'FORBIDDEN_CLASS'),
        ('Суп с креветками', 'FORBIDDEN_CLASS'),
        ('Набор морепродуктов', 'FORBIDDEN_CLASS'),
    ])
    def test_1620_rejects_wrong_caliber_and_junk(self, npc_data, candidate, expected_reject):
        """16/20 отклоняет неправильные калибры и мусор."""
        result = explain_npc_match(self.REF_16_20, candidate)
        assert result['strict_result']['passed'] == False, f"{candidate} should be rejected"
        reason = result['strict_result']['block_reason'] or ''
        assert expected_reject in reason, f"Expected {expected_reject} in {reason}"
    
    def test_1620_accepts_same_caliber(self, npc_data):
        """16/20 принимает только 16/20."""
        candidates = [
            'Креветки ваннамей б/г с/м 16/20 500г',
            'Креветки ваннамей б/г с/м 16/20 2кг',
            'Креветки ваннамей б/г с/м 16-20 1кг',  # Альтернативный формат
        ]
        for cand in candidates:
            result = explain_npc_match(self.REF_16_20, cand)
            assert result['strict_result']['passed'] == True, f"{cand} should pass"


# =============================================================================
# КАЛИБР: НОРМАЛИЗАЦИЯ РАЗНЫХ ФОРМАТОВ
# =============================================================================

class TestCaliberNormalization:
    """Тест нормализации калибра: 16/20, 16-20, 16 / 20, 16/20*."""
    
    @pytest.mark.parametrize("name,expected_caliber", [
        ('Креветки 16/20 с/м', '16/20'),
        ('Креветки 16-20 с/м', '16/20'),
        ('Креветки 16 / 20 с/м', '16/20'),
        ('Креветки 16/20* с/м', '16/20'),
        ('Креветки 16/20 шт/ф с/м', '16/20'),
        ('Креветки 21/25 с/м', '21/25'),
        ('Креветки 31-40 с/м', '31/40'),
        ('Креветки 90/120 с/м', '90/120'),
    ])
    def test_caliber_normalization(self, npc_data, name, expected_caliber):
        """Калибр нормализуется корректно."""
        cal, _, _ = extract_shrimp_caliber(name.lower())
        assert cal == expected_caliber


# =============================================================================
# КАЛИБР: MISSING CALIBER = REJECT
# =============================================================================

class TestCaliberMissing:
    """Если у REF есть калибр, а у кандидата нет → REJECT."""
    
    def test_ref_has_caliber_cand_missing(self, npc_data):
        """REF с калибром отклоняет кандидата без калибра."""
        result = explain_npc_match('Креветки ваннамей 16/20 с/м', 'Креветки ваннамей с/м')
        assert result['strict_result']['passed'] == False
        reason = result['strict_result']['block_reason'] or ''
        assert 'CALIBER' in reason


# =============================================================================
# FORBIDDEN CLASS: МУСОР ВСЕГДА ОТКЛОНЯЕТСЯ
# =============================================================================

class TestForbiddenClassAlwaysReject:
    """FORBIDDEN_CLASS отклоняется ВСЕГДА, даже если есть слово 'креветка'."""
    
    FORBIDDEN_ITEMS = [
        ('Гёдза с креветкой', 'гёдза'),
        ('Гедза с креветкой 1кг', 'гедза'),
        ('Пельмени с креветкой', 'пельмен'),
        ('Пельмени морские', 'пельмен'),
        ('Вареники с креветкой', 'вареник'),
        ('Хинкали с креветкой', 'хинкали'),
        ('Суп с креветками', 'суп'),
        ('Суп том-ям с креветками', 'суп'),
        ('Салат с креветками', 'салат'),
        ('Салат цезарь с креветкой', 'салат'),
        ('Набор морепродуктов', 'набор'),
        ('Набор с креветками', 'набор'),
        ('Ассорти креветок', 'ассорти'),
        ('Ассорти морепродуктов', 'ассорти'),
        ('Микс морепродуктов', 'микс'),
        ('Котлеты из креветок', 'котлет'),
        ('Котлеты креветочные', 'котлет'),
        ('Наггетсы креветочные', 'наггетс'),
        ('Наггетсы из креветки', 'наггетс'),
        ('Лапша удон с креветкой', 'лапша'),
        ('Лапша рамен с креветками', 'лапша'),
        ('Полуфабрикат из креветок', 'полуфабрикат'),
        ('Закуска с креветкой', 'закуска'),
    ]
    
    @pytest.mark.parametrize("forbidden_name,keyword", FORBIDDEN_ITEMS)
    def test_forbidden_blocked(self, npc_data, forbidden_name, keyword):
        """Мусор блокируется через FORBIDDEN_CLASS."""
        is_blocked, reason = check_blacklist(forbidden_name.lower())
        assert is_blocked, f"{forbidden_name} should be blocked"
        assert 'FORBIDDEN_CLASS' in reason
    
    @pytest.mark.parametrize("forbidden_name,keyword", FORBIDDEN_ITEMS)
    def test_forbidden_not_in_strict(self, npc_data, forbidden_name, keyword):
        """Мусор не попадает в strict."""
        result = explain_npc_match('Креветки ваннамей 16/20 с/м', forbidden_name)
        assert result['strict_result']['passed'] == False


# =============================================================================
# ALL HARD GATES: SHRIMP-ONLY, SPECIES, STATE, FORM, TAIL, BREADED, UOM
# =============================================================================

class TestAllHardGates:
    """Все hard gates должны работать."""
    
    @pytest.mark.parametrize("ref,candidate,expected_reject", [
        # SHRIMP-only gate
        ('Креветки 16/20 с/м', 'Лосось филе с/м', 'NOT_SHRIMP'),
        ('Креветки 16/20 с/м', 'Кальмар тушка', 'NOT_SHRIMP'),
        ('Креветки 16/20 с/м', 'Мидии в/м', 'NOT_SHRIMP'),
        # species
        ('Креветки ваннамей 16/20 с/м', 'Креветки тигровые 16/20 с/м', 'SPECIES'),
        ('Креветки северные 90/120 с/м', 'Креветки ваннамей 90/120 с/м', 'SPECIES'),
        # state
        ('Креветки с/м 16/20', 'Креветки в/м 16/20', 'STATE'),
        ('Креветки сыромор 16/20', 'Креветки варёно-мор 16/20', 'STATE'),
        # form
        ('Креветки очищ б/г 16/20 с/м', 'Креветки неочищ б/г 16/20 с/м', 'FORM'),
        # tail_state
        ('Креветки с/хв 16/20 с/м', 'Креветки б/хв 16/20 с/м', 'TAIL'),
        ('Креветки с хвостом 16/20', 'Креветки без хвоста 16/20', 'TAIL'),
        # breaded
        ('Креветки 16/20 с/м', 'Креветки в панировке 16/20', 'BREADED|EXCLUDED'),
        ('Креветки 16/20 с/м', 'Креветки в темпуре 16/20', 'BREADED|EXCLUDED'),
        # UOM
        ('Креветки 16/20 1кг', 'Креветки 16/20 10шт', 'UOM'),
    ])
    def test_hard_gate(self, npc_data, ref, candidate, expected_reject):
        """Hard gate работает."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False, f"{candidate} should be rejected"
        reason = result['strict_result']['block_reason'] or ''
        assert expected_reject in reason, f"Expected {expected_reject} in {reason}"


# =============================================================================
# BRAND/COUNTRY: НЕ БЛОКИРУЮТ
# =============================================================================

class TestBrandCountryNotBlock:
    """Brand и Country НЕ блокируют, только ranking."""
    
    def test_different_brand_passes(self, npc_data):
        """Разные бренды проходят."""
        source = {'name_raw': 'Креветки VICI 16/20 с/м', 'brand_id': 'vici'}
        candidate = {'name_raw': 'Креветки AGAMA 16/20 с/м', 'brand_id': 'agama'}
        
        sig_s = extract_npc_signature(source)
        sig_c = extract_npc_signature(candidate)
        result = check_npc_strict(sig_s, sig_c)
        
        assert result.passed_strict == True
    
    def test_different_country_passes(self, npc_data):
        """Разные страны проходят."""
        result = explain_npc_match('Креветки Вьетнам 16/20 с/м', 'Креветки Индия 16/20 с/м')
        assert result['strict_result']['passed'] == True


# =============================================================================
# DEBUG OUTPUT
# =============================================================================

class TestDebugOutput:
    """Debug output содержит все нужные поля."""
    
    def test_passed_gates_present(self, npc_data):
        """passed_gates присутствует."""
        result = explain_npc_match('Креветки 16/20 с/м', 'Креветки 16/20 с/м 1кг')
        assert 'passed_gates' in result['strict_result']
        assert len(result['strict_result']['passed_gates']) > 0
    
    def test_rejected_reason_present(self, npc_data):
        """rejected_reason присутствует для отклонённых."""
        result = explain_npc_match('Креветки 16/20 с/м', 'Креветки 21/25 с/м')
        assert result['strict_result']['passed'] == False
        reason = result['strict_result']['rejected_reason'] or result['strict_result']['block_reason']
        assert reason is not None
    
    def test_rank_features_present(self, npc_data):
        """rank_features присутствует."""
        result = explain_npc_match('Креветки 16/20 с/м', 'Креветки 16/20 с/м 1кг')
        rf = result['strict_result']['rank_features']
        assert 'caliber_exact' in rf
        assert 'brand_match' in rf
        assert 'country_match' in rf
    
    def test_candidate_parsed_attributes(self, npc_data):
        """Атрибуты кандидата доступны."""
        result = explain_npc_match('Креветки 16/20 с/м', 'Креветки 16/20 с/м 1кг')
        assert 'shrimp_caliber' in result['candidate']
        assert result['candidate']['shrimp_caliber'] == '16/20'


# =============================================================================
# INTEGRATION: apply_npc_filter
# =============================================================================

class TestApplyNPCFilter:
    """Тест apply_npc_filter — главная функция фильтрации."""
    
    def test_filter_rejects_wrong_caliber(self, npc_data):
        """apply_npc_filter отклоняет неправильные калибры."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 16/20 1кг'}
        candidates = [
            {'name_raw': 'Креветки ваннамей б/г с/м 31/40 1кг', 'id': '1'},
            {'name_raw': 'Креветки ваннамей б/г с/м 26/30 1кг', 'id': '2'},
            {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг', 'id': '3'},
            {'name_raw': 'Креветки ваннамей б/г с/м 16/20 500г', 'id': '4'},  # OK
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, candidates, mode='strict')
        strict_ids = [r['item']['id'] for r in strict]
        
        # Только 16/20 должен пройти
        assert '4' in strict_ids
        assert '1' not in strict_ids
        assert '2' not in strict_ids
        assert '3' not in strict_ids
        
        # rejected должен содержать CALIBER_MISMATCH
        assert 'CALIBER_MISMATCH' in rejected
    
    def test_filter_rejects_forbidden(self, npc_data):
        """apply_npc_filter отклоняет мусор."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 16/20 1кг'}
        candidates = [
            {'name_raw': 'Гёдза с креветкой', 'id': '1'},
            {'name_raw': 'Суп с креветками', 'id': '2'},
            {'name_raw': 'Набор морепродуктов', 'id': '3'},
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, candidates, mode='strict')
        
        assert len(strict) == 0
        assert 'FORBIDDEN_CLASS' in rejected


# =============================================================================
# REGRESSION: 30+ CASES
# =============================================================================

class TestRegressionCases:
    """30+ регрессионных кейсов."""
    
    CASES = [
        # Калибр 16/20 vs другие (8 кейсов)
        ('Креветки 16/20', 'Креветки 31/40', False, 'caliber_16_vs_31'),
        ('Креветки 16/20', 'Креветки 26/30', False, 'caliber_16_vs_26'),
        ('Креветки 16/20', 'Креветки 21/25', False, 'caliber_16_vs_21'),
        ('Креветки 16/20', 'Креветки 41/50', False, 'caliber_16_vs_41'),
        ('Креветки 16/20', 'Креветки 51/60', False, 'caliber_16_vs_51'),
        ('Креветки 16/20', 'Креветки 61/70', False, 'caliber_16_vs_61'),
        ('Креветки 16/20', 'Креветки 71/90', False, 'caliber_16_vs_71'),
        ('Креветки 16/20', 'Креветки 90/120', False, 'caliber_16_vs_90'),
        
        # Калибр 21/25 vs другие (4 кейса)
        ('Креветки 21/25', 'Креветки 16/20', False, 'caliber_21_vs_16'),
        ('Креветки 21/25', 'Креветки 31/40', False, 'caliber_21_vs_31'),
        ('Креветки 21/25', 'Креветки 26/30', False, 'caliber_21_vs_26'),
        ('Креветки 21/25', 'Креветки 41/50', False, 'caliber_21_vs_41'),
        
        # FORBIDDEN_CLASS (8 кейсов)
        ('Креветки 16/20', 'Гёдза с креветкой', False, 'forbidden_gyoza'),
        ('Креветки 16/20', 'Пельмени с креветкой', False, 'forbidden_pelmeni'),
        ('Креветки 16/20', 'Суп с креветками', False, 'forbidden_soup'),
        ('Креветки 16/20', 'Салат с креветками', False, 'forbidden_salad'),
        ('Креветки 16/20', 'Набор морепродуктов', False, 'forbidden_set'),
        ('Креветки 16/20', 'Котлеты из креветок', False, 'forbidden_cutlets'),
        ('Креветки 16/20', 'Наггетсы креветочные', False, 'forbidden_nuggets'),
        ('Креветки 16/20', 'Лапша с креветкой', False, 'forbidden_noodles'),
        
        # Hard gates (6 кейсов)
        ('Креветки ваннамей 16/20', 'Креветки тигровые 16/20', False, 'species_mismatch'),
        ('Креветки с/м 16/20', 'Креветки в/м 16/20', False, 'state_mismatch'),
        ('Креветки очищ 16/20', 'Креветки неочищ 16/20', False, 'form_mismatch'),
        ('Креветки с/хв 16/20', 'Креветки б/хв 16/20', False, 'tail_mismatch'),
        ('Креветки 16/20', 'Креветки в панировке 16/20', False, 'breaded_mismatch'),
        ('Креветки 1кг 16/20', 'Креветки 10шт 16/20', False, 'uom_mismatch'),
        
        # NOT_SHRIMP (3 кейса)
        ('Креветки 16/20', 'Лосось филе', False, 'not_shrimp_fish'),
        ('Креветки 16/20', 'Кальмар тушка', False, 'not_shrimp_squid'),
        ('Креветки 16/20', 'Мидии в/м', False, 'not_shrimp_mussel'),
        
        # PASS cases (3 кейса)
        ('Креветки 16/20', 'Креветки 16/20 1кг', True, 'same_16_ok'),
        ('Креветки 21/25', 'Креветки 21/25 1кг', True, 'same_21_ok'),
        ('Креветки ваннамей 16/20', 'Креветки ваннамей 16/20 500г', True, 'same_vannamei_ok'),
    ]
    
    @pytest.mark.parametrize("ref,candidate,should_pass,desc", CASES)
    def test_regression_case(self, npc_data, ref, candidate, should_pass, desc):
        """Регрессионный кейс."""
        result = explain_npc_match(ref, candidate)
        passed = result['strict_result']['passed']
        assert passed == should_pass, f"[{desc}] {ref} vs {candidate}: expected {should_pass}, got {passed}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
