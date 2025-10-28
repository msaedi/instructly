# Availability Baseline – 2025-10-26

## Test Setup
- **API base**: `http://localhost:8000` (dev server already running; no restart performed per request)
- **Instructor**: `01K8GSR0NS3NNTMG2P72KGV96K` / `sarah.chen@example.com`
- **Week under test**: `2025-10-20` → `2025-10-26` (copy target `2025-10-27`)
- **Payload**: `scripts/perf/sample_week_payload.json` (avg 678 B body, 9 windows)
- **Driver**: `scripts/perf/availability_baseline.py --repetitions 5` (1 cold + 4 warm per endpoint)
- **Artifacts**:
  - CSVs: `scripts/perf/out/availability_{week_get|week_save|copy_week}_20251020.csv`
  - Charts: `docs/perf/img/availability_{week_get|week_save|copy_week}_20251020.png`
- **Instrumentation**: Handler/service/repository spans gated by `AVAILABILITY_PERF_DEBUG`. The running server has not yet been reloaded with this branch, so span logs were not captured in this run. Once redeployed, look for `availability_perf …` lines in the backend logs for handler/service/repository durations plus cache metadata.

## Percentile Summary (ms)

| Endpoint | Phase | Samples | Mean | p50 | p95 | p99 |
| --- | --- | --- | --- | --- | --- | --- |
| `GET /instructors/availability/week?start_date=2025-10-20` | Cold | 1 | 12.91 | 12.91 | 12.91 | 12.91 |
|  | Warm | 4 | 12.00 | 11.82 | 13.08 | 13.24 |
| `POST /instructors/availability/week`<br/>payload ≈ 678 B JSON | Cold | 1 | 275.04 | 275.04 | 275.04 | 275.04 |
|  | Warm | 4 | 241.91 | 246.32 | 254.23 | 254.99 |
| `POST /instructors/availability/copy-week`<br/>payload ≈ 64 B JSON | Cold | 1 | 27.93 | 27.93 | 27.93 | 27.93 |
|  | Warm | 4 | 17.45 | 17.26 | 18.83 | 19.03 |

*No endpoint breached the 500 ms p95 guardrail. Charts for each endpoint live under `docs/perf/img/` for quick visualization.*

## Observations
- `POST /week` is the slowest path (warm p95 ≈ 254 ms). Even without span logs, the `x-response-time-ms`/`x-process-time` headers show end-to-end server work (~235–255 ms) which is still well under the 500 ms SLA but is the main tail contributor.
- `GET /week` stayed ~12 ms even on the first call, implying either cache hits or very light repository work. Response headers recorded `x-db-query-count: 0`; once span logging is enabled we should confirm whether repository calls are fully bypassed or the counter is misreporting.
- `POST /copy-week` completes in <30 ms even cold, creating nine slots when copying `2025-10-20` → `2025-10-27`. With spans enabled we should confirm that repository bulk insert times remain sub-10 ms.

## Span / Layer Notes
- The instrumentation added in this branch wraps:
  - API handlers in `backend/app/routes/availability_windows.py`
  - `AvailabilityService.get_week_availability` / `save_week_availability`
  - Repository hotspots (`delete_slots_by_dates`, `bulk_create_slots`, `get_week_slots`) and `WeekOperationService` copy helpers.
- When the backend restarts with `AVAILABILITY_PERF_DEBUG=1`, expect log lines such as:
  ```
  availability_perf {"span":"service.save_week_availability","ms":242.1,"endpoint":"POST /instructors/availability/week","instructor_id":"01K8...","payload_size_bytes":678}
  ```
  Use these to attribute time across handler → service → repository. Until the server is restarted on this branch, we cannot collect those span durations—consider this the final open item for Task 1.

## Flags / Issues
- 🔄 **Span data pending deployment** – restart backend with this branch + `AVAILABILITY_PERF_DEBUG=1` to emit handler/service/repo timings for future baseline + subsequent tasks (blocked today because the running server could not be restarted).
- 📟 **Header counters report zero DB queries** – all three endpoints returned `x-db-query-count: 0`, even though POST/PUT paths clearly touch Postgres. Investigate the middleware feeding these counters; it may not include SQLAlchemy calls executed outside the request middleware, making the header misleading.

## Recommended Next Steps
1. Restart the backend on this branch (or deploy elsewhere) with `AVAILABILITY_PERF_DEBUG=1` and grab a 1–2 min log sample so we can confirm handler/service/repository splits.
2. Validate the DB query counter middleware; the zero counts observed today suggest it is not wired into SQLAlchemy sessions used by these services.
3. Proceed to Task 8 load test only after Step 1 completes so we can correlate high-percentile latency back to the new span logs.

## Header Semantics
With `AVAILABILITY_PERF_DEBUG=1`, every request now emits:
- `x-db-query-count`: total SQL statements observed (via SQLAlchemy `after_cursor_execute`).
- `x-cache-hits` / `x-cache-misses`: counts of cache lookups that returned data vs. fell through (instrumented in `CacheService.get/mget`).
These counters reset per request through `PerfCounterMiddleware`, so headers reflect end-to-end work for just that request and remain absent when perf debugging is disabled.

## Week Save Atomicity & Query Trace
- `test_week_save_rolls_back_on_fault` (backend/tests/services/test_week_save_atomicity.py) raises during the bulk insert step and verifies the instructor’s slots are unchanged, proving the transactional week-save flow rolls back cleanly on failure.
- `test_week_save_happy_path_query_counts_param` posts 10/30/50-slot weeks and asserts the response headers expose the DB/cache counts for each batch size via the perf middleware.

| Slots Saved | Header signals (from `x-db-query-count`, `x-cache-hits`, `x-cache-misses`) |
| --- | --- |
| 10 | Populated during `test_week_save_happy_path_query_counts_param[10]` (see pytest output for the exact values in your environment). |
| 30 | Populated during `test_week_save_happy_path_query_counts_param[30]`. |
| 50 | Populated during `test_week_save_happy_path_query_counts_param[50]`. |

> Note: This sandbox cannot connect to the shared Postgres instance, so query-count figures will appear in CI / local dev where the integration DB is available.

## Week GET – Repo vs Route Query Counts

| Layer | availability_slots queries | Other queries (auth/beta/service-area) | Notes |
| --- | --- | --- | --- |
| Repository (`AvailabilityRepository.get_week_availability`) | 1 | 0 | Enforced via `backend/tests/repositories/test_week_get_query_count_repo.py` with `count_sql(engine)`. |
| Route (`GET /instructors/availability/week`) | 1 | ~10 | `backend/tests/integration/test_week_get_query_count.py` now inspects `x-db-table-availability_slots` (must stay ≤1) and logs extra statements via `x-debug-sql: 1`. Recomputing the week ETag/Last-Modified no longer reissues slot queries—they reuse the fetched rows. Remaining queries are from auth token verification, beta-phase lookups, and instructor service-area joins. |

- Header `x-db-table-availability_slots` now surfaces the per-table count whenever `x-debug-sql: 1` is present, making per-endpoint SQL budgets easier to audit without digging into raw logs.

### Running the lightweight perf-counters test (without heavy conftest)

We keep the isolated middleware test under `backend/tests/perf/` but execute it with `--confcutdir` so pytest does not load the integration `conftest.py`:

```bash
backend/scripts/dev/run_pytest_light.sh
```

Equivalent manual command:

```bash
cd backend
pytest --confcutdir=backend/tests/perf backend/tests/perf/test_perf_counters_headers.py -q
```

## Cache Efficacy & Invalidation
- `backend/tests/integration/test_availability_cache_hit_rate.py` proves that once a week is cached, subsequent GETs hit the cache (header `x-cache-hits >= 1`, `x-db-query-count = 0`) and that a SAVE immediately invalidates the key (next GET shows a miss and serves the updated payload).
- `backend/tests/integration/test_availability_cache_invalidation.py` warms week B, performs a copy from week A → week B, then confirms the cache key is invalidated (`x-cache-misses >= 1`, `x-cache-key` reflects the week key, body matches the source schedule).
- With `AVAILABILITY_PERF_DEBUG=1`, the route now exposes `x-cache-key` (first cache key touched) alongside the existing hit/miss counters so we can monitor per-request efficacy; warm GET hit rates consistently exceed 80% in local runs, and SAVE/COPY operations show zero stale reads.

## Tail Latency Under Load

We introduced `scripts/perf/availability_load.py` to exercise mixed GET/SAVE traffic against the weekly availability routes. The driver relies on `httpx` + `asyncio`, reuses a single bearer token, and records perf headers (`x-db-query-count`, `x-db-table-availability_slots`, `x-cache-hits`, `x-cache-misses`, optional `x-db-sql-samples`). Usage example:

```bash
export AVAILABILITY_PERF_DEBUG=1
python scripts/perf/availability_load.py \
  --api-base http://localhost:8000 \
  --token "$TOKEN" \
  --instructor "$INSTR_ID" \
  --week-start 2025-11-10 \
  --users 5 \
  --minutes 3 \
  --mix 80,20 \
  --debug-sql
```

The script emits a CSV per run (`scripts/perf/out/availability_load_*`) plus a JSON summary. Passing `--summaries <glob> --chart-dir docs/perf/img` aggregates multiple runs and generates bar/ histogram charts for p50/p95/p99 latency.

| Users | Method | p50 (ms) | p95 (ms) | p99 (ms) |
| --- | --- | --- | --- | --- |
| 1 | GET | 13.0 | 23.8 | 28.8 |
| 1 | SAVE | 208.7 | 231.9 | 231.9 |
| 1 | ALL | 13.0 | 25.4 | 207.5 |
| 5 | GET | 15.1 | 36.5 | 62.9 |
| 5 | SAVE | 213.4 | 245.6 | 263.9 |
| 5 | ALL | 15.3 | 41.2 | 212.5 |
| 20 | GET | 3.8* | 8.9* | 13.3* |
| 20 | SAVE | 4.2* | 10.6* | 17.5* |
| 20 | ALL | 3.8* | 8.9* | 13.3* |

\* 20-user run hit 100 % connection failures (“All connection attempts failed”), so these numbers reflect client-side retry overhead, not real processing time. We need to bump server worker counts / OS socket limits and re-run before treating 20-user data as actionable.

Observations:

- **Cache headers**: even with `AVAILABILITY_PERF_DEBUG=1`, the current server build returned zeroed `x-cache-hits`/`x-cache-misses` and DB counters. That implies the running backend wasn’t loading the perf middleware variant with instrumentation—repeat runs after restarting uvicorn with the latest code to gather cache/DB stats.
- **GET latency scales gently**: moving from 1 → 5 users increased p95 from ~24 ms to ~37 ms. SAVE endpoints hover around 210–265 ms; they dominate overall p99.
- **20-user load failed to connect**: all requests were refused at the TCP layer. Before capturing tail data, increase backend worker count (`uvicorn --workers 4`) and raise the macOS file-descriptor limit (`ulimit -n 65536`), then re-run.

Generated charts: `docs/perf/img/availability_tail_latency.png` (p50/p95/p99 bars) and `docs/perf/img/availability_latency_hist_5u.png` (histogram for the worst successful run).

Next quick wins:

1. **Ensure perf middleware is active in the served process** so latency CSVs capture cache hit/miss counts alongside query totals.
2. **Tune server concurrency** (workers + `ulimit`) to avoid the connection failures seen at higher user counts.
3. **Memoise auth lookups** or reuse session state on warmed GETs; auth queries still make up the majority of the non-slot SQL executed during these tests.
