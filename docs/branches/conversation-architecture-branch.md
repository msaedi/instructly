# `feat/conversation-architecture` Branch Summary

## Overview
- Total commits: 166
- Files changed: 509
- Net diff: +96,910 / -35,799 lines

---

## 1. Per-User-Pair Conversation Architecture

- Introduced `Conversation` domain model and `conversations` table:
  - One conversation per student–instructor pair.
  - ULID primary key, indexed by student/instructor/last_message_at.
  - DB-level uniqueness enforced via LEAST/GREATEST pair index.
- Messages are keyed by `conversation_id` (booking context optional):
  - `messages.conversation_id` FK to `conversations.id`.
  - `booking_id` retained as nullable for context and display.
- New conversation repository/service/route layer:
  - `ConversationRepository` with idempotent get/create, pagination, unread counts.
  - `ConversationService` handles listing, state, read receipts, upcoming bookings, N+1 avoidance.
  - Versioned routes under `/api/v1/conversations` with zero direct DB access in routes.
- Full multi-phase migration from booking-based messaging to conversation-based:
  - REST APIs updated for list/thread/send/edit/delete/reactions/read receipts.
  - SSE payloads and routing updated to use `conversation_id`.
  - Legacy booking-based routes removed.
- Booking lifecycle system messages:
  - Server-side `SystemMessageService` publishes booking created/cancelled/rescheduled/completed messages.
  - Frontend renders system messages alongside user messages.
- Pre-booking messaging:
  - `/api/v1/conversations` supports creating a conversation and sending first message.
  - UI hooks (`MessageInstructorButton`, `useCreateConversation`) open inbox directly.

---

## 2. Scalable SSE Stack

- Replaced per-client Redis PubSub with a shared Broadcaster multiplexer:
  - `backend/app/core/broadcast.py` holds one `Broadcast(redis_url)` per worker.
  - Startup/shutdown connect/disconnect; readiness checks updated.
- SSE streaming refactor (`backend/app/services/messaging/sse_stream.py`):
  - DB-free streaming after prefetch to avoid idle-in-transaction leaks.
  - Broadcaster subscribe -> internal queue -> SSE events fan-out.
  - Supports `Last-Event-ID`, heartbeat, and safe disconnect handling.
- Publisher refactor (`publisher.py` + `events.py`):
  - Strongly typed event builders with server-side recipient selection.
  - Sync DB lookups wrapped in `asyncio.to_thread` before publish.

---

## 3. Clean-Architecture Enforcement

- Enforced routes -> services -> repositories:
  - Routes no longer perform direct DB queries.
  - Repository pattern expanded across bookings, messaging, analytics, monitoring, search, and more.
- Added pre-commit guardrails:
  - Blocks sync calls inside async functions without `asyncio.to_thread`.
  - Prevents DB access in routes.
  - Enforces `@BaseService.measure_operation` on public service methods.
- Phased elimination of async blocking across hot paths (auth, permissions, bookings, analytics, messaging).

---

## 4. Auth Performance + Safety

- Redis-backed auth caching:
  - User/permission lookups cached for `/auth/me` and SSE auth.
  - Transient ORM objects built from cached dicts to avoid detached instances.
- Reduced redundant DB queries:
  - Avoid eager-loading cascades in auth dependencies.
  - Permission checks use cached values when available.
- SSE auth fixes:
  - Explicit rollbacks and safe disconnect handling.
  - Import and session cleanup fixes to prevent pool leaks.

---

## 5. Login Hardening

- Concurrency slots + queue timeout for login verification.
- Per-account rate limits (minute/hour) with `Retry-After` headers.
- Progressive lockout thresholds.
- Turnstile CAPTCHA enforcement when thresholds hit.
- Prometheus metrics for all outcomes.
- Frontend login UI updated to surface CAPTCHA/lockout states.

---

## 6. Event-Driven Notifications

- Booking domain events introduced (`BookingCreated`, `Cancelled`, `Reminder`, `Completed`).
- Event worker processes `event:*` jobs via centralized handlers.
- Booking flows publish events rather than sending emails inline.
- Background worker moved to dedicated thread; poll interval increased for stability.

---

## 7. Monitoring + Analytics

- New monitoring persistence:
  - `alert_history` table + `AlertsRepository`.
  - Monitoring routes secured by API key.
- Platform config surfaced via `platform_config` table.
- Search analytics overhaul:
  - `SearchAnalyticsRepository` + `SearchAnalyticsService` for aggregate queries.
  - `/api/v1/analytics/search/*` routes reworked to use service/repo pattern.
- Background analytics logging hardened:
  - Fire-and-forget writes now guarded by load threshold and a short timeout.
  - Pool exhaustion returns 503 (with `Retry-After`) instead of 500 for retriable failure.
- Added `metrics_history.json` for historical perf/load snapshots.

---

## 8. Load Testing Harness

- Locust load tests under `backend/tests/load/`:
  - Messaging flows, SSE TTFE, cross-user E2E latency.
  - NL Search specific load test (`locustfile_search.py`).
  - Scenario scripts S0–S4 (smoke, capacity, throughput, burst, soak).
  - CSV/HTML parsing helpers and thresholds.
- CI workflow for on-demand load testing: `.github/workflows/load-test.yml`.
- Rate-limit bypass token supported for load tests.

---

## 9. Database/Infra Changes

- Alembic migrations:
  - Messaging migration (conversations table, conversation_user_state, message FK).
  - Search schema additions: `region_boundaries`, `location_aliases`, `instructor_service_areas`.
  - Monitoring/outbox tables and performance indexes.
- DB session hardening:
  - Rollback-before-close on hot paths to prevent idle-in-transaction leaks.
  - Pool exhaustion now returns 503 (retriable) instead of 500.
- Production reliability:
  - Gunicorn worker recycling (`--max-requests`).
  - Supavisor connection resilience improvements.
- Dependency upgrades:
  - Next.js upgraded for CVE fix.
  - Broadcaster + Locust added; Redis cache moved async.

---

## 10. Frontend Messaging Migration

- New conversation-first API service layer (`frontend/src/api/services/conversations.ts`).
- Hooks updated for conversation list, thread fetch, read receipts, and SSE invalidation.
- Chat UI migrated to `conversation_id`:
  - System message rendering, reactions, typing indicators, read receipts.
  - Booking context displayed when relevant.
- Legacy inbox code removed; tests updated to match conversation schema.

---

## 11. NL Search Performance Optimizations (NEW/EXPAND)

### Baseline Search Architecture (foundational work)
- Multi-city support and location alias architecture (`region_boundaries`, `location_aliases`).
- Hybrid retrieval (pgvector + pg_trgm) with ranking and filtering.
- Location resolution tiers 1–5 (exact, alias, fuzzy, embedding, LLM).
- Self-learning aliases from user behavior and click feedback.

### Phase 0: Stability Patches
- Dedicated concurrency controls and better failure modes for overloaded paths.
- Pool exhaustion converted to 503 (retriable) rather than 500.
- Embedding request coalescing and Redis singleflight to reduce duplicate OpenAI calls.

### Phase 1: AsyncOpenAI Conversion
- Location embedding and LLM services switched to `AsyncOpenAI`.
- Embedding provider and parser align with async OpenAI usage.

### Phase 2: DB Session Two-Burst Pattern
- DB operations split into pre-OpenAI and post-OpenAI bursts.
- Avoids holding DB connections during OpenAI calls.

### Phase 3: Pipeline Parallelization
- Parallelized Burst 1 + embedding generation to reduce tail latency.

### Phase 3.5: Early Tier 5 After Tier 1–3 Miss
- Tier 5 LLM call can start immediately after a Tier 1–3 miss.
- Uses top-k fuzzy candidates to keep prompt small and focused.

### Phase 4: Request Budget + Progressive Degradation
- RequestBudget governs Tier 4/5, vector search, hydration.
- Budget metadata surfaced to clients (degraded/skipped operations).

### Semaphore Strategy (Per-OpenAI Throttling)
- Full-pipeline semaphore replaced with per-OpenAI gating.
- OpenAI calls now gated by `OPENAI_CALL_CONCURRENCY`.
- Soft uncached search limit retained for overall backpressure.

### Tier 5 Fixes
- Timeout enforcement for Tier 5 requests.
- Runtime model selection (default `gpt-4o-mini`).
- Last-chance Tier 5 attempt when Tiers 1–4 miss and budget remains.
- LLM prompt logging for diagnostics.

### Diagnostics + Observability
- Stage-level timing instrumentation across parse, burst1, embedding, location, burst2.
- Location tier breakdown and candidate funnel counts in diagnostics payload.

---

## 12. Admin Dashboard (NEW/EXPAND)

- Search diagnostics page (`/admin/nl-search`):
  - Pipeline timeline visualization with per-stage timing and status.
  - Location tier breakdown (tiers 1–5 with confidence and duration).
  - Request budget visualization and skipped operations.
  - Candidate funnel (text -> vector -> filters -> final).
- Runtime config controls (`/api/v1/admin/search-config`):
  - Parsing model, embedding model (read-only), location model.
  - Parsing/embedding/location timeouts.
  - Budget and high-load settings.
  - OpenAI max retries and uncached concurrency limit.
- Testing overrides:
  - Force skip Tier 4/5, skip embedding/vector, simulate high load.

---

## 13. Load Test Results (NEW/EXPAND)

- Capacity observations recorded in `metrics_history.json`:
  - 25 users: stable baseline.
  - 150 users: stable with expected load shedding.
  - 175+ users: instability due to CPU saturation.
- Key fixes reflected in test results:
  - Pool exhaustion now returns 503 with `Retry-After`.
  - Analytics writes skip under high load to prevent pool starvation.
  - OpenAI call concurrency gated separately from fast-path queries.

---

## 14. Configuration Reference (NEW)

### Search + OpenAI
| Variable | Default | Description |
|----------|---------|-------------|
| `OPENAI_PARSING_MODEL` | `gpt-5-nano` | Query parsing model |
| `OPENAI_PARSING_TIMEOUT_MS` | `1000` | Parsing timeout |
| `OPENAI_EMBEDDING_MODEL` | `text-embedding-3-small` | Embedding model |
| `OPENAI_EMBEDDING_TIMEOUT_MS` | `2000` | Embedding timeout |
| `OPENAI_LOCATION_MODEL` | `gpt-4o-mini` | Tier 5 location model |
| `OPENAI_LOCATION_TIMEOUT_MS` | `3000` | Tier 5 timeout |
| `OPENAI_MAX_RETRIES` | `2` | OpenAI retries |
| `OPENAI_TIMEOUT_S` | `2.0` | Legacy OpenAI timeout (some providers) |
| `OPENAI_CALL_CONCURRENCY` | `3` | Per-worker OpenAI call concurrency |
| `SEARCH_BUDGET_MS` | `500` | Default request budget |
| `SEARCH_HIGH_LOAD_BUDGET_MS` | `300` | Budget under load |
| `SEARCH_HIGH_LOAD_THRESHOLD` | `10` | High-load threshold |
| `UNCACHED_SEARCH_CONCURRENCY` | `6` | Soft cap per worker |
| `SEARCH_ANALYTICS_TIMEOUT_S` | `0.5` | Analytics write timeout |
| `EMBEDDING_PROVIDER` | `openai` | Embedding provider (`openai` or `mock`) |
| `EMBEDDING_DIMENSIONS` | `1536` | Embedding vector size |

### Search Tuning (Advanced)
| Variable | Default | Description |
|----------|---------|-------------|
| `LOCATION_LLM_TOP_K` | `5` | Top-k candidates for Tier 5 prompt |
| `LOCATION_TIER4_HIGH_CONFIDENCE` | `0.85` | Tier 4 confidence threshold |
| `LOCATION_LLM_CONFIDENCE_THRESHOLD` | `0.7` | Tier 5 confidence threshold |
| `LOCATION_LLM_EMBEDDING_THRESHOLD` | `0.7` | Threshold for LLM embedding candidates |
| `NL_SEARCH_TEXT_SKIP_VECTOR_SCORE_THRESHOLD` | `0.60` | Skip vector if text is strong |
| `NL_SEARCH_TEXT_SKIP_VECTOR_MIN_RESULTS` | `10` | Minimum text matches for skip |
| `NL_SEARCH_TEXT_REQUIRE_TEXT_MATCH_SCORE_THRESHOLD` | `0.45` | Require text support for vector-only |
| `NL_SEARCH_EMBEDDING_SOFT_TIMEOUT_MS` | unset | Soft timeout for embeddings |
| `NL_SEARCH_PERF_LOG` | unset | Enable perf logging |
| `NL_SEARCH_PERF_LOG_SLOW_MS` | `0` | Slow log threshold |

### Load Testing
| Variable | Description |
|----------|-------------|
| `LOADTEST_BYPASS_TOKEN` | Bypass rate limits in load tests |
| `LOADTEST_USERS` | Comma-separated load test users |
| `LOADTEST_PASSWORD` | Shared password for test users |
| `LOADTEST_BASE_URL` | Target API base URL |
| `LOADTEST_FRONTEND_ORIGIN` | Frontend origin for CSRF |
| `LOADTEST_SSE_HOLD_SECONDS` | SSE hold duration |
| `LOADTEST_E2E_TIMEOUT_SECONDS` | E2E timeout |

---

## 15. Deletions/Cleanup

- Removed legacy booking-based messaging routes, repositories, and tests.
- Removed deprecated conversation_state model in favor of `conversation_user_state`.
- Cleaned up dead code and fixed Knip config to avoid false positives.
- Replaced full-pipeline search semaphore with per-OpenAI gating.

---

## 16. Migration Notes

- Messaging: clients must use `conversation_id` and updated SSE payloads.
- Search: location resolution tiers and diagnostics now surfaced in metadata.
- Admin UI: new `/api/v1/admin/search-config` endpoint for runtime tuning.
- Load testing: requires `LOADTEST_BYPASS_TOKEN` to avoid rate limits.
- Rollback: revert NL search phases in reverse (budget -> parallel -> two-burst -> async OpenAI).
