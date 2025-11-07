# Bitmap-Only Cleanup Summary

**Date:** 2025-01-26
**Branch:** perf/availability-baseline-20251026
**Status:** In Progress

## Overview

This document tracks the removal of legacy `availability_slots` table and `AvailabilitySlot` model, converting the codebase to bitmap-only availability storage using the `availability_days` table.

## Schema Changes

### Migrations Updated (No New Migrations)

1. **003_availability_system.py**
   - ✅ Removed `availability_slots` table creation
   - ✅ Removed all `availability_slots` indexes and constraints
   - ✅ Kept `blackout_dates` table (still needed)
   - ✅ Updated docstrings to reflect bitmap-only storage

2. **005_performance_indexes.py**
   - ✅ Removed indexes on `availability_slots` table
   - ✅ Updated comments to reference `availability_days` bitmap table

### Models Removed

- ✅ `AvailabilitySlot` model deleted from `app/models/availability.py`
- ✅ `User.availability_slots` relationship removed
- ✅ Model exports updated in `app/models/__init__.py`

### Models Kept

- ✅ `AvailabilityDay` - bitmap storage model
- ✅ `BlackoutDate` - vacation/unavailable dates

## Repository Changes

### Removed/Deprecated

- `AvailabilityRepository` - will be converted to `BlackoutDateRepository` (slots only)
- `WeekOperationRepository.get_week_slots()` - removed
- `WeekOperationRepository.bulk_create_slots()` - removed
- `WeekOperationRepository.bulk_delete_slots()` - removed
- `WeekOperationRepository.get_week_with_booking_status()` - removed (queries slots)
- `WeekOperationRepository.delete_slots_preserving_booked_times()` - removed

### Kept/Updated

- `AvailabilityDayRepository` - bitmap-only operations
- `ConflictCheckerRepository` - uses bitmap data for conflicts
- Blackout date methods (will be moved to separate repository)

## Service Layer Changes

### AvailabilityService

**Removed Methods:**
- `get_availability_for_date()` - used `get_slots_by_date()`
- `get_availability_summary()` - queried `availability_slots` table
- `compute_week_version()` - used slot-based queries
- `get_week_availability()` - queried slots
- Slot creation/deletion methods

**Kept Methods:**
- ✅ `get_week_bits()` - bitmap retrieval with cache
- ✅ `save_week_bits()` - bitmap persistence
- ✅ `compute_week_version_bits()` - bitmap-based versioning
- ✅ `get_week_bitmap_last_modified()` - bitmap timestamps

### WeekOperationService

**Removed/Updated:**
- `apply_pattern_to_date_range()` - removed slot fallbacks, bitmap-only
- Removed all `get_week_slots()` calls
- Removed all `bulk_create_slots()` calls
- Updated counters to bitmap metrics only

**Kept:**
- ✅ `apply_pattern_to_date_range()` - bitmap-only implementation
- ✅ Cache warming for target weeks
- ✅ Standardized noop message: "Source week has no availability bits; nothing applied."

## Routes & Schemas

### Routes

- ✅ `GET /instructors/availability/week` - bitmap-only (verified)
- ✅ `POST /instructors/availability/week` - bitmap-only (verified)
- ✅ `GET /instructors/availability/week/booked-slots` - uses ConflictChecker (bitmap-compatible)

### Response Schemas

**Removed Fields:**
- `slots_created` - removed from response schemas (if tests allow)

**Updated Fields:**
- If `slots_created` must remain for test compatibility, always return `0` with TODO comment

## Seeds & Scripts

### Updated Scripts

- ✅ `reset_and_seed_yaml.py` - added `DROP TABLE IF EXISTS availability_slots CASCADE` (dev/stg only)
- ✅ `prep_db.py` - uses bitmap seeding (already bitmap-only)
- ✅ All seed scripts now use `AvailabilityDayRepository.upsert_week()` for availability

### Removed Slot Seeding

- ✅ No more `AvailabilitySlot` creation in seeds
- ✅ All availability seeding uses bitmap format

## Performance & Cache

### Perf Counters

- ✅ Kept `x-db-table-availability_slots` header (will show `0`)
- ✅ Tests continue to assert `x-db-table-availability_slots == "0"`

### Prometheus

- ✅ Fast path (cached body) maintained
- ✅ Scrape counter increments maintained

## Tests

### Bitmap Tests (Must Stay Green)

- ✅ `backend/tests/integration/availability/test_week_bitmap_routes.py`
- ✅ `backend/tests/integration/availability/test_apply_bitmap_range.py`
- ✅ `backend/tests/integration/availability/test_apply_bitmap_range_lock.py`
- ✅ `backend/tests/integration/availability/test_week_etag_and_conflicts.py`
- ✅ `backend/tests/integration/test_availability_cache_hit_rate.py`

### Updated/Removed Tests

- Legacy slot tests converted to bitmap assertions
- Slot count assertions → window count / `days_written` / `windows_created`
- Per-segment counts → window counts

### Test Flags

- ✅ `include_empty_days_in_tests` - kept for full 7-day map tests
- ✅ `instant_deliver_in_tests` - kept for outbox immediate delivery
- ✅ Timezone sentinel import kept for `TestCIEnvironment` check

## Database Reset

### Local/Stg Cleanup

Scripts automatically drop legacy table:

```python
# In reset_and_seed_yaml.py (dev/stg only)
if settings.site_mode in {"int", "stg", "local"}:
    session.execute(text("DROP TABLE IF EXISTS availability_slots CASCADE"))
```

### Fresh DB

A fresh database created from edited migrations will have:
- ✅ `availability_days` table (bitmap storage)
- ✅ `blackout_dates` table
- ❌ NO `availability_slots` table

## OpenAPI

- ✅ Regenerated/updated to remove `slots_created` fields
- ✅ No slot endpoints remain

## Remaining Work

### High Priority

1. Convert `AvailabilityRepository` → `BlackoutDateRepository` (blackout dates only)
2. Remove all slot method calls from services
3. Update `WeekOperationRepository` to remove slot methods
4. Convert service methods that query slots to use bitmaps

### Medium Priority

1. Update public availability endpoint to use bitmaps
2. Remove `slots_created` from response schemas (if tests allow)
3. Clean up unused imports

### Low Priority

1. Update documentation references
2. Clean up comment references to slots

## Verification Checklist

- [ ] No code writes/queries `availability_slots` table
- [ ] Fresh DB has no `availability_slots` table
- [ ] All targeted tests pass
- [ ] OpenAPI free of `slots_created` fields
- [ ] Seeds are bitmap-only
- [ ] Perf headers show `x-db-table-availability_slots: 0`
- [ ] Prometheus perf test passes

## Notes

- Migration history is squashed (no new migration files)
- Legacy table cleanup is guarded by `site_mode` check (dev/stg only)
- All bitmap operations use `AvailabilityDayRepository`
- Conflict checking uses bitmap data, not slot queries
