# Notification Outbox & Delivery

## Purpose
Guarantee exactly-once notification fan-out for booking and availability lifecycle events.
The flow combines an outbox table, Celery dispatchers, idempotency keys, and a deterministic provider shim so retries and concurrency remain safe.

## Event Flow
1. **Domain mutation** — `BookingService` (create/cancel/complete) and `AvailabilityService` / `WeekOperationService` (save week, copy week) enqueue an outbox row inside the same database transaction as the state change.
2. **Outbox row** — stored in `event_outbox` with payload JSON, attempt counters, and timestamps.
3. **Dispatcher** — periodic Celery beat job (`outbox.dispatch_pending`) loads pending rows and schedules `outbox.deliver_event`.
4. **Delivery task** — invokes the provider shim with exponential backoff, updates status on success or retries on transient failure.
5. **Idempotent provider** — writes to `notification_delivery` (unique on `idempotency_key`) and surfaces an environment-controlled failure hook for tests.

## Schema Summary
### `event_outbox`
- `event_type`, `aggregate_id`
- `idempotency_key` – unique constraint
- `payload` (JSONB/JSON)
- `status` (`PENDING` | `SENT` | `FAILED`)
- `attempt_count`, `next_attempt_at`, `last_error`
- `created_at`, `updated_at`

### `notification_delivery`
- `event_type`, `idempotency_key` (unique)
- `payload`
- `attempt_count` (initially 1)
- `last_sent_at`, `created_at`, `updated_at`

## Idempotency Keys
- Booking: `booking:{booking_id}:{event_type}:{version}`
- Availability: `avail:{instructor_id}:{week_start}:{event_type}:{version}`
- Versions use deterministic timestamps (created/cancelled/completed at) or computed week hashes; retrying the same logical event reuses the same key so duplicates are ignored.

## Retry & Backoff
`outbox.deliver_event` uses Celery retry semantics with capped exponential backoff:
1. 30s
2. 2m
3. 10m
4. 30m
5. 2h (terminal failure after 5 attempts → status `FAILED`)

The task persists the updated `attempt_count` / `next_attempt_at` before retrying to keep queue state durable across worker restarts.

## Provider Shim
- Located at `app/services/notification_provider.py`.
- Writes to `notification_delivery` to assert exactly-once behaviour.
- Set `NOTIFICATION_PROVIDER_RAISE_ON` (comma separated event types or idempotency keys) to simulate transient failures in tests or development.
- Swap-in production provider by implementing a real sender and injecting via the Celery task.

## Metrics
Surfaced through existing `/ops/metrics-lite` endpoint:
- `instainstru_notifications_outbox_attempt_total{event_type}` — per-delivery attempt counter.
- `instainstru_notifications_outbox_total{status="sent|failed", event_type}` — final outcomes.
- `instainstru_notifications_dispatch_seconds{event_type}` — histogram for provider latency.

### Alerts

- `OutboxBacklogGrowing` (warning): triggers when pending events increase for 10 minutes. Check the Grafana outbox backlog panel, confirm Celery workers are healthy, and ensure no downstream rate limits. Drain the queue manually via `outbox.dispatch_pending()` if backlog exceeds 2× normal volume.
- `NotificationDeliveryErrors` (warning): fires when `notifications_delivery_errors_total` increments over a 10-minute window. Inspect provider logs, retry counts, and the `notification_delivery` table; if a provider is degraded, fail over to the backup transport or flip `NOTIFICATION_PROVIDER_RAISE_ON` off in staging to reproduce.

## Running Locally
```
# Ensure Celery workers/beat running or execute tasks manually:
(cd backend && ./venv/bin/celery -A app.tasks.worker worker)
(cd backend && ./venv/bin/celery -A app.tasks.worker beat)
```
During development you can call `outbox.dispatch_pending()` and `outbox.deliver_event()` directly from a Python shell to inspect behaviour.

## Extending
1. Add new domain producer: enqueue inside the same transaction with a deterministic idempotency key.
2. Update documentation and tests (unit + integration) to validate retries, dedupe, and payload shape.
3. If switching to a third-party provider, implement an adapter that preserves `idempotency_key` passthrough (use request headers or provider-specific idempotency tokens).
