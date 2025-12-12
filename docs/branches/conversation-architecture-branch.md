# `feat/conversation-architecture` branch summary

This branch is a large architectural and feature migration centered on messaging, real‑time delivery, and clean‑architecture enforcement, with substantial auth hardening and performance work across the stack. Net diff: ~26.7k insertions / ~10.8k deletions across 267 files.

## 1. Per‑user‑pair conversation architecture (backend + frontend)

- Introduced a new `Conversation` domain model (`backend/app/models/conversation.py`) and `conversations` table:
  - One conversation per student–instructor pair regardless of bookings.
  - ULID primary key, indexed by student/instructor/last_message_at.
  - DB‑level uniqueness enforced via a LEAST/GREATEST pair unique index.
- Messages are now primarily keyed by `conversation_id` (booking remains optional context):
  - `messages.conversation_id` FK to `conversations.id`.
  - `booking_id` kept nullable for contextual filtering/display.
- Added full repository/service/routing stack for conversations:
  - `ConversationRepository` with idempotent `get_or_create`, cursor pagination, unread counts, and state filtering via JOINs.
  - `ConversationService` for business logic: list/detail, message send w/ booking tagging, typing, unread batching, per‑user state (active/archived/trashed), batch upcoming bookings, N+1 avoidance.
  - New versioned routes under `/api/v1/conversations` (`backend/app/routes/v1/conversations.py`) with zero direct DB access in routes.
- Completed multi‑phase migration from `booking_id`‑based messaging to `conversation_id`:
  - REST APIs updated for conversation list, thread fetch, send/edit/delete, reactions, read receipts, typing, unread totals.
  - Removed legacy booking‑based endpoints and dead code (e.g., old `backend/app/routes/messages.py`).
  - Updated all SSE routing and payloads to include `conversation_id` for client‑side targeting.
- Added booking lifecycle system messages:
  - Backend `SystemMessageService` generates system messages on booking created/cancelled/rescheduled/completed.
  - Frontend `SystemMessage` component renders these alongside user messages.
- Enabled pre‑booking messaging:
  - Backend POST `/api/v1/conversations` creates/returns pair conversation and can accept an initial message.
  - Frontend `MessageInstructorButton` + `useCreateConversation` allow users to start a chat before booking and navigate directly to inbox.

## 2. Scalable SSE stack (v4.0 Broadcaster fan‑out)

- Replaced per‑client Redis PubSub connections with a shared Broadcaster multiplexer:
  - New `backend/app/core/broadcast.py` holds a single `Broadcast(redis_url)` per worker.
  - Startup/shutdown lifecycle connects/disconnects the broadcast instance; readiness checks updated.
- SSE stream refactor (`backend/app/services/messaging/sse_stream.py`):
  - DB‑free streaming after prefetch to prevent “idle in transaction” leaks.
  - Uses Broadcaster subscribe → internal asyncio queue → SSE events fan‑out.
  - Supports `Last-Event-ID` catch‑up, heartbeat, safe disconnect handling (`GeneratorExit`), no busy‑wait.
- Publishing refactor (`backend/app/services/messaging/publisher.py` + `events.py`):
  - Strongly typed event builders (`new_message`, `reaction_update`, `read_receipt`, `typing_status`, `message_edited`, `message_deleted`).
  - Recipients derived server‑side from conversation participants (defense‑in‑depth).
  - All sync DB lookups wrapped in `asyncio.to_thread` before publish.

## 3. Clean‑architecture enforcement + async blocking elimination

- Massive refactor to enforce “routes → services → repositories”:
  - Routes no longer call `db.query()` directly; all DB access moved into repositories/services.
  - Updated/added repositories across domains (booking, message, conversation_state, availability, instructor_profile, user, alerts, metrics, payment monitoring, search analytics, jobs).
  - Added `RepositoryFactory` to centralize repository instantiation.
- Added pre‑commit guardrails:
  - `check-repository-pattern` blocks DB access from services.
  - `check-no-db-in-routes` blocks DB access from routes.
  - `check-async-blocking` flags sync blocking calls inside async functions lacking `asyncio.to_thread`.
  - `check_service_metrics` enforces `@BaseService.measure_operation` on public service methods.
- Phased wrapping of remaining sync operations in `asyncio.to_thread` to keep the event loop responsive under load:
  - Messaging, auth, permissions, bookings, analytics, notifications, background checks, etc.

## 4. Auth performance improvements + safety fixes

- Added Redis‑backed auth caching (`backend/app/core/auth_cache.py`):
  - Non‑blocking user lookups for auth dependencies and SSE auth.
  - Cache stores user dict incl. roles/permissions; transient ORM objects built from dicts avoid `DetachedInstanceError`.
  - Cache TTL increased to 30 minutes; graceful fallback if Redis unavailable.
- Optimized `/auth/me` and core auth deps:
  - Removed redundant DB lookups/eager‑loading cascades.
  - Permission checks use cached permissions to avoid hot‑path DB queries.
- Fixed SSE auth/session leaks:
  - Explicit rollbacks before close.
  - Correct Redis imports and cleanup.
  - Handle disconnects cleanly to avoid generator/runtime errors.

## 5. Login hardening: rate limiting, lockout, CAPTCHA

- Added `backend/app/core/login_protection.py`:
  - Global concurrency semaphore with queue timeout.
  - Per‑account (email) rate limits per minute/hour.
  - Progressive lockout thresholds with `Retry-After`.
  - Turnstile CAPTCHA verification when required.
  - Prometheus counters/histograms for all outcomes.
- Integrated into login endpoint (`/api/v1/auth/login`) and related auth flows.
- Frontend login UI updated (`frontend/app/(shared)/login/LoginClient.tsx`):
  - Renders Turnstile widget when backend signals CAPTCHA requirement.
  - Includes `captcha_token` on retry.
  - Displays rate‑limit cooldown UI.
- Added comprehensive unit tests for lockouts, CAPTCHA gating, and login concurrency slots.

## 6. Event‑driven notification architecture

- Introduced booking domain events (`BookingCreated`, `BookingCancelled`, `BookingReminder`, `BookingCompleted`) and `EventPublisher`.
- Background worker now processes `event:*` jobs via centralized handlers (`backend/app/events/handlers.py`), delegating to `NotificationService`.
- Booking flows updated to publish events rather than sending emails inline.
- Worker moved to a dedicated thread and poll interval increased to 60s for stability.

## 7. Monitoring + analytics + platform config

- Added monitoring persistence and APIs:
  - New `alert_history` table plus `AlertsRepository`.
  - New `/api/monitoring/alerts/*` routes secured by a monitoring API key.
  - New metrics/payment monitoring repositories feeding monitoring routes.
- Added `platform_config` table for dynamic server‑side configuration.
- Search analytics overhaul:
  - New `SearchAnalyticsRepository` with aggregate queries.
  - New `SearchAnalyticsService`.
  - `/api/v1/analytics/search/*` routes rewritten to use service/repo layer and non‑blocking `to_thread`.
- Added `metrics_history.json` artifact (historical perf/load results).

## 8. Load testing harness + CI

- Added Locust load tests under `backend/tests/load/`:
  - Scenarios S0–S4 (smoke, capacity, throughput, burst, soak).
  - Measures login success, SSE TTFE, and cross‑user E2E delivery latency.
  - Threshold checks and a parser for CSV/HTML results.
- New GitHub Actions workflow `.github/workflows/load-test.yml` for manual CI smoke load tests.
- Added a rate‑limit bypass token specifically for load testing.

## 9. Database, infra, and dependency changes

- Alembic migrations updated to:
  - Create `conversations` table before `messages`.
  - Add/migrate `messages.conversation_id`, update triggers to publish `conversation_id` in SSE payloads.
  - Migrate `conversation_user_state` from booking to conversation, add unique constraints/indexes.
  - Add final schema constraints, monitoring/outbox tables, RLS policies, and performance indexes.
- Hardened DB session/pool behavior:
  - Rollback‑before‑close everywhere on hot paths to avoid Supabase/Supavisor idle‑transaction kills.
  - Tuned pool sizes and recycle settings; added “zombie protection.”
- Added Gunicorn for production worker recycling (`--max-requests` pattern).
- Backend deps: `argon2-cffi` (Argon2id hashing), `broadcaster[redis]` (SSE fan‑out), `locust` (load tests), `gunicorn`.
- Frontend deps: upgraded Next.js to `15.5.7` for CVE‑2025‑55182; added Turnstile React wrapper.
- Redis config and `.gitignore` updated for new artifacts/results.
- Fixed misc issues: Checkr client typing, seeding overlap detection, Alembic `statement_timeout` connect_args, admin BGC tests, readiness probe, session isolation.

## 10. Frontend messaging/UI migration

- Conversation‑first API service layer added (`frontend/src/api/services/conversations.ts`) plus strongly typed interfaces (`frontend/types/conversation.ts`).
- Instructor inbox/hooks updated to new conversation list API and SSE invalidation (`useConversations`, `useConversationMessages`, etc.).
- Chat UI updated:
  - Fetches history by `conversation_id` (not booking).
  - Handles system messages, reactions, read receipts, typing indicators, delivered/edited states.
  - Shows booking context and supports read‑only mode for closed chats.
- Removed legacy inbox state and generated message clients (`useInboxState`, old `messages-v1` Orval output, outdated tests).
- Added new tests for `MessageInstructorButton` and updated chat/conversation hooks tests.

## 11. Notable deletions/cleanup

- Deleted legacy messaging routes, repositories, services, and tests tied to booking‑based architecture.
- Removed deprecated `conversation_state` model (replaced by per‑user `conversation_user_state`).
- Cleaned up dead code and fixed Knip config to avoid false positives.

## 12. Local note

- Your working tree currently has an uncommitted change in `backend/tests/integration/availability/test_week_etag_and_conflicts.py`; it is not part of the branch history.
