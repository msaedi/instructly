## Existing Event Infrastructure Report

### Event System
- Location: `backend/app/events/publisher.py`, `backend/app/events/handlers.py`, `backend/app/events/booking_events.py`, `backend/app/main.py`
- How it works: `EventPublisher.publish()` enqueues rows in `background_jobs` with type `event:{EventName}`; `_background_jobs_worker_sync` pulls jobs and dispatches to `EVENT_HANDLERS` via `process_event`.
- Current events (job-queue): `BookingCreated`, `BookingCancelled`, `BookingReminder` (note: `BookingCompleted` exists but is not published or handled).
- Location (outbox): `backend/app/repositories/event_outbox_repository.py`, `backend/app/services/booking_service.py`, `backend/app/services/availability_service.py`, `backend/app/services/week_operation_service.py`, `backend/app/tasks/notification_tasks.py`
- How it works (outbox): services enqueue `event_outbox` rows in-transaction; Celery tasks `outbox.dispatch_pending` and `outbox.deliver_event` deliver with retries and backoff.
- Current events (outbox): `booking.created`, `booking.cancelled`, `booking.completed`, `booking.no_show`, `availability.week_saved`, `availability.week_copied`.
- Location (referral events): `backend/app/events/referral_events.py`, emitters in `backend/app/services/referral_service.py`, `backend/app/services/wallet_service.py`
- How it works (referral): in-process listener registry; dispatch is synchronous and best-effort.
- Current events (referral): `ReferralCodeIssued`, `ReferralLinkClicked`, `ReferredSignup`, `FirstBookingCompleted`, `RewardPending`, `RewardUnlocked`, `RewardRedeemed`, `RewardVoided`; no listener registrations found.
- Location (messaging pub/sub): `backend/app/services/messaging/events.py`, `backend/app/services/messaging/publisher.py`, `backend/app/services/messaging/sse_stream.py`, `backend/app/core/broadcast.py`
- How it works (messaging): SSE uses Broadcaster to publish JSON events to Redis channels `user:{id}`; the broadcast connection is initialized in `backend/app/main.py`.
- Current events (messaging): `new_message`, `typing_status`, `reaction_update`, `message_edited`, `read_receipt`, `message_deleted`.
- Event -> cache invalidation: no direct event-driven cache invalidation found; `backend/app/services/search/cache_invalidation.py` defines hooks but has no call sites.

### Celery Tasks
- Task files:
  - `backend/app/tasks/analytics.py`
  - `backend/app/tasks/badge_digest.py`
  - `backend/app/tasks/badge_tasks.py`
  - `backend/app/tasks/beat.py`
  - `backend/app/tasks/beat_schedule.py`
  - `backend/app/tasks/celery_app.py`
  - `backend/app/tasks/celery_init.py`
  - `backend/app/tasks/codebase_metrics.py`
  - `backend/app/tasks/email.py`
  - `backend/app/tasks/embedding_migration.py`
  - `backend/app/tasks/location_learning.py`
  - `backend/app/tasks/monitoring_tasks.py`
  - `backend/app/tasks/notification_tasks.py`
  - `backend/app/tasks/payment_tasks.py`
  - `backend/app/tasks/privacy_audit_task.py`
  - `backend/app/tasks/privacy_tasks.py`
  - `backend/app/tasks/referrals.py`
  - `backend/app/tasks/retention_tasks.py`
  - `backend/app/tasks/search_analytics.py`
  - `backend/app/tasks/search_history_cleanup.py`
  - `backend/app/tasks/worker.py`
- Task pattern: `celery_app` defined in `backend/app/tasks/celery_app.py` with `@celery_app.task` and typed_task wrappers; tasks are registered via autodiscovery and forced imports; some tasks use `shared_task` (privacy audit, search history cleanup).
- Queues defined: `celery`, `email`, `notifications`, `analytics`, `maintenance`, `payments` in `backend/app/tasks/celery_app.py`; `privacy` appears in `backend/app/tasks/beat_schedule.py`; `bookings` and `cache` are present in worker defaults (`backend/app/tasks/worker.py`) and in `backend/app/core/celery_config.py`.
- Cache queue usage: no tasks use `queue="cache"` and no `app.tasks.cache.*` module exists; `backend/app/tasks/README.md` references `tasks/cache.py` but the file is missing; cache warmers in `backend/app/tasks/beat_schedule.py` are commented out.

### Handler Registration
- Job-queue events: `EVENT_HANDLERS` in `backend/app/events/handlers.py` maps `event:*` to handler functions; `process_event` is invoked from `_background_jobs_worker_sync` in `backend/app/main.py`.
- Outbox delivery: `outbox.dispatch_pending` is scheduled in `backend/app/tasks/beat_schedule.py`; `outbox.deliver_event` performs delivery and updates outbox state.
- Referral events: `ReferralEvents.register()` exists but no registrations were found in the codebase.
- Messaging pub/sub: publish functions are used in routes and services; Broadcaster connect/disconnect is managed in `backend/app/main.py`.

### Recommendations
- Extend existing system: Yes, prefer the outbox + Celery pattern for cache invalidation where durability and retries are needed.
- Build new: No, unless you need cross-process pub/sub with fanout or a unified event bus across services.
- Pattern to follow: enqueue a domain outbox event in the same DB transaction, include an idempotency key, deliver via a dedicated Celery task with retries and logging, and keep handler code stateless.
