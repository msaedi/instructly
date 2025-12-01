# Availability Bitmap System

*Last Updated: November 2025 (Session v117)*

## Overview

InstaInstru uses a **bitmap-based availability storage system** where each day's availability is encoded as 6 bytes (48 bits), representing 30-minute time slots. This compact representation replaced the previous slot-based approach, providing significant storage and query efficiency gains.

### Key Characteristics

| Aspect | Implementation |
|--------|---------------|
| Resolution | 30-minute time slots |
| Bits per Day | 48 (only first 48 of 64 bits used) |
| Bytes per Day | 6 bytes (BYTEA in PostgreSQL) |
| Storage Table | `availability_days` |
| Primary Key | `(instructor_id, day_date)` |
| Cache Strategy | Hot/warm tier with week-level versioning |

### Storage Efficiency

| Metric | Old Slot-Based | New Bitmap |
|--------|----------------|------------|
| Rows per Week | 1-48 per day | 1 per day |
| Bytes per Day | ~200+ per slot | 6 bytes |
| Index Size | Large | Minimal |
| Query Complexity | JOIN-heavy | Direct lookup |

---

## Architecture

### Database Model

Located in `backend/app/models/availability_day.py`:

```python
class AvailabilityDay(Base):
    __tablename__ = "availability_days"

    instructor_id = Column(String(26), primary_key=True)  # ULID
    day_date = Column(Date, primary_key=True)
    bits = Column(BYTEA, nullable=False)  # 6 bytes for 48 slots
    updated_at = Column(DateTime(timezone=True), nullable=False)
```

### Bit Layout

Each day uses 6 bytes (48 bits) representing 30-minute slots:

```
Byte 0 (bits 0-7):   00:00-04:00
Byte 1 (bits 8-15):  04:00-08:00
Byte 2 (bits 16-23): 08:00-12:00
Byte 3 (bits 24-31): 12:00-16:00
Byte 4 (bits 32-39): 16:00-20:00
Byte 5 (bits 40-47): 20:00-24:00

Bit index formula: bit_index = hour * 2 + (1 if minute >= 30 else 0)

Examples:
- 09:00 → bit 18 (9 * 2 + 0)
- 09:30 → bit 19 (9 * 2 + 1)
- 14:00 → bit 28 (14 * 2 + 0)
- 23:30 → bit 47 (23 * 2 + 1)
```

### Service Layer

| Component | Location | Purpose |
|-----------|----------|---------|
| `AvailabilityService` | `app/services/availability_service.py` | Business logic for availability |
| `AvailabilityDayRepository` | `app/repositories/availability_day_repository.py` | Bitmap persistence |
| `bitset` utilities | `app/utils/bitset.py` | Bit manipulation helpers |

---

## Key Components

### 1. Bitset Utilities

Located in `backend/app/utils/bitset.py`:

```python
SLOTS_PER_DAY = 48  # 30-minute resolution
BYTES_PER_DAY = 6   # 48 bits = 6 bytes

def new_empty_bits() -> bytes:
    """Create empty 6-byte bitmap."""
    return bytes(BYTES_PER_DAY)

def pack_indexes(indexes: List[int]) -> bytes:
    """Convert list of slot indexes to bitmap."""
    b = bytearray(BYTES_PER_DAY)
    for idx in indexes:
        byte_i = idx // 8
        bit_i = idx % 8
        b[byte_i] |= 1 << bit_i
    return bytes(b)

def unpack_indexes(bits: bytes) -> List[int]:
    """Convert bitmap to list of slot indexes."""
    out = []
    for byte_i, val in enumerate(bits):
        for bit_i in range(8):
            idx = byte_i * 8 + bit_i
            if idx >= SLOTS_PER_DAY:
                break
            if (val >> bit_i) & 1:
                out.append(idx)
    return out

def windows_from_bits(bits: bytes) -> List[Tuple[str, str]]:
    """Convert bitmap to merged time windows as ('HH:MM:SS','HH:MM:SS') tuples."""
    idxs = unpack_indexes(bits)
    if not idxs:
        return []

    # Merge consecutive indexes into windows
    windows = []
    start = prev = idxs[0]
    for idx in idxs[1:]:
        if idx == prev + 1:
            prev = idx
            continue
        windows.append((start, prev + 1))
        start = prev = idx
    windows.append((start, prev + 1))

    return [(idx_to_time(s), idx_to_time(e)) for s, e in windows]

def bits_from_windows(windows: List[Tuple[str, str]]) -> bytes:
    """Convert time windows to bitmap."""
    idxs = []
    for start, end in windows:
        s = time_to_index(start)
        e = time_to_index(end)
        idxs.extend(range(s, e))
    return pack_indexes(idxs)
```

### 2. Week Versioning

The system uses SHA1 hashing of concatenated bitmaps for optimistic concurrency control:

```python
def compute_week_version_bits(self, bits_by_day: Dict[date, bytes]) -> str:
    """Stable SHA1 of concatenated 7×bits ordered chronologically."""
    if not bits_by_day:
        concat = new_empty_bits() * 7
    else:
        anchor = min(bits_by_day.keys())
        monday = anchor - timedelta(days=anchor.weekday())
        ordered_days = [monday + timedelta(days=i) for i in range(7)]
        concat = b"".join(bits_by_day.get(day, new_empty_bits()) for day in ordered_days)
    return hashlib.sha1(concat).hexdigest()
```

**Conflict Detection:**
```python
# In save_week_bits()
server_version = self.compute_week_version_bits(current_map)
if base_version and base_version != server_version and not override:
    raise ConflictException("Week has changed; please refresh and retry")
```

### 3. Week Save Operation

Located in `AvailabilityService.save_week_bits()`:

```python
def save_week_bits(
    self,
    instructor_id: str,
    week_start: date,
    windows_by_day: Dict[date, List[Tuple[str, str]]],
    base_version: Optional[str],
    override: bool,
    clear_existing: bool,
    *,
    actor: Any | None = None,
) -> SaveWeekBitsResult:
    """
    Persist week availability using bitmap storage.

    Args:
        instructor_id: The instructor ULID
        week_start: Monday of the week
        windows_by_day: Dict mapping dates to list of (start_time, end_time) tuples
        base_version: Client's expected version for conflict detection
        override: Skip version check if True
        clear_existing: Clear all existing windows before applying new ones
        actor: Who made the change (for audit logging)

    Returns:
        SaveWeekBitsResult with persistence metadata
    """
    monday = week_start - timedelta(days=week_start.weekday())

    # 1. Load current bitmap state
    current_map = self.get_week_bits(instructor_id, monday)

    # 2. Version check (optimistic concurrency)
    server_version = self.compute_week_version_bits(current_map)
    if base_version and base_version != server_version and not override:
        raise ConflictException("Week has changed; please refresh and retry")

    # 3. Build target bitmap state
    updates = []
    for day in week_dates:
        if day in windows_by_day:
            desired_bits = bits_from_windows(windows_by_day[day])
        elif clear_existing:
            desired_bits = new_empty_bits()
        else:
            desired_bits = current_map[day]

        if desired_bits != current_map[day]:
            updates.append((day, desired_bits))

    # 4. Persist to database
    repo.upsert_week(instructor_id, updates)

    # 5. Update cache and emit events
    ...
```

### 4. Public Availability Computation

When calculating availability visible to students, the system:
1. Loads raw bitmap windows
2. Subtracts booked time slots
3. Applies buffer times between lessons
4. Enforces minimum advance booking hours

```python
def compute_public_availability(
    self, instructor_id: str, start_date: date, end_date: date
) -> dict[str, list[tuple[time, time]]]:
    """Compute per-date availability with booked times subtracted."""

    # Get instructor settings
    profile = self.instructor_repository.get_by_user_id(instructor_id)
    min_advance_hours = profile.min_advance_booking_hours or 0
    buffer_minutes = profile.buffer_time_minutes or 0

    # Calculate earliest allowed booking time
    if min_advance_hours > 0:
        earliest_allowed = get_user_now_by_id(instructor_id) + timedelta(hours=min_advance_hours)

    # For each date in range
    for cur in date_range:
        # 1. Load and merge availability windows from bitmap
        bases = merge_intervals(by_date.get(cur, []))

        # 2. Get booked times with buffer expansion
        booked = [
            expand_booking_interval(b.start_time, b.end_time)
            for b in conflict_repository.get_bookings_for_date(instructor_id, cur)
        ]

        # 3. Subtract booked from available
        remaining = subtract(bases, booked)

        # 4. Apply earliest booking cutoff
        if cur == earliest_allowed_date:
            remaining = trim_intervals_for_min_start(remaining, earliest_allowed_minutes)

        result[cur.isoformat()] = remaining
```

---

## Data Flow

### Saving Week Availability

```
1. Frontend sends week schedule
   PUT /api/v1/availability/week

2. Parse and validate schedule data
   - Group by date
   - Validate no overlaps
   - Check past date restrictions

3. Convert to bitmap format
   windows_by_day = {
     date(2025, 12, 1): [("09:00:00", "12:00:00"), ("14:00:00", "18:00:00")],
     ...
   }

4. Version check (if base_version provided)
   - Compute current server version
   - Reject if mismatch and not override

5. Calculate deltas
   - For each day, compute desired_bits from windows
   - Only write days where bits changed

6. Persist to availability_days table
   repo.upsert_week(instructor_id, updates)

7. Warm cache and emit events
   - Update week cache with new map
   - Enqueue availability.week_saved event

8. Return updated availability map
```

### Reading Week Availability

```
1. Request week availability
   GET /api/v1/availability/week?start_date=2025-12-01

2. Check cache
   cache_key = f"availability:week:{instructor_id}:{monday}"

3. Cache hit → Return cached week_map

4. Cache miss → Query database
   rows = repo.get_week_rows(instructor_id, monday)

5. Convert bitmaps to week_map format
   for day in rows:
       windows = windows_from_bits(day.bits)
       week_map[day.isoformat()] = [{"start_time": s, "end_time": e} for s, e in windows]

6. Populate cache and return
```

---

## Error Handling

### Conflict Detection

```python
class ConflictException(Exception):
    """Raised when optimistic concurrency check fails."""
    pass

# Usage
if base_version and base_version != server_version:
    raise ConflictException("Week has changed; please refresh and retry")
```

**Resolution:** Frontend should refresh data and retry with new version.

### Overlap Validation

```python
class AvailabilityOverlapException(Exception):
    """Raised when time windows overlap."""
    def __init__(self, specific_date: str, new_range: str, conflicting_range: str):
        self.specific_date = specific_date
        self.new_range = new_range
        self.conflicting_range = conflicting_range
```

The system validates:
1. No overlapping windows within the same day
2. Windows are valid (start < end)
3. End time uses proper 24:00 representation for midnight

### Past Date Restrictions

Controlled by `AVAILABILITY_ALLOW_PAST` environment variable:
- `true` (default): Allow editing past dates
- `false`: Reject edits to past dates (with `past_edit_window_days` grace period)

---

## Monitoring

### Performance Tracking

```python
from ..monitoring.availability_perf import availability_perf_span

with availability_perf_span(
    "service.save_week_availability",
    endpoint=endpoint,
    instructor_id=instructor_id,
    payload_size_bytes=payload_size,
) as perf:
    # ... operation
    perf(cache_used=cache_used)
```

### Audit Logging

Week saves are audited with before/after snapshots:

```python
audit_entry = AuditLog.from_change(
    entity_type="availability",
    entity_id=f"{instructor_id}:{week_start.isoformat()}",
    action="save_week",
    actor=actor_payload,
    before={"week_start": ..., "windows": ..., "window_counts": ...},
    after={"week_start": ..., "windows": ..., "edited_dates": ...},
)
```

### Event Outbox

Week saves emit `availability.week_saved` events:

```python
self.event_outbox_repository.enqueue(
    event_type="availability.week_saved",
    aggregate_id=f"{instructor_id}:{week_start.isoformat()}",
    payload={
        "instructor_id": instructor_id,
        "week_start": week_start.isoformat(),
        "affected_dates": sorted(affected),
        "clear_existing": bool(clear_existing),
        "version": version,
    },
    idempotency_key=key,
)
```

---

## Common Operations

### Get Week Availability

```bash
# API: GET /api/v1/availability/week
curl "/api/v1/availability/week?start_date=2025-12-01" \
  -H "Authorization: Bearer $TOKEN"

# Response:
{
  "2025-12-01": [{"start_time": "09:00:00", "end_time": "12:00:00"}],
  "2025-12-02": [],
  "2025-12-03": [{"start_time": "14:00:00", "end_time": "18:00:00"}],
  ...
}
```

### Save Week Availability

```bash
# API: PUT /api/v1/availability/week
curl -X PUT "/api/v1/availability/week" \
  -H "Authorization: Bearer $TOKEN" \
  -d '{
    "week_start": "2025-12-01",
    "clear_existing": true,
    "schedule": [
      {"date": "2025-12-01", "start_time": "09:00", "end_time": "12:00"},
      {"date": "2025-12-01", "start_time": "14:00", "end_time": "18:00"}
    ]
  }'
```

### Debug Bitmap Contents

```python
# In Python shell
from app.utils.bitset import windows_from_bits, unpack_indexes

bits = b'\x00\x00\xfc\x0f\x00\x00'  # Example bitmap
print(f"Set slots: {unpack_indexes(bits)}")
print(f"Windows: {windows_from_bits(bits)}")
# Output: Set slots: [16, 17, 18, 19, 20, 21, 22, 23, 24, 25, 26, 27]
#         Windows: [('08:00:00', '14:00:00')]
```

### Query Raw Bitmap Data

```sql
SELECT instructor_id, day_date, encode(bits, 'hex') as bits_hex
FROM availability_days
WHERE instructor_id = '01K2...'
AND day_date >= '2025-12-01'
ORDER BY day_date;
```

---

## Troubleshooting

### Availability Not Showing

1. **Check bitmap exists**:
   ```sql
   SELECT * FROM availability_days
   WHERE instructor_id = '01K2...' AND day_date = '2025-12-01';
   ```

2. **Verify bits are set**:
   ```python
   from app.utils.bitset import unpack_indexes
   # If bits are all zeros, no availability is set
   print(unpack_indexes(bits))  # Should show slot indexes
   ```

3. **Check cache staleness**:
   ```bash
   redis-cli DEL "availability:week:01K2...:2025-12-01"
   ```

### Conflict Errors on Save

1. **Client has stale version** - Frontend should refresh and retry

2. **Multiple tabs editing** - Only one can succeed; others must refresh

3. **Check current version**:
   ```python
   service = AvailabilityService(db)
   version = service.compute_week_version(instructor_id, monday, monday + timedelta(days=6))
   print(f"Current version: {version}")
   ```

### Overlapping Windows Error

The system enforces half-open interval semantics: `[start, end)`

**Valid adjacent windows:**
```
09:00-12:00, 12:00-15:00  ✅ (12:00 end = 12:00 start)
```

**Invalid overlapping windows:**
```
09:00-12:30, 12:00-15:00  ❌ (12:00 < 12:30)
```

### Past Dates Being Skipped

Check configuration:
```python
ALLOW_PAST = os.getenv("AVAILABILITY_ALLOW_PAST", "true")
past_edit_window_days = settings.past_edit_window_days
```

Past dates within `past_edit_window_days` are allowed even when `ALLOW_PAST=false`.

---

## Configuration

### Environment Variables

| Variable | Default | Purpose |
|----------|---------|---------|
| `AVAILABILITY_ALLOW_PAST` | `true` | Allow editing past availability |
| `AVAILABILITY_PERF_DEBUG` | `false` | Enable detailed bitmap change logging |
| `AUDIT_ENABLED` | `true` | Log availability changes to audit_logs |

### Cache Configuration

```python
# Cache key structure
week_key = f"availability:week:{instructor_id}:{monday}"
composite_key = f"{week_key}:with_slots"

# TTL tiers
"hot": 300,    # 5 minutes for current/future weeks
"warm": 3600,  # 1 hour for past weeks
```

---

## Migration from Slot-Based Storage

The bitmap system replaced the previous `availability_slots` table:

**Before (slot-based):**
- One row per 30-minute slot
- Up to 48 rows per day per instructor
- Complex JOIN queries for range lookups

**After (bitmap-based):**
- One row per day per instructor
- 6-byte bitmap encodes all 48 slots
- Simple single-row lookups

**Migration was handled by:**
1. Creating `availability_days` table
2. Converting existing slots to bitmaps
3. Removing legacy slot code paths
4. Maintaining API compatibility

---

## Related Documentation

- Bitset utilities: `backend/app/utils/bitset.py`
- Repository: `backend/app/repositories/availability_day_repository.py`
- Service: `backend/app/services/availability_service.py`
- Routes: `backend/app/routes/v1/availability_windows.py`
