# BestPrice B2B Marketplace - Product Requirements Document

## Original Problem Statement
B2B marketplace platform for HoReCa (Hotels, Restaurants, Cafes) that connects suppliers and restaurants for efficient product purchasing with automatic "Best Price" functionality.

## Core Requirements
1. **Best Price Engine**: Automatically find the cheapest matching products across all suppliers
2. **Brand Management**: Comprehensive brand dictionary with aliases for product matching
3. **Favorites System**: Allow customers to save and manage favorite products with brand preferences
4. **Multi-supplier Orders**: Group orders by supplier based on best prices

## Current Status (December 2025)

### ✅ Completed

#### Part A - Brand Dictionary Replacement
- [x] Replaced old brand file with `BESTPRICE_BRANDS_MASTER_UNIFIED_RF_HORECA_ULTRA_SAFE.xlsx`
- [x] 1502 brands, 1603 aliases across 23 categories
- [x] Updated `brand_master.py` with brand_family_id support

#### Part B - Brand Backfill
- [x] Created endpoint `/api/admin/brands/backfill`
- [x] Created endpoint `/api/admin/brands/stats`
- [x] 76.6% brand coverage (5854 of 7645 products)

#### Part C - Favorites v2 + Migration
- [x] Created endpoint `/api/admin/favorites/migrate-v2`
- [x] Created endpoint `/api/favorites/{id}/enriched`
- [x] Old favorites work without crashing

#### Part D - Null-safe Matching Engine
- [x] Never returns 500 error
- [x] Returns structured responses: `ok`, `not_found`, `insufficient_data`, `error`

#### Part E - Brand Critical Logic Fix
- [x] When `brand_critical=false`: brand COMPLETELY IGNORED (no filter, no score bonus)
- [x] When `brand_critical=true`: filter by brand_id, 10% bonus

#### NEW: Two-Phase Search Engine (search_engine.py)
- [x] **Phase 1 (STRICT)**: MIN_SCORE=0.70, exact matching rules
- [x] **Phase 2 (RESCUE)**: MIN_SCORE=0.60, penalties instead of filters
  - Pack missing: -10% penalty
  - Unit mismatch: -5% penalty
  - Only triggered if Phase 1 returns 0 results
- [x] Comprehensive SearchDebugEvent logging

#### NEW: Brand Family Support
- [x] brand_family_id in brand_master.py (27 families, 29 brands with family)
- [x] Mappings: miratorg_chef → miratorg, hochland professional → hochland, etc.
- [x] Brand critical fallback: if brand_id=0 results → search by brand_family_id
- [x] Endpoint `/api/admin/brands/families`

#### NEW: Search Quality Reports
- [x] Endpoint `/api/admin/search/quality-report`
- [x] Brand coverage by supplier
- [x] Sample products without brand
- [x] Overall statistics (75.2% brand coverage)

## Verified Test Results (11/11 PASSED)

| Test | Description | Result |
|------|-------------|--------|
| 1 | FAV_TEST_1 (brand_critical=false) → SI_TEST_2 (931.44₽ BRAND_B) | ✅ PASSED |
| 2 | FAV_TEST_2 (brand_critical=true) → SI_TEST_1 (990.60₽ BRAND_A) | ✅ PASSED |
| 3 | FAV_TEST_FAMILY → miratorg_chef finds via family | ✅ PASSED |
| 4 | FAV_TEST_PACK_MISSING → found with penalty | ✅ PASSED |
| 5 | FAV_TEST_OLD → no 500 error | ✅ PASSED |
| 6 | /api/admin/search/quality-report | ✅ PASSED |
| 7 | /api/admin/brands/families | ✅ PASSED |
| 8 | debug_log contains all fields | ✅ PASSED |
| 9 | brand_critical comparison | ✅ PASSED |
| 10 | non-existent favorite | ✅ PASSED |
| 11 | fixtures creation | ✅ PASSED |

## Key API Endpoints

### Add From Favorite (Two-Phase Search)
```
POST /api/cart/add-from-favorite
{
  "favorite_id": "FAV_TEST_1",
  "qty": 1
}

Response (SearchDebugEvent):
{
  "status": "ok",
  "selected_offer": {...},
  "debug_log": {
    "search_id": "abc123",
    "phase": "strict",  // or "rescue"
    "counters": {
      "total": 8224,
      "after_brand_filter": 1500,
      "after_score_filter": 50
    },
    "filters_applied": ["brand_filter: DISABLED", "score_filter: >= 0.7"],
    "result": {
      "status": "ok",
      "failure_reason": null,
      "selected_item_id": "SI_TEST_2",
      "selected_price": 931.44
    }
  }
}
```

### Quality Reports
```
GET /api/admin/search/quality-report  # Brand coverage by supplier
GET /api/admin/brands/families        # Brand family list
```

## Tech Stack
- **Backend**: FastAPI (Python 3.11)
- **Frontend**: React with Shadcn/UI
- **Database**: MongoDB (`test_database`)
- **Search Engine**: TwoPhaseSearchEngine (search_engine.py)
- **Key Libraries**: pandas, openpyxl, thefuzz

## Test Credentials
- **Customer**: `customer@bestprice.ru` / `password123`

## Backlog

### P1 - High Priority
- [ ] Order creation flow finalization
- [ ] API performance optimization for large lists

### P2 - Medium Priority
- [ ] Telegram Bot integration
- [ ] Advanced user permissions (presets, approval workflows)

## Files Reference
- `/app/backend/server.py` - Main API server
- `/app/backend/search_engine.py` - TwoPhaseSearchEngine, SearchDebugEvent
- `/app/backend/brand_master.py` - Brand dictionary with family support
- `/app/frontend/src/pages/customer/CustomerFavorites.js` - Favorites UI
- `/app/tests/test_two_phase_search.py` - Acceptance tests (11 tests)
