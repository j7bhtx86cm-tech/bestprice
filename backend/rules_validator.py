"""
RULES VALIDATOR - Автоматическая валидация правил системы BestPrice

Запускается при старте сервера для проверки:
1. Консистентность правил классификации
2. Покрытие данных в базе
3. Отсутствие cross-contamination (баранина↔свинина и т.д.)
4. Работоспособность всех компонентов

Использование:
    from rules_validator import validate_all_rules, ValidationReport
    
    report = validate_all_rules()
    if report.has_critical_errors:
        logger.error(f"Critical validation errors: {report.critical_errors}")
    else:
        logger.info(f"Validation passed: {report.summary}")
"""
import os
import re
import logging
from typing import Dict, List, Optional, Tuple, Set
from dataclasses import dataclass, field
from datetime import datetime
from pymongo import MongoClient

logger = logging.getLogger(__name__)

# MongoDB connection
MONGO_URL = os.environ.get('MONGO_URL')
DB_NAME = os.environ.get('DB_NAME', 'test_database')
SKIP_VALIDATION = os.environ.get('BESTPRICE_SKIP_RULES_VALIDATION', '').strip().lower() in {'1', 'true', 'yes', 'on'}


@dataclass
class ValidationIssue:
    """Single validation issue"""
    severity: str  # CRITICAL, WARNING, INFO
    category: str  # classification, cross_match, coverage, consistency
    message: str
    details: Optional[Dict] = None


@dataclass
class ValidationReport:
    """Complete validation report"""
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    issues: List[ValidationIssue] = field(default_factory=list)
    stats: Dict = field(default_factory=dict)
    
    @property
    def critical_errors(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == 'CRITICAL']
    
    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == 'WARNING']
    
    @property
    def has_critical_errors(self) -> bool:
        return len(self.critical_errors) > 0
    
    @property
    def summary(self) -> str:
        return f"Critical: {len(self.critical_errors)}, Warnings: {len(self.warnings)}, Info: {len([i for i in self.issues if i.severity == 'INFO'])}"
    
    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'summary': self.summary,
            'has_critical_errors': self.has_critical_errors,
            'stats': self.stats,
            'issues': [
                {
                    'severity': i.severity,
                    'category': i.category,
                    'message': i.message,
                    'details': i.details
                }
                for i in self.issues
            ]
        }


def validate_classification_rules() -> List[ValidationIssue]:
    """Validate classification rules in universal_super_class_mapper.py"""
    issues = []
    
    try:
        from universal_super_class_mapper import detect_super_class
        
        # Test cases that MUST work correctly
        test_cases = [
            # (name, expected_prefix, description)
            ('Ягнятина корейка 8 ребер', 'meat.lamb', 'Lamb rack must be lamb'),
            ('Баранина окорок', 'meat.lamb', 'Lamb leg must be lamb'),
            ('Свинина корейка б/к', 'meat.pork', 'Pork loin must be pork'),
            ('Говядина тазобедренный', 'meat.beef', 'Beef round must be beef'),
            ('ГОВЯДИНА внутренняя часть', 'meat.beef', 'Beef inner part must be beef (not chickpeas)'),
            ('Корейка б/к с/м', 'meat.pork', 'Generic koreyka defaults to pork'),
            ('СОК юдзу Yuzu 500 гр', 'beverages.juice', 'Yuzu juice must be juice'),
            ('СОК томатный с солью', 'beverages.juice', 'Tomato juice must be juice (not salt)'),
            ('ПЮРЕ юдзу 10% сахара', 'ready_meals.puree', 'Puree must be puree (not sugar)'),
            ('Кальмар тушка', 'seafood', 'Squid must be seafood'),
            ('Краб камчатский', 'seafood.crab', 'Kamchatka crab must be crab'),
            ('Крабовые палочки', 'seafood.crab', 'Crab sticks must be crab category'),
            ('НУТ 800 гр', 'vegetables.chickpeas', 'Chickpeas must be vegetables'),
            ('Мука пшеничная в/с', 'staples', 'Flour must be staples'),
            ('Оленина филе', 'meat.venison', 'Venison must be venison'),
            ('Утка целая', 'meat.duck', 'Duck must be duck'),
        ]
        
        for name, expected_prefix, description in test_cases:
            result, conf = detect_super_class(name)
            if not result.startswith(expected_prefix):
                issues.append(ValidationIssue(
                    severity='CRITICAL',
                    category='classification',
                    message=f'Classification FAILED: {description}',
                    details={
                        'input': name,
                        'expected_prefix': expected_prefix,
                        'actual': result,
                        'confidence': conf
                    }
                ))
        
        logger.info(f"Classification rules validation: {len(test_cases)} tests, {len([i for i in issues if i.category == 'classification'])} failures")
        
    except ImportError as e:
        issues.append(ValidationIssue(
            severity='CRITICAL',
            category='classification',
            message=f'Cannot import classification module: {e}'
        ))
    except Exception as e:
        issues.append(ValidationIssue(
            severity='CRITICAL',
            category='classification',
            message=f'Classification validation error: {e}'
        ))
    
    return issues


def validate_cross_match_prevention() -> List[ValidationIssue]:
    """Validate that cross-matches between incompatible categories are prevented"""
    issues = []
    
    try:
        from p0_hotfix_stabilization import FORBIDDEN_CROSS_MATCHES, REQUIRED_ANCHORS
        
        # Verify critical forbidden cross-matches exist
        critical_rules = [
            ('meat.lamb', ['свинин', 'pork']),
            ('meat.lamb.rack', ['свинин', 'pork']),
            ('meat.pork', ['баранин', 'ягнятин']),
            ('meat.pork.loin', ['баранин', 'ягнятин']),
            ('seafood.crab.kamchatka', ['палочк', 'сурими']),
            ('seafood.crab_sticks', ['камчат', 'натур']),
            ('seafood.squid', ['курин', 'chicken']),
        ]
        
        for category, required_forbidden in critical_rules:
            if category not in FORBIDDEN_CROSS_MATCHES:
                issues.append(ValidationIssue(
                    severity='WARNING',
                    category='cross_match',
                    message=f'Missing FORBIDDEN_CROSS_MATCHES for: {category}'
                ))
            else:
                actual_forbidden = FORBIDDEN_CROSS_MATCHES[category]
                for word in required_forbidden:
                    if word not in actual_forbidden:
                        issues.append(ValidationIssue(
                            severity='WARNING',
                            category='cross_match',
                            message=f'Missing forbidden word "{word}" for category {category}',
                            details={'category': category, 'missing_word': word}
                        ))
        
        # Verify required anchors exist for meat types
        meat_anchors = [
            ('meat.beef', ['говядин', 'beef']),
            ('meat.pork', ['свинин', 'pork']),
            ('meat.lamb', ['баранин', 'ягнятин', 'lamb']),
            ('meat.chicken', ['курин', 'chicken']),
        ]
        
        for category, required_words in meat_anchors:
            if category not in REQUIRED_ANCHORS:
                issues.append(ValidationIssue(
                    severity='WARNING',
                    category='cross_match',
                    message=f'Missing REQUIRED_ANCHORS for: {category}'
                ))
            else:
                actual_anchors = REQUIRED_ANCHORS[category]
                has_any = any(word in actual_anchors for word in required_words)
                if not has_any:
                    issues.append(ValidationIssue(
                        severity='WARNING',
                        category='cross_match',
                        message=f'No required anchor words found for {category}',
                        details={'category': category, 'expected_any_of': required_words}
                    ))
        
        logger.info(f"Cross-match prevention validation: {len(issues)} issues found")
        
    except ImportError as e:
        issues.append(ValidationIssue(
            severity='CRITICAL',
            category='cross_match',
            message=f'Cannot import p0_hotfix_stabilization: {e}'
        ))
    except Exception as e:
        issues.append(ValidationIssue(
            severity='CRITICAL',
            category='cross_match',
            message=f'Cross-match validation error: {e}'
        ))
    
    return issues


def validate_database_coverage() -> Tuple[List[ValidationIssue], Dict]:
    """Validate database coverage and data quality"""
    issues = []
    stats = {}
    
    try:
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        
        # Total items
        total_active = db.supplier_items.count_documents({'active': True})
        stats['total_active_items'] = total_active
        
        if total_active == 0:
            severity = 'WARNING' if SKIP_VALIDATION else 'CRITICAL'
            issues.append(ValidationIssue(
                severity=severity,
                category='coverage',
                message='No active items in supplier_items collection!'
            ))
            return issues, stats
        
        # Product core coverage
        with_product_core = db.supplier_items.count_documents({
            'active': True,
            'product_core_id': {'$exists': True, '$ne': None, '$ne': ''}
        })
        stats['product_core_coverage'] = round(with_product_core / total_active * 100, 1)
        
        if stats['product_core_coverage'] < 90:
            issues.append(ValidationIssue(
                severity='WARNING',
                category='coverage',
                message=f'Low product_core coverage: {stats["product_core_coverage"]}% (target: 90%+)'
            ))
        
        # Super class coverage
        with_super_class = db.supplier_items.count_documents({
            'active': True,
            'super_class': {'$exists': True, '$ne': None, '$ne': ''}
        })
        stats['super_class_coverage'] = round(with_super_class / total_active * 100, 1)
        
        # "Other" category - should be low
        other_count = db.supplier_items.count_documents({
            'active': True,
            'super_class': {'$regex': '^other', '$options': 'i'}
        })
        stats['other_percentage'] = round(other_count / total_active * 100, 1)
        
        if stats['other_percentage'] > 5:
            issues.append(ValidationIssue(
                severity='WARNING',
                category='coverage',
                message=f'High "other" category: {stats["other_percentage"]}% (target: <5%)'
            ))
        
        # Brand coverage
        with_brand = db.supplier_items.count_documents({
            'active': True,
            'brand_id': {'$exists': True, '$ne': None, '$ne': ''}
        })
        stats['brand_coverage'] = round(with_brand / total_active * 100, 1)
        
        # Geography coverage
        with_country = db.supplier_items.count_documents({
            'active': True,
            'origin_country': {'$exists': True, '$ne': None, '$ne': ''}
        })
        stats['geo_coverage'] = round(with_country / total_active * 100, 1)
        
        # Cross-contamination check: Lamb with pork keywords
        lamb_with_pork = db.supplier_items.count_documents({
            'active': True,
            'name_raw': {'$regex': 'баранин|ягнятин', '$options': 'i'},
            'super_class': {'$regex': 'pork', '$options': 'i'}
        })
        stats['lamb_as_pork_errors'] = lamb_with_pork
        
        if lamb_with_pork > 0:
            issues.append(ValidationIssue(
                severity='CRITICAL',
                category='cross_match',
                message=f'Found {lamb_with_pork} lamb items classified as pork!',
                details={'count': lamb_with_pork}
            ))
        
        # Pork classified as lamb
        pork_as_lamb = db.supplier_items.count_documents({
            'active': True,
            'name_raw': {'$regex': 'свинин', '$options': 'i'},
            'super_class': {'$regex': 'lamb', '$options': 'i'}
        })
        stats['pork_as_lamb_errors'] = pork_as_lamb
        
        if pork_as_lamb > 0:
            issues.append(ValidationIssue(
                severity='CRITICAL',
                category='cross_match',
                message=f'Found {pork_as_lamb} pork items classified as lamb!',
                details={'count': pork_as_lamb}
            ))
        
        # Meat classified as vegetables
        meat_as_vegetables = db.supplier_items.count_documents({
            'active': True,
            'name_raw': {'$regex': 'говядин|свинин|баранин|курин', '$options': 'i'},
            'super_class': {'$regex': 'vegetables', '$options': 'i'}
        })
        stats['meat_as_vegetables_errors'] = meat_as_vegetables
        
        if meat_as_vegetables > 0:
            issues.append(ValidationIssue(
                severity='CRITICAL',
                category='cross_match',
                message=f'Found {meat_as_vegetables} meat items classified as vegetables!',
                details={'count': meat_as_vegetables}
            ))
        
        # Meat classified as seafood
        meat_as_seafood = db.supplier_items.count_documents({
            'active': True,
            'name_raw': {'$regex': 'говядин|свинин|баранин|курин', '$options': 'i'},
            'super_class': {'$regex': 'seafood', '$options': 'i'}
        })
        stats['meat_as_seafood_errors'] = meat_as_seafood
        
        if meat_as_seafood > 0:
            issues.append(ValidationIssue(
                severity='CRITICAL',
                category='cross_match',
                message=f'Found {meat_as_seafood} meat items classified as seafood!',
                details={'count': meat_as_seafood}
            ))
        
        logger.info(f"Database coverage validation: {len(issues)} issues, stats: {stats}")
        
    except Exception as e:
        issues.append(ValidationIssue(
            severity='CRITICAL',
            category='coverage',
            message=f'Database validation error: {e}'
        ))
    
    return issues, stats


def validate_geography_extractor() -> List[ValidationIssue]:
    """Validate geography extraction rules"""
    issues = []
    
    try:
        from geography_extractor import extract_geography_from_text, FALSE_POSITIVE_EXCLUSIONS
        
        # Test cases for geography extraction
        test_cases = [
            # (name, expected_country, should_NOT_be_country, description)
            ('Говядина БЕЛАРУСЬ', 'БЕЛАРУСЬ', None, 'Belarus should be detected'),
            ('Креветки Аргентина 16/20', 'АРГЕНТИНА', None, 'Argentina should be detected'),
            ('СОУС сладкий чили', None, 'ЧИЛИ', 'Chili sauce should NOT be Chile country'),
            ('Соус Голландез', None, 'НИДЕРЛАНДЫ', 'Hollandaise should NOT be Netherlands'),
            ('Орехи грецкие', None, 'ГРЕЦИЯ', 'Greek nuts should NOT be Greece'),
            ('Краб Камчатка', 'РОССИЯ', None, 'Kamchatka implies Russia'),
        ]
        
        for name, expected_country, should_not_be, description in test_cases:
            result = extract_geography_from_text(name)
            actual_country = result.get('origin_country')
            
            if expected_country and actual_country != expected_country:
                issues.append(ValidationIssue(
                    severity='WARNING',
                    category='geography',
                    message=f'Geography extraction: {description}',
                    details={
                        'input': name,
                        'expected': expected_country,
                        'actual': actual_country
                    }
                ))
            
            if should_not_be and actual_country == should_not_be:
                issues.append(ValidationIssue(
                    severity='CRITICAL',
                    category='geography',
                    message=f'False positive geography: {description}',
                    details={
                        'input': name,
                        'false_positive_country': should_not_be
                    }
                ))
        
        # Verify false positive exclusions exist
        required_exclusions = ['чили', 'голланд']
        for pattern in required_exclusions:
            if pattern not in FALSE_POSITIVE_EXCLUSIONS:
                issues.append(ValidationIssue(
                    severity='WARNING',
                    category='geography',
                    message=f'Missing false positive exclusion for: {pattern}'
                ))
        
        logger.info(f"Geography validation: {len(issues)} issues found")
        
    except ImportError as e:
        issues.append(ValidationIssue(
            severity='WARNING',
            category='geography',
            message=f'Cannot import geography_extractor: {e}'
        ))
    except Exception as e:
        issues.append(ValidationIssue(
            severity='WARNING',
            category='geography',
            message=f'Geography validation error: {e}'
        ))
    
    return issues


def validate_unit_normalizer() -> List[ValidationIssue]:
    """Validate unit normalizer functionality"""
    issues = []
    
    try:
        from unit_normalizer import parse_pack_from_text, UnitType
        
        # Test cases
        test_cases = [
            ('500 гр', UnitType.WEIGHT, 0.5),
            ('1 кг', UnitType.WEIGHT, 1.0),
            ('1л', UnitType.VOLUME, 1.0),
            ('500 мл', UnitType.VOLUME, 0.5),
            ('10 шт', UnitType.PIECE, 10),
        ]
        
        for text, expected_type, expected_value in test_cases:
            result = parse_pack_from_text(text)
            if result.unit_type != expected_type:
                issues.append(ValidationIssue(
                    severity='WARNING',
                    category='unit_parser',
                    message=f'Unit type mismatch for "{text}"',
                    details={
                        'expected_type': expected_type.value,
                        'actual_type': result.unit_type.value
                    }
                ))
        
        logger.info(f"Unit normalizer validation: {len(issues)} issues found")
        
    except ImportError as e:
        issues.append(ValidationIssue(
            severity='WARNING',
            category='unit_parser',
            message=f'Cannot import unit_normalizer: {e}'
        ))
    except Exception as e:
        issues.append(ValidationIssue(
            severity='WARNING',
            category='unit_parser',
            message=f'Unit normalizer validation error: {e}'
        ))
    
    return issues


def validate_all_rules(strict: bool = False) -> ValidationReport:
    """
    Run all validation checks and return a comprehensive report.
    
    Args:
        strict: If True, raises exception on critical errors
        
    Returns:
        ValidationReport with all issues and stats
    """
    logger.info("=" * 60)
    logger.info("STARTING RULES VALIDATION")
    logger.info("=" * 60)
    
    report = ValidationReport()
    
    # 1. Classification rules
    logger.info("Validating classification rules...")
    report.issues.extend(validate_classification_rules())
    
    # 2. Cross-match prevention
    logger.info("Validating cross-match prevention...")
    report.issues.extend(validate_cross_match_prevention())
    
    # 3. Database coverage
    logger.info("Validating database coverage...")
    coverage_issues, coverage_stats = validate_database_coverage()
    report.issues.extend(coverage_issues)
    report.stats.update(coverage_stats)
    
    # 4. Geography extractor
    logger.info("Validating geography extractor...")
    report.issues.extend(validate_geography_extractor())
    
    # 5. Unit normalizer
    logger.info("Validating unit normalizer...")
    report.issues.extend(validate_unit_normalizer())
    
    # Summary
    logger.info("=" * 60)
    logger.info(f"VALIDATION COMPLETE: {report.summary}")
    logger.info("=" * 60)
    
    if SKIP_VALIDATION and report.has_critical_errors:
        logger.warning("BESTPRICE_SKIP_RULES_VALIDATION enabled – downgrading critical issues to warnings.")
        for issue in report.critical_errors:
            issue.severity = 'WARNING'

    if report.has_critical_errors:
        for error in report.critical_errors:
            logger.error(f"CRITICAL: {error.message}")
        
        if strict:
            raise RuntimeError(f"Validation failed with {len(report.critical_errors)} critical errors")
    
    if report.warnings:
        for warning in report.warnings:
            logger.warning(f"WARNING: {warning.message}")
    
    return report


def print_validation_report(report: ValidationReport) -> str:
    """Generate a human-readable validation report"""
    lines = []
    lines.append("=" * 70)
    lines.append("RULES VALIDATION REPORT")
    lines.append(f"Timestamp: {report.timestamp}")
    lines.append("=" * 70)
    lines.append("")
    
    # Stats
    if report.stats:
        lines.append("📊 DATABASE STATISTICS:")
        lines.append("-" * 40)
        for key, value in report.stats.items():
            if 'error' in key.lower():
                status = '❌' if value > 0 else '✅'
            elif 'coverage' in key.lower() or 'percentage' in key.lower():
                status = '✅' if value >= 90 else ('⚠️' if value >= 70 else '❌')
            else:
                status = '📈'
            lines.append(f"  {status} {key}: {value}")
        lines.append("")
    
    # Critical errors
    if report.critical_errors:
        lines.append("🔴 CRITICAL ERRORS:")
        lines.append("-" * 40)
        for issue in report.critical_errors:
            lines.append(f"  ❌ [{issue.category}] {issue.message}")
            if issue.details:
                for k, v in issue.details.items():
                    lines.append(f"      {k}: {v}")
        lines.append("")
    
    # Warnings
    if report.warnings:
        lines.append("🟡 WARNINGS:")
        lines.append("-" * 40)
        for issue in report.warnings:
            lines.append(f"  ⚠️ [{issue.category}] {issue.message}")
        lines.append("")
    
    # Summary
    lines.append("=" * 70)
    lines.append(f"SUMMARY: {report.summary}")
    if report.has_critical_errors:
        lines.append("🔴 VALIDATION FAILED - Critical errors must be fixed!")
    else:
        lines.append("✅ VALIDATION PASSED")
    lines.append("=" * 70)
    
    return "\n".join(lines)


if __name__ == "__main__":
    # Run validation and print report
    logging.basicConfig(level=logging.INFO)
    
    report = validate_all_rules(strict=False)
    print(print_validation_report(report))
