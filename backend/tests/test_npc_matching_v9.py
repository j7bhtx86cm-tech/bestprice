"""
BestPrice v12 - NPC Matching Tests v10
======================================

Tests for NPC-matching v10 «Нулевой мусор» + приоритет идентичности.

HARD GATES:
- PROCESSING_FORM
- CUT_TYPE
- SPECIES
- IS_BOX (в обе стороны)
- BRAND (если у REF есть)
- 85% GUARD (если бренда нет)
- SHRIMP: state/form/caliber
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from bestprice_v12.npc_matching_v9 import (
    extract_npc_signature, check_npc_strict, check_npc_similar,
    apply_npc_filter, explain_npc_match, load_npc_data,
    calculate_similarity, extract_semantic_tokens,
    ProcessingForm, CutType, NPCSignature
)


@pytest.fixture(scope="module")
def npc_data():
    load_npc_data()
    return True


# =============================================================================
# PROCESSING_FORM
# =============================================================================

class TestProcessingForm:
    @pytest.mark.parametrize("source,candidate,expected_block", [
        ('Скумбрия ж/б в масле', 'Скумбрия х/к', True),  # CANNED ≠ SMOKED
        ('Скумбрия х/к', 'Скумбрия ж/б', True),          # SMOKED ≠ CANNED
        ('Скумбрия консервы', 'Скумбрия с/м', True),     # CANNED ≠ FROZEN
        ('Лосось х/к', 'Лосось с/м', True),              # SMOKED ≠ FROZEN
    ])
    def test_processing_form_strict(self, npc_data, source, candidate, expected_block):
        result = explain_npc_match(source, candidate)
        assert result['strict_result']['passed'] != expected_block


# =============================================================================
# CUT_TYPE
# =============================================================================

class TestCutType:
    @pytest.mark.parametrize("source,candidate,expected_block", [
        ('Окунь тушка с/м', 'Окунь филе с/м', True),     # WHOLE ≠ FILLET
        ('Окунь филе с/м', 'Окунь тушка с/м', True),     # FILLET ≠ WHOLE
        ('Лосось стейк с/м', 'Лосось филе с/м', True),   # STEAK ≠ FILLET
    ])
    def test_cut_type_strict(self, npc_data, source, candidate, expected_block):
        result = explain_npc_match(source, candidate)
        assert result['strict_result']['passed'] != expected_block


# =============================================================================
# SPECIES
# =============================================================================

class TestSpecies:
    @pytest.mark.parametrize("source,candidate,expected_block", [
        ('Окунь тушка с/м', 'Сибас тушка с/м', True),
        ('Окунь филе с/м', 'Тилапия филе с/м', True),
        ('Лосось филе с/м', 'Форель филе с/м', True),
    ])
    def test_species_strict(self, npc_data, source, candidate, expected_block):
        result = explain_npc_match(source, candidate)
        assert result['strict_result']['passed'] != expected_block


# =============================================================================
# IS_BOX (в обе стороны)
# =============================================================================

class TestIsBox:
    def test_box_blocked_when_ref_not_box(self, npc_data):
        """Короб блокируется если REF не короб."""
        result = explain_npc_match('Лосось филе 1кг', 'Лосось филе 10кг/кор')
        assert result['strict_result']['passed'] == False
        assert 'IS_BOX_MISMATCH' in result['strict_result']['block_reason']
    
    def test_not_box_blocked_when_ref_is_box(self, npc_data):
        """Не-короб блокируется если REF короб."""
        result = explain_npc_match('Лосось филе 10кг/кор', 'Лосось филе 1кг')
        assert result['strict_result']['passed'] == False
        assert 'IS_BOX_MISMATCH' in result['strict_result']['block_reason']


# =============================================================================
# BRAND GATE
# =============================================================================

class TestBrandGate:
    def test_brand_ranking_only_fish(self, npc_data):
        """v11: Разные бренды НЕ блокируют для FISH, только ранжирование."""
        source = {'name_raw': 'Лосось SANGO филе с/м', 'brand_id': 'brand_sango'}
        candidate = {'name_raw': 'Лосось AGAMA филе с/м', 'brand_id': 'brand_agama'}
        
        sig_src = extract_npc_signature(source)
        sig_cand = extract_npc_signature(candidate)
        
        result = check_npc_strict(sig_src, sig_cand)
        # v11: Brand не блокирует, только ranking
        assert result.passed_strict == True
        assert result.same_brand == False
    
    def test_same_brand_passes(self, npc_data):
        """Тот же бренд проходит с выше rank."""
        source = {'name_raw': 'Лосось SANGO филе с/м', 'brand_id': 'brand_sango'}
        candidate = {'name_raw': 'Лосось SANGO филе с/м 600г', 'brand_id': 'brand_sango'}
        
        sig_src = extract_npc_signature(source)
        sig_cand = extract_npc_signature(candidate)
        
        result = check_npc_strict(sig_src, sig_cand)
        assert result.passed_strict == True
        assert result.same_brand == True
        assert result.brand_score > 0


# =============================================================================
# 85% GUARD
# =============================================================================

class TestSimilarityGuard:
    def test_low_similarity_blocked(self, npc_data):
        """Низкий similarity блокируется когда нет бренда."""
        tokens1 = extract_semantic_tokens('Лосось филе')
        tokens2 = extract_semantic_tokens('Кальмар тушка')
        
        sim = calculate_similarity(tokens1, tokens2)
        assert sim < 0.85  # Should be low
    
    def test_same_product_high_similarity(self, npc_data):
        """Одинаковый продукт имеет высокий similarity."""
        tokens1 = extract_semantic_tokens('Лосось филе')
        tokens2 = extract_semantic_tokens('Лосось филе')
        
        sim = calculate_similarity(tokens1, tokens2)
        assert sim >= 0.85  # Same tokens = high similarity


# =============================================================================
# SHRIMP RULES
# =============================================================================

class TestShrimpRules:
    @pytest.mark.parametrize("source,candidate,expected_block", [
        ('Креветки ваннамей б/г с/м 16/20', 'Креветки ваннамей б/г с/м 21/25', True),  # Caliber
        ('Креветки ваннамей б/г с/м 16/20', 'Креветки ваннамей б/г с/м 31/40', True),  # Caliber
        ('Креветки с/м 21/25', 'Креветки бланш 21/25', True),  # State
        ('Креветки ваннамей 21/25', 'Гёдза с креветкой', True),  # Gyoza excluded
    ])
    def test_shrimp_strict(self, npc_data, source, candidate, expected_block):
        result = explain_npc_match(source, candidate)
        assert result['strict_result']['passed'] != expected_block


# =============================================================================
# COUNTRY RANKING
# =============================================================================

class TestCountryRanking:
    def test_same_country_higher_score(self, npc_data):
        """Та же страна получает выше score (при прохождении Strict)."""
        # Use same product name to pass 85% guard
        source = {'name_raw': 'Лосось филе с/м Мурманск'}
        cand_ru = {'name_raw': 'Лосось филе с/м Мурманск 600г'}
        
        sig_src = extract_npc_signature(source)
        sig_ru = extract_npc_signature(cand_ru)
        
        result_ru = check_npc_strict(sig_src, sig_ru)
        
        # Should pass Strict (same product)
        assert result_ru.passed_strict == True
        # Same country bonus
        assert result_ru.same_country == True
        assert result_ru.country_score == 50


# =============================================================================
# SAME PRODUCTS (should pass)
# =============================================================================

class TestSameProducts:
    @pytest.mark.parametrize("source,candidate", [
        ('Лосось филе с/м 500г', 'Лосось филе с/м 600г'),
        ('Окунь тушка с/м 300г', 'Окунь тушка с/м 400г'),
        ('Креветки ваннамей б/г с/м 21/25', 'Креветки ваннамей б/г с/м 21/25 1кг'),
    ])
    def test_same_products_pass(self, npc_data, source, candidate):
        result = explain_npc_match(source, candidate)
        assert result['strict_result']['passed'] == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
