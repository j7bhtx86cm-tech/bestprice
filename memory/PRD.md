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
- [x] New file contains 1502 brands, 1603 aliases across 23 categories
- [x] Updated `brand_master.py` to load new format with `BRANDS_MASTER` and `BRAND_ALIASES` sheets

#### Part B - Brand Backfill
- [x] Created endpoint `/api/admin/brands/backfill` for admin to trigger backfill
- [x] Created endpoint `/api/admin/brands/stats` for brand statistics
- [x] Successfully backfilled 5698 products with correct brand_id (76.6%)

#### Part C - Favorites v2 + Migration
- [x] Created endpoint `/api/admin/favorites/migrate-v2` for schema migration
- [x] Created endpoint `/api/favorites/{id}/enriched` for debugging
- [x] V2 schema: `source_item_id`, `brand_id`, `brand_critical`, `unit_norm`, `pack`, `tokens`, `schema_version=2`, `broken`
- [x] Old favorites work without crashing

#### Part D - Null-safe Matching Engine
- [x] `/api/cart/select-offer` never returns 500 error
- [x] `/api/cart/add-from-favorite` never returns 500 error
- [x] Returns structured responses: `ok`, `not_found`, `insufficient_data`, `error`
- [x] All exceptions caught and returned as structured responses

#### Part E - Brand Critical Logic Fix (CRITICAL BUG FIX)
- [x] When `brand_critical=false`: brand is COMPLETELY IGNORED
  - No filtering by brand_id
  - 0 bonus points for brand match in scoring
  - System finds cheapest across ALL brands
- [x] When `brand_critical=true`: brand is required
  - Filter candidates by brand_id
  - 10% bonus for brand match
  - System finds cheapest within specified brand only

#### New: Add From Favorite Endpoint
- [x] Created `/api/cart/add-from-favorite` endpoint
- [x] ALWAYS runs full best price search (no shortcut)
- [x] Gets `brand_id` from database, not from frontend
- [x] Includes comprehensive debug_log:
  - favorite_id
  - brand_critical
  - reference_item (name, brand_id, unit_norm)
  - candidates_before_filters
  - filters_applied
  - selected_supplier_item_id
  - selected_price
  - selection_reason

#### Test Fixtures
- [x] Created `/api/test/create-fixtures` endpoint for acceptance tests
- [x] Test data: FAV_TEST_1 (brand_critical=false), FAV_TEST_2 (brand_critical=true), FAV_TEST_OLD (v1 format)
- [x] Products: СИБАС охлажденный with different brands and prices

## Verified Test Results (9/9 PASSED)

| Test | Description | Result |
|------|-------------|--------|
| A | FAV_TEST_1 (brand_critical=false) selects SI_TEST_2 (931.44₽ BRAND_B) | ✅ PASSED |
| B | FAV_TEST_2 (brand_critical=true) selects SI_TEST_1 (990.60₽ BRAND_A) | ✅ PASSED |
| C | FAV_TEST_OLD (old format) no 500 error | ✅ PASSED |
| D | /api/cart/select-offer works | ✅ PASSED |
| E | debug_log contains all fields | ✅ PASSED |
| F | brand_critical=false shows "DISABLED" | ✅ PASSED |
| G | brand_critical=true shows brand_id filter | ✅ PASSED |
| H | /api/admin/favorites/migrate-v2 works | ✅ PASSED |
| I | Different results for brand_critical true/false | ✅ PASSED |

## Key API Endpoints

### Add From Favorite (NEW)
```
POST /api/cart/add-from-favorite
{
  "favorite_id": "FAV_TEST_1",
  "qty": 1,
  "match_threshold": 0.6
}

Response:
{
  "status": "ok",
  "selected_offer": {...},
  "top_candidates": [...],
  "debug_log": {
    "favorite_id": "...",
    "brand_critical": false,
    "filters_applied": ["brand_filter: DISABLED", ...],
    "selected_supplier_item_id": "...",
    "selected_price": 931.44,
    "selection_reason": "cheapest_total_cost"
  }
}
```

### Select Best Offer
```
POST /api/cart/select-offer
{
  "reference_item": {"name_raw": "...", "brand_critical": false},
  "match_threshold": 0.6
}
```

### Admin Endpoints
```
POST /api/admin/brands/backfill
GET /api/admin/brands/stats
POST /api/admin/favorites/migrate-v2
POST /api/test/create-fixtures
DELETE /api/test/cleanup-fixtures
```

## Tech Stack
- **Backend**: FastAPI (Python 3.11)
- **Frontend**: React with Shadcn/UI
- **Database**: MongoDB (`test_database`)
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
- `/app/backend/server.py` - Main API server with add-from-favorite endpoint
- `/app/backend/brand_master.py` - Brand dictionary loader
- `/app/backend/backfill_brands.py` - Standalone backfill script
- `/app/frontend/src/pages/customer/CustomerFavorites.js` - Favorites UI
- `/app/tests/test_add_from_favorite.py` - Acceptance tests
