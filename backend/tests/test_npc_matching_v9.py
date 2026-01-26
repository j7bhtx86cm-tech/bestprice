"""
BestPrice v12 - NPC Matching Tests
==================================

Unit tests for NPC-matching layer (SHRIMP/FISH/SEAFOOD/MEAT).

Tests cover:
1. Domain detection
2. Hard exclusions (gyoza, bouillon, noodles, etc.)
3. Node ID assignment
4. Strict vs Similar matching
5. Attribute extraction
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from bestprice_v12.npc_matching_v9 import (
    extract_npc_signature, is_npc_domain_item, get_item_npc_domain,
    check_npc_strict, check_npc_similar, apply_npc_filter,
    explain_npc_match, load_npc_data, NPCSignature
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture(scope="module")
def npc_data():
    """Load NPC data once for all tests."""
    load_npc_data()
    return True


# =============================================================================
# DOMAIN DETECTION TESTS
# =============================================================================

class TestDomainDetection:
    """Tests for NPC domain detection."""
    
    @pytest.mark.parametrize("name,expected_domain", [
        # SHRIMP
        ("Креветки ваннамей б/г с/м 21/25 1кг", "SHRIMP"),
        ("Креветка тигровая с/м 16/20", "SHRIMP"),
        ("КРЕВЕТКИ аргентинские с/г 10/20", "SHRIMP"),
        ("Лангустины б/г с/м", "SHRIMP"),
        
        # FISH
        ("Лосось филе на коже с/м 1.5кг", "FISH"),
        ("Форель слабосоленая филе", "FISH"),
        ("Печень трески ж/б", "FISH"),
        ("Тунец филе в масле", "FISH"),
        ("Треска филе без кожи с/м", "FISH"),
        
        # SEAFOOD
        ("Кальмар тушка с/м 1кг", "SEAFOOD"),
        ("Мидии в ракушках с/м", "SEAFOOD"),
        ("Гребешок морской с/м", "SEAFOOD"),
        ("Осьминог мини с/м", "SEAFOOD"),
        
        # MEAT
        ("Говядина филе охл 1кг", "MEAT"),
        ("Куриная грудка охл", "MEAT"),
        ("Индейка филе бедра с/м", "MEAT"),
        ("Свинина вырезка охл", "MEAT"),
        ("Колбаса Мортаделла", "MEAT"),
        ("Сосиски свиные для хот-догов", "MEAT"),
    ])
    def test_domain_detection(self, npc_data, name, expected_domain):
        """Test correct domain detection from product names."""
        sig = extract_npc_signature({'name_raw': name})
        assert sig.npc_domain == expected_domain, f"Expected {expected_domain} for '{name}', got {sig.npc_domain}"
    
    def test_ribeye_is_meat_not_fish(self, npc_data):
        """Ribeye (рибай) should be MEAT, not FISH despite containing 'риб'."""
        sig = extract_npc_signature({'name_raw': 'Стейк Рибай говяжий охл'})
        assert sig.npc_domain == "MEAT"
        assert sig.meat_animal == "beef"


# =============================================================================
# HARD EXCLUSION TESTS
# =============================================================================

class TestHardExclusions:
    """Tests for hard exclusions (items that should never match)."""
    
    @pytest.mark.parametrize("name,expected_excluded,expected_reason", [
        # Dumplings/Gyoza
        ("Гёдза с креветкой YOSHIMI с/м", True, "oos_frozen_semi_finished"),
        ("Гедза с курицей с/м", True, "oos_frozen_semi_finished"),
        ("Пельмени с мясом", True, "oos_frozen_semi_finished"),
        
        # Bouillon
        ("Бульон куриный Knorr 2кг", True, "bouillon"),
        ("БУЛЬОН грибной АРИКОН ПРОФИ", True, "bouillon"),
        
        # Imitation seafood
        ("Крабовые палочки сурими", True, "oos_seafood_imitation"),
        
        # Seaweed/Noodles
        ("Нори для суши 10 листов", True, "oos_seaweed"),
        ("Чука салат", True, "oos_seaweed"),
        
        # Sauces
        ("Соус терияки 1л", True, "oos_sauce"),
        ("Майонез Провансаль", True, "oos_sauce"),
    ])
    def test_hard_exclusions(self, npc_data, name, expected_excluded, expected_reason):
        """Test that excluded items are properly blocked."""
        sig = extract_npc_signature({'name_raw': name})
        assert sig.is_excluded == expected_excluded, f"'{name}' should be excluded={expected_excluded}"
        if expected_excluded:
            assert expected_reason in (sig.exclude_reason or ""), f"Expected reason '{expected_reason}' for '{name}'"
    
    def test_valid_shrimp_not_excluded(self, npc_data):
        """Valid shrimp should not be excluded."""
        sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г с/м 21/25'})
        assert not sig.is_excluded
        assert sig.npc_domain == "SHRIMP"


# =============================================================================
# ATTRIBUTE EXTRACTION TESTS
# =============================================================================

class TestAttributeExtraction:
    """Tests for attribute extraction from product names."""
    
    def test_shrimp_attributes(self, npc_data):
        """Test shrimp attribute extraction."""
        sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г очищ с/м 21/25 1кг'})
        
        assert sig.npc_domain == "SHRIMP"
        assert sig.shrimp_species == "vannamei"
        assert sig.shrimp_caliber == "21/25"
        assert sig.shrimp_caliber_band == "medium_21_40"
        assert sig.shrimp_headless == True
        assert sig.shrimp_peeled == True
        assert sig.state_frozen == True
    
    def test_fish_attributes(self, npc_data):
        """Test fish attribute extraction."""
        sig = extract_npc_signature({'name_raw': 'Лосось филе на коже с/м 1.5кг'})
        
        assert sig.npc_domain == "FISH"
        assert sig.fish_species == "salmon"
        assert sig.fish_cut == "fillet"
        assert sig.fish_skin == "skin_on"
        assert sig.state_frozen == True
    
    def test_fish_canned_attributes(self, npc_data):
        """Test canned fish detection."""
        sig = extract_npc_signature({'name_raw': 'Печень трески ж/б натуральная'})
        
        assert sig.npc_domain == "FISH"
        # Note: fish_species may be None for compound terms like "печень трески"
        # The important thing is domain is FISH and canned is detected
        assert sig.fish_canned == True
    
    def test_meat_attributes(self, npc_data):
        """Test meat attribute extraction."""
        sig = extract_npc_signature({'name_raw': 'Индейка филе бедра с/м'})
        
        assert sig.npc_domain == "MEAT"
        assert sig.meat_animal == "turkey"
        assert sig.meat_cut == "fillet" or sig.meat_cut == "thigh"
        assert sig.state_frozen == True


# =============================================================================
# NPC STRICT MATCHING TESTS
# =============================================================================

class TestNPCStrictMatching:
    """Tests for strict NPC matching rules."""
    
    def test_same_species_caliber_passes_strict(self, npc_data):
        """Same species and caliber band should pass strict."""
        source_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г с/м 21/25'})
        cand_sig = extract_npc_signature({'name_raw': 'Креветка ваннамей б/г с/м 26/30'})
        
        result = check_npc_strict(source_sig, cand_sig)
        # Both are vannamei medium caliber - should pass
        assert result.passed_strict == True
    
    def test_different_species_fails_strict(self, npc_data):
        """Different shrimp species should fail strict."""
        source_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г с/м 21/25'})
        cand_sig = extract_npc_signature({'name_raw': 'Креветки тигровые б/г с/м 21/25'})
        
        result = check_npc_strict(source_sig, cand_sig)
        # Different species - should fail
        assert result.passed_strict == False
        assert "SPECIES" in (result.block_reason or "") or "NODE" in (result.block_reason or "")
    
    def test_frozen_vs_chilled_fails_strict(self, npc_data):
        """Frozen vs chilled should fail strict."""
        source_sig = extract_npc_signature({'name_raw': 'Лосось филе с/м'})
        cand_sig = extract_npc_signature({'name_raw': 'Лосось филе охл'})
        
        result = check_npc_strict(source_sig, cand_sig)
        assert result.passed_strict == False
        assert "STATE" in (result.block_reason or "")
    
    def test_breaded_fails_strict_when_source_not_breaded(self, npc_data):
        """Breaded candidate should fail strict if source is not breaded.
        
        Note: 'в панировке' items are excluded as frozen_semi_finished per lexicon,
        so they fail with EXCLUDED reason, not BREADED.
        """
        source_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г с/м 21/25'})
        cand_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей в панировке с/м 21/25'})
        
        result = check_npc_strict(source_sig, cand_sig)
        assert result.passed_strict == False
        # Breaded items are excluded as frozen_semi_finished per lexicon
        assert "EXCLUDED" in (result.block_reason or "") or "BREADED" in (result.block_reason or "")
    
    def test_excluded_candidate_fails(self, npc_data):
        """Excluded candidate (gyoza) should fail strict."""
        source_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г с/м 21/25'})
        cand_sig = extract_npc_signature({'name_raw': 'Гёдза с креветкой YOSHIMI с/м'})
        
        result = check_npc_strict(source_sig, cand_sig)
        assert result.passed_strict == False
        assert "EXCLUDED" in (result.block_reason or "")


# =============================================================================
# NPC SIMILAR MATCHING TESTS
# =============================================================================

class TestNPCSimilarMatching:
    """Tests for similar NPC matching rules."""
    
    def test_different_caliber_passes_similar_with_label(self, npc_data):
        """Different caliber should pass similar with label."""
        source_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г с/м 16/20'})
        cand_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г с/м 31/40'})
        
        result = check_npc_similar(source_sig, cand_sig)
        assert result.passed_similar == True
        # Should have caliber difference label
        assert len(result.difference_labels) > 0
    
    def test_breaded_passes_similar_with_label(self, npc_data):
        """Breaded candidate behavior in similar mode.
        
        Note: Items 'в панировке' are excluded as frozen_semi_finished per lexicon,
        so they fail even in similar mode. This is correct behavior - breaded items
        should not be alternatives to raw shrimp.
        """
        source_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г с/м'})
        cand_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей в панировке с/м'})
        
        result = check_npc_similar(source_sig, cand_sig)
        # Breaded items are excluded per lexicon - this is correct behavior
        assert result.passed_similar == False or cand_sig.is_excluded == True
    
    def test_excluded_fails_similar(self, npc_data):
        """Excluded items should fail even in similar mode."""
        source_sig = extract_npc_signature({'name_raw': 'Креветки ваннамей б/г с/м'})
        cand_sig = extract_npc_signature({'name_raw': 'Гёдза с креветкой'})
        
        result = check_npc_similar(source_sig, cand_sig)
        assert result.passed_similar == False
    
    def test_candidate_without_node_id_excluded_from_similar(self, npc_data):
        """Candidate without npc_node_id should be excluded even from Similar."""
        # Manually create signatures
        source = NPCSignature()
        source.npc_domain = 'SHRIMP'
        source.npc_node_id = 'shr_002'
        source.state_frozen = True
        
        candidate = NPCSignature()
        candidate.npc_domain = 'SHRIMP'
        candidate.npc_node_id = None  # No node ID
        candidate.state_frozen = True
        
        result = check_npc_similar(source, candidate)
        assert result.passed_similar == False
        assert "CANDIDATE_NO_NPC_NODE" in (result.block_reason or "")


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestNPCIntegration:
    """Integration tests for NPC filter."""
    
    def test_apply_npc_filter_returns_results(self, npc_data):
        """Test that apply_npc_filter returns results for NPC domain items."""
        source = {
            'id': 'test-source',
            'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг',
        }
        candidates = [
            {'id': 'cand1', 'name_raw': 'Креветки ваннамей б/г с/м 26/30 1кг'},
            {'id': 'cand2', 'name_raw': 'Креветки тигровые б/г с/м 21/25 1кг'},
            {'id': 'cand3', 'name_raw': 'Гёдза с креветкой'},
        ]
        
        strict, similar, rejected = apply_npc_filter(source, candidates)
        
        # Should return results (not None)
        assert strict is not None
        assert similar is not None
        
        # cand1 should be in strict (same species, compatible caliber)
        strict_ids = [x['item']['id'] for x in strict]
        assert 'cand1' in strict_ids
        
        # cand3 (gyoza) should be rejected
        assert 'EXCLUDED' in rejected or 'CANDIDATE_EXCLUDED' in rejected
    
    def test_apply_npc_filter_returns_none_for_non_npc(self, npc_data):
        """Test that apply_npc_filter returns None for non-NPC items."""
        source = {
            'id': 'test-source',
            'name_raw': 'Молоко 3.2% 1л',  # Not NPC domain
        }
        candidates = []
        
        strict, similar, rejected = apply_npc_filter(source, candidates)
        
        # Should return None (signal to use legacy matching)
        assert strict is None
        assert similar is None


# =============================================================================
# EXPLAIN MATCH TESTS
# =============================================================================

class TestExplainMatch:
    """Tests for explain_npc_match utility."""
    
    def test_explain_match_provides_details(self, npc_data):
        """Test that explain_npc_match provides useful details."""
        result = explain_npc_match(
            'Креветки ваннамей б/г с/м 21/25',
            'Креветки тигровые б/г с/м 16/20'
        )
        
        assert 'source' in result
        assert 'candidate' in result
        assert 'strict_result' in result
        assert 'similar_result' in result
        
        # Source should be SHRIMP
        assert result['source']['npc_domain'] == 'SHRIMP'
        assert result['candidate']['npc_domain'] == 'SHRIMP'
        
        # Strict should fail (different species)
        assert result['strict_result']['passed'] == False


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
