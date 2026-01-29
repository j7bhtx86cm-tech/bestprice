"""
FISH_FILLET Regression Tests v1
================================

80+ тестовых кейсов для npc_fish_fillet_v1:
- ref: "тушка" → strict НЕ должен показывать "филе"
- ref: "филе" → strict НЕ должен показывать "тушка/стейк"
- ref: "в панировке" → strict только "в панировке"
- species mismatch: треска ≠ минтай
- skin mismatch: на коже ≠ без кожи
- state mismatch: охл ≠ с/м
- uom mismatch: кг ≠ шт
- pack tolerance: 200г/150г допускаем, но сортируем "ближе сначала"
"""

import pytest
import sys
sys.path.insert(0, '/app/backend')

from bestprice_v12.npc_fish_fillet import (
    extract_fish_fillet_signature,
    check_fish_fillet_strict,
    apply_fish_fillet_filter,
    extract_fish_species,
    extract_fish_cut_type,
    extract_skin_flag,
    extract_breaded_flag,
    extract_fish_state,
    looks_like_fish_fillet,
    detect_fish_fillet_domain,
    check_fish_fillet_blacklist,
    FishCutType,
    FishState,
    SkinFlag,
)


# ============================================================================
# Test Data: REF Items
# ============================================================================

REF_FILLET_COD_SKINOFF = {
    'id': 'ref_fillet_cod_skinoff',
    'name_raw': 'Филе трески без кожи с/м 1кг',
    'price': 800,
    'unit_type': 'kg',
}

REF_FILLET_POLLOCK_SKINON = {
    'id': 'ref_fillet_pollock_skinon',
    'name_raw': 'Минтай филе на коже с/м 500г',
    'price': 350,
    'unit_type': 'kg',
}

REF_FILLET_SALMON_CHILLED = {
    'id': 'ref_fillet_salmon_chilled',
    'name_raw': 'Лосось филе охл Норвегия 1кг',
    'price': 1500,
    'unit_type': 'kg',
}

REF_FILLET_BREADED = {
    'id': 'ref_fillet_breaded',
    'name_raw': 'Филе минтая в панировке 500г',
    'price': 400,
    'unit_type': 'pcs',
}

REF_WHOLE_COD = {
    'id': 'ref_whole_cod',
    'name_raw': 'Треска тушка с/м б/г 1кг',
    'price': 500,
    'unit_type': 'kg',
}

REF_STEAK_SALMON = {
    'id': 'ref_steak_salmon',
    'name_raw': 'Стейк лосося с/м 300г',
    'price': 600,
    'unit_type': 'pcs',
}


# ============================================================================
# Test Data: Candidate Items
# ============================================================================

# === VALID ALTERNATIVES (должны пройти strict) ===
CAND_FILLET_COD_SKINOFF_CHEAP = {
    'id': 'cand_fillet_cod_skinoff_cheap',
    'name_raw': 'Треска филе без кожи с/м 1кг',
    'price': 750,
    'unit_type': 'kg',
}

CAND_FILLET_COD_SKINOFF_EXPENSIVE = {
    'id': 'cand_fillet_cod_skinoff_expensive',
    'name_raw': 'Филе трески б/к свежемороженое 1кг Россия',
    'price': 900,
    'unit_type': 'kg',
}

CAND_FILLET_POLLOCK_SKINON_SIMILAR = {
    'id': 'cand_fillet_pollock_skinon_similar',
    'name_raw': 'Филе минтая на коже с/м 500г',
    'price': 330,
    'unit_type': 'kg',
}

CAND_FILLET_SALMON_CHILLED_SIMILAR = {
    'id': 'cand_fillet_salmon_chilled_similar',
    'name_raw': 'Семга филе охлаждённая 1кг Фарерские о-ва',
    'price': 1600,
    'unit_type': 'kg',
}

CAND_FILLET_BREADED_SIMILAR = {
    'id': 'cand_fillet_breaded_similar',
    'name_raw': 'Минтай филе в кляре 500г',
    'price': 380,
    'unit_type': 'pcs',
}


# === INVALID ALTERNATIVES (должны быть отвергнуты) ===
CAND_WHOLE_COD_WRONG_CUT = {
    'id': 'cand_whole_cod_wrong_cut',
    'name_raw': 'Треска тушка с/м потрошёная 1кг',
    'price': 450,
    'unit_type': 'kg',
}

CAND_STEAK_COD_WRONG_CUT = {
    'id': 'cand_steak_cod_wrong_cut',
    'name_raw': 'Стейк трески с/м 500г',
    'price': 400,
    'unit_type': 'kg',
}

CAND_FILLET_POLLOCK_WRONG_SPECIES = {
    'id': 'cand_fillet_pollock_wrong_species',
    'name_raw': 'Минтай филе без кожи с/м 1кг',
    'price': 400,
    'unit_type': 'kg',
}

CAND_FILLET_COD_SKINON_WRONG_SKIN = {
    'id': 'cand_fillet_cod_skinon_wrong_skin',
    'name_raw': 'Филе трески на коже с/м 1кг',
    'price': 780,
    'unit_type': 'kg',
}

CAND_FILLET_COD_CHILLED_WRONG_STATE = {
    'id': 'cand_fillet_cod_chilled_wrong_state',
    'name_raw': 'Филе трески охлаждённое 1кг',
    'price': 1000,
    'unit_type': 'kg',
}

CAND_FILLET_COD_BREADED_WRONG = {
    'id': 'cand_fillet_cod_breaded_wrong',
    'name_raw': 'Филе трески в панировке 500г',
    'price': 500,
    'unit_type': 'pcs',
}

CAND_FILLET_NOT_BREADED_WRONG = {
    'id': 'cand_fillet_not_breaded_wrong',
    'name_raw': 'Минтай филе с/м 500г',
    'price': 300,
    'unit_type': 'kg',
}

CAND_BLACKLISTED_KOTLETA = {
    'id': 'cand_blacklisted_kotleta',
    'name_raw': 'Котлеты из трески 500г',
    'price': 400,
    'unit_type': 'pcs',
}

CAND_BLACKLISTED_CONSERV = {
    'id': 'cand_blacklisted_conserv',
    'name_raw': 'Треска в масле консервы ж/б 200г',
    'price': 150,
    'unit_type': 'pcs',
}

CAND_BLACKLISTED_SOUP = {
    'id': 'cand_blacklisted_soup',
    'name_raw': 'Суп рыбный с треской 300г',
    'price': 100,
    'unit_type': 'pcs',
}


# ============================================================================
# SECTION 1: Species Detection Tests (10 cases)
# ============================================================================

class TestFishSpeciesDetection:
    """Тесты определения вида рыбы"""
    
    def test_cod_species(self):
        """Треска определяется как cod"""
        assert extract_fish_species('филе трески б/к') == 'cod'
        assert extract_fish_species('треска тушка') == 'cod'
    
    def test_pollock_species(self):
        """Минтай определяется как pollock"""
        assert extract_fish_species('минтай филе') == 'pollock'
        assert extract_fish_species('филе минтая') == 'pollock'
    
    def test_salmon_species(self):
        """Лосось/семга определяется как salmon"""
        assert extract_fish_species('лосось филе') == 'salmon'
        assert extract_fish_species('семга стейк') == 'salmon'
        assert extract_fish_species('сёмга охл') == 'salmon'
    
    def test_trout_species(self):
        """Форель определяется как trout"""
        assert extract_fish_species('форель филе') == 'trout'
    
    def test_hake_species(self):
        """Хек определяется как hake"""
        assert extract_fish_species('хек филе') == 'hake'
    
    def test_pangasius_species(self):
        """Пангасиус определяется как pangasius"""
        assert extract_fish_species('пангасиус филе') == 'pangasius'
    
    def test_tilapia_species(self):
        """Тилапия определяется как tilapia"""
        assert extract_fish_species('тилапия филе') == 'tilapia'
    
    def test_pink_salmon_species(self):
        """Горбуша определяется как pink_salmon"""
        assert extract_fish_species('горбуша филе') == 'pink_salmon'
    
    def test_perch_species(self):
        """Окунь/судак определяется как perch"""
        assert extract_fish_species('окунь филе') == 'perch'
    
    def test_unknown_species(self):
        """Неизвестный вид возвращает None"""
        assert extract_fish_species('рыба филе') is None
        assert extract_fish_species('морепродукты') is None


# ============================================================================
# SECTION 2: Cut Type Detection Tests (12 cases)
# ============================================================================

class TestFishCutTypeDetection:
    """Тесты определения типа разделки"""
    
    def test_fillet_detection(self):
        """FILLET определяется корректно"""
        assert extract_fish_cut_type('филе трески') == FishCutType.FILLET
        assert extract_fish_cut_type('треска fillet') == FishCutType.FILLET
    
    def test_whole_detection(self):
        """WHOLE (тушка) определяется корректно"""
        assert extract_fish_cut_type('тушка трески') == FishCutType.WHOLE
        assert extract_fish_cut_type('треска целая') == FishCutType.WHOLE
        assert extract_fish_cut_type('треска н/р') == FishCutType.WHOLE
    
    def test_steak_detection(self):
        """STEAK определяется корректно"""
        assert extract_fish_cut_type('стейк лосося') == FishCutType.STEAK
        assert extract_fish_cut_type('лосось порционный') == FishCutType.STEAK
    
    def test_minced_detection(self):
        """MINCED (фарш) определяется корректно"""
        assert extract_fish_cut_type('фарш из трески') == FishCutType.MINCED
    
    def test_carcass_detection(self):
        """CARCASS (каркас) определяется корректно"""
        assert extract_fish_cut_type('каркас лосося') == FishCutType.CARCASS
        assert extract_fish_cut_type('хребет лосося') == FishCutType.CARCASS
    
    def test_fillet_priority_over_whole(self):
        """FILLET имеет приоритет над WHOLE"""
        # "филе" должен победить над "потрошёная"
        assert extract_fish_cut_type('филе трески потрошёная') == FishCutType.FILLET
    
    def test_headless_is_whole(self):
        """б/г без филе = WHOLE"""
        assert extract_fish_cut_type('треска б/г с/м') == FishCutType.WHOLE
    
    def test_gutted_is_whole(self):
        """Потрошёная = WHOLE"""
        assert extract_fish_cut_type('треска потрошёная') == FishCutType.WHOLE
    
    def test_no_cut_type(self):
        """Без разделки = None"""
        assert extract_fish_cut_type('треска свежая') is None
    
    def test_chunk_as_steak(self):
        """Кусок → STEAK"""
        assert extract_fish_cut_type('кусок лосося') == FishCutType.STEAK
    
    def test_portion_as_steak(self):
        """Порционный → STEAK"""
        assert extract_fish_cut_type('треска порционная') == FishCutType.STEAK
    
    def test_liver_detection(self):
        """Печень определяется как LIVER"""
        assert extract_fish_cut_type('печень трески') == FishCutType.LIVER


# ============================================================================
# SECTION 3: Skin Flag Detection Tests (8 cases)
# ============================================================================

class TestSkinFlagDetection:
    """Тесты определения состояния кожи"""
    
    def test_skin_off_bk(self):
        """б/к = skin_off"""
        assert extract_skin_flag('филе трески б/к') == SkinFlag.SKIN_OFF
    
    def test_skin_off_bez_kozhi(self):
        """без кожи = skin_off"""
        assert extract_skin_flag('филе трески без кожи') == SkinFlag.SKIN_OFF
    
    def test_skin_off_skinless(self):
        """skinless = skin_off"""
        assert extract_skin_flag('cod fillet skinless') == SkinFlag.SKIN_OFF
    
    def test_skin_on_na_kozhe(self):
        """на коже = skin_on"""
        assert extract_skin_flag('филе минтая на коже') == SkinFlag.SKIN_ON
    
    def test_skin_on_s_kozhei(self):
        """с кожей = skin_on"""
        assert extract_skin_flag('филе лосося с кожей') == SkinFlag.SKIN_ON
    
    def test_skin_on_english(self):
        """skin-on = skin_on"""
        assert extract_skin_flag('salmon fillet skin-on') == SkinFlag.SKIN_ON
    
    def test_skin_unknown(self):
        """Без указания = None"""
        assert extract_skin_flag('филе трески с/м') is None
    
    def test_skin_off_priority(self):
        """skin_off проверяется первым"""
        # Маловероятный кейс, но важен порядок
        assert extract_skin_flag('без кожи на коже') == SkinFlag.SKIN_OFF


# ============================================================================
# SECTION 4: Breaded Flag Detection Tests (6 cases)
# ============================================================================

class TestBreadedFlagDetection:
    """Тесты определения панировки"""
    
    def test_breaded_panir(self):
        """панир* = breaded"""
        assert extract_breaded_flag('филе в панировке') is True
    
    def test_breaded_klyar(self):
        """в кляре = breaded"""
        assert extract_breaded_flag('минтай в кляре') is True
    
    def test_breaded_tempura(self):
        """темпура = breaded"""
        assert extract_breaded_flag('креветки темпура') is True
    
    def test_breaded_panko(self):
        """панко = breaded"""
        assert extract_breaded_flag('филе трески панко') is True
    
    def test_not_breaded(self):
        """Обычное филе = not breaded"""
        assert extract_breaded_flag('филе трески с/м') is False
    
    def test_breaded_hrustyash(self):
        """хрустящ* = breaded"""
        assert extract_breaded_flag('минтай хрустящий') is True


# ============================================================================
# SECTION 5: State Detection Tests (6 cases)
# ============================================================================

class TestStateDetection:
    """Тесты определения состояния"""
    
    def test_frozen_sm(self):
        """с/м = frozen"""
        assert extract_fish_state('филе трески с/м') == FishState.FROZEN
    
    def test_frozen_zamorozh(self):
        """замороженн* = frozen"""
        assert extract_fish_state('минтай замороженный') == FishState.FROZEN
    
    def test_chilled_ohl(self):
        """охл = chilled"""
        assert extract_fish_state('лосось охл') == FishState.CHILLED
    
    def test_chilled_ohlazhdenniy(self):
        """охлаждённ* = chilled"""
        assert extract_fish_state('семга охлаждённая') == FishState.CHILLED
    
    def test_fresh_svezh(self):
        """свежий → chilled (fresh)"""
        assert extract_fish_state('форель свежая') == FishState.CHILLED
    
    def test_state_unknown(self):
        """Без указания = None"""
        assert extract_fish_state('филе трески') is None


# ============================================================================
# SECTION 6: Domain Detection Tests (8 cases)
# ============================================================================

class TestDomainDetection:
    """Тесты определения домена FISH_FILLET"""
    
    def test_fillet_cod_is_fish_fillet(self):
        """Филе трески = FISH_FILLET"""
        assert detect_fish_fillet_domain('филе трески с/м') == 'FISH_FILLET'
    
    def test_fillet_pollock_is_fish_fillet(self):
        """Филе минтая = FISH_FILLET"""
        assert detect_fish_fillet_domain('минтай филе б/к') == 'FISH_FILLET'
    
    def test_whole_cod_not_fish_fillet(self):
        """Тушка трески НЕ FISH_FILLET"""
        assert detect_fish_fillet_domain('треска тушка с/м') is None
    
    def test_steak_salmon_not_fish_fillet(self):
        """Стейк лосося НЕ FISH_FILLET"""
        assert detect_fish_fillet_domain('стейк лосося') is None
    
    def test_conserv_not_fish_fillet(self):
        """Консервы НЕ FISH_FILLET (blacklist)"""
        assert detect_fish_fillet_domain('треска в масле консервы') is None
    
    def test_kotlety_not_fish_fillet(self):
        """Котлеты НЕ FISH_FILLET (blacklist)"""
        assert detect_fish_fillet_domain('котлеты из трески') is None
    
    def test_breaded_fillet_is_fish_fillet(self):
        """Панированное филе = FISH_FILLET"""
        assert detect_fish_fillet_domain('минтай в кляре') == 'FISH_FILLET'
    
    def test_no_species_not_fish_fillet(self):
        """Без species = NOT FISH_FILLET"""
        assert detect_fish_fillet_domain('филе рыбное') is None


# ============================================================================
# SECTION 7: Blacklist Tests (8 cases)
# ============================================================================

class TestBlacklist:
    """Тесты blacklist (FORBIDDEN_CLASS)"""
    
    def test_kotlety_blacklisted(self):
        """Котлеты в blacklist"""
        is_bl, reason = check_fish_fillet_blacklist('котлеты из минтая')
        assert is_bl is True
        assert 'котлет' in reason.lower()
    
    def test_conserv_blacklisted(self):
        """Консервы в blacklist"""
        is_bl, _ = check_fish_fillet_blacklist('треска в масле консервы')
        assert is_bl is True
    
    def test_soup_blacklisted(self):
        """Суп в blacklist"""
        is_bl, _ = check_fish_fillet_blacklist('суп рыбный')
        assert is_bl is True
    
    def test_salat_blacklisted(self):
        """Салат в blacklist"""
        is_bl, _ = check_fish_fillet_blacklist('салат с треской')
        assert is_bl is True
    
    def test_gedza_blacklisted(self):
        """Гёдза в blacklist"""
        is_bl, _ = check_fish_fillet_blacklist('гёдза с рыбой')
        assert is_bl is True
    
    def test_kopch_blacklisted(self):
        """Копчёное в blacklist"""
        is_bl, _ = check_fish_fillet_blacklist('лосось х/к')
        assert is_bl is True
    
    def test_ikra_blacklisted(self):
        """Икра в blacklist"""
        is_bl, _ = check_fish_fillet_blacklist('икра лососевая')
        assert is_bl is True
    
    def test_fillet_not_blacklisted(self):
        """Филе НЕ в blacklist"""
        is_bl, _ = check_fish_fillet_blacklist('филе трески с/м')
        assert is_bl is False


# ============================================================================
# SECTION 8: Strict Gate Tests - CUT_TYPE (10 cases) CRITICAL
# ============================================================================

class TestStrictGateCutType:
    """КРИТИЧЕСКИЕ тесты: CUT_TYPE gate (тушка ≠ филе ≠ стейк)"""
    
    def test_fillet_vs_whole_rejected(self):
        """REF: филе → CAND: тушка = REJECTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = CAND_WHOLE_COD_WRONG_CUT
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'CUT_TYPE' in result.block_reason or 'NOT_FISH_FILLET' in result.block_reason
    
    def test_fillet_vs_steak_rejected(self):
        """REF: филе → CAND: стейк = REJECTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = CAND_STEAK_COD_WRONG_CUT
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'CUT_TYPE' in result.block_reason or 'NOT_FISH_FILLET' in result.block_reason
    
    def test_whole_vs_fillet_rejected(self):
        """REF: тушка → CAND: филе = REJECTED (REF not FISH_FILLET)"""
        ref = REF_WHOLE_COD
        cand = CAND_FILLET_COD_SKINOFF_CHEAP
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        # REF тушка не классифицируется как FISH_FILLET
        assert result.passed_strict is False
    
    def test_fillet_vs_fillet_accepted(self):
        """REF: филе → CAND: филе = ACCEPTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = CAND_FILLET_COD_SKINOFF_CHEAP
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
        assert 'CUT_TYPE' in result.passed_gates
    
    def test_steak_vs_fillet_rejected(self):
        """REF: стейк → CAND: филе = REJECTED (REF not FISH_FILLET)"""
        ref = REF_STEAK_SALMON
        cand = CAND_FILLET_SALMON_CHILLED_SIMILAR
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        # REF стейк не классифицируется как FISH_FILLET
        assert result.passed_strict is False
    
    def test_fillet_minced_rejected(self):
        """REF: филе → CAND: фарш = REJECTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = {
            'id': 'cand_minced',
            'name_raw': 'Фарш из трески 500г',
            'price': 300,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
    
    def test_fillet_carcass_rejected(self):
        """REF: филе → CAND: каркас = REJECTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = {
            'id': 'cand_carcass',
            'name_raw': 'Каркас трески с/м 1кг',
            'price': 200,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
    
    def test_cut_type_exact_match_required(self):
        """CUT_TYPE должен совпадать точно"""
        # Оба FILLET
        ref = REF_FILLET_POLLOCK_SKINON
        cand = CAND_FILLET_POLLOCK_SKINON_SIMILAR
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
        assert result.same_cut_type is True
    
    def test_fillet_vs_liver_rejected(self):
        """REF: филе → CAND: печень = REJECTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = {
            'id': 'cand_liver',
            'name_raw': 'Печень трески натуральная 200г',
            'price': 150,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
    
    def test_tushka_never_in_fillet_strict(self):
        """Тушка НИКОГДА не попадает в strict для филе"""
        ref = REF_FILLET_COD_SKINOFF
        candidates = [
            {'id': 'c1', 'name_raw': 'Треска тушка с/м 1кг', 'price': 400},
            {'id': 'c2', 'name_raw': 'Треска целая б/г с/м 1кг', 'price': 450},
            {'id': 'c3', 'name_raw': 'Треска н/р свежемороженая 1кг', 'price': 350},
        ]
        
        strict, similar, rejected = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        assert len(strict) == 0
        # Все должны быть отвергнуты по CUT_TYPE или NOT_FISH_FILLET
        assert sum(rejected.values()) > 0


# ============================================================================
# SECTION 9: Strict Gate Tests - SPECIES (8 cases)
# ============================================================================

class TestStrictGateSpecies:
    """Тесты SPECIES gate: треска ≠ минтай ≠ лосось"""
    
    def test_cod_vs_pollock_rejected(self):
        """REF: треска → CAND: минтай = REJECTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = CAND_FILLET_POLLOCK_WRONG_SPECIES
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'SPECIES_MISMATCH' in result.block_reason
    
    def test_cod_vs_salmon_rejected(self):
        """REF: треска → CAND: лосось = REJECTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = {
            'id': 'cand_salmon',
            'name_raw': 'Филе лосося б/к с/м 1кг',
            'price': 1200,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'SPECIES' in result.block_reason
    
    def test_same_species_accepted(self):
        """REF: треска → CAND: треска = ACCEPTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = CAND_FILLET_COD_SKINOFF_CHEAP
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
        assert result.same_species is True
    
    def test_salmon_vs_trout_rejected(self):
        """REF: лосось → CAND: форель = REJECTED"""
        ref = REF_FILLET_SALMON_CHILLED
        cand = {
            'id': 'cand_trout',
            'name_raw': 'Форель филе охл 1кг',
            'price': 1400,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'SPECIES' in result.block_reason
    
    def test_semga_equals_salmon(self):
        """Сёмга = Лосось (тот же species)"""
        ref = REF_FILLET_SALMON_CHILLED  # "Лосось"
        cand = CAND_FILLET_SALMON_CHILLED_SIMILAR  # "Семга"
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
        assert result.same_species is True
    
    def test_pollock_vs_hake_rejected(self):
        """REF: минтай → CAND: хек = REJECTED"""
        ref = REF_FILLET_POLLOCK_SKINON
        cand = {
            'id': 'cand_hake',
            'name_raw': 'Хек филе на коже с/м 500г',
            'price': 320,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'SPECIES' in result.block_reason
    
    def test_species_priority_over_brand(self):
        """SPECIES важнее бренда"""
        ref = REF_FILLET_COD_SKINOFF
        cand = {
            'id': 'cand_wrong_species_same_brand',
            'name_raw': 'Минтай филе б/к с/м 1кг',  # Другой вид
            'price': 400,
            'brand_id': ref.get('brand_id'),  # Тот же бренд (если бы был)
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False  # Бренд не спасает от SPECIES mismatch
    
    def test_species_priority_over_price(self):
        """SPECIES важнее цены"""
        ref = REF_FILLET_COD_SKINOFF  # Треска, 800₽
        cand = {
            'id': 'cand_cheaper_wrong_species',
            'name_raw': 'Минтай филе б/к с/м 1кг',
            'price': 300,  # Дешевле!
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False  # Цена не спасает


# ============================================================================
# SECTION 10: Strict Gate Tests - BREADED (6 cases)
# ============================================================================

class TestStrictGateBreaded:
    """Тесты BREADED gate: панировка ≠ без панировки"""
    
    def test_breaded_vs_not_breaded_rejected(self):
        """REF: в панировке → CAND: без панировки = REJECTED"""
        ref = REF_FILLET_BREADED
        cand = CAND_FILLET_NOT_BREADED_WRONG
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'BREADED' in result.block_reason
    
    def test_not_breaded_vs_breaded_rejected(self):
        """REF: без панировки → CAND: в панировке = REJECTED"""
        ref = REF_FILLET_POLLOCK_SKINON  # без панировки
        cand = {
            'id': 'cand_breaded',
            'name_raw': 'Минтай филе в панировке на коже 500г',
            'price': 380,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'BREADED' in result.block_reason
    
    def test_breaded_vs_breaded_accepted(self):
        """REF: в панировке → CAND: в панировке = ACCEPTED"""
        ref = REF_FILLET_BREADED
        cand = CAND_FILLET_BREADED_SIMILAR
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
        assert result.same_breaded is True
    
    def test_not_breaded_vs_not_breaded_accepted(self):
        """REF: без панировки → CAND: без панировки = ACCEPTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = CAND_FILLET_COD_SKINOFF_CHEAP
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
        assert result.same_breaded is True
    
    def test_klyar_equals_panirovka(self):
        """в кляре = в панировке"""
        ref = REF_FILLET_BREADED  # "в панировке"
        cand = CAND_FILLET_BREADED_SIMILAR  # "в кляре"
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
    
    def test_tempura_equals_panirovka(self):
        """темпура = панировка"""
        ref = REF_FILLET_BREADED
        cand = {
            'id': 'cand_tempura',
            'name_raw': 'Минтай темпура 500г',
            'price': 420,
            'unit_type': 'pcs',
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True


# ============================================================================
# SECTION 11: Strict Gate Tests - SKIN (6 cases)
# ============================================================================

class TestStrictGateSkin:
    """Тесты SKIN gate: на коже ≠ без кожи"""
    
    def test_skinoff_vs_skinon_rejected(self):
        """REF: б/к → CAND: на коже = REJECTED"""
        ref = REF_FILLET_COD_SKINOFF  # "без кожи"
        cand = CAND_FILLET_COD_SKINON_WRONG_SKIN  # "на коже"
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'SKIN_MISMATCH' in result.block_reason
    
    def test_skinon_vs_skinoff_rejected(self):
        """REF: на коже → CAND: б/к = REJECTED"""
        ref = REF_FILLET_POLLOCK_SKINON  # "на коже"
        cand = {
            'id': 'cand_skinoff',
            'name_raw': 'Минтай филе б/к с/м 500г',
            'price': 340,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'SKIN_MISMATCH' in result.block_reason
    
    def test_skinon_vs_skinon_accepted(self):
        """REF: на коже → CAND: на коже = ACCEPTED"""
        ref = REF_FILLET_POLLOCK_SKINON
        cand = CAND_FILLET_POLLOCK_SKINON_SIMILAR
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
        assert result.same_skin_flag is True
    
    def test_skinoff_vs_skinoff_accepted(self):
        """REF: б/к → CAND: б/к = ACCEPTED"""
        ref = REF_FILLET_COD_SKINOFF
        cand = CAND_FILLET_COD_SKINOFF_CHEAP
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
        assert result.same_skin_flag is True
    
    def test_skin_unknown_ref_passes(self):
        """REF: skin unknown → любой CAND по skin проходит"""
        ref = {
            'id': 'ref_no_skin',
            'name_raw': 'Филе трески с/м 1кг',  # Без указания кожи
            'price': 800,
        }
        cand = CAND_FILLET_COD_SKINON_WRONG_SKIN  # "на коже"
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        # Без REF skin_flag gate не применяется
        assert result.passed_strict is True
    
    def test_skin_unknown_cand_passes(self):
        """REF: б/к → CAND: skin unknown = PASSED (не reject)"""
        ref = REF_FILLET_COD_SKINOFF
        cand = {
            'id': 'cand_no_skin',
            'name_raw': 'Филе трески с/м 1кг',  # Без указания кожи
            'price': 750,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        # Если у CAND skin unknown, gate не reject'ит
        assert result.passed_strict is True


# ============================================================================
# SECTION 12: Strict Gate Tests - STATE (4 cases)
# ============================================================================

class TestStrictGateState:
    """Тесты STATE gate: с/м ≠ охл"""
    
    def test_frozen_vs_chilled_rejected(self):
        """REF: с/м → CAND: охл = REJECTED"""
        ref = REF_FILLET_COD_SKINOFF  # "с/м"
        cand = CAND_FILLET_COD_CHILLED_WRONG_STATE  # "охлаждённое"
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'STATE_MISMATCH' in result.block_reason
    
    def test_chilled_vs_frozen_rejected(self):
        """REF: охл → CAND: с/м = REJECTED"""
        ref = REF_FILLET_SALMON_CHILLED  # "охл"
        cand = {
            'id': 'cand_frozen',
            'name_raw': 'Лосось филе с/м 1кг',
            'price': 1200,
        }
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is False
        assert 'STATE_MISMATCH' in result.block_reason
    
    def test_same_state_accepted(self):
        """REF: охл → CAND: охл = ACCEPTED"""
        ref = REF_FILLET_SALMON_CHILLED
        cand = CAND_FILLET_SALMON_CHILLED_SIMILAR
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        assert result.passed_strict is True
        assert result.same_state is True
    
    def test_state_unknown_passes(self):
        """REF: state unknown → любой state проходит"""
        ref = {
            'id': 'ref_no_state',
            'name_raw': 'Филе трески 1кг',  # Без с/м или охл
            'price': 800,
        }
        cand = REF_FILLET_COD_SKINOFF  # "с/м"
        
        ref_sig = extract_fish_fillet_signature(ref)
        cand_sig = extract_fish_fillet_signature(cand)
        result = check_fish_fillet_strict(ref_sig, cand_sig)
        
        # Gate не применяется если REF state unknown
        assert result.passed_strict is True


# ============================================================================
# SECTION 13: Apply Filter Integration Tests (6 cases)
# ============================================================================

class TestApplyFilter:
    """Интеграционные тесты apply_fish_fillet_filter"""
    
    def test_filter_returns_only_valid_alternatives(self):
        """Фильтр возвращает только валидные альтернативы"""
        ref = REF_FILLET_COD_SKINOFF
        candidates = [
            CAND_FILLET_COD_SKINOFF_CHEAP,
            CAND_FILLET_COD_SKINOFF_EXPENSIVE,
            CAND_WHOLE_COD_WRONG_CUT,
            CAND_FILLET_POLLOCK_WRONG_SPECIES,
            CAND_BLACKLISTED_KOTLETA,
        ]
        
        strict, similar, rejected = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        # Только 2 валидных (оба филе трески б/к с/м)
        assert len(strict) == 2
        
        # Все валидные имеют cut_type=FILLET и species=cod
        for s in strict:
            sig = s['npc_signature']
            assert sig.cut_type == FishCutType.FILLET
            assert sig.fish_species == 'cod'
    
    def test_filter_sorting_by_price(self):
        """Результаты отсортированы по цене"""
        ref = REF_FILLET_COD_SKINOFF
        candidates = [
            CAND_FILLET_COD_SKINOFF_EXPENSIVE,  # 900₽
            CAND_FILLET_COD_SKINOFF_CHEAP,      # 750₽
        ]
        
        strict, _, _ = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        assert len(strict) == 2
        # Дешевле первым
        assert strict[0]['item']['price'] < strict[1]['item']['price']
    
    def test_filter_empty_when_ref_not_fillet(self):
        """Пустой strict если REF не FISH_FILLET"""
        ref = REF_WHOLE_COD  # тушка
        candidates = [CAND_FILLET_COD_SKINOFF_CHEAP]
        
        strict, similar, rejected = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        assert len(strict) == 0
        assert 'REF_NOT_CLASSIFIED' in rejected or 'SOURCE_EXCLUDED' in rejected
    
    def test_filter_rejected_reasons_tracked(self):
        """Причины отклонения отслеживаются"""
        ref = REF_FILLET_COD_SKINOFF
        candidates = [
            CAND_WHOLE_COD_WRONG_CUT,
            CAND_FILLET_POLLOCK_WRONG_SPECIES,
            CAND_BLACKLISTED_KOTLETA,
        ]
        
        strict, similar, rejected = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        assert len(strict) == 0
        # Должны быть причины отклонения
        assert sum(rejected.values()) > 0
    
    def test_filter_limit_respected(self):
        """Лимит соблюдается"""
        ref = REF_FILLET_COD_SKINOFF
        candidates = [
            {**CAND_FILLET_COD_SKINOFF_CHEAP, 'id': f'c{i}'}
            for i in range(20)
        ]
        
        strict, _, _ = apply_fish_fillet_filter(ref, candidates, limit=5, mode='strict')
        
        assert len(strict) <= 5
    
    def test_filter_similar_mode(self):
        """Режим similar возвращает больше результатов"""
        ref = REF_FILLET_COD_SKINOFF
        candidates = [
            CAND_FILLET_COD_SKINOFF_CHEAP,
            CAND_FILLET_POLLOCK_WRONG_SPECIES,  # strict rejected, similar ok
        ]
        
        strict, similar, rejected = apply_fish_fillet_filter(ref, candidates, limit=10, mode='similar')
        
        assert len(strict) == 1
        # В similar должен попасть минтай
        assert len(similar) >= 1


# ============================================================================
# SECTION 14: ZERO-TRASH Policy Tests (6 cases)
# ============================================================================

class TestZeroTrashPolicy:
    """Тесты политики ZERO-TRASH"""
    
    def test_unclassified_ref_returns_empty(self):
        """Неклассифицированный REF возвращает пустой strict"""
        ref = {
            'id': 'ref_unknown',
            'name_raw': 'Рыба неизвестная 1кг',
            'price': 500,
        }
        candidates = [CAND_FILLET_COD_SKINOFF_CHEAP]
        
        strict, similar, rejected = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        assert len(strict) == 0
    
    def test_blacklisted_ref_returns_empty(self):
        """Blacklisted REF возвращает пустой strict"""
        ref = {
            'id': 'ref_conserv',
            'name_raw': 'Треска в масле консервы ж/б',
            'price': 150,
        }
        candidates = [CAND_FILLET_COD_SKINOFF_CHEAP]
        
        strict, similar, rejected = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        assert len(strict) == 0
        assert 'SOURCE_BLACKLISTED' in rejected or 'SOURCE_EXCLUDED' in rejected
    
    def test_no_legacy_fallback(self):
        """Legacy fallback запрещён"""
        ref = {
            'id': 'ref_fillet_like',
            'name_raw': 'Филе рыбное белое 1кг',  # Похоже на fillet, но нет species
            'price': 400,
        }
        candidates = [CAND_FILLET_COD_SKINOFF_CHEAP]
        
        strict, similar, rejected = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        # Должен вернуть пустой strict, не fallback на legacy
        assert len(strict) == 0
    
    def test_empty_strict_better_than_junk(self):
        """Пустой strict лучше мусора"""
        ref = REF_FILLET_COD_SKINOFF
        candidates = [
            CAND_WHOLE_COD_WRONG_CUT,
            CAND_BLACKLISTED_KOTLETA,
            CAND_BLACKLISTED_SOUP,
        ]
        
        strict, _, _ = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        # Лучше пусто, чем показать тушку или котлеты
        assert len(strict) == 0
    
    def test_blacklisted_candidates_never_in_strict(self):
        """Blacklisted кандидаты НИКОГДА не в strict"""
        ref = REF_FILLET_COD_SKINOFF
        candidates = [
            CAND_BLACKLISTED_KOTLETA,
            CAND_BLACKLISTED_CONSERV,
            CAND_BLACKLISTED_SOUP,
        ]
        
        strict, similar, rejected = apply_fish_fillet_filter(ref, candidates, limit=10, mode='strict')
        
        assert len(strict) == 0
    
    def test_ref_debug_explains_empty_strict(self):
        """ref_debug объясняет пустой strict"""
        from bestprice_v12.npc_fish_fillet import build_fish_fillet_ref_debug
        
        ref = {
            'id': 'ref_unknown',
            'name_raw': 'Рыба какая-то 1кг',
            'price': 500,
        }
        
        debug = build_fish_fillet_ref_debug(ref)
        
        assert debug['npc_domain'] is None
        assert debug['why_empty_strict'] is not None


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
