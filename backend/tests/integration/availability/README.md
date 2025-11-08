# Availability Tests

This directory contains comprehensive integration tests that lock the current bitmap availability behavior and prevent regressions.

## Test Files

### `test_week_etag_and_conflicts.py`
Tests the week availability GET/POST endpoints with ETag and conflict handling:
- `test_week_get_sets_etag_and_allow_past`: Verifies GET returns proper headers (ETag, Access-Control-Expose-Headers, X-Allow-Past)
- `test_week_post_200_updates_bits_and_changes_etag`: Verifies POST updates bits and changes ETag
- `test_week_post_409_with_stale_if_match`: Verifies 409 conflict response with stale If-Match
- `test_week_post_override_true_bypasses_conflict`: Verifies override=true bypasses conflict checks

### `test_past_day_toggles.py`
Tests past-day editing behavior based on `AVAILABILITY_ALLOW_PAST` setting:
- `test_past_day_edits_persist_when_allow_past_true`: Past day edits persist when enabled
- `test_past_day_edits_ignored_when_allow_past_false`: Past day edits ignored when disabled

### `test_apply_bitmap_range_lock.py`
Tests the apply-to-date-range endpoint (bitmap copy):
- `test_apply_bitmap_pattern_across_weeks_exact_copy`: Verifies exact bit-for-bit copy across multiple weeks
- `test_apply_bitmap_empty_source_returns_noop_message`: Verifies empty source week returns appropriate message

### `test_booking_independence.py`
Tests that bookings do not interfere with availability saving:
- `test_save_week_succeeds_even_with_overlapping_bookings`: Availability saves succeed even with overlapping bookings

## Environment Variables

These tests use the following environment variables (set via module-scoped `conftest.py` autouse fixture):

- `AVAILABILITY_ALLOW_PAST=true`: Allows editing past dates (can be overridden per-test)
- `AVAILABILITY_PERF_DEBUG=1`: Enables performance debug logging and headers

The module-scoped fixture ensures these env vars are set only for availability tests, preventing side-effects on other test suites. Tests can override these by using `monkeypatch.setenv()` before reloading modules.

## Running Tests

Run all availability tests:
```bash
pytest backend/tests/integration/availability/
```

Run specific test file:
```bash
pytest backend/tests/integration/availability/test_week_etag_and_conflicts.py
```

Run specific test:
```bash
pytest backend/tests/integration/availability/test_week_etag_and_conflicts.py::TestWeekGetSetsEtagAndAllowPast::test_week_get_sets_etag_and_allow_past
```

Run with verbose output:
```bash
pytest -v backend/tests/integration/availability/
```

## Test Dependencies

Tests use:
- `test_instructor` fixture: Creates an instructor user with profile and services
- `bitmap_client` fixture: TestClient with bitmap availability enabled
- `db` fixture: Database session
- `auth_headers_instructor` fixture: Authentication headers for instructor

## Deterministic Testing

- Tests use fixed dates (e.g., `date(2025, 11, 3)`) to avoid midnight/DST flakes
- Time can be frozen using monkeypatch (see `test_past_day_toggles.py` for examples)
- ULIDs are generated using existing generators, but time-based derivation is controlled via time freezing

## Notes

- These tests are **tests-only** - they do not modify production code
- Tests preserve current behavior as implemented on branch `perf/availability-baseline-20251026`
- If a test reveals a true spec gap, STOP and return a minimal diff proposal rather than changing prod code
