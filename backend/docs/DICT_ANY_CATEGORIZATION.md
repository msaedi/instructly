# Dict[str, Any] Categorization for API Response Schemas

This document categorizes all `Dict[str, Any]` occurrences in backend schemas as part of the Phase 3 Guardrails Migration.

## Summary

| Category | Count | Status |
|----------|-------|--------|
| A - Fix Now | 7 | Fixed |
| B - Truly Dynamic | 17 | Justified |
| C - Internal/Admin Monitoring | 19 | Infrastructure |
| D - Dead Code | 4 | To Remove |
| **Total** | 47 | - |

**Baseline after fixes: 36** (Category B + C)

---

## Category A - FIXED (Previously 7)

These had predictable structures and have been fixed with proper Pydantic models.

| File | Field | Fix Applied |
|------|-------|-------------|
| `review.py:28` | `overall` | Created `OverallRatingStats` model |
| `review.py:29` | `by_service` | Created `ServiceRatingStats` model |
| `booking.py:116` | `conflicts_with` | Created `ConflictingBookingInfo` model |
| `booking.py:199` | `time_info` | Created `TimeSlotInfo` model |
| `booking.py:210` | `search_parameters` | Created `BookingSearchParameters` model |
| `availability_window.py:44` | `schedule` | Created `ScheduleItem` model |
| `availability_window.py:94` | `conflicts_with` | Created `AvailabilityConflictInfo` model |
| `availability_responses.py:90` | `booked_slots` | Created `BookedSlotItem` model |

---

## Category B - TRULY DYNAMIC (17 occurrences)

Each has explicit justification for requiring runtime flexibility.

### 1. User Metadata (`user.py:46`)
```python
metadata: Optional[Dict[str, Any]]
```
**Justification**: User-provided arbitrary metadata during signup (invite_code, referral source, marketing tags). Users can provide any key/value pairs. This is intentionally open for extensibility.

### 2-3. Audit Log Snapshots (`audit.py:22-23`)
```python
before: Optional[Dict[str, Any]]
after: Optional[Dict[str, Any]]
```
**Justification**: Audit logs capture arbitrary model state before/after changes. Different tables have completely different schemas (User vs Booking vs Service). Must be dynamic to audit any model type.

### 4. Location Metadata (`address.py:54`)
```python
location_metadata: Optional[Dict[str, Any]]
```
**Justification**: External geocoding service responses vary by provider (Google Places, Mapbox, OpenStreetMap). Provider-agnostic design requires accepting dynamic metadata structures.

### 5. Stripe Payout Settings (`payment_schemas.py:126`)
```python
settings: Optional[Dict[str, Any]]
```
**Justification**: Stripe's payout schedule settings vary by schedule type (daily/weekly/monthly) and account type. External API contract we don't control.

### 6. Stripe Error Details (`payment_schemas.py:263`)
```python
details: Optional[Dict[str, Any]]
```
**Justification**: Stripe error response formats vary widely by error type. External API contract we don't control.

### 7. Pipeline Stage Details (`nl_search.py:184`)
```python
details: Optional[Dict[str, Any]]
```
**Justification**: Each NL search pipeline stage (parsing, embedding, location, ranking) has different diagnostic fields. Intentionally polymorphic for observability.

### 8. Availability Summary (`public_availability.py:90`)
```python
availability_summary: Optional[Dict[str, Dict[str, Any]]]
```
**Justification**: Summary view structure varies by detail_level parameter. Part of designed API flexibility for minimal/summary/full responses.

### 9. Alert Details (`alert_responses.py:32`)
```python
details: Optional[Dict[str, Any]]
```
**Justification**: Alert types (auth failures, rate limits, errors) have different contextual fields. Intentionally polymorphic for admin tooling.

### 10-12. Privacy Export (`privacy.py:43,53,64`)
```python
data: Dict[str, Any]
statistics: Dict[str, Any]
stats: Dict[str, Any]
```
**Justification**: GDPR data export includes whatever data exists for a user. Users have different data (some have bookings, some don't). Statistics vary by retention policies configured.

### 13. GeoJSON Features (`address_responses.py:8`)
```python
features: List[Dict[str, Any]]
```
**Justification**: Standard GeoJSON format from mapping APIs. GeoJSON properties field is intentionally dynamic per the specification (RFC 7946).

### 14. Base Response Data (`base_responses.py:58`)
```python
data: Optional[Dict[str, Any]]
```
**Justification**: Generic response wrapper designed for extensibility across different endpoints. Intentionally flexible.

### 15-16. Search Context (`search_history.py:50,53`)
```python
search_context: Optional[Dict[str, Any]]
device_context: Optional[Dict[str, Any]]
```
**Justification**: Client-provided context varies by frontend version, device capabilities, and feature flags. Intentionally open for A/B testing and analytics.

### 17. Performance Metrics (`main_responses.py:48`)
```python
metrics: Dict[str, Any]
```
**Justification**: Health check metrics vary by enabled monitoring components. Different deployments track different metrics.

---

## Category C - INFRASTRUCTURE/ADMIN (19 occurrences)

Internal monitoring endpoints not exposed to end users. Structures match external system outputs (Redis INFO, SQLAlchemy pool stats).

### Infrastructure Responses (`infrastructure_responses.py`)
| Line | Field | Description |
|------|-------|-------------|
| 14 | `stats` | Redis stats from INFO command |
| 21 | `queues` | Celery queue info |
| 28 | `connections` | Active connections list |
| 43 | `pool_status` | SQLAlchemy pool stats |
| 50 | `stats` | Generic stats |
| 59 | `checks` | Health check results |

### Monitoring Responses (`monitoring_responses.py`)
| Line | Field | Description |
|------|-------|-------------|
| 131 | `database` | DB pool/query metrics |
| 270 | `basic_stats` | Cache statistics |
| 271 | `redis_info` | Redis INFO output |
| 335 | `cache` | Cache statistics |
| 337 | `database` | Database metrics |
| 380 | `availability_metrics` | Availability cache metrics |
| 381 | `redis_info` | Redis INFO output |
| 410 | `availability_cache_metrics` | Availability cache |
| 448 | `top_limited_clients` | Rate limit stats |

### Redis Monitor (`redis_monitor_responses.py`)
| Line | Field | Description |
|------|-------|-------------|
| 43 | `stats` | Redis stats |
| 50 | `queues` | Queue info |
| 57 | `connections` | Connection list |

### Database Monitor (`database_monitor_responses.py`)
| Line | Field | Description |
|------|-------|-------------|
| 22 | `pool_status` | Pool stats |
| 33 | `pool` | Pool config |
| 34 | `configuration` | DB config |
| 35 | `recommendations` | Optimization tips |
| 43 | `pool` | Pool config |
| 44 | `configuration` | DB config |
| 45 | `health` | Health metrics |

### Analytics Responses (`analytics_responses.py`)
| Line | Field | Description |
|------|-------|-------------|
| 248 | `conversions` | Conversion metrics (admin) |

---

## Category D - DEAD CODE (4 occurrences)

`search_responses.py` schemas are NOT imported anywhere in production code. Replaced by properly-typed `nl_search.py` schemas.

| Line | Field | Status |
|------|-------|--------|
| 103 | `service` | Unused |
| 108 | `coverage_regions` | Unused |
| 125 | `observability_candidates` | Unused |
| 140 | `parsed` | Unused |

**Action**: Consider removing `search_responses.py` or marking as deprecated.

---

## Service Catalog Responses - Deferred

`service_catalog_responses.py` has 3 `Dict[str, Any]` fields:
- `filters_applied` - Could be typed (6 known fields)
- `pagination` - Could be typed (3 known fields)
- `instructors` - Complex nested structure (~30+ fields)

These require significant refactoring of `instructor_service.py` to return typed Pydantic models instead of dictionaries. Marked for future improvement.

---

## Excluded from Schema Count

### Password Reset (`password_reset.py:60-61`)
```python
def model_post_init(self, handler: Callable[["PasswordResetVerifyResponse"], Dict[str, Any]]) -> Dict[str, Any]:
```
This is a **method signature**, not a schema field. Not applicable to API response typing.

### Badge Progress (`badge.py:30,56`)
```python
progress: Optional[BadgeProgressView | Dict[str, Any]]
progress_snapshot: Optional[Dict[str, Any]]
```
These are internal state fields, not user-facing API responses. The `Dict[str, Any]` provides fallback for legacy data migration.

---

## Guardrail Baseline

After this categorization:
- **Category A**: 8 FIXED
- **Category B**: 17 JUSTIFIED (truly dynamic)
- **Category C**: 19 INFRASTRUCTURE (admin-only)
- **Category D**: 4 DEAD CODE

**Recommended baseline**: 36 (B + C)
