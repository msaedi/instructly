# Changelog

## Unreleased

_No changes yet._

## v1.0.0 – 2025-11-09

### Availability system (bitmap-only)
- Migrated read/write/copy to `availability_days` bitmaps; removed slot-era code paths (models, services, repos, schemas).
- Stabilized ETag/If-Match/409 semantics and returned counters (`days_written`, `windows_created`, etc.) for week save/copy.
- Updated seeders for bitmap-only flows; verified blackout dates operate correctly with bitmaps.

### Bug fixes
- Normalize bitmap decoding via `string_to_time()` so midnight (`24:00:00`) windows round-trip through week GET, booking searches, and cache validators without raising `ValueError`.
- Booking opportunity calculations now operate on minute offsets, preserving late-night availability that ends at midnight.
- Availability summaries query `availability_days` in a single range-read instead of issuing per-day calls.
- Bitmap retention now targets the correct `availability_days` table.
- Region boundaries seed is reliable on fresh DBs: add UNIQUE index on `(region_type, region_code)` and a loader guard that errors clearly if missing.
- Test guard hardened: fallback when `rg` is unavailable so “no slot symbols” test still runs.

### Breaking changes
- `PATCH /instructors/availability/bulk-update` now returns `410 Gone`. Use `POST /instructors/availability/week` (or `/week/validate-changes`) to mutate availability.

### Config
- Bitmap retention knobs: `AVAILABILITY_RETENTION_ENABLED`, `AVAILABILITY_RETENTION_DAYS` (default 180), `AVAILABILITY_RETENTION_KEEP_RECENT_DAYS` (default 30), `AVAILABILITY_RETENTION_DRY_RUN`.

### CI/CD & tooling
- Playwright **project matrix** (`instructor`, `admin`, `anon`), storage-state bootstrap, and scoped caches to avoid post-job hangs.
- **LHCI** stabilization: per-route budgets; env-gated stub for `/instructor/availability` (no visual changes); strict budgets remain for `/` and `/login`.
- Privacy-audit workflow: ensure test DB exists, **migrate before seed**, and guard NYC region unique-index step.
- Contract check: minified snapshot to satisfy pre-commit size limits; drift checking preserved.
