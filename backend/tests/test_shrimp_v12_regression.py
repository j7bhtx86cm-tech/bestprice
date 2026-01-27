"""
BestPrice - NPC Matching SHRIMP v12 Complete Regression Suite
=============================================================

Полный regression тест для NPC-matching SHRIMP.

REQUIREMENTS:
1. Режимы: strict (default), similar (by button/param)
2. Hard gates (строго 1-в-1): category, species, state, form, caliber, tail, breaded, UOM
3. Forbidden class: гёдза/пельмени/вареники/хинкали/лапша/суп/салат/набор/ассорти/котлеты/наггетсы
4. Ranking: brand → country → ppu (НЕ блокируют!)
5. Debug: passed_gates, rejected_reason, rank_features
6. Автотесты: все кейсы должны проходить
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from bestprice_v12.npc_matching_v9 import (
    extract_npc_signature, check_npc_strict, check_npc_similar,
    explain_npc_match, apply_npc_filter, load_npc_data,
    check_blacklist, extract_shrimp_tail_state, extract_shrimp_breaded,
)


@pytest.fixture(scope="module")
def npc_data():
    load_npc_data()
    return True


# =============================================================================
# REQUIREMENT 2: HARD GATES (строго 1-в-1)
# =============================================================================

class TestHardGates:
    """Все hard gates должны работать строго 1-в-1."""
    
    # --- SHRIMP-only gate ---
    @pytest.mark.parametrize("ref,candidate", [
        ('Креветки 21/25 с/м', 'Лосось филе с/м'),
        ('Креветки 21/25 с/м', 'Кальмар тушка'),
        ('Креветки 21/25 с/м', 'Мидии в/м'),
        ('Креветки 21/25 с/м', 'Осьминог тушка'),
    ])
    def test_not_shrimp_blocked(self, npc_data, ref, candidate):
        """Не-SHRIMP кандидаты блокируются."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False
        assert 'NOT_SHRIMP' in (result['strict_result']['block_reason'] or '')
    
    # --- species ---
    @pytest.mark.parametrize("ref,candidate", [
        ('Креветки ваннамей 21/25 с/м', 'Креветки тигровые 21/25 с/м'),
        ('Креветки северные 90/120 с/м', 'Креветки ваннамей 90/120 с/м'),
        ('Креветки королевские 21/25 с/м', 'Креветки ваннамей 21/25 с/м'),
    ])
    def test_species_mismatch_blocked(self, npc_data, ref, candidate):
        """Разные виды блокируются."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False
    
    # --- state (с/м vs в/м) ---
    @pytest.mark.parametrize("ref,candidate", [
        ('Креветки с/м 21/25', 'Креветки в/м 21/25'),
        ('Креветки сыромор 21/25', 'Креветки варёно-мор 21/25'),
        ('Креветки raw 21/25', 'Креветки cooked 21/25'),
    ])
    def test_state_mismatch_blocked(self, npc_data, ref, candidate):
        """Разные состояния блокируются."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False
    
    # --- form (очищ vs неочищ) ---
    @pytest.mark.parametrize("ref,candidate", [
        ('Креветки очищ б/г 21/25 с/м', 'Креветки неочищ б/г 21/25 с/м'),
        ('Креветки в панцире 21/25 с/м', 'Креветки очищенные 21/25 с/м'),
    ])
    def test_form_mismatch_blocked(self, npc_data, ref, candidate):
        """Разные формы блокируются."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False
    
    # --- caliber (НИКОГДА не ослаблять) ---
    @pytest.mark.parametrize("ref,candidate", [
        ('Креветки 16/20 с/м', 'Креветки 21/25 с/м'),
        ('Креветки 21/25 с/м', 'Креветки 31/40 с/м'),
        ('Креветки 31/40 с/м', 'Креветки 41/50 с/м'),
        ('Креветки 41/50 с/м', 'Креветки 51/60 с/м'),
        ('Креветки 90/120 с/м', 'Креветки 120/150 с/м'),
    ])
    def test_caliber_mismatch_blocked(self, npc_data, ref, candidate):
        """Разные калибры ВСЕГДА блокируются."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False
        assert 'CALIBER' in (result['strict_result']['block_reason'] or '')
    
    # --- tail_state ---
    @pytest.mark.parametrize("ref,candidate", [
        ('Креветки с/хв 21/25 с/м', 'Креветки б/хв 21/25 с/м'),
        ('Креветки с хвостом 21/25', 'Креветки без хвоста 21/25'),
        ('Креветки tail-on 21/25', 'Креветки tail-off 21/25'),
    ])
    def test_tail_mismatch_blocked(self, npc_data, ref, candidate):
        """Разные tail_state блокируются."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False
        assert 'TAIL' in (result['strict_result']['block_reason'] or '')
    
    # --- breaded_flag ---
    @pytest.mark.parametrize("ref,candidate", [
        ('Креветки 21/25 с/м', 'Креветки в панировке 21/25'),
        ('Креветки 21/25 с/м', 'Креветки в темпуре 21/25'),
        ('Креветки 21/25 с/м', 'Креветки в кляре 21/25'),
    ])
    def test_breaded_mismatch_blocked(self, npc_data, ref, candidate):
        """Панировка vs без панировки блокируется."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False
    
    # --- UOM gate ---
    @pytest.mark.parametrize("ref,candidate", [
        ('Креветки 21/25 1кг', 'Креветки 21/25 10шт'),
        ('Креветки 21/25 10шт', 'Креветки 21/25 1кг'),
    ])
    def test_uom_mismatch_blocked(self, npc_data, ref, candidate):
        """UOM шт vs кг блокируется."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == False
        assert 'UOM' in (result['strict_result']['block_reason'] or '')
    
    # --- PASS cases ---
    @pytest.mark.parametrize("ref,candidate", [
        ('Креветки 21/25 с/м', 'Креветки 21/25 с/м 1кг'),
        ('Креветки ваннамей 21/25 с/м', 'Креветки ваннамей 21/25 с/м 500г'),
        ('Креветки ваннамей б/г с/м 21/25', 'Креветки ваннамей б/г с/м 21/25 2кг'),
    ])
    def test_same_passes(self, npc_data, ref, candidate):
        """Одинаковые товары проходят."""
        result = explain_npc_match(ref, candidate)
        assert result['strict_result']['passed'] == True


# =============================================================================
# REQUIREMENT 3: FORBIDDEN CLASS (NEVER показывать)
# =============================================================================

class TestForbiddenClass:
    """Forbidden класс НЕ показывается НИКОГДА (ни в strict, ни в similar)."""
    
    FORBIDDEN_ITEMS = [
        'Гёдза с креветкой',
        'Гедза с креветкой 1кг',
        'Пельмени с креветкой',
        'Пельмени морские',
        'Вареники с креветкой',
        'Хинкали с креветкой',
        'Лапша удон с креветкой',
        'Лапша рамен с креветками',
        'Суп с креветками',
        'Суп том-ям с креветками',
        'Салат с креветками',
        'Салат цезарь с креветкой',
        'Набор морепродуктов',
        'Набор с креветками',
        'Ассорти креветок',
        'Ассорти морепродуктов',
        'Микс морепродуктов',
        'Котлеты из креветок',
        'Котлеты креветочные',
        'Наггетсы креветочные',
        'Наггетсы из креветки',
        'Полуфабрикат из креветок',
        'Закуска с креветкой',
    ]
    
    @pytest.mark.parametrize("forbidden_name", FORBIDDEN_ITEMS)
    def test_forbidden_blocked_by_blacklist(self, npc_data, forbidden_name):
        """Forbidden items блокируются через blacklist."""
        is_blocked, reason = check_blacklist(forbidden_name.lower())
        assert is_blocked, f"{forbidden_name} should be blocked"
        assert 'FORBIDDEN_CLASS' in reason
    
    def test_forbidden_not_in_strict(self, npc_data):
        """Forbidden items НЕ появляются в strict."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        candidates = [{'name_raw': name, 'id': str(i)} for i, name in enumerate(self.FORBIDDEN_ITEMS[:5])]
        
        strict, similar, rejected = apply_npc_filter(ref, candidates, mode='strict')
        assert len(strict) == 0, "No forbidden items should appear in strict"
    
    def test_forbidden_not_in_similar(self, npc_data):
        """Forbidden items НЕ появляются в similar."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        candidates = [{'name_raw': name, 'id': str(i)} for i, name in enumerate(self.FORBIDDEN_ITEMS[:5])]
        
        strict, similar, rejected = apply_npc_filter(ref, candidates, mode='similar')
        assert len(similar) == 0, "No forbidden items should appear in similar"
    
    def test_normal_shrimp_not_blocked(self, npc_data):
        """Нормальные креветки НЕ блокируются."""
        normal_items = [
            'Креветки 21/25 с/м',
            'Креветки ваннамей б/г с/м 21/25 1кг',
            'Креветки тигровые очищенные 16/20',
            'Креветки северные 90/120 с/м',
        ]
        for name in normal_items:
            is_blocked, _ = check_blacklist(name.lower())
            assert not is_blocked, f"{name} should NOT be blocked"


# =============================================================================
# REQUIREMENT 4: RANKING (brand → country → ppu, НЕ блокируют!)
# =============================================================================

class TestRanking:
    """Brand и Country влияют только на ranking, НЕ блокируют."""
    
    def test_different_brand_passes(self, npc_data):
        """Разные бренды НЕ блокируются."""
        source = {'name_raw': 'Креветки VICI 21/25 с/м', 'brand_id': 'vici'}
        candidate = {'name_raw': 'Креветки AGAMA 21/25 с/м', 'brand_id': 'agama'}
        
        sig_s = extract_npc_signature(source)
        sig_c = extract_npc_signature(candidate)
        result = check_npc_strict(sig_s, sig_c)
        
        assert result.passed_strict == True, "Different brand should NOT block"
        assert result.same_brand == False
    
    def test_missing_brand_passes(self, npc_data):
        """Отсутствие бренда у candidate НЕ блокирует."""
        source = {'name_raw': 'Креветки VICI 21/25 с/м', 'brand_id': 'vici'}
        candidate = {'name_raw': 'Креветки 21/25 с/м'}  # No brand
        
        sig_s = extract_npc_signature(source)
        sig_c = extract_npc_signature(candidate)
        result = check_npc_strict(sig_s, sig_c)
        
        assert result.passed_strict == True, "Missing brand should NOT block"
    
    def test_different_country_passes(self, npc_data):
        """Разные страны НЕ блокируются."""
        result = explain_npc_match('Креветки Вьетнам 21/25 с/м', 'Креветки Индия 21/25 с/м')
        assert result['strict_result']['passed'] == True, "Different country should NOT block"
    
    def test_same_brand_higher_rank(self, npc_data):
        """Тот же бренд = выше в ranking."""
        source = {'name_raw': 'Креветки VICI 21/25 с/м', 'brand_id': 'vici'}
        cand_same = {'name_raw': 'Креветки VICI 21/25 с/м 1кг', 'brand_id': 'vici'}
        cand_diff = {'name_raw': 'Креветки AGAMA 21/25 с/м', 'brand_id': 'agama'}
        
        sig_s = extract_npc_signature(source)
        sig_same = extract_npc_signature(cand_same)
        sig_diff = extract_npc_signature(cand_diff)
        
        r_same = check_npc_strict(sig_s, sig_same)
        r_diff = check_npc_strict(sig_s, sig_diff)
        
        assert r_same.brand_score > r_diff.brand_score
    
    def test_same_country_higher_rank(self, npc_data):
        """Та же страна = выше в ranking."""
        source = {'name_raw': 'Креветки Вьетнам 21/25 с/м'}
        cand_same = {'name_raw': 'Креветки Вьетнам 21/25 с/м 1кг'}
        cand_diff = {'name_raw': 'Креветки Индия 21/25 с/м'}
        
        sig_s = extract_npc_signature(source)
        sig_same = extract_npc_signature(cand_same)
        sig_diff = extract_npc_signature(cand_diff)
        
        r_same = check_npc_strict(sig_s, sig_same)
        r_diff = check_npc_strict(sig_s, sig_diff)
        
        assert r_same.country_score > r_diff.country_score


# =============================================================================
# REQUIREMENT 5: DEBUG OUTPUT
# =============================================================================

class TestDebugOutput:
    """Debug output должен содержать passed_gates, rejected_reason, rank_features."""
    
    def test_passed_gates_present(self, npc_data):
        """passed_gates присутствует и не пустой."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки 21/25 с/м 1кг')
        assert 'passed_gates' in result['strict_result']
        assert len(result['strict_result']['passed_gates']) > 0
    
    def test_rejected_reason_for_blocked(self, npc_data):
        """rejected_reason заполнен для заблокированных."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки 16/20 с/м')
        assert result['strict_result']['passed'] == False
        reason = result['strict_result']['rejected_reason'] or result['strict_result']['block_reason']
        assert reason is not None
    
    def test_rank_features_present(self, npc_data):
        """rank_features содержит все нужные поля."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки 21/25 с/м 1кг')
        rf = result['strict_result']['rank_features']
        
        required = ['brand_match', 'country_match', 'caliber_exact']
        for key in required:
            assert key in rf, f"Missing rank_feature: {key}"
    
    def test_candidate_attributes_in_response(self, npc_data):
        """Атрибуты кандидата доступны в ответе."""
        result = explain_npc_match('Креветки с/хв 21/25 с/м', 'Креветки с/хв 21/25 с/м 1кг')
        
        assert 'shrimp_caliber' in result['candidate']
        assert 'shrimp_state' in result['candidate']
        assert 'shrimp_form' in result['candidate']
        assert 'shrimp_tail_state' in result['candidate']
        assert 'shrimp_breaded' in result['candidate']


# =============================================================================
# INTEGRATION: Full Flow Test
# =============================================================================

class TestIntegration:
    """Интеграционные тесты для полного потока."""
    
    def test_strict_mode_default(self, npc_data):
        """Strict режим по умолчанию работает корректно."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        
        candidates = [
            # Good
            {'name_raw': 'Креветки ваннамей б/г с/м 21/25 500г', 'id': '1'},
            {'name_raw': 'Креветки ваннамей б/г с/м 21/25 2кг', 'id': '2'},
            # Bad - different caliber
            {'name_raw': 'Креветки ваннамей б/г с/м 16/20 1кг', 'id': '3'},
            # Bad - forbidden
            {'name_raw': 'Гёдза с креветкой', 'id': '4'},
            # Bad - different species
            {'name_raw': 'Креветки тигровые б/г с/м 21/25', 'id': '5'},
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, candidates, mode='strict')
        strict_ids = [r['item']['id'] for r in strict]
        
        # Good candidates should pass
        assert '1' in strict_ids or '2' in strict_ids
        # Bad candidates should NOT pass
        assert '3' not in strict_ids  # wrong caliber
        assert '4' not in strict_ids  # forbidden
        assert '5' not in strict_ids  # wrong species
    
    def test_similar_mode_by_param(self, npc_data):
        """Similar режим включается по параметру."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        
        candidates = [
            # Good for strict
            {'name_raw': 'Креветки ваннамей б/г с/м 21/25 500г', 'id': '1'},
            # Bad for strict but maybe similar
            {'name_raw': 'Креветки ваннамей б/г с/м 16/20 1кг', 'id': '2'},
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, candidates, mode='similar')
        
        # Similar mode returns both strict and similar results
        assert isinstance(strict, list)
        assert isinstance(similar, list)
    
    def test_no_false_positives(self, npc_data):
        """Нет ложных срабатываний (мусор не проходит)."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        
        junk_candidates = [
            {'name_raw': 'Гёдза с креветкой', 'id': '1'},
            {'name_raw': 'Пельмени с креветкой', 'id': '2'},
            {'name_raw': 'Суп с креветками', 'id': '3'},
            {'name_raw': 'Салат с креветками', 'id': '4'},
            {'name_raw': 'Лапша удон с креветкой', 'id': '5'},
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, junk_candidates, mode='strict')
        
        assert len(strict) == 0, "No junk should pass strict"
    
    def test_no_false_negatives(self, npc_data):
        """Нет ложных отклонений (хорошие товары проходят)."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        
        good_candidates = [
            {'name_raw': 'Креветки ваннамей б/г с/м 21/25 500г', 'id': '1'},
            {'name_raw': 'Креветки ваннамей б/г с/м 21/25 2кг', 'id': '2'},
            {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1.5кг', 'id': '3'},
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, good_candidates, mode='strict')
        
        assert len(strict) > 0, "Good candidates should pass strict"


# =============================================================================
# REGRESSION: Many Cases Autocheck
# =============================================================================

class TestRegressionManyCases:
    """Регрессионные тесты для множества кейсов."""
    
    # Кейсы из типичных ошибок
    REGRESSION_CASES = [
        # (ref, candidate, should_pass, description)
        ('Креветки 21/25 с/м', 'Гёдза с креветкой', False, 'forbidden_gyoza'),
        ('Креветки 21/25 с/м', 'Пельмени с креветкой', False, 'forbidden_pelmeni'),
        ('Креветки 21/25 с/м', 'Суп с креветками', False, 'forbidden_soup'),
        ('Креветки 21/25 с/м', 'Салат с креветками', False, 'forbidden_salad'),
        ('Креветки 21/25 с/м', 'Набор морепродуктов', False, 'forbidden_set'),
        ('Креветки 21/25 с/м', 'Лапша удон с креветкой', False, 'forbidden_noodles'),
        ('Креветки 21/25 с/м', 'Котлеты из креветок', False, 'forbidden_cutlets'),
        ('Креветки 21/25 с/м', 'Наггетсы креветочные', False, 'forbidden_nuggets'),
        
        ('Креветки 16/20 с/м', 'Креветки 21/25 с/м', False, 'caliber_mismatch'),
        ('Креветки ваннамей 21/25', 'Креветки тигровые 21/25', False, 'species_mismatch'),
        ('Креветки с/м 21/25', 'Креветки в/м 21/25', False, 'state_mismatch'),
        ('Креветки очищ 21/25', 'Креветки неочищ 21/25', False, 'form_mismatch'),
        ('Креветки с/хв 21/25', 'Креветки б/хв 21/25', False, 'tail_mismatch'),
        ('Креветки 21/25', 'Креветки в темпуре 21/25', False, 'breaded_mismatch'),
        ('Креветки 1кг 21/25', 'Креветки 10шт 21/25', False, 'uom_mismatch'),
        
        ('Креветки 21/25 с/м', 'Креветки 21/25 с/м 1кг', True, 'same_ok'),
        ('Креветки ваннамей 21/25', 'Креветки ваннамей 21/25 500г', True, 'same_species_ok'),
    ]
    
    @pytest.mark.parametrize("ref,candidate,should_pass,desc", REGRESSION_CASES)
    def test_regression_case(self, npc_data, ref, candidate, should_pass, desc):
        """Регрессионный тест для кейса."""
        result = explain_npc_match(ref, candidate)
        passed = result['strict_result']['passed']
        assert passed == should_pass, f"[{desc}] {ref} vs {candidate}: expected {should_pass}, got {passed}"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
