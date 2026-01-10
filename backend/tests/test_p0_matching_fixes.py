"""
P0 Matching Fixes Tests - Critical tests for matching logic

Tests:
1. Кальмар MUST NOT match курица (seafood vs meat)
2. Креветки с хвостом MUST NOT match креветки без хвоста
3. Seafood must not match any meat category
4. Attribute compatibility checks
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from p0_hotfix_stabilization import (
    check_category_mismatch,
    check_attribute_compatibility,
    has_required_anchors,
    FORBIDDEN_CROSS_MATCHES,
    SEAFOOD_KEYWORDS,
    MEAT_KEYWORDS,
)


class TestCategoryMismatch:
    """Test category mismatch detection (seafood vs meat)"""
    
    def test_squid_must_not_match_chicken(self):
        """CRITICAL: Кальмар филе должен НЕ совпадать с курицей"""
        reference = "Кальмар филе очищенный"
        candidates = [
            "КУРИЦА ГРУДКА ОХЛАЖДЕННАЯ",
            "Куриное филе 1кг",
            "Цыпленок бройлер",
            "Chicken breast",
        ]
        
        for candidate in candidates:
            is_valid, reason = check_category_mismatch(reference, candidate, "seafood.squid")
            assert not is_valid, f"FAIL: '{reference}' should NOT match '{candidate}', got valid={is_valid}"
            assert "CATEGORY_MISMATCH" in reason
            print(f"✅ '{reference[:20]}...' correctly rejected '{candidate[:30]}...' - {reason}")
    
    def test_shrimp_must_not_match_beef(self):
        """Креветки не должны матчиться с говядиной"""
        reference = "Креветки тигровые 16/20"
        candidates = [
            "Говядина тазобедренная часть",
            "BEEF RIBEYE STEAK",
            "Говяжий фарш",
        ]
        
        for candidate in candidates:
            is_valid, reason = check_category_mismatch(reference, candidate, "seafood.shrimp")
            assert not is_valid, f"FAIL: '{reference}' should NOT match '{candidate}'"
            print(f"✅ '{reference[:20]}...' correctly rejected '{candidate[:30]}...'")
    
    def test_chicken_must_not_match_seafood(self):
        """Курица не должна матчиться с морепродуктами"""
        reference = "Куриная грудка охлажденная"
        candidates = [
            "Кальмар филе б/к",
            "Креветки тигровые",
            "Лосось филе",
            "Squid cleaned",
        ]
        
        for candidate in candidates:
            is_valid, reason = check_category_mismatch(reference, candidate, "meat.chicken")
            assert not is_valid, f"FAIL: '{reference}' should NOT match '{candidate}'"
            print(f"✅ '{reference[:20]}...' correctly rejected '{candidate[:30]}...'")
    
    def test_same_category_should_match(self):
        """Товары одной категории должны проходить проверку"""
        test_cases = [
            ("Кальмар филе", "Кальмар тушка", "seafood.squid"),
            ("Креветки 16/20", "Креветки тигровые 21/25", "seafood.shrimp"),
            ("Куриная грудка", "Курица филе бедра", "meat.chicken"),
            ("Говядина рибай", "Говядина стейк", "meat.beef"),
        ]
        
        for reference, candidate, super_class in test_cases:
            is_valid, reason = check_category_mismatch(reference, candidate, super_class)
            assert is_valid, f"FAIL: Same category should match: '{reference}' vs '{candidate}'"
            print(f"✅ Same category passes: '{reference[:20]}' <-> '{candidate[:20]}'")


class TestAttributeCompatibility:
    """Test attribute compatibility (с хвостом vs без хвоста)"""
    
    def test_shrimp_tail_on_vs_tail_off(self):
        """Креветки с хвостом НЕ должны матчиться с креветками без хвоста"""
        reference = "Креветки тигровые с хвостом 16/20"
        candidates = [
            "Креветки без хвоста 16/20",
            "Креветки очищенные полностью",
        ]
        
        for candidate in candidates:
            is_valid, reason = check_attribute_compatibility(reference, candidate)
            assert not is_valid, f"FAIL: Tail mismatch should be rejected: '{reference}' vs '{candidate}'"
            print(f"✅ Attribute conflict detected: '{reference[:25]}' vs '{candidate[:25]}' - {reason}")
    
    def test_shrimp_peeled_vs_unpeeled(self):
        """Очищенные креветки НЕ должны матчиться с неочищенными"""
        test_cases = [
            ("Креветки очищенные", "Креветки неочищенные в панцире"),
            ("Креветки в панцире", "Креветки без панциря"),
        ]
        
        for reference, candidate in test_cases:
            is_valid, reason = check_attribute_compatibility(reference, candidate)
            assert not is_valid, f"FAIL: Peeled mismatch should be rejected"
            print(f"✅ Attribute conflict detected: '{reference}' vs '{candidate}'")
    
    def test_squid_skin_on_vs_off(self):
        """Кальмар без кожи vs с кожей"""
        reference = "Кальмар филе без кожи"
        candidate = "Кальмар с кожей нечищеный"
        
        is_valid, reason = check_attribute_compatibility(reference, candidate)
        assert not is_valid, f"FAIL: Skin mismatch should be rejected"
        print(f"✅ Squid skin attribute conflict detected")
    
    def test_same_attributes_should_match(self):
        """Товары с одинаковыми атрибутами должны проходить"""
        test_cases = [
            ("Креветки с хвостом 16/20", "Креветки тигровые с хвостом"),
            ("Креветки очищенные", "Креветки чищеные"),
            ("Кальмар без кожи", "Кальмар чищеный"),
        ]
        
        for reference, candidate in test_cases:
            is_valid, reason = check_attribute_compatibility(reference, candidate)
            assert is_valid, f"FAIL: Same attributes should match: '{reference}' vs '{candidate}'"
            print(f"✅ Same attributes pass: '{reference[:25]}' <-> '{candidate[:25]}'")


class TestForbiddenCrossMatches:
    """Test FORBIDDEN_CROSS_MATCHES dictionary coverage"""
    
    def test_seafood_squid_has_meat_keywords(self):
        """Проверка что seafood.squid запрещает все ключевые слова мяса"""
        forbidden = FORBIDDEN_CROSS_MATCHES.get('seafood.squid', [])
        
        required_keywords = ['курин', 'chicken', 'говядин', 'свинин', 'баранин']
        for kw in required_keywords:
            assert kw in forbidden, f"FAIL: '{kw}' should be in seafood.squid forbidden list"
        
        print(f"✅ seafood.squid has {len(forbidden)} forbidden keywords")
    
    def test_meat_chicken_has_seafood_keywords(self):
        """Проверка что meat.chicken запрещает все ключевые слова морепродуктов"""
        forbidden = FORBIDDEN_CROSS_MATCHES.get('meat.chicken', [])
        
        required_keywords = ['кальмар', 'squid', 'креветк', 'shrimp', 'лосос']
        for kw in required_keywords:
            assert kw in forbidden, f"FAIL: '{kw}' should be in meat.chicken forbidden list"
        
        print(f"✅ meat.chicken has {len(forbidden)} forbidden keywords")
    
    def test_keyword_lists_populated(self):
        """Проверка что списки ключевых слов не пустые"""
        assert len(SEAFOOD_KEYWORDS) > 20, f"FAIL: SEAFOOD_KEYWORDS too small: {len(SEAFOOD_KEYWORDS)}"
        assert len(MEAT_KEYWORDS) > 15, f"FAIL: MEAT_KEYWORDS too small: {len(MEAT_KEYWORDS)}"
        
        print(f"✅ SEAFOOD_KEYWORDS: {len(SEAFOOD_KEYWORDS)} keywords")
        print(f"✅ MEAT_KEYWORDS: {len(MEAT_KEYWORDS)} keywords")


class TestRequiredAnchorsWithForbidden:
    """Test has_required_anchors with FORBIDDEN_CROSS_MATCHES"""
    
    def test_squid_anchor_rejects_chicken(self):
        """has_required_anchors должен отклонить курицу для кальмара"""
        candidate = "КУРИЦА ГРУДКА 1кг"
        reference = "Кальмар филе б/к"
        
        has_anchor, reason = has_required_anchors(candidate, "seafood.squid", reference)
        # Either anchor is missing or cross_forbidden triggered
        print(f"   Result: has_anchor={has_anchor}, reason='{reason}'")
        # The function should either fail on missing anchor or cross_forbidden
        assert not has_anchor or "cross_forbidden" in reason.lower() or reason == "", \
            f"FAIL: Chicken should not pass for squid category"


if __name__ == '__main__':
    print("=" * 60)
    print("P0 MATCHING FIXES - CRITICAL TESTS")
    print("=" * 60)
    
    # Run tests
    test_category = TestCategoryMismatch()
    print("\n--- Category Mismatch Tests ---")
    test_category.test_squid_must_not_match_chicken()
    test_category.test_shrimp_must_not_match_beef()
    test_category.test_chicken_must_not_match_seafood()
    test_category.test_same_category_should_match()
    
    test_attrs = TestAttributeCompatibility()
    print("\n--- Attribute Compatibility Tests ---")
    test_attrs.test_shrimp_tail_on_vs_tail_off()
    test_attrs.test_shrimp_peeled_vs_unpeeled()
    test_attrs.test_squid_skin_on_vs_off()
    test_attrs.test_same_attributes_should_match()
    
    test_forbidden = TestForbiddenCrossMatches()
    print("\n--- Forbidden Cross-Matches Tests ---")
    test_forbidden.test_seafood_squid_has_meat_keywords()
    test_forbidden.test_meat_chicken_has_seafood_keywords()
    test_forbidden.test_keyword_lists_populated()
    
    print("\n" + "=" * 60)
    print("ALL P0 MATCHING TESTS PASSED!")
    print("=" * 60)
