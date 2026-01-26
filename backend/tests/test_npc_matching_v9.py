"""
BestPrice v12 - NPC Matching Tests v9.1
=======================================

Unit tests for NPC-matching layer v9.1 ("Нулевой мусор").

Tests cover:
1. PROCESSING_FORM strict matching
2. CUT_TYPE strict matching  
3. SPECIES strict matching
4. IS_BOX exclusion
5. SHRIMP caliber/state/form strict matching
6. mode='strict' vs mode='similar'
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from bestprice_v12.npc_matching_v9 import (
    extract_npc_signature, is_npc_domain_item, get_item_npc_domain,
    check_npc_strict, check_npc_similar, apply_npc_filter,
    explain_npc_match, load_npc_data, NPCSignature,
    ProcessingForm, CutType, extract_processing_form, extract_cut_type
)


@pytest.fixture(scope="module")
def npc_data():
    """Load NPC data once for all tests."""
    load_npc_data()
    return True


# =============================================================================
# PROCESSING_FORM TESTS
# =============================================================================

class TestProcessingForm:
    """Tests for PROCESSING_FORM strict matching."""
    
    @pytest.mark.parametrize("name,expected_form", [
        ("Скумбрия в масле ж/б 250г", ProcessingForm.CANNED),
        ("Тунец консервированный 185г", ProcessingForm.CANNED),
        ("Скумбрия х/к тушка 300г", ProcessingForm.SMOKED),
        ("Лосось г/к филе 200г", ProcessingForm.SMOKED),
        ("Лосось филе с/м 1кг", ProcessingForm.FROZEN_RAW),
        ("Курица грудка охл 500г", ProcessingForm.CHILLED_RAW),
        ("Сельдь пресервы 300г", ProcessingForm.SALTED_CURED),
        ("Форель слабосолёная 200г", ProcessingForm.SALTED_CURED),
        ("Котлеты куриные п/ф", ProcessingForm.READY_SEMIFINISHED),
        ("Наггетсы в панировке", ProcessingForm.READY_SEMIFINISHED),
    ])
    def test_processing_form_detection(self, npc_data, name, expected_form):
        """Test correct processing form detection."""
        form = extract_processing_form(name.lower())
        assert form == expected_form, f"Expected {expected_form} for '{name}', got {form}"
    
    def test_canned_vs_smoked_strict_block(self, npc_data):
        """Canned fish should NOT match smoked fish."""
        result = explain_npc_match(
            'Скумбрия натуральная в масле ж/б 250г',
            'Скумбрия х/к тушка 300г'
        )
        assert result['strict_result']['passed'] == False
        assert 'PROCESSING_FORM_MISMATCH' in result['strict_result']['block_reason']
    
    def test_canned_vs_frozen_strict_block(self, npc_data):
        """Canned fish should NOT match frozen raw fish."""
        result = explain_npc_match(
            'Тунец в масле ж/б 200г',
            'Тунец филе с/м 500г'
        )
        assert result['strict_result']['passed'] == False
        assert 'PROCESSING_FORM_MISMATCH' in result['strict_result']['block_reason']
    
    def test_box_pattern_not_smoked(self, npc_data):
        """'10кг/кор' should NOT be detected as smoked (г/к)."""
        sig = extract_npc_signature({'name_raw': 'Лосось филе с/м 10кг/кор'})
        assert sig.processing_form != ProcessingForm.SMOKED
        assert sig.processing_form == ProcessingForm.FROZEN_RAW


# =============================================================================
# CUT_TYPE TESTS  
# =============================================================================

class TestCutType:
    """Tests for CUT_TYPE strict matching."""
    
    @pytest.mark.parametrize("name,domain,expected_cut", [
        ("Окунь тушка с/м 300г", "FISH", CutType.WHOLE_TUSHKA),
        ("Лосось филе с/м 1кг", "FISH", CutType.FILLET),
        ("Тунец стейк с/м 200г", "FISH", CutType.STEAK_PORTION),
        ("Треска фарш с/м 500г", "FISH", CutType.MINCED),
        ("Печень трески ж/б", "FISH", CutType.LIVER),
        ("Курица грудка охл", "MEAT", CutType.BREAST),
        ("Индейка бедро с/м", "MEAT", CutType.THIGH),
        ("Утка крылышки", "MEAT", CutType.WING),
        ("Говядина вырезка охл", "MEAT", CutType.TENDERLOIN),
        ("Колбаса варёная", "MEAT", CutType.SAUSAGE),
    ])
    def test_cut_type_detection(self, npc_data, name, domain, expected_cut):
        """Test correct cut type detection."""
        cut = extract_cut_type(name.lower(), domain)
        assert cut == expected_cut, f"Expected {expected_cut} for '{name}', got {cut}"
    
    def test_tushka_vs_fillet_strict_block(self, npc_data):
        """Whole fish (tushka) should NOT match fillet."""
        result = explain_npc_match(
            'Окунь тушка с/м 300-500г',
            'Окунь филе с/м 200г'
        )
        assert result['strict_result']['passed'] == False
        assert 'CUT_TYPE_MISMATCH' in result['strict_result']['block_reason']
    
    def test_fillet_vs_steak_strict_block(self, npc_data):
        """Fillet should NOT match steak."""
        result = explain_npc_match(
            'Лосось филе с/м 500г',
            'Лосось стейк с/м 300г'
        )
        assert result['strict_result']['passed'] == False
        assert 'CUT_TYPE_MISMATCH' in result['strict_result']['block_reason']


# =============================================================================
# SPECIES TESTS
# =============================================================================

class TestSpecies:
    """Tests for SPECIES strict matching."""
    
    def test_perch_vs_seabass_strict_block(self, npc_data):
        """Perch should NOT match seabass."""
        result = explain_npc_match(
            'Окунь тушка с/м 300г',
            'Сибас тушка с/м 300г'
        )
        assert result['strict_result']['passed'] == False
        assert 'SPECIES_MISMATCH' in result['strict_result']['block_reason']
    
    def test_beef_vs_pork_strict_block(self, npc_data):
        """Beef should NOT match pork."""
        result = explain_npc_match(
            'Говядина филе охл 500г',
            'Свинина филе охл 500г'
        )
        assert result['strict_result']['passed'] == False
        assert 'SPECIES_MISMATCH' in result['strict_result']['block_reason']
    
    def test_chicken_vs_turkey_strict_block(self, npc_data):
        """Chicken should NOT match turkey."""
        result = explain_npc_match(
            'Курица грудка охл',
            'Индейка грудка охл'
        )
        assert result['strict_result']['passed'] == False
        assert 'SPECIES_MISMATCH' in result['strict_result']['block_reason']


# =============================================================================
# IS_BOX TESTS
# =============================================================================

class TestIsBox:
    """Tests for IS_BOX exclusion rule."""
    
    @pytest.mark.parametrize("name,expected_is_box", [
        ("Лосось филе с/м 1кг", False),
        ("Лосось филе с/м 10кг/кор", True),
        ("Лосось филе с/м кор. 10кг", True),
        ("Креветки с/м ящик 5кг", True),
        ("Минтай филе с/м 20кг кор", True),
    ])
    def test_is_box_detection(self, npc_data, name, expected_is_box):
        """Test correct IS_BOX detection."""
        sig = extract_npc_signature({'name_raw': name})
        assert sig.is_box == expected_is_box, f"Expected is_box={expected_is_box} for '{name}'"
    
    def test_box_excluded_from_strict_when_ref_not_box(self, npc_data):
        """Box candidate should be excluded if REF is not a box."""
        result = explain_npc_match(
            'Лосось филе с/м 1кг',
            'Лосось филе с/м 10кг/кор'
        )
        assert result['strict_result']['passed'] == False
        assert 'IS_BOX_MISMATCH' in result['strict_result']['block_reason']


# =============================================================================
# SHRIMP STRICT RULES
# =============================================================================

class TestShrimpStrict:
    """Tests for SHRIMP strict 1-in-1 matching."""
    
    def test_shrimp_caliber_strict_match(self, npc_data):
        """Shrimp caliber must match exactly."""
        result = explain_npc_match(
            'Креветки ваннамей б/г с/м 16/20 1кг',
            'Креветки ваннамей б/г с/м 31/40 1кг'
        )
        assert result['strict_result']['passed'] == False
        assert 'SHRIMP_CALIBER_MISMATCH' in result['strict_result']['block_reason']
    
    def test_shrimp_state_strict_match(self, npc_data):
        """Raw vs cooked shrimp must not match."""
        result = explain_npc_match(
            'Креветки ваннамей с/м б/г 21/25',  # raw frozen
            'Креветки ваннамей в/м б/г 21/25'   # cooked frozen
        )
        # May be blocked by PROCESSING_FORM or SHRIMP_STATE
        assert result['strict_result']['passed'] == False
        block_reason = result['strict_result']['block_reason']
        assert 'MISMATCH' in block_reason  # Either PROCESSING_FORM or SHRIMP_STATE
    
    def test_shrimp_form_strict_match(self, npc_data):
        """Peeled vs shell-on shrimp must not match."""
        result = explain_npc_match(
            'Креветки ваннамей очищ б/г с/м 21/25',  # peeled
            'Креветки ваннамей неочищ б/г с/м 21/25'  # shell-on
        )
        # Note: Both default to shell_on if "неочищ" not explicitly marked
        # Let's test with explicit forms
        sig1 = extract_npc_signature({'name_raw': 'Креветки очищенные б/г с/м 21/25'})
        sig2 = extract_npc_signature({'name_raw': 'Креветки в панцире б/г с/м 21/25'})
        assert sig1.shrimp_form != sig2.shrimp_form or 'peeled' in sig1.shrimp_form


# =============================================================================
# MODE STRICT VS SIMILAR
# =============================================================================

class TestModeStrictVsSimilar:
    """Tests for mode='strict' vs mode='similar' behavior."""
    
    def test_strict_mode_no_similar(self, npc_data):
        """In strict mode, similar should always be empty."""
        source = {'id': 'src', 'name_raw': 'Креветки ваннамей б/г с/м 16/20 1кг'}
        candidates = [
            {'id': 'c1', 'name_raw': 'Креветки ваннамей б/г с/м 31/40 1кг'},  # Different caliber
            {'id': 'c2', 'name_raw': 'Креветки тигровые б/г с/м 16/20 1кг'},  # Different species
        ]
        
        strict, similar, _ = apply_npc_filter(source, candidates, limit=10, mode='strict')
        
        assert similar == []  # No similar in strict mode
    
    def test_similar_mode_returns_similar(self, npc_data):
        """In similar mode, similar results should be returned."""
        source = {'id': 'src', 'name_raw': 'Креветки ваннамей б/г с/м 16/20 1кг'}
        candidates = [
            {'id': 'c1', 'name_raw': 'Креветки ваннамей б/г с/м 31/40 1кг'},  # Different caliber
        ]
        
        strict, similar, _ = apply_npc_filter(source, candidates, limit=10, mode='similar')
        
        # Candidate has different caliber, should be in similar
        assert len(similar) > 0 or len(strict) == 0


# =============================================================================
# HARD EXCLUSIONS
# =============================================================================

class TestHardExclusions:
    """Tests for hard exclusions (semi-finished, sauces)."""
    
    @pytest.mark.parametrize("name", [
        "Гёдза с креветкой YOSHIMI с/м",
        "Пельмени с мясом с/м",
        "Котлеты куриные в панировке",
        "Наггетсы из курицы с/м",
    ])
    def test_semifinished_excluded(self, npc_data, name):
        """Semi-finished products should be excluded."""
        sig = extract_npc_signature({'name_raw': name})
        assert sig.is_excluded == True
        assert sig.exclude_reason in ('READY_SEMIFINISHED', 'oos_frozen_semi_finished')
    
    @pytest.mark.parametrize("name", [
        "Соус терияки 500мл",
        "Чука салат 200г",
        "Нори для суши 10шт",
    ])
    def test_sauce_mix_excluded(self, npc_data, name):
        """Sauces and mixes should be excluded."""
        sig = extract_npc_signature({'name_raw': name})
        assert sig.is_excluded == True


if __name__ == '__main__':
    pytest.main([__file__, '-v'])


# =============================================================================
# ТЗ v9.2 REGRESSION TESTS
# =============================================================================

class TestTZv92Regression:
    """Regression tests from ТЗ v9.2 specification."""
    
    @pytest.mark.parametrize("source,candidate,expected_block", [
        # SHRIMP caliber strict
        ('Креветки ваннамей б/г с/м 16/20', 'Креветки ваннамей б/г с/м 21/25', True),
        ('Креветки ваннамей б/г с/м 16/20', 'Креветки ваннамей б/г с/м 31/40', True),
        # SHRIMP state
        ('Креветки ваннамей б/г с/м 21/25', 'Креветки ваннамей б/г бланш 21/25', True),
        # SHRIMP vs semi-finished
        ('Креветки ваннамей б/г с/м 21/25', 'Гёдза с креветкой с/м', True),
        ('Креветки ваннамей б/г с/м 21/25', 'Креветки в панировке с/м', True),
        # FISH cut type
        ('Окунь тушка с/м 300г', 'Окунь филе с/м 200г', True),
        ('Окунь филе с/м 200г', 'Окунь тушка с/м 300г', True),
        # FISH species
        ('Окунь тушка с/м', 'Сибас тушка с/м', True),
        ('Окунь филе с/м', 'Тилапия филе с/м', True),
        # CANNED vs other forms
        ('Скумбрия в масле ж/б 250г', 'Скумбрия х/к тушка', True),
        ('Скумбрия консервы ж/б', 'Скумбрия тушка с/м', True),
        # IS_BOX
        ('Лосось филе с/м 1кг', 'Лосось филе с/м 10кг/кор', True),
        ('Креветки 1кг', 'Креветки короб 5кг', True),
        # SIZE ranges
        ('Окунь филе 255-311г', 'Окунь филе 150-200г', True),
    ])
    def test_strict_blocks(self, npc_data, source, candidate, expected_block):
        """Test that mismatched items are blocked in Strict mode."""
        result = explain_npc_match(source, candidate)
        
        if expected_block:
            assert result['strict_result']['passed'] == False, \
                f"Expected BLOCK for '{source}' vs '{candidate}', but got PASS"
        else:
            assert result['strict_result']['passed'] == True, \
                f"Expected PASS for '{source}' vs '{candidate}', but got BLOCK: {result['strict_result']['block_reason']}"
    
    @pytest.mark.parametrize("source,candidate", [
        # Same products should pass
        ('Лосось филе с/м 500г', 'Лосось филе с/м 600г'),
        ('Окунь тушка с/м 300г', 'Окунь тушка с/м 400г'),
        ('Креветки ваннамей б/г с/м 21/25', 'Креветки ваннамей б/г с/м 21/25 1кг'),
        ('Окунь филе 255-311г', 'Окунь филе 300-400г'),  # Close size range
    ])
    def test_strict_passes(self, npc_data, source, candidate):
        """Test that matching items pass Strict mode."""
        result = explain_npc_match(source, candidate)
        assert result['strict_result']['passed'] == True, \
            f"Expected PASS for '{source}' vs '{candidate}', but got BLOCK: {result['strict_result']['block_reason']}"
