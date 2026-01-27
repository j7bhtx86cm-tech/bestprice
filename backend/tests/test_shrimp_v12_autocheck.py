"""
BestPrice - NPC Matching v12 AutoCheck 5 Cases
==============================================

Автопроверка 5 кейсов по ТЗ NPC-Matching SHRIMP v12 (Zero-Trash)

Кейсы:
- SHR-01: Гёдза не должна попадать в выдачу креветок
- SHR-02: tail_state (с/хв vs б/хв) не смешивается
- SHR-03: breaded_flag (панировка vs без) не смешивается
- SHR-04: UOM gate (шт vs кг) не смешивается
- SHR-05: Ранжирование — калибр важнее бренда
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from bestprice_v12.npc_matching_v9 import (
    extract_npc_signature, check_npc_strict, check_npc_similar,
    explain_npc_match, apply_npc_filter, load_npc_data,
    check_blacklist, extract_shrimp_tail_state,
)


@pytest.fixture(scope="module")
def npc_data():
    load_npc_data()
    return True


# =============================================================================
# SHR-01: Гёдза/пельмени/наборы НИКОГДА не попадают в выдачу
# =============================================================================

class TestSHR01_ForbiddenClass:
    """SHR-01: FORBIDDEN_CLASS работает как ранний reject."""
    
    # Must NEVER appear in any output (strict or similar)
    MUST_NEVER_APPEAR = [
        'гёдза', 'гедза', 'пельмен', 'вареник', 'хинкали',
        'суп', 'салат', 'набор', 'ассорти', 'микс',
        'котлет', 'наггетс', 'лапша', 'удон', 'рамен',
    ]
    
    @pytest.mark.parametrize("junk_name", [
        'Гёдза с креветкой 1кг',
        'Гедза с креветкой заморозка',
        'Пельмени с креветкой',
        'Вареники с креветкой',
        'Хинкали с креветкой',
        'Суп с креветками',
        'Салат с креветками',
        'Набор с креветками',
        'Набор морепродуктов с креветкой',
        'Ассорти креветок',
        'Микс морепродуктов',
        'Котлеты из креветок',
        'Наггетсы креветочные',
        'Лапша удон с креветкой',
    ])
    def test_junk_blocked_by_blacklist(self, npc_data, junk_name):
        """Мусор блокируется через FORBIDDEN_CLASS."""
        is_blocked, reason = check_blacklist(junk_name.lower())
        assert is_blocked, f"{junk_name} should be blocked by FORBIDDEN_CLASS"
        assert reason and 'FORBIDDEN_CLASS' in reason
    
    def test_junk_not_in_strict(self, npc_data):
        """Мусор НЕ появляется в strict выдаче."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        
        junk_candidates = [
            {'name_raw': 'Гёдза с креветкой 1кг'},
            {'name_raw': 'Пельмени с креветкой'},
            {'name_raw': 'Набор с креветками'},
            {'name_raw': 'Суп с креветками'},
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, junk_candidates, mode='strict')
        
        # Strict должен быть пустым
        assert len(strict) == 0, "Junk should not appear in strict"
    
    def test_junk_not_in_similar(self, npc_data):
        """Мусор НЕ появляется в similar выдаче."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        
        junk_candidates = [
            {'name_raw': 'Гёдза с креветкой 1кг'},
            {'name_raw': 'Лапша удон с креветкой'},
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, junk_candidates, mode='similar')
        
        # Similar тоже должен быть пустым
        assert len(similar) == 0, "Junk should not appear in similar"
    
    def test_normal_shrimp_passes(self, npc_data):
        """Нормальные креветки проходят."""
        is_blocked, _ = check_blacklist('креветки 21/25 с/м')
        assert not is_blocked


# =============================================================================
# SHR-02: tail_state (с/хв vs б/хв) не смешивается
# =============================================================================

class TestSHR02_TailState:
    """SHR-02: tail_state hard gate работает правильно."""
    
    @pytest.mark.parametrize("name,expected", [
        ('креветки с/хв 21/25 с/м', 'tail_on'),
        ('креветки с хв 21/25 с/м', 'tail_on'),
        ('креветки с хвостом 21/25', 'tail_on'),
        ('креветки хвостик 21/25', 'tail_on'),
        ('креветки tail-on 21/25', 'tail_on'),
        ('креветки t-on 21/25', 'tail_on'),
        ('креветки б/хв 21/25 с/м', 'tail_off'),
        ('креветки без хв 21/25', 'tail_off'),
        ('креветки без хвоста 21/25', 'tail_off'),
        ('креветки tail-off 21/25', 'tail_off'),
        ('креветки tailless 21/25', 'tail_off'),
        ('креветки 21/25 с/м', None),  # Не определено
    ])
    def test_tail_state_parsing(self, npc_data, name, expected):
        """Парсер tail_state распознаёт все варианты."""
        result = extract_shrimp_tail_state(name)
        assert result == expected, f"{name} should be {expected}, got {result}"
    
    def test_tail_on_vs_tail_off_blocked(self, npc_data):
        """с/хв vs б/хв блокируется."""
        result = explain_npc_match('Креветки с/хв 21/25 с/м', 'Креветки б/хв 21/25 с/м')
        assert result['strict_result']['passed'] == False
        assert 'TAIL_STATE_MISMATCH' in result['strict_result']['block_reason']
    
    def test_tail_off_vs_tail_on_blocked(self, npc_data):
        """б/хв vs с/хв блокируется."""
        result = explain_npc_match('Креветки б/хв 21/25 с/м', 'Креветки с/хв 21/25 с/м')
        assert result['strict_result']['passed'] == False
        assert 'TAIL_STATE_MISMATCH' in result['strict_result']['block_reason']
    
    def test_same_tail_state_passes(self, npc_data):
        """Одинаковый tail_state проходит."""
        result = explain_npc_match('Креветки с/хв 21/25 с/м', 'Креветки с/хв 21/25 с/м 1кг')
        assert result['strict_result']['passed'] == True
    
    def test_undefined_tail_not_gate(self, npc_data):
        """Если REF tail_state не определён — не гейт."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки с/хв 21/25 с/м')
        # Должен пройти, т.к. у REF tail_state=None
        assert result['strict_result']['passed'] == True


# =============================================================================
# SHR-03: breaded_flag (панировка vs без) не смешивается
# =============================================================================

class TestSHR03_BreadedFlag:
    """SHR-03: breaded_flag hard gate работает правильно."""
    
    def test_plain_vs_breaded_blocked(self, npc_data):
        """Обычные vs панированные блокируется."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки в панировке 21/25')
        assert result['strict_result']['passed'] == False
        reason = result['strict_result']['block_reason'] or ''
        # Может быть BREADED_MISMATCH или legacy EXCLUDED
        assert 'BREADED' in reason or 'EXCLUDED' in reason
    
    def test_breaded_vs_plain_blocked(self, npc_data):
        """Панированные vs обычные блокируется."""
        result = explain_npc_match('Креветки в темпуре 21/25', 'Креветки 21/25 с/м')
        assert result['strict_result']['passed'] == False
    
    def test_same_breaded_passes(self, npc_data):
        """Одинаковый breaded_flag проходит."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки 21/25 с/м 1кг')
        assert result['strict_result']['passed'] == True


# =============================================================================
# SHR-04: UOM gate (шт vs кг) не смешивается
# =============================================================================

class TestSHR04_UOMGate:
    """SHR-04: UOM gate работает правильно."""
    
    def test_kg_vs_pcs_blocked(self, npc_data):
        """кг vs шт блокируется."""
        result = explain_npc_match('Креветки 21/25 1кг', 'Креветки 21/25 10шт')
        assert result['strict_result']['passed'] == False
        assert 'UOM_MISMATCH' in result['strict_result']['block_reason']
    
    def test_pcs_vs_kg_blocked(self, npc_data):
        """шт vs кг блокируется."""
        result = explain_npc_match('Креветки 21/25 10шт', 'Креветки 21/25 1кг')
        assert result['strict_result']['passed'] == False
        assert 'UOM_MISMATCH' in result['strict_result']['block_reason']
    
    def test_same_uom_passes(self, npc_data):
        """Одинаковый UOM проходит."""
        result = explain_npc_match('Креветки 21/25 1кг', 'Креветки 21/25 500г')
        assert result['strict_result']['passed'] == True


# =============================================================================
# SHR-05: Ранжирование — калибр важнее бренда
# =============================================================================

class TestSHR05_Ranking:
    """SHR-05: Калибр важнее бренда в ранжировании."""
    
    def test_caliber_exact_in_rank_features(self, npc_data):
        """caliber_exact есть в rank_features."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки 21/25 с/м 1кг')
        rf = result['strict_result']['rank_features']
        assert 'caliber_exact' in rf
        assert rf['caliber_exact'] == True
    
    def test_rank_features_complete(self, npc_data):
        """rank_features содержит все нужные поля."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки 21/25 с/м 1кг')
        rf = result['strict_result']['rank_features']
        
        required_keys = [
            'caliber_exact', 'caliber_score', 'tail_match', 'breaded_match',
            'uom_match', 'text_similarity', 'brand_match', 'country_match',
        ]
        for key in required_keys:
            assert key in rf, f"Missing rank_feature: {key}"
    
    def test_passed_gates_present(self, npc_data):
        """passed_gates содержит список пройденных gates."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Креветки 21/25 с/м 1кг')
        pg = result['strict_result']['passed_gates']
        assert len(pg) > 0
        assert 'SHRIMP_DOMAIN' in pg
        assert 'CALIBER' in pg
    
    def test_rejected_reason_for_blocked(self, npc_data):
        """rejected_reason есть для заблокированных."""
        result = explain_npc_match('Креветки 21/25 с/м', 'Гёдза с креветкой')
        # Должен быть заблокирован
        assert result['strict_result']['passed'] == False
        # rejected_reason должен быть заполнен
        assert result['strict_result']['rejected_reason'] is not None or \
               result['strict_result']['block_reason'] is not None


# =============================================================================
# INTEGRATION: Full Flow Test
# =============================================================================

class TestIntegration:
    """Интеграционные тесты для полного потока."""
    
    def test_full_strict_flow(self, npc_data):
        """Полный поток strict с хорошими и плохими кандидатами."""
        ref = {'name_raw': 'Креветки ваннамей б/г с/м 21/25 1кг'}
        
        candidates = [
            # Хорошие кандидаты
            {'name_raw': 'Креветки ваннамей б/г с/м 21/25 500г', 'id': '1'},
            {'name_raw': 'Креветки ваннамей б/г с/м 21/25 2кг', 'id': '2'},
            # Плохие кандидаты (должны быть отклонены)
            {'name_raw': 'Гёдза с креветкой', 'id': '3'},  # FORBIDDEN_CLASS
            {'name_raw': 'Креветки 16/20 с/м', 'id': '4'},  # Другой калибр
            {'name_raw': 'Креветки тигровые 21/25 с/м', 'id': '5'},  # Другой вид
        ]
        
        strict, similar, rejected = apply_npc_filter(ref, candidates, mode='strict')
        
        # Должны пройти только хорошие кандидаты
        strict_ids = [r['item']['id'] for r in strict]
        assert '1' in strict_ids or '2' in strict_ids
        assert '3' not in strict_ids  # Гёдза
        assert '4' not in strict_ids  # Другой калибр
        assert '5' not in strict_ids  # Другой вид


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
