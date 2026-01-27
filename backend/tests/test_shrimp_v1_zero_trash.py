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
    """Brand gate и Country ranking."""
    
    def test_brand_same_passes(self, npc_data):
        """Тот же бренд проходит."""
        source = {'name_raw': 'Креветки VICI 21/25 с/м', 'brand_id': 'vici'}
        candidate = {'name_raw': 'Креветки VICI 21/25 с/м 1кг', 'brand_id': 'vici'}
        
        sig_s = extract_npc_signature(source)
        sig_c = extract_npc_signature(candidate)
        result = check_npc_strict(sig_s, sig_c)
        
        assert result.passed_strict == True
        assert result.same_brand == True
    
    def test_brand_different_blocked(self, npc_data):
        """Другой бренд блокируется."""
        source = {'name_raw': 'Креветки VICI 21/25 с/м', 'brand_id': 'vici'}
        candidate = {'name_raw': 'Креветки AGAMA 21/25 с/м', 'brand_id': 'agama'}
        
        sig_s = extract_npc_signature(source)
        sig_c = extract_npc_signature(candidate)
        result = check_npc_strict(sig_s, sig_c)
        
        assert result.passed_strict == False
        assert 'BRAND_MISMATCH' in result.block_reason
    
    def test_brand_missing_blocked_for_shrimp(self, npc_data):
        """Если REF с брендом, candidate без бренда — blocked."""
        source = {'name_raw': 'Креветки VICI 21/25 с/м', 'brand_id': 'vici'}
        candidate = {'name_raw': 'Креветки 21/25 с/м'}
        
        sig_s = extract_npc_signature(source)
        sig_c = extract_npc_signature(candidate)
        result = check_npc_strict(sig_s, sig_c)
        
        assert result.passed_strict == False
        assert 'BRAND_MISSING' in result.block_reason
    
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
        assert 'SHRIMP_CALIBER_MISMATCH' in rejected
    
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
