# Bitmap Availability Sanity Checks

Quick verification tools for checking bitmap availability coverage in the database.

## Prerequisites

- PostgreSQL connection to the target database
- `psql` client or database access via Python

## Quick Verification Queries

### 1. Check Past 21 Days Coverage

For a specific instructor (e.g., Robert Davis: `01K8YGPXNZ096E3VS0SDF4JZP3`):

```sql
SELECT day_date, octet_length(bits) AS bytes, updated_at
FROM availability_days
WHERE instructor_id = '01K8YGPXNZ096E3VS0SDF4JZP3'
  AND day_date BETWEEN CURRENT_DATE - INTERVAL '21 days' AND CURRENT_DATE
ORDER BY day_date;
```

**Expected:** Rows for past dates indicate bitmap availability exists for completed bookings.

### 2. Check Next 21 Days Coverage

```sql
SELECT day_date, octet_length(bits) AS bytes, updated_at
FROM availability_days
WHERE instructor_id = '01K8YGPXNZ096E3VS0SDF4JZP3'
  AND day_date BETWEEN CURRENT_DATE + INTERVAL '1 day' AND CURRENT_DATE + INTERVAL '21 days'
ORDER BY day_date;
```

**Expected:** Rows for future dates indicate the public calendar will show availability.

### 3. Check Next 14 Days (Common Lookahead)

```sql
SELECT day_date, octet_length(bits) AS bytes, updated_at
FROM availability_days
WHERE instructor_id = '01K8YGPXNZ096E3VS0SDF4JZP3'
  AND day_date BETWEEN CURRENT_DATE + INTERVAL '1 day' AND CURRENT_DATE + INTERVAL '14 days'
ORDER BY day_date;
```

**Expected:** 14 rows if week-based availability is seeded forward.

### 4. Overall Coverage Summary

Count bitmap rows per instructor in the last 30 days:

```sql
SELECT
    instructor_id,
    COUNT(*) AS rows_in_last_30d,
    MIN(day_date) AS earliest_date,
    MAX(day_date) AS latest_date
FROM availability_days
WHERE day_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY instructor_id
ORDER BY rows_in_last_30d DESC;
```

**Expected:** Active instructors should have multiple rows (e.g., 21+ rows for 3 weeks of past + current week).

### 5. Count Non-Empty Bitmaps

Count rows with actual availability bits (non-zero):

```sql
SELECT
    instructor_id,
    COUNT(*) AS total_rows,
    COUNT(*) FILTER (WHERE octet_length(bits) > 0 AND bits != '\x00'::bytea) AS non_empty_rows
FROM availability_days
WHERE day_date >= CURRENT_DATE - INTERVAL '30 days'
GROUP BY instructor_id
HAVING COUNT(*) > 0
ORDER BY non_empty_rows DESC;
```

**Expected:** `non_empty_rows > 0` indicates instructors with actual availability windows set.

## Example psql Invocations

### Connect and Run Query

```bash
# Using environment variable
psql $DATABASE_URL -c "SELECT COUNT(*) FROM availability_days WHERE day_date >= CURRENT_DATE - INTERVAL '30 days';"

# Using connection string directly
psql "postgresql://user:pass@host:5432/dbname" -c "SELECT day_date, octet_length(bits) FROM availability_days WHERE instructor_id = '01K8YGPXNZ096E3VS0SDF4JZP3' AND day_date BETWEEN CURRENT_DATE - INTERVAL '21 days' AND CURRENT_DATE ORDER BY day_date;"
```

### Interactive Session

```bash
psql $DATABASE_URL
```

Then paste queries directly.

## Using the Dump Script

See `dump_bitmap_rows.py` for a Python-based helper that prints CSV output:

```bash
python backend/scripts/ops/dump_bitmap_rows.py \
  --db-url "$DATABASE_URL" \
  --instructor-id 01K8YGPXNZ096E3VS0SDF4JZP3 \
  --days-back 21 --days-forward 21
```

To backfill historical bitmap rows, run:

```bash
python backend/scripts/backfill_bitmaps.py --days 56
```

### Staging Seeding Recipe

```
export AVAILABILITY_V2_BITMAPS=1
export SEED_AVAILABILITY_BITMAP=1
export SEED_AVAILABILITY_BITMAP_WEEKS=4
export BITMAP_BACKFILL_DAYS=56
export SEED_REVIEW_LOOKBACK_DAYS=90
export SEED_REVIEW_HORIZON_DAYS=21
export SEED_REVIEW_DURATIONS="60,45,30"
# optional: isolate a clean review student
export SEED_REVIEW_STUDENT_EMAIL=seed.reviews@example.com

python backend/scripts/prep_db.py --migrate --seed-all
```

The seeding pipeline now executes migrations first, then bitmap future seeding and backfill **before** review seeding. The review phase consumes the structured diagnostics (`review_booking_seeded` / `review_booking_skipped`) to highlight any remaining conflicts.

## Troubleshooting

### No Rows Found

- **Past rows missing:** Review seeding may skip bookings (check `SEED_REVIEW_LOOKBACK_DAYS` env var)
- **Future rows missing:** "Apply" button may have copied empty week (check logs for "source week has no availability bits")

### Empty Bitmaps (zero bytes)

- Bitmap rows exist but contain no availability windows
- Check if instructor has set availability in the editor
- Verify `SEED_AVAILABILITY_BITMAP=1` was set during seeding

### Coverage Gaps

- Missing days indicate incomplete week seeding
- Verify `SEED_AVAILABILITY_BITMAP_WEEKS` setting (default: 3 weeks)
- Check if bitmap seeding ran before review seeding

## Review Seeding Environment Knobs

| Variable | Default | Purpose |
|----------|---------|---------|
| `SEED_REVIEW_LOOKBACK_DAYS` | 90 | Backward search window (days) for completed bookings |
| `SEED_REVIEW_HORIZON_DAYS` | 21 | Forward search window (days) for fallback windows |
| `SEED_REVIEW_DURATIONS` | `60,45,30` | Durations to attempt (minutes, in order) |
| `SEED_REVIEW_STUDENT_EMAIL` | unset | Force all seeded reviews to use a specific student |
| `SEED_REVIEW_STEP_MINUTES` | 15 | Step size when sliding within a bitmap window |
| `SEED_AVAILABILITY_BITMAP_WEEKS` | 3 | Future weeks to seed default availability |
| `BITMAP_BACKFILL_DAYS` | 56 | Backfill range for past bitmap coverage |

## Typical Staging Seeding Recipe

```bash
export SEED_AVAILABILITY_BITMAP=1
export SEED_AVAILABILITY_BITMAP_WEEKS=4
export BITMAP_BACKFILL_DAYS=56
export SEED_REVIEW_LOOKBACK_DAYS=90
export SEED_REVIEW_HORIZON_DAYS=21
export SEED_REVIEW_DURATIONS="60,45,30"

python backend/scripts/prep_db.py --migrate --seed-all
```

This order ensures:

1. Default bitmap availability is created for the next few weeks.
2. The backfill helper copies the current week backward to cover recent history.
3. Review seeding can reliably insert completed bookings into the past.

## Sample Logs

```
INFO  review_booking_seeded {"instructor_id":"01K8YGPXNZ096E3VS0SDF4JZP3","student_id":"01HT7NKQ5WZGW1S5FYY1B2R3V9","examined_start":"2024-11-28","examined_end":"2025-02-17","durations_minutes":[60,45,30],"bitmap_days":12,"instructor_conflicts":0,"student_conflicts":0,"status":"created","base_date":"2025-01-25","lookback_days":90,"horizon_days":21,"booking_date":"2025-01-05","start_time":"10:00:00","end_time":"11:00:00","duration_minutes":60,"day_start_hour":9,"day_end_hour":18,"step_minutes":15,"durations_attempted":[60,45,30]}
WARNING review_booking_skipped {"instructor_id":"01K8YGPXNZ096E3VS0SDF4JZP3","student_id":"01HT7NKQ5WZGW1S5FYY1B2R3V9","examined_start":"2024-10-27","examined_end":"2025-02-16","durations_minutes":[60,45,30],"bitmap_days":0,"instructor_conflicts":0,"student_conflicts":0,"status":"skipped","base_date":"2024-12-01","lookback_days":90,"horizon_days":21,"day_start_hour":9,"day_end_hour":18,"step_minutes":15,"durations_attempted":[60,45,30],"reason":"no_free_slot_within_span","slot_found":false}
```

The first line shows a successful booking placement (including window and duration).
The second line captures the structured diagnostics when no slot was available in the search span.
