# Payment Policy v2.1 Compliance Checklist (Phase 0–6)

Last updated: 2025-12-28
Environment: staging DB (instainstru_stg), SITE_MODE=local, Stripe test mode
Scope: Baseline pre-audit (Phase 0), Phase 0 mutex changes, Phase 1 critical money fixes (Tasks 1.1–1.4), Phase 2 LOCK anti-gaming mechanism, Phase 3 credit reservation model, Phase 4 no-show handling, Phase 5 authorization timing, and Phase 6 state machine alignment + failure handling.

Note: As of Phase 6, booking.payment_status is canonical (scheduled, authorized, payment_method_required, manual_review, locked, settled). Legacy labels (captured/refunded/released/credit_issued/auth_failed/capture_failed/disputed) are now expressed via settlement_outcome + failure fields.

## A) Entrypoint Inventory (money movement / payment state, current state)

| Type | Entrypoint | File / Function | Writes (booking/payment fields) | Stripe side-effects | Idempotency keys / caching | Locking / mutex |
| --- | --- | --- | --- | --- | --- | --- |
| API | POST /api/v1/payments/checkout | backend/app/routes/v1/payments.py:504 create_checkout<br>backend/app/services/stripe_service.py:444 create_booking_checkout | booking.status (CONFIRMED)<br>booking.payment_status (authorized or scheduled)<br>booking.auth_scheduled_for/auth_attempted_at/auth_failure_count/auth_last_error<br>booking.payment_intent_id<br>payment_intents.status | PaymentIntent.create + confirm (immediate)<br>PaymentIntent.create only (scheduled ≥24h)<br>optional PaymentMethod save | Cache key `POST:/api/v1/payments/checkout:user:{user_id}:booking:{booking_id}` | Per-user lock `"{user_id}:checkout"` (TTL 30s) |
| API | POST /api/v1/bookings/{id}/cancel | backend/app/routes/v1/bookings.py:633 cancel_booking<br>backend/app/services/booking_service.py:1226 cancel_booking | booking.status (CANCELLED)<br>booking.cancelled_at/booking.cancelled_by_id<br>booking.payment_status -> settled (settlement_outcome + amount fields)<br>payment_events + platform_credits<br>locked parent booking: lock_resolution/lock_resolved_at/settlement_outcome (if has_locked_funds) | PaymentIntent.cancel (>=24h/instructor)<br>PaymentIntent.capture (12-24h/<12h/gaming)<br>Transfer reversal (12-24h/gaming)<br>LOCK resolution (if has_locked_funds): manual transfer/credit/refund | Stripe keys: `cancel_{booking_id}`, `cancel_instructor_{booking_id}`, `capture_cancel_{booking_id}`, `capture_late_cancel_{booking_id}`, `capture_resched_{booking_id}`, `reverse_{booking_id}`, `reverse_resched_{booking_id}` | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/bookings/{id}/reschedule | backend/app/routes/v1/bookings.py:663 reschedule_booking<br>backend/app/services/booking_service.py:833 create_rescheduled_booking_with_existing_payment | New booking: rescheduled_from_booking_id, rescheduled_to_booking_id, original_lesson_datetime, has_locked_funds, payment_status (locked when LOCK)<br>Old booking: status CANCELLED; payment_status locked + locked_at/locked_amount_cents (LOCK); payment_intent_id cleared when reuse | If reuse: no Stripe call<br>If LOCK: PaymentIntent.capture + Transfer.create_reversal<br>If new: SetupIntent create + PaymentIntent auth (confirm_booking_payment) | No API idempotency; relies on Stripe idempotency in cancel/auth flows | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/bookings/{id}/confirm-payment (deprecated) | backend/app/routes/v1/bookings.py:1044 confirm_booking_payment<br>backend/app/services/booking_service.py:952 confirm_booking_payment | booking.payment_method_id<br>booking.payment_status (scheduled -> authorized/payment_method_required)<br>booking.status (CONFIRMED), booking.confirmed_at<br>payment_events auth_scheduled/auth_immediate | Optional save payment method<br>Immediate auth uses PaymentIntent create + confirm | None | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | PATCH /api/v1/bookings/{id}/payment-method | backend/app/routes/v1/bookings.py:1082 update_booking_payment_method<br>backend/app/services/booking_service.py:952 confirm_booking_payment | booking.payment_method_id<br>booking.payment_status (scheduled -> authorized/payment_method_required)<br>booking.status (CONFIRMED), booking.confirmed_at | Optional save payment method<br>Immediate auth uses PaymentIntent create + confirm | None | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/bookings/{id}/retry-payment | backend/app/routes/v1/bookings.py:1112 retry_payment_authorization<br>backend/app/services/booking_service.py:1359 retry_authorization | booking.payment_status (authorized/payment_method_required)<br>booking.auth_attempted_at/auth_failure_count/auth_last_error<br>booking.payment_intent_id (if new) | PaymentIntent.confirm (retry existing)<br>PaymentIntent.create + confirm (if no PI) | Stripe idempotency in service | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/bookings/{id}/complete | backend/app/routes/v1/bookings.py:870 complete_booking<br>backend/app/services/booking_service.py:2053 complete_booking | booking.status (COMPLETED) + completed_at (via repository)<br>payment_events (milestone credits) | None | None | None |
| API | POST /api/v1/instructor/bookings/{id}/complete | backend/app/routes/v1/instructor_bookings.py:255 mark_lesson_complete<br>backend/app/services/booking_service.py:2150 instructor_mark_complete | booking.status (COMPLETED), completed_at, instructor_note<br>payment_events (instructor_marked_complete) | None | None | None |
| API | POST /api/v1/bookings/{id}/no-show | backend/app/routes/v1/bookings.py:956 report_no_show<br>backend/app/services/booking_service.py:3259 report_no_show | booking.payment_status -> manual_review<br>booking.no_show_reported_* | None | None | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/bookings/{id}/no-show/dispute | backend/app/routes/v1/bookings.py:1002 dispute_no_show<br>backend/app/services/booking_service.py:3361 dispute_no_show | booking.no_show_disputed* + dispute metadata | None | None | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/instructor/bookings/{id}/dispute | backend/app/routes/v1/instructor_bookings.py:315 dispute_completion<br>backend/app/services/booking_service.py:2248 instructor_dispute_completion | booking.payment_status -> manual_review (if authorized)<br>payment_events completion_disputed | None | None | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/admin/bookings/{id}/cancel | backend/app/routes/v1/admin/bookings.py:131 admin_cancel_booking<br>backend/app/services/admin_booking_service.py:248 cancel_booking | booking.status (CANCELLED), cancelled_at, cancelled_by_id, cancellation_reason<br>booking.payment_status -> settled (settlement_outcome admin_refund/instructor_cancel_full_refund) | Optional Stripe refund (reverse_transfer=True) | Stripe key `admin_cancel_{booking_id}_{timestamp}` | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/admin/bookings/{id}/no-show/resolve | backend/app/routes/v1/admin/bookings.py:232 resolve_no_show<br>backend/app/services/booking_service.py:3445 resolve_no_show | booking.no_show_resolution + no_show_resolved_at<br>booking.status/payment_status/settlement_outcome | Stripe refund/capture (if applicable) | Stripe idempotency in service | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/admin/refunds/{id}/refund | backend/app/routes/v1/admin/refunds.py:39 admin_refund_booking | booking.payment_status -> settled (settlement_outcome admin_refund)<br>refund_id/refund metadata | Stripe refund (reverse_transfer=True) | Stripe key `admin_refund_{booking_id}_{uuid}` | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| API | POST /api/v1/payments/webhooks/stripe | backend/app/routes/v1/payments.py:728 handle_stripe_webhook<br>backend/app/services/stripe_service.py:3061 handle_webhook_event | payment_intents.status (update_payment_status)<br>booking.status -> CONFIRMED when PI succeeds and booking PENDING<br>charge.refunded triggers credit hooks<br>charge.dispute.* sets manual_review/settled + dispute fields + credit freeze/unfreeze | None (webhook processing only) | None | Dispute handlers use booking_lock_sync; other webhook handlers are idempotent + state-checked (no booking mutex) |
| Task | process_scheduled_authorizations | backend/app/tasks/payment_tasks.py:375 process_scheduled_authorizations | booking.payment_status (authorized/payment_method_required/settled)<br>booking.auth_attempted_at/auth_failure_count/auth_last_error<br>booking.payment_intent_id<br>payment_events auth_scheduled/auth_succeeded/auth_failed | PaymentIntent create/confirm via create_or_retry_booking_payment_intent | Stripe create/confirm idempotency handled in service (no booking-level dedupe) | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| Task | retry_failed_authorizations | backend/app/tasks/payment_tasks.py:708 retry_failed_authorizations | booking.payment_status (authorized/payment_method_required/settled)<br>booking.auth_attempted_at/auth_failure_count/auth_last_error<br>booking.status -> CANCELLED when failure at T-12 | PaymentIntent create/confirm retry | Stripe idempotency handled in service | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| Task | check_immediate_auth_timeout | backend/app/tasks/payment_tasks.py:1034 check_immediate_auth_timeout | booking.status -> CANCELLED (if still payment_method_required after 30m)<br>booking.payment_status -> settled (settlement_outcome student_cancel_gt24_no_charge) | PaymentIntent cancel (via _cancel_booking_payment_failed) | Stripe idempotency handled in service | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| Task | capture_completed_lessons | backend/app/tasks/payment_tasks.py:1260 capture_completed_lessons | booking.payment_status (settled/payment_method_required)<br>booking.status -> COMPLETED (auto_complete path)<br>booking.payment_intent_id (reauth)<br>locked parent booking: settlement_outcome/lock_resolution (if has_locked_funds) | PaymentIntent.capture<br>LOCK resolution (has_locked_funds): manual transfer on locked parent (new_lesson_completed)<br>Possible reauth (create_new_authorization_and_capture) | Stripe key `capture_{reason}_{booking_id}_{payment_intent_id}` | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| Task | retry_failed_captures | backend/app/tasks/payment_tasks.py:1083 retry_failed_captures | booking.payment_status (payment_method_required/manual_review)<br>booking.capture_failed_at/capture_retry_count<br>student.account_locked (escalation) | PaymentIntent.capture retries<br>Manual Transfer payout on escalation | Stripe key `capture_retry_failed_capture_{booking_id}_{payment_intent_id}` | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| Task | capture_late_cancellation | backend/app/tasks/payment_tasks.py:1673 capture_late_cancellation | booking.payment_status -> settled<br>payment_events late_cancellation_captured | PaymentIntent.capture | Stripe key `capture_late_cancel_{booking_id}_{payment_intent_id}` | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| Task | resolve_undisputed_no_shows | backend/app/tasks/payment_tasks.py:2105 resolve_undisputed_no_shows | booking.no_show_resolution + no_show_resolved_at<br>booking.status/payment_status/settlement_outcome | Stripe refund/capture (via booking_service) | Stripe idempotency in service | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |
| Task | create_new_authorization_and_capture (internal) | backend/app/tasks/payment_tasks.py:1579 create_new_authorization_and_capture | booking.payment_intent_id (new)<br>booking.payment_status -> settled<br>payment_events reauth_and_capture | PaymentIntent create + capture | Stripe capture idempotency inside call | Booking mutex `booking:{booking_id}:mutex` (TTL 90s) |

Notes:
- Instructor cancel uses the same `/api/v1/bookings/{id}/cancel` entrypoint; there is no separate instructor-cancel route.
- No dedicated credit issuance task; credits are created in booking_service cancellation finalization and in refund hooks.

## B) Concurrency Race Repro Truth Tests (staging, pre-Phase 0 baseline)

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
| 2025-12-27 11:10:32-05 | 01KDG95BAKXGN7JNNYPETR1FT7 | pi_3Sj03x0LanJcM8Lu0THaoRXZ | settled | capture_failed: "already been captured" (capture_reason=auto_completed) |

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
| 2025-12-27 11:11:23-05 | 01KDG8ZRB5EA3VG3X6SJ432CP1 | pi_3Sj00z0LanJcM8Lu0QqGlYek | settled | Stripe error: idempotency_key_in_use for capture_cancel_{booking_id} |

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
  - Redis booking mutex implemented for confirm-payment/payment-method/cancel/reschedule/no-show/dispute/admin cancel/refund/retry-payment and payment tasks (per booking, TTL 90s).
- Observed race outcomes (staging baseline, pre-Phase 0):
- Cancel vs capture job can double-attempt capture; Stripe returns "already captured" and booking remains CANCELLED/settled.
  - Double cancel can produce one Stripe capture and one idempotency error; credit issuance is guarded by existing credit check.
  - Reschedule vs scheduled auth can authorize a cancelled booking (stale auth) and leave PI attached to CANCELLED booking.

## D) Phase 0 Changes Implemented

- Booking-level Redis mutex helper: `backend/app/core/booking_lock.py` (`booking:{booking_id}:mutex`, TTL 90s, async + sync context managers).
- API endpoints wrapped with booking lock (429 on contention): cancel, reschedule, no-show, instructor dispute, admin cancel, admin refund.
- Celery tasks wrapped per booking (skip on contention): scheduled auth, auth retries, capture job, late-cancel capture, reauth+capture.
- Fresh-read guardrails inside locked execution: auth tasks skip CANCELLED/not eligible; capture job skips CANCELLED/manual_review/not authorized; cancel flow is idempotent for already-cancelled bookings and avoids re-capture when already captured.
- Automated regression tests for Phase 0 mutex/guardrails: `backend/tests/unit/core/test_booking_lock.py`, `backend/tests/integration/test_booking_mutex_endpoints.py`, `backend/tests/integration/test_booking_mutex_tasks.py`, `backend/tests/integration/test_fresh_read_guardrails.py`, `backend/tests/integration/test_booking_race_conditions.py` (maps to truth tests 0.1-0.3).

## E) Phase 0 Post-Verification Results (staging)

### Test 0.1 - Cancel vs Capture race (POST)
Results:
| Timestamp (local) | booking_id | payment_intent_id | Final booking.payment_status | Stripe errors/responses |
| --- | --- | --- | --- | --- |
| 2025-12-27 12:11:49-05 | 01KDGCP1R4N6AQKXNWV4PFY2HB | pi_3Sj11X0LanJcM8Lu173GNOzO | settled | capture job skipped (lock); no capture_failed event |

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
| 2025-12-27 12:13:25-05 | 01KDGCRS34TR39A9KZ4BJM00F0 | pi_3Sj12x0LanJcM8Lu0AXZwZEs | settled | 1x 429 (Operation in progress); no Stripe idempotency_key_in_use |

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
| 2025-12-27 12:14:44-05 | 01KDGCV75YSEBZ5KN7AVZB68QT (original) | none | payment_method_required (CANCELLED) | auth job skipped (lock); no auth on cancelled booking |
| 2025-12-27 12:14:43-05 | 01KDGCWAZ1ZCH4AXFRJNST3VF5 (new) | pi_3Sj14h0LanJcM8Lu1X0t6Kqn | authorized | reschedule succeeded |

Evidence:
```
process_scheduled_authorizations output:
{'success': 0, 'failed': 0, 'failures': [], 'processed_at': '2025-12-27T17:14:44.251681+00:00'}
booking state (original):
status=CANCELLED payment_status=payment_method_required payment_intent_id=NULL
booking state (new):
status=CONFIRMED payment_status=authorized payment_intent_id=pi_3Sj14h0LanJcM8Lu1X0t6Kqn
```

Note: Evidence tables above show canonical payment_status values; raw logs may still include legacy labels.

Canonical payment_status mapping summary:
| Scenario | payment_status | settlement_outcome |
| --- | --- | --- |
| Lesson complete | settled | lesson_completed_full_payout |
| Cancel >=24h | settled | student_cancel_gt24_no_charge |
| Cancel 12-24h | settled | student_cancel_12_24_full_credit |
| Cancel <12h | settled | student_cancel_lt12_split_50_50 |
| Auth failure | payment_method_required | - |
| Dispute opened | manual_review | - |
| Capture failure (retrying) | payment_method_required | - |
| Capture failure (escalated) | manual_review | capture_failure_instructor_paid |

## F) Gap Matrix (Phase 0–6)

| Scenario | Status | Evidence | Severity | Proposed fix | Notes |
| --- | --- | --- | --- | --- | --- |
| Concurrency safety (per-booking mutual exclusion) | PASS ✅ | Tests 0.1–0.3 (POST) with booking_ids + PIs above | P0 | Implemented | commit: pending (local changes; user to commit) |
| Student cancel <12h 50/50 split (credit + payout) | PASS ✅ | `backend/tests/integration/test_cancel_lt12_split.py` | P0 | Implemented | Capture → reverse transfer → 50% payout + 50% credit |
| Instructor cancel full refund (incl. SF) | PASS ✅ | `backend/tests/integration/test_instructor_cancel_refund.py` | P0 | Implemented | Refund uses `reverse_transfer` + `refund_application_fee` |
| Auth retry hard deadline at T-12h | PASS ✅ | `backend/tests/unit/tasks/test_auth_retry_deadline.py` | P0 | Implemented | Replaces prior T-6h cutoff |
| Settlement tracking fields on booking | PASS ✅ | `backend/app/models/booking.py`, `backend/app/services/booking_service.py`, `backend/app/tasks/payment_tasks.py` | P1 | Implemented | Tracks settlement_outcome + amount fields |
| LOCK anti-gaming (12–24h reschedule) | PASS ✅ | `backend/tests/integration/test_lock_mechanism.py` | P0 | Implemented | Capture + reverse transfer, set locked status, resolve on new lesson outcome |
| Credit reservation model (reserve/release/forfeit/issue) | PASS ✅ | `backend/tests/integration/test_credit_reservation.py` | P0 | Implemented | Credits reserved at checkout; released or forfeited on terminal outcomes |
| No-show handling (report/dispute/resolve) | PASS ✅ | `backend/tests/integration/test_no_show_handling.py` | P0 | Implemented | Manual review freeze + 24h dispute window + admin/auto resolution |
| Authorization timing at checkout (>=24h scheduled, <24h immediate) | PASS ✅ | `backend/tests/services/test_stripe_service.py` (`test_process_booking_payment_scheduled_auth`), `backend/tests/services/test_booking_payment_boundaries.py` | P0 | Implemented | Checkout now schedules auth for ≥24h; immediate auth <24h with 30m retry window |
| Canonical payment_status + settlement_outcome mapping | PASS ✅ | `backend/tests/integration/test_payment_status_canonical.py` | P0 | Implemented | settlement_outcome carries detail; legacy statuses removed |
| Failure handling (capture retry + dispute handling + account lock) | PASS ✅ | `backend/tests/integration/test_capture_failure_escalation.py`, `backend/tests/services/test_stripe_webhooks.py`, `backend/tests/integration/services/test_booking_service_account_status.py` | P0 | Implemented | Retry/escalation, dispute handling, credit freeze, account lock |

## G) Phase 1 Changes Implemented

- Task 1.1 (<12h cancel 50/50 split): `backend/app/services/booking_service.py` now captures, reverses destination transfer, issues 50% credit, and pays 50% net payout via manual transfer. Settlement fields set on booking.
- Task 1.2 (Instructor cancel refund): `backend/app/services/booking_service.py` refunds captured payments with `reverse_transfer=True` + `refund_application_fee=True`; releases auth if not captured; releases reserved credits; sets settlement_outcome.
- Task 1.3 (T-12h deadline): `backend/app/tasks/payment_tasks.py` retry job now auto-cancels at 12h remaining (not 6h).
- Task 1.4 (Settlement tracking fields): `backend/app/models/booking.py` adds settlement fields; `backend/app/schemas/booking.py` exposes them; `backend/app/services/booking_service.py` and `backend/app/tasks/payment_tasks.py` set values on cancel/complete flows.

## H) Phase 1 Verification (Automated)

- New tests: `backend/tests/integration/test_cancel_lt12_split.py`, `backend/tests/integration/test_instructor_cancel_refund.py`, `backend/tests/unit/tasks/test_auth_retry_deadline.py`
- Updated assertions: `backend/tests/services/test_booking_cancellation_policy.py`, `backend/tests/tasks/test_payment_tasks.py`
- Evidence type: automated tests only (staging verification pending)

## I) Phase 2 Changes Implemented

- Task 2.1–2.2: LOCK trigger + activation on student reschedule in 12–24h window (capture + reverse transfer, set `payment_status=locked`, `locked_at`, `locked_amount_cents`).
- Task 2.3 + 2.7: Booking model + migration add lock tracking + reschedule linking fields (`locked_at`, `lock_resolution`, `rescheduled_to_booking_id`, `has_locked_funds`, etc.).
- Task 2.4: Reschedule flow now branches to LOCK activation + rescheduled booking with locked funds (no PI reuse).
- Task 2.5–2.6: LOCK resolution implemented for completion/cancellation/instructor cancel; wired into cancel flow and capture job.
- Task 2.8: Frontend payment status types include `locked` for UI consistency.
- New automated tests: `backend/tests/integration/test_lock_mechanism.py`.

## J) Phase 2 Verification (Automated)

- Test file: `backend/tests/integration/test_lock_mechanism.py`
- Result: `pytest backend/tests/integration/test_lock_mechanism.py -q` (14 passed)

## K) Phase 3 Changes Implemented

- Credit reservation lifecycle: new `CreditService` + `CreditRepository` (reserve/release/forfeit/issue/expire).
- Platform credits now track `status`, reservation fields, and source_type/source_booking_id; booking tracks `credits_reserved_cents`.
- Checkout now reserves credits (FIFO) and persists reserved amount; credits never cover student fee.
- Cancellation/capture/LOCK flows release or forfeit reserved credits and issue new credits per policy.

## L) Phase 3 Verification (Automated)

- Test file: `backend/tests/integration/test_credit_reservation.py`
- Result: `pytest backend/tests/integration/test_credit_reservation.py -q` (12 passed)

## M) Phase 4 Changes Implemented

- No-show tracking fields on bookings: report/dispute/resolution timestamps and metadata.
- Reporting + dispute endpoints: `/api/v1/bookings/{id}/no-show` and `/api/v1/bookings/{id}/no-show/dispute`.
- Resolution endpoint + auto-resolution task: `/api/v1/admin/bookings/{id}/no-show/resolve`, `resolve_undisputed_no_shows` (hourly).
- Settlement rules wired: instructor no-show refunds (incl. SF) + credit release; student no-show captures + credit forfeit.

## N) Phase 4 Verification (Automated)

- Test file: `backend/tests/integration/test_no_show_handling.py`
- Result: `pytest backend/tests/integration/test_no_show_handling.py -q` (16 passed)

## O) Phase 5 Changes Implemented

- Authorization timing fields added to booking (`auth_scheduled_for`, `auth_attempted_at`, `auth_failure_count`, `auth_last_error`).
- Checkout now schedules auth for bookings ≥24h out (PaymentIntent created, not confirmed); immediate auth for <24h with 30-minute retry window.
- Scheduled auth job honors `auth_scheduled_for` (fallback to 23.5–24.5h window for legacy bookings).
- Retry job uses dynamic intervals (1h/4h/8h) with T-13h warning and T-12h auto-cancel.
- Manual retry endpoint added: `POST /api/v1/bookings/{id}/retry-payment`.
- New `check_immediate_auth_timeout` task auto-cancels immediate auth failures after 30 minutes.
- Beat schedule updated (scheduled auth every 5 minutes; retry every 15 minutes).

## P) Phase 5 Verification (Automated)

- Tests: `backend/tests/services/test_stripe_service.py` (scheduled checkout auth), `backend/tests/tasks/test_payment_tasks.py` (auth_scheduled_for + immediate auth timeout), `backend/tests/routes/test_bookings.py` (retry-payment endpoint)
- Result: targeted pytest runs passed (see Phase 5 implementation report)

## Q) Phase 6 Changes Implemented

- Canonical payment_status (6 values) enforced via model + check constraint; legacy statuses replaced by settlement_outcome + failure fields.
- Capture failure handling: added `capture_failed_at`/`capture_retry_count`, `retry_failed_captures` task, escalation to manual_review after 72h, manual payout to instructor, student account lock.
- Dispute handling: booking dispute fields + Stripe charge dispute handlers; credits frozen/unfrozen; transfer reversal attempts recorded.
- Account locking fields on user; booking creation blocked when account_locked is true.
- Credit status expanded to include frozen with audit fields.

## R) Phase 6 Verification (Automated)

- Tests: `backend/tests/integration/test_payment_status_canonical.py`, `backend/tests/integration/test_capture_failure_escalation.py`, `backend/tests/tasks/test_payment_tasks.py` (retry_failed_captures), `backend/tests/services/test_stripe_webhooks.py` (charge.dispute.*)
- Result: PASS (migrated DB; all Phase 6 tests green)

## S) Phase 6 Gap Matrix (Verification)

| Gap | Severity | Status | Evidence |
| --- | --- | --- | --- |
| Canonical payment_status (6 values only) | P0 | ✅ PASS | `backend/tests/integration/test_payment_status_canonical.py` |
| settlement_outcome carries detail | P0 | ✅ PASS | Cancel/capture/lock flows set settlement_outcome + amount fields |
| Capture failure retry (4h, 72h escalation) | P0 | ✅ PASS | `backend/tests/integration/test_capture_failure_escalation.py` |
| Account locking on escalation | P1 | ✅ PASS | `backend/tests/integration/services/test_booking_service_account_status.py` |
| Dispute webhook handling | P0 | ✅ PASS | `backend/tests/services/test_stripe_webhooks.py` |
| Credit freezing on dispute | P1 | ✅ PASS | `backend/tests/services/test_stripe_webhooks.py` |
| Transfer reversal attempt | P1 | ✅ PASS | `backend/tests/services/test_stripe_webhooks.py` |

## T) Endpoint Mutex Coverage

Note: There is no `/api/v1/payments/confirm-payment` route in this codebase; confirm-payment is under `/api/v1/bookings/{id}/confirm-payment` and is mutex-protected.

Protected endpoints (booking_lock required):
| Endpoint | Has Mutex | Notes |
| --- | --- | --- |
| POST /api/v1/bookings/{id}/cancel | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| POST /api/v1/bookings/{id}/reschedule | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| POST /api/v1/bookings/{id}/no-show | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| POST /api/v1/bookings/{id}/no-show/dispute | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| POST /api/v1/bookings/{id}/retry-payment | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| POST /api/v1/bookings/{id}/confirm-payment (deprecated) | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| PATCH /api/v1/bookings/{id}/payment-method | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| POST /api/v1/instructor/bookings/{id}/dispute | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| POST /api/v1/admin/bookings/{id}/cancel | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| POST /api/v1/admin/bookings/{id}/no-show/resolve | ✅ | Booking mutex `booking:{booking_id}:mutex` |
| POST /api/v1/admin/refunds/{id}/refund | ✅ | Booking mutex `booking:{booking_id}:mutex` |

Endpoints without mutex (documented safe):
| Endpoint | Mutex | Rationale |
| --- | --- | --- |
| POST /api/v1/payments/webhooks/stripe | ❌ | Dispute handlers use booking_lock_sync; other handlers are idempotent + state-checked |

Celery tasks (booking_lock_sync required):
| Task | Has Mutex | Notes |
| --- | --- | --- |
| process_scheduled_authorizations | ✅ | Skips if locked |
| retry_failed_authorizations | ✅ | Skips if locked |
| capture_completed_lessons | ✅ | Skips if locked |
| retry_failed_captures | ✅ | Skips if locked |
| resolve_undisputed_no_shows | ✅ | Skips if locked |

## U) v2.1.1 Compliance Summary

Status: ✅ FULLY ALIGNED

| Phase | Description | Status | Tests |
| --- | --- | --- | --- |
| Phase 0 | Booking mutex | ✅ PASS | Phase 0 mutex suite |
| Phase 1 | Critical money fixes | ✅ PASS | Cancel/refund/deadline tests |
| Phase 2 | LOCK anti-gaming | ✅ PASS | `backend/tests/integration/test_lock_mechanism.py` |
| Phase 3 | Credit reservation | ✅ PASS | `backend/tests/integration/test_credit_reservation.py` |
| Phase 4 | No-show handling | ✅ PASS | `backend/tests/integration/test_no_show_handling.py` |
| Phase 5 | Authorization timing | ✅ PASS | Booking payment boundary + task tests |
| Phase 6 | State machine & failures | ✅ PASS | Canonical status + capture failure + dispute tests |

Canonical payment_status values (Section 4.1):
- [x] Only 6 values used: scheduled, authorized, payment_method_required, manual_review, locked, settled
- [x] settlement_outcome carries resolution detail
- [x] No legacy values remain in code paths

Section 10 failure handling:
- [x] Auth failure -> payment_method_required -> retry -> T-12h cancel
- [x] Capture failure -> payment_method_required -> retry 4h -> 72h escalate -> manual_review + account lock
- [x] Dispute -> manual_review -> freeze credits -> attempt transfer reversal

Endpoint coverage:
- [x] All payment-critical endpoints protected by booking_lock
- [x] All Celery tasks use booking_lock_sync
- [x] Webhook handlers documented as idempotent; disputes use booking_lock_sync

Last verified: 2025-12-28
