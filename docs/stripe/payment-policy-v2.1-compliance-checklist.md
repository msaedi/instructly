# Payment Policy v2.1 Compliance Checklist (Phase 0 - Pre-Audit)

Last updated: 2025-12-27
Environment: staging DB (instainstru_stg), SITE_MODE=local, Stripe test mode
Scope: Pre-audit only. No fixes. Captures current truth for entrypoints, concurrency, and idempotency/locking.

## A) Entrypoint Inventory (money movement / payment state)

| Type | Entrypoint | File / Function | Writes (booking/payment fields) | Stripe side-effects | Idempotency keys / caching | Locking / mutex |
| --- | --- | --- | --- | --- | --- | --- |
| API | POST /api/v1/payments/checkout | backend/app/routes/v1/payments.py:504 create_checkout<br>backend/app/services/stripe_service.py:444 create_booking_checkout | booking.status (CONFIRMED)<br>booking.payment_status (authorized when requires_capture)<br>booking.payment_intent_id<br>payment_intents.status | PaymentIntent.create + confirm<br>optional PaymentMethod save | Cache key `POST:/api/v1/payments/checkout:user:{user_id}:booking:{booking_id}` | Per-user lock `"{user_id}:checkout"` (TTL 30s) |
| API | POST /api/v1/bookings/{id}/cancel | backend/app/routes/v1/bookings.py:633 cancel_booking<br>backend/app/services/booking_service.py:1226 cancel_booking | booking.status (CANCELLED)<br>booking.cancelled_at/booking.cancelled_by_id<br>booking.payment_status (released/credit_issued/captured/etc)<br>payment_events + platform_credits | PaymentIntent.cancel (>=24h/instructor)<br>PaymentIntent.capture (12-24h/<12h/gaming)<br>Transfer reversal (12-24h/gaming) | Stripe keys: `cancel_{booking_id}`, `cancel_instructor_{booking_id}`, `capture_cancel_{booking_id}`, `capture_late_cancel_{booking_id}`, `capture_resched_{booking_id}`, `reverse_{booking_id}`, `reverse_resched_{booking_id}` | None |
| API | POST /api/v1/bookings/{id}/reschedule | backend/app/routes/v1/bookings.py:663 reschedule_booking<br>backend/app/services/booking_service.py:833 create_rescheduled_booking_with_existing_payment | New booking: rescheduled_from_booking_id, original_lesson_datetime<br>payment_intent_id/payment_method_id/payment_status (reuse)<br>Old booking: status CANCELLED (and payment_intent_id cleared when reuse) | If reuse: no Stripe call<br>If new: SetupIntent create + PaymentIntent auth (confirm_booking_payment) | No API idempotency; relies on Stripe idempotency in cancel/auth flows | None |
| API | POST /api/v1/bookings/{id}/confirm-payment (deprecated) | backend/app/routes/v1/bookings.py:937 confirm_booking_payment<br>backend/app/services/booking_service.py:952 confirm_booking_payment | booking.payment_method_id<br>booking.payment_status (payment_method_saved/scheduled/authorizing)<br>booking.status (CONFIRMED), booking.confirmed_at<br>payment_events auth_scheduled/auth_immediate | Optional save payment method<br>Immediate auth uses PaymentIntent create + confirm | None | None |
| API | PATCH /api/v1/bookings/{id}/payment-method | backend/app/routes/v1/bookings.py:974 update_booking_payment_method<br>backend/app/services/booking_service.py:952 confirm_booking_payment | booking.payment_method_id<br>booking.payment_status (payment_method_saved/scheduled/authorizing)<br>booking.status (CONFIRMED), booking.confirmed_at | Optional save payment method<br>Immediate auth uses PaymentIntent create + confirm | None | None |
| API | POST /api/v1/bookings/{id}/complete | backend/app/routes/v1/bookings.py:870 complete_booking<br>backend/app/services/booking_service.py:2053 complete_booking | booking.status (COMPLETED) + completed_at (via repository)<br>payment_events (milestone credits) | None | None | None |
| API | POST /api/v1/instructor/bookings/{id}/complete | backend/app/routes/v1/instructor_bookings.py:255 mark_lesson_complete<br>backend/app/services/booking_service.py:2150 instructor_mark_complete | booking.status (COMPLETED), completed_at, instructor_note<br>payment_events (instructor_marked_complete) | None | None | None |
| API | POST /api/v1/bookings/{id}/no-show | backend/app/routes/v1/bookings.py:903 mark_booking_no_show<br>backend/app/services/booking_service.py:2307 mark_no_show | booking.status (NO_SHOW via mark_no_show) | None | None | None |
| API | POST /api/v1/instructor/bookings/{id}/dispute | backend/app/routes/v1/instructor_bookings.py:315 dispute_completion<br>backend/app/services/booking_service.py:2248 instructor_dispute_completion | booking.payment_status -> disputed (if authorized)<br>payment_events completion_disputed | None | None | None |
| API | POST /api/v1/admin/bookings/{id}/cancel | backend/app/routes/v1/admin/bookings.py:131 admin_cancel_booking<br>backend/app/services/admin_booking_service.py:248 cancel_booking | booking.status (CANCELLED), cancelled_at, cancelled_by_id, cancellation_reason<br>booking.payment_status -> refunded (if refund) | Optional Stripe refund (reverse_transfer=True) | Stripe key `admin_cancel_{booking_id}_{timestamp}` | None |
| API | POST /api/v1/admin/refunds/{id}/refund | backend/app/routes/v1/admin/refunds.py:39 admin_refund_booking | booking.payment_status -> refunded (via apply_refund_updates)<br>refund_id/refund metadata | Stripe refund (reverse_transfer=True) | Stripe key `admin_refund_{booking_id}_{uuid}` | None |
| API | POST /api/v1/payments/webhooks/stripe | backend/app/routes/v1/payments.py:728 handle_stripe_webhook<br>backend/app/services/stripe_service.py:3061 handle_webhook_event | payment_intents.status (update_payment_status)<br>booking.status -> CONFIRMED when PI succeeds and booking PENDING<br>charge.refunded triggers credit hooks | None (webhook processing only) | None | None |
| Task | process_scheduled_authorizations | backend/app/tasks/payment_tasks.py:375 process_scheduled_authorizations | booking.payment_status (authorized/auth_failed/auth_abandoned)<br>booking.payment_intent_id<br>payment_events auth_scheduled/auth_succeeded/auth_failed | PaymentIntent create/confirm via create_or_retry_booking_payment_intent | Stripe create/confirm idempotency handled in service (no booking-level dedupe) | None (3-phase pattern only) |
| Task | retry_failed_authorizations | backend/app/tasks/payment_tasks.py:708 retry_failed_authorizations | booking.payment_status (authorized/auth_retry_failed/auth_abandoned)<br>booking.status -> CANCELLED when failure at T-6 | PaymentIntent create/confirm retry | Stripe idempotency handled in service | None |
| Task | capture_completed_lessons | backend/app/tasks/payment_tasks.py:1260 capture_completed_lessons | booking.payment_status (captured/auth_expired/capture_failed)<br>booking.status -> COMPLETED (auto_complete path)<br>booking.payment_intent_id (reauth) | PaymentIntent.capture<br>Possible reauth (create_new_authorization_and_capture) | Stripe key `capture_{reason}_{booking_id}_{payment_intent_id}` | None |
| Task | capture_late_cancellation | backend/app/tasks/payment_tasks.py:1673 capture_late_cancellation | booking.payment_status -> captured<br>payment_events late_cancellation_captured | PaymentIntent.capture | Stripe key `capture_late_cancel_{booking_id}_{payment_intent_id}` | None |
| Task | create_new_authorization_and_capture (internal) | backend/app/tasks/payment_tasks.py:1579 create_new_authorization_and_capture | booking.payment_intent_id (new)<br>booking.payment_status -> captured<br>payment_events reauth_and_capture | PaymentIntent create + capture | Stripe capture idempotency inside call | None |

Notes:
- Instructor cancel uses the same `/api/v1/bookings/{id}/cancel` entrypoint; there is no separate instructor-cancel route.
- No dedicated credit issuance task; credits are created in booking_service cancellation finalization and in refund hooks.

## B) Concurrency Race Repro Truth Tests (staging)

### Test 0.1 - Cancel vs Capture race
Setup:
- Booking: 01KDG95BAKXGN7JNNYPETR1FT7
- PaymentIntent: pi_3Sj03x0LanJcM8Lu0THaoRXZ
- Lesson end set to 2025-12-20 13:00:00-05:00 (eligible for capture_completed_lessons auto-complete)
Action:
- Ran capture_completed_lessons and POST /api/v1/bookings/{id}/cancel concurrently.

Results:
| Timestamp (local) | booking_id | payment_intent_id | Final booking.payment_status | Stripe errors/responses |
| --- | --- | --- | --- | --- |
| 2025-12-27 11:10:32-05 | 01KDG95BAKXGN7JNNYPETR1FT7 | pi_3Sj03x0LanJcM8Lu0THaoRXZ | captured | capture_failed: "already been captured" (capture_reason=auto_completed) |

Evidence:
```
payment_events:
- auto_completed @ 2025-12-27 11:10:32.450236-05
  {"reason":"No instructor confirmation within 24hr","lesson_end":"2025-12-20T13:00:00-05:00","auto_completed_at":"2025-12-27T16:10:32.375725+00:00"}
- captured_last_minute_cancel @ 2025-12-27 11:10:32.675672-05
  {"payment_intent_id":"pi_3Sj03x0LanJcM8Lu0THaoRXZ","amount":13440}
- capture_failed @ 2025-12-27 11:10:33.097427-05
  {"payment_intent_id":"pi_3Sj03x0LanJcM8Lu0THaoRXZ","error":"Failed to capture payment: Request req_6D8JJSCdJkwmv3: This PaymentIntent could not be captured because it has already been captured.","capture_reason":"auto_completed"}
backend_server.log:
- 2025-12-27 11:10:32,828 POST /api/v1/bookings/01KDG95BAKXGN7JNNYPETR1FT7/cancel 200
```

### Test 0.2 - Double cancel credit race
Setup:
- Booking: 01KDG8ZRB5EA3VG3X6SJ432CP1 (12-24h window)
- PaymentIntent: pi_3Sj00z0LanJcM8Lu0QqGlYek
Action:
- Sent two concurrent POST /api/v1/bookings/{id}/cancel requests.

Results:
| Timestamp (local) | booking_id | payment_intent_id | Final booking.payment_status | Stripe errors/responses |
| --- | --- | --- | --- | --- |
| 2025-12-27 11:11:23-05 | 01KDG8ZRB5EA3VG3X6SJ432CP1 | pi_3Sj00z0LanJcM8Lu0QqGlYek | credit_issued | Stripe error: idempotency_key_in_use for capture_cancel_{booking_id} |

Evidence:
```
payment_events:
- capture_failed_late_cancel @ 2025-12-27 11:11:23.885199-05
  {"payment_intent_id":"pi_3Sj00z0LanJcM8Lu0QqGlYek","error":"Failed to capture payment: Request req_IrQ8ksG9hKxWtR: There is currently another in-progress request using this Idempotent Key (that probably means you submitted twice, and the other request is still going through): capture_cancel_01KDG8ZRB5EA3VG3X6SJ432CP1. Please try again later."}
- credit_created_late_cancel @ 2025-12-27 11:11:24.691249-05
  {"amount":12000,"lesson_price_cents":12000,"used_credit_cents":0,"total_charged_cents":13440}
platform_credits:
- 1 row for source_booking_id=01KDG8ZRB5EA3VG3X6SJ432CP1 (amount_cents=12000)
backend_server.log:
- 2025-12-27 11:11:23,875 Stripe error idempotency_key_in_use for capture_cancel_01KDG8ZRB5EA3VG3X6SJ432CP1
```

### Test 0.3 - Reschedule vs scheduled auth job race
Setup:
- Original booking: 01KDG915YMH176YJRQ6FW12S4R (payment_status scheduled)
- New booking: 01KDG9ADP2WPKN2240MDSWPFFK created by reschedule
Action:
- Ran process_scheduled_authorizations while rescheduling the original booking.

Results:
| Timestamp (local) | booking_id | payment_intent_id | Final booking.payment_status | Stripe errors/responses |
| --- | --- | --- | --- | --- |
| 2025-12-27 11:12:31-05 | 01KDG9ADP2WPKN2240MDSWPFFK | pi_3Sj06U0LanJcM8Lu1wQBzcWE | authorized | None observed |
| 2025-12-27 11:12:32-05 | 01KDG915YMH176YJRQ6FW12S4R | pi_3Sj06V0LanJcM8Lu0IRFpvvO | authorized (booking status CANCELLED) | None observed |

Evidence:
```
payment_events:
- auth_scheduled (original) @ 2025-12-27 11:07:35.375442-05
  {"payment_method_id":"pm_card_visa","scheduled_for":"2026-01-22T09:00:00-05:00","hours_until_lesson":645.8735068330556}
- auth_immediate (new) @ 2025-12-27 11:12:30.470621-05
  {"payment_method_id":"pm_card_visa","hours_until_lesson":602.791535946389,"hours_from_original":23.923492470833335,"scheduled_for":"immediate","reason":"gaming_reschedule"}
- auth_succeeded (new) @ 2025-12-27 11:12:31.597872-05
  {"payment_intent_id":"pi_3Sj06U0LanJcM8Lu1wQBzcWE","amount_cents":13440,"application_fee_cents":2880,"authorized_at":"2025-12-27T16:12:31.597791+00:00","hours_before_lesson":602.8,"credits_applied_cents":0}
- auth_succeeded (original) @ 2025-12-27 11:12:32.352757-05
  {"payment_intent_id":"pi_3Sj06V0LanJcM8Lu0IRFpvvO","amount_cents":13440,"application_fee_cents":2880,"authorized_at":"2025-12-27T16:12:32.352703+00:00","hours_before_lesson":23.9,"credits_applied_cents":0}
backend_server.log:
- 2025-12-27 11:12:31,781 Booking 01KDG915YMH176YJRQ6FW12S4R cancelled (reschedule)
- 2025-12-27 11:12:31,599 Successfully authorized payment for booking 01KDG9ADP2WPKN2240MDSWPFFK
```

## C) Current Locking / Idempotency Summary

- Locks present:
  - `/api/v1/payments/checkout` uses a per-user cache lock (`{user_id}:checkout`) + cached response idempotency key.
- Stripe idempotency keys:
  - Cancellation captures/cancels/reversals use booking-scoped keys (see cancellation row above).
  - capture_completed_lessons uses `capture_{reason}_{booking_id}_{payment_intent_id}`.
  - capture_late_cancellation uses `capture_late_cancel_{booking_id}_{payment_intent_id}`.
  - Admin refund/cancel generate unique idempotency keys per request.
- Booking-level mutex:
  - None found. No `SELECT ... FOR UPDATE` usage in booking/payment repositories for cancel/reschedule/capture paths.
- Observed race outcomes (staging):
  - Cancel vs capture job can double-attempt capture; Stripe returns "already captured" and booking remains CANCELLED/captured.
  - Double cancel can produce one Stripe capture and one idempotency error; credit issuance is guarded by existing credit check.
  - Reschedule vs scheduled auth can authorize a cancelled booking (stale auth) and leave PI attached to CANCELLED booking.

## D) Phase 0 Changes Implemented

- Booking-level Redis mutex helper: `backend/app/core/booking_lock.py` (`booking:{booking_id}:mutex`, TTL 90s, async + sync context managers).
- API endpoints wrapped with booking lock (429 on contention): cancel, reschedule, no-show, instructor dispute, admin cancel, admin refund.
- Celery tasks wrapped per booking (skip on contention): scheduled auth, auth retries, capture job, late-cancel capture, reauth+capture.
- Fresh-read guardrails inside locked execution: auth tasks skip CANCELLED/not eligible; capture job skips CANCELLED/disputed/not authorized; cancel flow is idempotent for already-cancelled bookings and avoids re-capture when already captured.

## E) Phase 0 Post-Verification Results (staging)

### Test 0.1 - Cancel vs Capture race (POST)
Results:
| Timestamp (local) | booking_id | payment_intent_id | Final booking.payment_status | Stripe errors/responses |
| --- | --- | --- | --- | --- |
| 2025-12-27 12:11:49-05 | 01KDGCP1R4N6AQKXNWV4PFY2HB | pi_3Sj11X0LanJcM8Lu173GNOzO | captured | capture job skipped (lock); no capture_failed event |

Evidence:
```
capture_completed_lessons output:
{'captured': 0, 'failed': 0, 'auto_completed': 0, 'expired_handled': 0, 'processed_at': '2025-12-27T17:11:49.317447+00:00'}
payment_events:
- captured_last_minute_cancel @ 2025-12-27 12:11:49.553994-05
  {"payment_intent_id":"pi_3Sj11X0LanJcM8Lu173GNOzO","amount":13440}
```

### Test 0.2 - Double cancel credit race (POST)
Results:
| Timestamp (local) | booking_id | payment_intent_id | Final booking.payment_status | Stripe errors/responses |
| --- | --- | --- | --- | --- |
| 2025-12-27 12:13:25-05 | 01KDGCRS34TR39A9KZ4BJM00F0 | pi_3Sj12x0LanJcM8Lu0AXZwZEs | credit_issued | 1x 429 (Operation in progress); no Stripe idempotency_key_in_use |

Evidence:
```
cancel response A:
{"status":429,"detail":"Operation in progress"}
payment_events:
- credit_created_late_cancel @ 2025-12-27 12:13:25.710372-05
  {"amount":12000,"lesson_price_cents":12000,"used_credit_cents":0,"total_charged_cents":13440}
```

### Test 0.3 - Reschedule vs scheduled auth job race (POST)
Results:
| Timestamp (local) | booking_id | payment_intent_id | Final booking.payment_status | Stripe errors/responses |
| --- | --- | --- | --- | --- |
| 2025-12-27 12:14:44-05 | 01KDGCV75YSEBZ5KN7AVZB68QT (original) | none | capture_failed (CANCELLED) | auth job skipped (lock); no auth on cancelled booking |
| 2025-12-27 12:14:43-05 | 01KDGCWAZ1ZCH4AXFRJNST3VF5 (new) | pi_3Sj14h0LanJcM8Lu1X0t6Kqn | authorized | reschedule succeeded |

Evidence:
```
process_scheduled_authorizations output:
{'success': 0, 'failed': 0, 'failures': [], 'processed_at': '2025-12-27T17:14:44.251681+00:00'}
booking state (original):
status=CANCELLED payment_status=capture_failed payment_intent_id=NULL
booking state (new):
status=CONFIRMED payment_status=authorized payment_intent_id=pi_3Sj14h0LanJcM8Lu1X0t6Kqn
```

## F) Gap Matrix (Phase 0)

| Scenario | Status | Evidence | Severity | Proposed fix | Notes |
| --- | --- | --- | --- | --- | --- |
| Concurrency safety (per-booking mutual exclusion) | PASS ✅ | Tests 0.1–0.3 (POST) with booking_ids + PIs above | P0 | Implemented | commit: pending (local changes; user to commit) |
