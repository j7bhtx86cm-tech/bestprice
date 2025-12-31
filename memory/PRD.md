# BestPrice B2B Marketplace - Product Requirements Document

## Original Problem Statement
B2B marketplace platform for HoReCa (Hotels, Restaurants, Cafes) that connects suppliers and restaurants for efficient product purchasing with automatic "Best Price" functionality.

## Core Requirements
1. **Best Price Engine**: Automatically find the cheapest matching products across all suppliers
2. **Brand Management**: Comprehensive brand dictionary with aliases for product matching
3. **Favorites System**: Allow customers to save and manage favorite products with brand preferences
4. **Multi-supplier Orders**: Group orders by supplier based on best prices

## Current Status (December 2025)

### ✅ Completed (Part A-B-D-E)

#### Part A - Brand Dictionary Replacement
- [x] Replaced old brand file with `BESTPRICE_BRANDS_MASTER_UNIFIED_RF_HORECA_ULTRA_SAFE.xlsx`
- [x] New file contains 1570 brands, 232 aliases across 23 categories
- [x] Updated `brand_master.py` to load new format with `BRANDS_MASTER` and `BRAND_ALIASES` sheets
- [x] Deleted old `BESTPRICE_BRANDS_MASTER_EN_RU_SITE_STYLE_FINAL.xlsx`

#### Part B - Brand Backfill
- [x] Created endpoint `/api/admin/brands/backfill` for admin to trigger backfill
- [x] Created endpoint `/api/admin/brands/stats` for brand statistics
- [x] Successfully backfilled 5698 products with correct brand_id
- [x] 76.6% of products now have brand_id (5854 of 7645)
- [x] 552 products have strict brands

#### Part D - Null-safe Matching Engine
- [x] `/api/cart/select-offer` now never returns 500 error
- [x] Returns structured responses with statuses: `INSUFFICIENT_DATA`, `NOT_FOUND`, `NO_MATCH_OVER_THRESHOLD`, `ERROR: <message>`
- [x] Fixed `NoneType.__format__` error in logging statements
- [x] All exceptions are caught and returned as structured responses

#### Part E - Brand Critical Logic Fix
- [x] When `brand_critical=false`: brand is COMPLETELY NEUTRAL
  - No filtering by brand_id
  - 0 bonus points for brand match
  - Name similarity gets 70% weight instead of 60%
- [x] When `brand_critical=true`: brand is required
  - Filter candidates by brand_id
  - 10% bonus for brand match
  - Name similarity gets 60% weight

### 🔄 In Progress (Part C)
- [ ] Favorites v2 Schema migration
  - New schema: `source_item_id`, `brand_id`, `unit_norm`, `pack`, `tokens`, `brand_critical`, `schema_version=2`, `broken` flag
  - Migration script for old favorites
  - Backend enrichment using `favorite_id` and `source_item_id`

## Key API Endpoints

### Select Best Offer
```
POST /api/cart/select-offer
{
  "reference_item": {
    "name_raw": "Лосось филе охл 1.5кг",
    "brand_id": "heinz",  // optional
    "brand_critical": false  // true = strict brand, false = any brand
  },
  "qty": 1,
  "required_volume": 5.0,  // optional
  "match_threshold": 0.6  // default 0.85
}
```

### Admin Brand Management
```
POST /api/admin/brands/backfill  # Run brand backfill
GET /api/admin/brands/stats      # Get brand statistics
```

## Database Collections
- `products`: Product catalog with `brand_id`, `brand_strict` fields
- `pricelists`: Supplier prices
- `favorites`: User favorites (v1, being migrated to v2)
- `companies`: Supplier and customer companies

## Tech Stack
- **Backend**: FastAPI (Python 3.11)
- **Frontend**: React with Shadcn/UI
- **Database**: MongoDB (`test_database`)
- **Key Libraries**: pandas, openpyxl, thefuzz

## Test Credentials
- **Customer**: `customer@bestprice.ru` / `password123`

## Architecture Notes
- Server uses `DB_NAME="test_database"` from `.env`
- All scripts must use the same database
- Brand detection uses normalized aliases with longest-first matching
- Scoring algorithm varies based on `brand_critical` flag

## Backlog

### P0 - Critical
- [ ] Complete Favorites v2 migration (Part C)

### P1 - High Priority
- [ ] Order creation flow finalization
- [ ] API performance optimization for large lists

### P2 - Medium Priority
- [ ] Telegram Bot integration
- [ ] Advanced user permissions (presets, approval workflows)

## Files Reference
- `/app/backend/server.py` - Main API server
- `/app/backend/brand_master.py` - Brand dictionary loader
- `/app/backend/backfill_brands.py` - Standalone backfill script
- `/app/backend/BESTPRICE_BRANDS_MASTER_UNIFIED_RF_HORECA_ULTRA_SAFE.xlsx` - Brand data source
- `/app/frontend/src/pages/customer/CustomerFavorites.js` - Favorites UI
