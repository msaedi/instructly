# Availability Bitmap Architecture

## Overview

The InstaInstru platform uses a bitmap-based availability storage system that replaced the legacy slot-based approach. All availability data is stored in the `availability_days` table using compact bitmap representations.

## Storage Model

### `availability_days` Table

The `availability_days` table stores availability as compressed bitmaps:

- **Primary Key**: `(instructor_id, day_date)`
- **bits**: 6-byte bitmap representing 30-minute time slots (00:00-24:00 = 48 slots)
- **updated_at**: Timestamp tracking when the row was last modified

Each bitmap represents a full day (24 hours) at 30-minute resolution. A set bit indicates the instructor is available during that 30-minute window.

### Bitmap Format

- **Resolution**: 30-minute intervals
- **Range**: 00:00 to 24:00 (48 slots per day)
- **Storage**: 6 bytes per day (48 bits = 6 bytes)
- **Encoding**: Big-endian bit order, bit 0 = 00:00-00:30, bit 47 = 23:30-24:00

## Versioning & Caching

### ETag

The ETag header provides optimistic concurrency control for week-level operations:

```
ETag = SHA1(concat(bitmap_mon, bitmap_tue, ..., bitmap_sun))
```

- Hash of concatenated bitmaps for all 7 days in the week (ordered chronologically)
- Client sends `If-Match` header to prevent overwriting concurrent changes
- Server returns `409 Conflict` if ETag mismatch detected

### Last-Modified

The `Last-Modified` header tracks when availability was last updated:

```
Last-Modified = max(updated_at) across all availability_days rows for the week
```

- Used for HTTP conditional requests (`If-Modified-Since`)
- Maximum `updated_at` timestamp from all bitmap rows in the week
- UTC timezone normalized

## Guardrails

### Past Date Restrictions

- **Default**: Past dates cannot be modified (enforced by `AVAILABILITY_ALLOW_PAST` env var)
- **Validation**: `save_week_bits()` skips windows before today when `allow_past=false`
- **Bypass**: Set `AVAILABILITY_ALLOW_PAST=true` for testing/debugging

### Window Validation

- Windows must be 30-minute aligned
- End time must be after start time
- Overlapping windows within a day are merged automatically
- Windows are normalized to `HH:MM:SS` format

## Copy-Range Behavior

The `apply_pattern_to_date_range` operation copies a source week's pattern to multiple target dates:

1. **Extract Pattern**: Reads bitmap data from source week
2. **Apply to Targets**: For each target date in range:
   - Converts bitmap to windows for that weekday
   - Applies windows to target date
   - Merges with existing windows if any
3. **Metadata**: Returns `windows_created`, `days_written`, `dates_processed`

All operations are atomic per week (transactional boundaries).

## No Legacy Fallback

**Critical Guarantee**: The system has **no fallback** to legacy slot-based storage.

- `availability_slots` table was removed from migrations
- All `AvailabilitySlot` model references removed
- Slot-based repository methods raise `NotImplementedError`
- Runtime guard test verifies `x-db-table-availability_slots == "0"` on all operations

Any code attempting to use slot-based storage will fail immediately, ensuring bitmap-only operation.

## API Contracts

### Response Fields

All availability endpoints return bitmap counters:

- `windows_created`: Number of availability windows created
- `days_written`: Number of days with bitmap data written
- `weeks_affected`: Number of weeks modified
- `written_dates`: List of dates that were written
- `dates_processed`: Total dates processed in bulk operations

**Removed Fields**:
- `slots_created`: No longer returned (was deprecated, now removed)
- `dates_with_slots`: Replaced with `dates_with_windows`

### Performance Headers

- `x-db-table-availability_slots`: Always `"0"` (guardrail)
- `ETag`: Week version hash
- `Last-Modified`: Maximum `updated_at` timestamp
- `X-Allow-Past`: Whether past date modifications are allowed

## Repository Pattern

All availability operations go through `AvailabilityDayRepository`:

- `get_week_rows()`: Fetch bitmap rows for a week
- `get_day_bits()`: Get bitmap for a specific day
- `upsert_week()`: Write bitmap data for multiple days atomically

Service layer (`AvailabilityService`) handles:
- Bitmap ↔ window conversion (`bits_from_windows`, `windows_from_bits`)
- Version computation (`compute_week_version_bits`)
- Cache management
- Conflict detection

## Retention Policy

Bitmap availability rows are persisted indefinitely unless they violate the retention policy:

- **TTL**: Rows older than `AVAILABILITY_RETENTION_DAYS` (default **180**) are candidates.
- **Recent buffer**: The last `AVAILABILITY_RETENTION_KEEP_RECENT_DAYS` (default **30**) are always kept.
- **Bookings**: Any day that has or had a booking is preserved regardless of age.
- **Future safety**: Future dates are never purged.
- **Dry run**: When `AVAILABILITY_RETENTION_DRY_RUN=true`, the job inspects rows but does not delete them.
- **Enable flag**: Scheduling runs only when `AVAILABILITY_RETENTION_ENABLED=true` (disabled by default).

The retention task runs daily at 02:00 when enabled, emits one audit log per run, and records Prometheus metrics
(`availability_days_purged_total`, `availability_retention_run_seconds`) for observability.

Instructor deletion does **not** cascade to `availability_days`. Instead, the delete flow calls
`AvailabilityService.delete_orphan_availability_for_instructor`, which immediately purges every
AvailabilityDay row for that instructor that does **not** have a booking on the same calendar date.
Days with bookings are preserved for auditing/history, and the scheduled retention job provides the
long-tail safety net (180/30 day TTL, keep-with-booking rule) for any rows that appear later.

## Testing

Source-guard tests ensure no legacy code reappears:

- `test_no_slot_symbols_in_repo.py`: Scans backend codebase for `AvailabilitySlot` references
- `test_no_slot_queries_runtime.py`: Verifies no `availability_slots` table queries at runtime
