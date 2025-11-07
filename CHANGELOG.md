# Changelog

## Unreleased

### Bug fixes
- Normalize bitmap decoding via `string_to_time()` so midnight (`24:00:00`) windows round-trip through week GET, booking searches, and cache validators without raising `ValueError`.
- Booking opportunity calculations now operate on minute offsets, preserving late-night availability that ends at midnight.
- Availability summaries query `availability_days` in a single range-read instead of issuing per-day calls.
- Bitmap retention now targets the correct `availability_days` table.

### Breaking changes
- `PATCH /instructors/availability/bulk-update` now returns `410 Gone`. Use `POST /instructors/availability/week` (or `/week/validate-changes`) to mutate availability.

### Config
- Bitmap retention knobs: `AVAILABILITY_RETENTION_ENABLED`, `AVAILABILITY_RETENTION_DAYS` (default 180), `AVAILABILITY_RETENTION_KEEP_RECENT_DAYS` (default 30), `AVAILABILITY_RETENTION_DRY_RUN`.
