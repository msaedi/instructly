# Axiom APL Query Reference

Dataset: `instainstru-logs` (OTel traces exported via OTLP)

All queries verified against production data on 2026-04-08.

---

## 1. 5xx Errors Last Hour (by Service and Route)

Finds all spans with error status, grouped by service and span name (route).
Use to identify which endpoints are throwing errors and in which environment.

```apl
['instainstru-logs']
| where ['status.code'] == "ERROR"
| summarize error_count = count() by ['service.name'], name
| order by error_count desc
| take 20
```

**Time range:** 1 hour

**Notes:**
- `status.code` is the OTel status, not HTTP status. Value is `"ERROR"` for failures.
- `name` on server spans is the HTTP route (e.g., `GET /api/v1/search`).
  On client spans it's the operation (e.g., `SELECT postgres`, `connect`).
- To filter to HTTP errors only, add `| where kind == "server"`.

---

## 2. Top 10 Slowest Endpoints by p95 (Last 24h)

Ranks server-side endpoints by 95th percentile duration.
Use to find the slowest user-facing routes.

```apl
['instainstru-logs']
| where kind == "server"
| summarize p95_duration = percentile(duration, 95) by name
| order by p95_duration desc
| take 10
```

**Time range:** 24 hours

**Notes:**
- `duration` is a timespan type (nanosecond precision). Axiom displays in human-readable form.
- `kind == "server"` filters to inbound HTTP request spans only (excludes DB, Redis, outbound HTTP).
- To convert to milliseconds in output: `| extend p95_ms = p95_duration / 1ms`

---

## 3. Search Pipeline Trace Breakdown

Given a search request's `trace_id`, shows all spans in the trace ordered chronologically.
Use to understand the full execution path: FastAPI handler, Redis cache checks, SQLAlchemy queries, response serialization.

```apl
['instainstru-logs']
| where trace_id == "<TRACE_ID>"
| project _time, name, kind, duration, ['service.name'], parent_span_id, span_id, ['scope.name']
| order by _time asc
```

**Time range:** Narrow to the hour containing the trace (required for performance).

**How to find a search trace_id:**
```apl
['instainstru-logs']
| where name == "GET /api/v1/search" and kind == "server"
| project _time, trace_id, duration, ['service.name']
| take 5
```

**Typical search trace anatomy (verified):**
1. `GET /api/v1/search` (server) -- root span, ~240-320ms
2. `PING`, `EVAL`, `GET` (client, redis) -- rate limiter + cache checks, ~1-5ms each
3. `connect` (client, sqlalchemy) -- pool checkout, ~0.5ms
4. `SELECT` (client, sqlalchemy) -- permission/config queries, ~0.3-1.5ms each
5. `WITH` (client, sqlalchemy) -- main search CTE query, ~10-150ms (dominant)
6. `SETEX` (client, redis) -- cache write, ~1-9ms
7. `INSERT` (client, sqlalchemy) -- search history write, ~4ms
8. `GET /api/v1/search http send` (internal) -- response serialization, ~0.01ms

---

## 4. Error Rate by Service (Last 24h)

Shows total requests, error count, and error percentage for each service.
Use for daily health checks and SLO tracking.

```apl
['instainstru-logs']
| where kind == "server"
| summarize
    total = count(),
    errors = countif(['status.code'] == "ERROR"),
    error_rate = round(100.0 * countif(['status.code'] == "ERROR") / count(), 2)
  by ['service.name']
| order by error_rate desc
```

**Time range:** 24 hours

**Notes:**
- Filtered to `kind == "server"` to count only inbound HTTP requests.
- Services: `instainstru-api` (prod), `instainstru-preview-api` (preview),
  `instainstru-worker`/`instainstru-preview-worker` (Celery),
  `instainstru-mcp`/`instainstru-preview-mcp` (MCP server).

---

## 5. Connect Span Investigation (Count + Duration Distribution)

Counts SQLAlchemy `connect` spans per service with duration percentiles.
Use to monitor connection pool checkout behavior and detect connection churn.

```apl
['instainstru-logs']
| where name == "connect"
| summarize
    span_count = count(),
    p50 = percentile(duration, 50),
    p95 = percentile(duration, 95),
    p99 = percentile(duration, 99)
  by ['service.name']
| order by span_count desc
```

**Time range:** 1 hour

**Notes:**
- These spans are emitted by `opentelemetry.instrumentation.sqlalchemy` on every
  `Engine.connect()` call, which fires on every connection pool checkout.
- Normal p50: ~4ms (prod via Supavisor on port 6543), ~0.8ms (local).
- ~11K/hour was the pre-filter volume (51% of total ingest).
- **Status (2026-04-08):** `FilteringSpanProcessor` in `backend/app/monitoring/otel.py`
  now suppresses these spans before they reach the exporter (filters by span name +
  instrumentation scope). Expected post-filter volume: ~0 from sqlalchemy scope.
  Other `connect` spans (e.g., from Redis) are unaffected.
- To check if connect spans have parent traces vs orphaned:
  ```apl
  ['instainstru-logs']
  | where name == "connect"
  | summarize
      has_parent = countif(isnotempty(parent_span_id)),
      no_parent = countif(isempty(parent_span_id)),
      total = count()
  ```

---

## 6. All Errors for a Specific User

Finds all error spans associated with a user ID.
Use to investigate user-reported issues or trace a user's problematic requests.

```apl
['instainstru-logs']
| where ['attributes.custom']['app.user_id'] == "<USER_ULID>"
| where ['status.code'] == "ERROR"
| project _time, name, duration, ['service.name'], ['attributes.custom']
| order by _time desc
```

**Time range:** 24 hours (or narrow to the user's reported timeframe)

**Notes:**
- `app.user_id` is set via `add_business_context()` in `backend/app/monitoring/otel.py`.
- Injected automatically on all authenticated requests (via the auth dependency),
  plus explicitly on search, booking, and payment spans.
- These attributes live in `attributes.custom` map (Axiom OTLP receiver behavior),
  not as top-level columns. This is by design -- Axiom only promotes standard
  OTel semantic convention fields to top-level.
- Available business attributes: `app.user_id`, `app.instructor_id`,
  `app.booking_id`, `app.category`.
- To find all requests for a user (not just errors):
  ```apl
  ['instainstru-logs']
  | where ['attributes.custom']['app.user_id'] == "<USER_ULID>"
  | where kind == "server"
  | project _time, name, duration, ['status.code']
  | order by _time desc
  ```

---

## 7. Search Pipeline Stage Breakdown (p50/p95/p99 per Stage)

Shows duration percentiles for each pipeline stage span over the last 24 hours.
Use to identify which stage is the bottleneck in slow searches.

```apl
['instainstru-logs']
| where name startswith "search."
| summarize
    p50 = percentile(duration, 50),
    p95 = percentile(duration, 95),
    p99 = percentile(duration, 99),
    total = count()
  by name
| order by p95 desc
```

**Time range:** 24 hours

**Notes:**
- Stage spans: `search.preflight`, `search.ai_stage`, `search.postflight`,
  `search.hydration`, `search.location.setup`, `search.location.tier4`,
  `search.location.tier5`.
- `search.preflight` and `search.postflight` are wall-clock spans only
  (due to `asyncio.to_thread` context loss). For internal sub-stage
  breakdown, use the `PipelineTimer` diagnostics (`?diagnostics=true`).
- Location tier spans include attributes: `location.tier4.resolved`,
  `location.tier4.confidence`, `location.tier4.candidate_count`,
  `location.tier5.resolved`, `location.resolved_tier`.
- To drill into a specific tier's performance:
  ```apl
  ['instainstru-logs']
  | where name == "search.location.tier5"
  | summarize p50 = percentile(duration, 50), p95 = percentile(duration, 95) by bin_auto(_time)
  ```

---

## Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `name` | string | Span name (HTTP route for server spans, operation for client spans) |
| `kind` | string | `server`, `client`, `internal`, `producer`, `consumer` |
| `duration` | timespan | Span duration (nanosecond precision) |
| `service.name` | string | Service identifier (e.g., `instainstru-api`) |
| `status.code` | string | OTel status: empty (OK), `"ERROR"` |
| `trace_id` | string | 32-char hex trace ID |
| `span_id` | string | 16-char hex span ID |
| `parent_span_id` | string | Parent span ID (empty for root spans) |
| `scope.name` | string | Instrumentation library (e.g., `opentelemetry.instrumentation.fastapi`) |
| `attributes.custom` | map | Span-specific attributes (db.system, db.name, net.peer.name, etc.) |
| `attributes.http.route` | string | HTTP route template (on server spans) |
| `resource.custom` | map | Resource attributes (e.g., `deployment.environment`) |
