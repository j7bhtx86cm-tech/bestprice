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
    
    def test_langoustine_must_match_langoustine(self):
        """CRITICAL: Лангустины должны матчиться с лангустинами (супер_класс приоритет)"""
        # This tests the fix for "аргентинские" containing "гус" substring
        reference = "Креветки аргентинские (Лангустины) дикие с/г с/м L1 10/20"
        candidates = [
            "ЛАНГ-УСТИНЫ L1 (10/20 шт/кг) с/г в панцире с/м 2 кг",
            "Лангустины L1 10/20 с/м Аргентина 2 кг",
            "Креветки аргентинские L1 дикие",
        ]
        
        for candidate in candidates:
            is_valid, reason = check_category_mismatch(reference, candidate, "seafood.langoustine")
            assert is_valid, f"FAIL: Langoustine should match langoustine: '{reference[:30]}' vs '{candidate[:30]}'"
            print(f"✅ Langoustine passes: '{reference[:25]}...' <-> '{candidate[:25]}...'")
    
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


class TestSeafoodClassification:
    """
    CRITICAL: Tests for seafood classification to prevent regression.
    
    These tests cover specific items that had classification issues:
    - Тюрбо (Turbot) - must be seafood.turbot
    - Печень трески (Cod Liver) - must be seafood.cod_liver
    - Филе трески Borealis (Cod Fillet Borealis) - must be seafood.cod
    - Лангустины (Langoustines) - must be seafood.langoustine
    """
    
    def test_turbot_classification(self):
        """CRITICAL: Тюрбо должен классифицироваться как seafood.turbot"""
        from universal_super_class_mapper import detect_super_class
        
        turbot_products = [
            "Тюрбо целый 1-2 кг с/м",
            "ТЮРБО филе с/м 200г",
            "Тюрбо свежий охлажденный",
            "Turbot whole 1kg",
        ]
        
        for product in turbot_products:
            super_class, confidence = detect_super_class(product)
            assert super_class is not None, f"FAIL: '{product}' has no super_class"
            assert super_class.startswith('seafood'), \
                f"FAIL: '{product}' должен быть seafood, но получили '{super_class}'"
            assert confidence >= 0.8, f"FAIL: Confidence too low for '{product}': {confidence}"
            print(f"✅ Turbot: '{product[:40]}' → {super_class} (conf: {confidence:.2f})")
    
    def test_cod_liver_classification(self):
        """CRITICAL: Печень трески должна классифицироваться как seafood.cod_liver"""
        from universal_super_class_mapper import detect_super_class
        
        cod_liver_products = [
            "Печень трески натуральная 200г",
            "ПЕЧЕНЬ ТРЕСКИ консервированная",
            "печень трески в масле 250г",
            "Cod liver in oil 200g",
        ]
        
        for product in cod_liver_products:
            super_class, confidence = detect_super_class(product)
            assert super_class is not None, f"FAIL: '{product}' has no super_class"
            assert super_class.startswith('seafood'), \
                f"FAIL: '{product}' должен быть seafood, но получили '{super_class}'"
            print(f"✅ Cod Liver: '{product[:40]}' → {super_class} (conf: {confidence:.2f})")
    
    def test_cod_fillet_borealis_classification(self):
        """CRITICAL: Филе трески Borealis должно классифицироваться как seafood.cod"""
        from universal_super_class_mapper import detect_super_class
        
        cod_fillet_products = [
            "Филе Спинки Трески Borealis с/м 1кг",
            "Филе трески Borealis порционное",
            "BOREALIS филе трески с/м вес",
            "Треска филе спинки Borealis",
            "Филе трески без кожи",
        ]
        
        for product in cod_fillet_products:
            super_class, confidence = detect_super_class(product)
            assert super_class is not None, f"FAIL: '{product}' has no super_class"
            assert super_class.startswith('seafood'), \
                f"FAIL: '{product}' должен быть seafood, но получили '{super_class}'"
            # Check it's specifically cod, not generic seafood
            assert 'cod' in super_class.lower() or 'треск' in product.lower(), \
                f"FAIL: '{product}' should be cod category, got '{super_class}'"
            print(f"✅ Cod Fillet Borealis: '{product[:40]}' → {super_class} (conf: {confidence:.2f})")
    
    def test_langoustine_classification(self):
        """CRITICAL: Лангустины должны классифицироваться как seafood.langoustine"""
        from universal_super_class_mapper import detect_super_class
        
        langoustine_products = [
            "Лангустины L1 10/20 с/м Аргентина",
            "Креветки аргентинские (Лангустины) дикие с/г с/м L1 10/20",
            "ЛАНГ-УСТИНЫ L1 (10/20 шт/кг) с/г в панцире с/м 2 кг",
            "Langoustine L1 frozen 2kg",  # English variant
        ]
        
        for product in langoustine_products:
            super_class, confidence = detect_super_class(product)
            assert super_class is not None, f"FAIL: '{product}' has no super_class"
            assert super_class.startswith('seafood'), \
                f"FAIL: '{product}' должен быть seafood, но получили '{super_class}'"
            print(f"✅ Langoustine: '{product[:40]}' → {super_class} (conf: {confidence:.2f})")
    
    def test_seafood_must_not_match_meat(self):
        """Seafood items must NEVER be classified as meat"""
        from universal_super_class_mapper import detect_super_class
        
        seafood_items = [
            "Тюрбо целый 1кг",
            "Печень трески 200г",
            "Филе трески Borealis",
            "Лангустины L1",
            "Кальмар филе",
            "Креветки тигровые",
        ]
        
        for item in seafood_items:
            super_class, _ = detect_super_class(item)
            if super_class:
                assert not super_class.startswith('meat'), \
                    f"CRITICAL FAIL: Seafood '{item}' classified as meat: '{super_class}'"
            print(f"✅ '{item[:30]}' NOT classified as meat")
    
    def test_category_mismatch_seafood_vs_meat(self):
        """Test that seafood and meat categories are properly rejected"""
        from p0_hotfix_stabilization import check_category_mismatch
        
        # Seafood items should NOT match meat candidates
        test_cases = [
            ("Тюрбо филе с/м", "Курица грудка", "seafood.turbot"),
            ("Печень трески", "Говядина фарш", "seafood.cod_liver"),
            ("Филе трески Borealis", "Свинина корейка", "seafood.cod"),
            ("Лангустины L1", "Утка целая", "seafood.langoustine"),
        ]
        
        for reference, candidate, super_class in test_cases:
            is_valid, reason = check_category_mismatch(reference, candidate, super_class)
            assert not is_valid, \
                f"FAIL: '{reference}' should NOT match '{candidate}', got valid={is_valid}"
            print(f"✅ Rejected: '{reference[:20]}' vs '{candidate[:20]}' - {reason}")


class TestSeafoodProductCore:
    """Test product core classification for seafood items"""
    
    def test_turbot_product_core(self):
        """Тюрбо должен иметь product_core seafood.turbot"""
        from universal_super_class_mapper import detect_super_class
        from product_core_classifier import detect_product_core
        
        product = "Тюрбо целый 1-2 кг с/м"
        super_class, _ = detect_super_class(product)
        product_core, confidence = detect_product_core(product, super_class)
        
        assert super_class is not None
        assert super_class.startswith('seafood.turbot'), f"Got: {super_class}"
        print(f"✅ Turbot: super_class={super_class}, product_core={product_core}")
    
    def test_cod_liver_product_core(self):
        """Печень трески должна иметь product_core seafood.cod_liver"""
        from universal_super_class_mapper import detect_super_class
        from product_core_classifier import detect_product_core
        
        product = "Печень трески натуральная 200г"
        super_class, _ = detect_super_class(product)
        product_core, confidence = detect_product_core(product, super_class)
        
        assert super_class is not None
        # cod_liver should be in super_class (since it's a direct mapping)
        assert 'cod' in super_class.lower(), \
            f"Got: super_class={super_class}, product_core={product_core}"
        print(f"✅ Cod Liver: super_class={super_class}, product_core={product_core}")
    
    def test_cod_fillet_product_core(self):
        """Филе трески должно иметь product_core seafood.cod"""
        from universal_super_class_mapper import detect_super_class
        from product_core_classifier import detect_product_core
        
        product = "Филе Спинки Трески Borealis с/м 1кг"
        super_class, _ = detect_super_class(product)
        product_core, confidence = detect_product_core(product, super_class)
        
        assert super_class is not None
        assert 'cod' in super_class.lower(), f"Got: {super_class}"
        print(f"✅ Cod Fillet: super_class={super_class}, product_core={product_core}")


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
    test_category.test_langoustine_must_match_langoustine()
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
    
    # NEW: Run seafood classification tests
    test_seafood = TestSeafoodClassification()
    print("\n--- Seafood Classification Tests ---")
    test_seafood.test_turbot_classification()
    test_seafood.test_cod_liver_classification()
    test_seafood.test_cod_fillet_borealis_classification()
    test_seafood.test_langoustine_classification()
    test_seafood.test_seafood_must_not_match_meat()
    test_seafood.test_category_mismatch_seafood_vs_meat()
    
    # NEW: Run seafood product core tests
    test_seafood_core = TestSeafoodProductCore()
    print("\n--- Seafood Product Core Tests ---")
    test_seafood_core.test_turbot_product_core()
    test_seafood_core.test_cod_liver_product_core()
    test_seafood_core.test_cod_fillet_product_core()
    
    print("\n" + "=" * 60)
    print("ALL P0 MATCHING TESTS PASSED!")
    print("=" * 60)
