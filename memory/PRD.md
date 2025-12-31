# BestPrice B2B Marketplace - Product Requirements Document

## Original Problem Statement
B2B marketplace platform for HoReCa (Hotels, Restaurants, Cafes) that connects suppliers and restaurants for efficient product purchasing with automatic "Best Price" functionality.

## Core Requirements
1. **Best Price Engine**: Automatically find the cheapest matching products across all suppliers
2. **Brand Management**: Comprehensive brand dictionary with aliases for product matching
3. **Favorites System**: Allow customers to save and manage favorite products with brand preferences
4. **Multi-supplier Orders**: Group orders by supplier based on best prices

## Current Status (December 2025)

### ✅ Completed - Enhanced Search Engine (MVP Safe-Mode)

#### Pack Range Filter (0.5x - 2x)
- [x] Reference pack of 800г → valid range: 400г - 1600г
- [x] 340г rejected (too_small_0.340<0.400)
- [x] 5кг rejected (too_large_5.000>1.600)
- [x] 1кг selected (in range)

#### Guard Rules (кетчуп ≠ соус)
- [x] Conflicting product types cannot substitute each other
- [x] Guard conflicts: кетчуп≠соус, паста≠соус, майонез≠кетчуп, etc.
- [x] 5 sauce products rejected for ketchup search

#### brand_critical Logic Fixed
- [x] `brand_critical=false` → brand COMPLETELY IGNORED (no filter, no score bonus)
  - Result: PIKADOR PRO Кетчуп (199.2₽/кг) - cheapest across ALL brands
- [x] `brand_critical=true` → filter by brand_id only
  - Result: SI_KETCHUP_HEINZ_1KG (280₽/кг) - cheapest Heinz in pack range

#### Economics (total_cost selection)
- [x] price_per_base_unit = price / pack_value
- [x] total_cost = requested_qty × price_per_base_unit
- [x] Selection by total_cost, token_score is tie-breaker

#### Comprehensive Debug Logging
- [x] SearchDebugEvent with:
  - counters (total, after_brand, after_unit, after_pack, after_token, after_guard, final)
  - pack_rejections_sample
  - guard_rejections_sample
  - filters_applied
  - failure_reason

### Verified Test Results (10/10 PASSED)

| Test | Description | Result |
|------|-------------|--------|
| 1 | FAV_KETCHUP_ANY (brand_critical=false) | ✅ 199.2₽/кг PIKADOR PRO |
| 2 | FAV_KETCHUP_HEINZ (brand_critical=true) | ✅ 280₽/кг Heinz 1кг |
| 3 | Pack range rejects 340г, 5кг | ✅ too_small, too_large |
| 4 | Economics total_cost selection | ✅ 212.21₽/кг cheapest |
| 5 | Old format favorite no crash | ✅ status=ok |
| 6 | Guard rules reject sauce | ✅ 5 rejected |
| 7 | debug_log counters complete | ✅ all counters |
| 8 | brand_critical comparison | ✅ different results |
| 9 | Fixtures created | ✅ 9 products |
| 10 | Non-existent favorite | ✅ not_found |

## Key API Endpoints

### Add From Favorite (Enhanced Search)
```
POST /api/cart/add-from-favorite
{
  "favorite_id": "FAV_KETCHUP_ANY",
  "qty": 0.8  // requested qty in base units (kg/l)
}

Response:
{
  "status": "ok",
  "selected_offer": {
    "supplier_item_id": "...",
    "name_raw": "КЕТЧУП томатный пакет 1 кг. PIKADOR PRO",
    "price": 199.2,
    "price_per_base_unit": 199.2,
    "total_cost": 159.36,
    "pack_value": 1.0
  },
  "debug_log": {
    "counters": {
      "total": 8233,
      "after_brand_filter": 8233,
      "after_unit_filter": 1958,
      "after_pack_filter": 546,
      "after_token_filter": 10,
      "after_guard_filter": 5,
      "final": 5
    },
    "filters_applied": [
      "brand_filter: DISABLED (brand_critical=false)",
      "pack_filter: 0.40-1.60",
      "guard_filter: applied"
    ],
    "pack_rejections_sample": [...],
    "guard_rejections_sample": [...]
  }
}
```

## Tech Stack
- **Backend**: FastAPI (Python 3.11)
- **Frontend**: React with Shadcn/UI
- **Database**: MongoDB (`test_database`)
- **Search Engine**: EnhancedSearchEngine (search_engine.py)

## Test Credentials
- **Customer**: `customer@bestprice.ru` / `password123`

## Backlog

### P1 - High Priority
- [ ] Order creation flow finalization
- [ ] API performance optimization for large lists

### P2 - Medium Priority
- [ ] Telegram Bot integration
- [ ] Advanced user permissions

## Files Reference
- `/app/backend/server.py` - Main API server
- `/app/backend/search_engine.py` - EnhancedSearchEngine with pack range filter
- `/app/backend/brand_master.py` - Brand dictionary with family support
- `/app/tests/test_enhanced_search_mvp.py` - 10 acceptance tests
