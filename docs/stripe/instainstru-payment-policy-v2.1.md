# iNSTAiNSTRU Payment Policy - Definitive Reference
*Version 2.1 — December 2025*
*This document supersedes v2.0 and all prior payment policy documents.*

---

## 0. Scope

This document defines the **intended (“correct”) behavior** for:
- Booking payments
- Authorization and capture timing
- Instructor payouts
- Student cancellations and reschedules (including anti-gaming rules)
- Credits, refunds, disputes/no-shows, chargebacks
- Error handling (auth/capture/transfer/reversal failures)

This is a **policy and behavior spec**. It is not legal advice.

---

## 1. Stripe Architecture

### 1.1 Connect model
- iNSTAiNSTRU is a marketplace: students book lessons with instructors.
- We use **Stripe Connect** and **destination charges** (PaymentIntents created on the platform, with `transfer_data.destination` set to the instructor’s connected account).
- We should set `on_behalf_of` so that the instructor is the settlement merchant / merchant of record on receipts where applicable (confirm with counsel for your jurisdiction).

### 1.2 Key Stripe mechanics (must-haves)
1. **Authorization** = hold funds on student card using `capture_method="manual"`.
2. **Capture** = actually charge the student (funds move into Stripe balance).
3. **Destination transfer** = a transfer to the connected account that occurs automatically on capture when using destination charges.
4. **Transfer reversal** = claw back funds from the connected account (`Transfer.create_reversal()`).
5. **Refund** = return funds to the student’s card (`Refund.create()`), optionally reversing transfers and application fees.

---

## 2. Definitions and Amounts

### 2.1 Pricing terms
- `lesson_price` (**LP**) — base price of the lesson (ex: $120.00)
- `student_fee_rate` — 12% “Booking Protection Fee”
- `student_fee_amount` (**SF**) = `round(LP * 0.12)`
- `instructor_fee_rate` — tier-based (8–15%)
- `instructor_fee_amount` (**IF**) = `round(LP * instructor_fee_rate)`
- `instructor_payout_full` (**P_full**) = `LP - IF`

### 2.2 Credits
- `credits_reserved` (**CR**) — portion of LP paid using platform credits (0 ≤ CR ≤ LP)
- `card_lesson_amount` (**CL**) = `LP - CR`
- **Student always pays SF by card. Credits never cover SF.**

The amount placed on a PaymentIntent (card side) is:

- `payment_intent_amount` (**PI_amt**) = `CL + SF`

### 2.3 50/50 cancellation split (Option B)
For **student cancellations within <12 hours**, we split the lesson value:

- Student credit returned:
  - `credit_return_amount = round(0.5 * LP)`
- Instructor payout:
  - `payout_amount = round(0.5 * P_full)`
  (i.e., 50% of what they would have received for a completed lesson)

Notes:
- The student **still loses SF** (non-refundable for student-initiated cancels).
- The instructor still pays the instructor fee implicitly because payout is based on `P_full` (net payout).

---

## 3. Time Windows and Boundary Rules

All time comparisons are done in UTC using exact timestamps.

Define:
- `t_until_start = lesson_start_at - now`

**Boundaries are strict and consistent:**
- `>24h` means **`t_until_start >= 24h`** (exactly 24h counts as “>24h”)
- `12–24h` means **`12h <= t_until_start < 24h`**
- `<12h` means **`t_until_start < 12h`** (exactly 12h is in the 12–24h bucket)

---

## 4. Payment States

We keep payment status values **small and unambiguous**. Booking lifecycle (scheduled/completed/canceled) is tracked separately from payment status.

### 4.1 `payment_status` values

| Status | Meaning |
|---|---|
| `scheduled` | Authorization is scheduled for T-24h (no authorized PI yet) |
| `authorized` | PaymentIntent is authorized (`requires_capture`) |
| `locked` | Payment was captured and any automatic destination transfer was reversed; funds are held by platform pending outcome |
| `settled` | Financial outcome is final (no further automated money movement) |
| `payment_method_required` | Payment cannot proceed without student action (card declined / SCA needed) |
| `manual_review` | Exception state: reversal/transfer/refund failed or dispute/chargeback requires ops |

### 4.2 `settlement_outcome` values (recommended)
When `payment_status = settled`, we record one of:

- `lesson_completed_full_payout`
- `student_cancel_12_24_full_credit`
- `student_cancel_lt12_split_50_50`
- `student_cancel_gt24_no_charge`
- `locked_cancel_ge12_full_credit`
- `locked_cancel_lt12_split_50_50`
- `instructor_cancel_full_refund`
- `student_wins_dispute_full_refund`

Also record:
- `student_credit_amount` (0 / 50% LP / 100% LP)
- `instructor_payout_amount` (0 / 50% payout / 100% payout)
- `refunded_to_card_amount` (usually 0, except instructor fault/dispute)

---

## 5. Normal Flow (No Lock)

### 5.1 Timeline
```
BOOKING              T-24h                 LESSON END            T+24h after lesson end
   │                   │                      │                           │
   ▼                   ▼                      ▼                           ▼
Collect PM        AUTHORIZE (hold)       Dispute window            CAPTURE + PAYOUT
(no capture)                                                   (if not in dispute)
```

### 5.2 Authorization timing
| When booking is created | Authorization behavior |
|---|---|
| `t_until_start >= 24h` | Schedule authorization at `lesson_start_at - 24h` |
| `t_until_start < 24h` | Authorize immediately at checkout |

**Important:** booking inside 24h should not be “confirmed” unless authorization succeeds.

### 5.3 Capture and payout timing
- There is a **24-hour dispute window** after `lesson_end_at`.
- At `lesson_end_at + 24h`, if the booking is not in dispute and not already captured:
  - Capture the PaymentIntent
  - Pay the instructor (full payout)

**Completion marker:**
- Instructor can mark complete any time after the lesson.
- If not marked complete, system auto-completes at `lesson_end_at + 24h` (right before capture).

---

## 6. Reschedule Policy (Anti-Gaming via Lock)

### 6.1 Reschedule eligibility (correct behavior)
A student may reschedule if:

| Condition at time of reschedule request | Allowed? | Notes |
|---|---:|---|
| `t_until_start >= 24h` | ✅ Yes | Unlimited reschedules allowed in this window |
| `12h <= t_until_start < 24h` | ✅ Yes (once) | This triggers **LOCK** and becomes the student’s **last reschedule** |
| `t_until_start < 12h` | ❌ No | Must cancel (late cancel rules apply) |

### 6.2 What “LOCK” means
A **LOCK** is a protective action triggered by a **late reschedule (12–24h window)**. It prevents students from dodging late-cancel penalties by rescheduling last-minute.

When a booking becomes locked:
- The student’s card is charged (capture happens immediately).
- Any automatic transfer to the instructor is **reversed immediately** (instructor is not paid yet).
- Future student-initiated refunds become **credit-only** (no card refunds), except instructor fault/dispute.

### 6.3 Payment handling on reschedule
At reschedule time:

**Case A — Reschedule in `t_until_start >= 24h` (no lock):**
- If `payment_status = scheduled`: cancel prior auth task and schedule a new auth for the new time.
- No capture occurs.

**Case B — Reschedule in `12h <= t_until_start < 24h` (LOCK-triggering reschedule):**
- Must be the first late reschedule (after this, further reschedules are blocked).
- If `payment_status = authorized`:
  1) Capture immediately
  2) Reverse the resulting destination transfer immediately
  3) Set `payment_status = locked`
- If `payment_status = scheduled` (edge case: auth hasn’t fired yet but you’re now inside 24h):
  - Perform authorization immediately, then apply steps above.
- Record:
  - `locked_at`
  - `locked_from_lesson_start_at` (the lesson start time that was <24h away)
  - `late_reschedule_used = true`

---

## 7. Student Cancellation Policy

### 7.1 Regular bookings (not locked)

| Cancel window (relative to current lesson start) | Payment status expected | Money action | Student receives | Instructor receives |
|---|---|---|---|---|
| `t_until_start >= 24h` | `scheduled` | Cancel auth task; release reserved credits | Credits reserved are released (if any); **no new credit** | $0 |
| `12h <= t_until_start < 24h` | `authorized` | Capture → reverse destination transfer → issue credit | **100% LP as credit** (SF kept) | $0 |
| `t_until_start < 12h` | `authorized` | Capture → reverse destination transfer → pay 50% payout → issue 50% credit | **50% LP as credit** (SF kept) | **50% of net payout** |

**Implementation note:** For the 12–24 and <12 windows we **always reverse the full automatic transfer** and then create explicit transfers for any instructor payout (0% or 50%). This prevents “captured” from meaning “paid” and keeps payout logic deterministic.

### 7.2 Locked bookings (post late-reschedule)

Once `payment_status = locked`, the student has already been charged and the auto-transfer has already been reversed.

| Cancel window (relative to new lesson start) | Money action | Student receives | Instructor receives |
|---|---|---|---|
| `t_until_start >= 12h` | Issue credit | **100% LP as credit** | $0 |
| `t_until_start < 12h` | Pay 50% payout + issue 50% credit | **50% LP as credit** | **50% of net payout** |

**Important:** Locked cancellations are **credit-only** (no card refunds), except instructor fault/dispute.

---

## 8. Instructor Cancellation, No-Shows, and Disputes

### 8.1 Instructor cancellation (any time)
If the instructor cancels:
- Student is made whole:
  - **Full refund to card (including SF)** if any amount was captured
  - If not captured: release authorization (if exists) and cancel tasks
- Any credits reserved are released back to the student
- Instructor receives $0

Set:
- `payment_status = settled`
- `settlement_outcome = instructor_cancel_full_refund`

### 8.2 Instructor no-show
If the instructor does not show up:
- Student is made whole (same as instructor cancel):
  - Refund to card (including SF) if captured
  - Otherwise release authorization / cancel tasks
- Instructor receives $0
- Student receives no penalty; credits reserved are released back

### 8.3 Dispute resolution (student is right)
If a dispute is resolved in the student’s favor:
- Student is made whole:
  - Refund to card (including SF) if captured
- Reverse any instructor payout if already paid (if reversal fails → manual review)
- Invalidate/freeze any credits issued for that booking (if relevant)

Set:
- `payment_status = settled`
- `settlement_outcome = student_wins_dispute_full_refund`

---

## 9. Credits Policy

### 9.1 What credits can pay for
- Credits can cover **lesson price (LP) only**.
- Credits **cannot** pay for SF (Booking Protection Fee).
- Credit usage order is FIFO (earliest expiring used first).

### 9.2 Reservation model (recommended)
To avoid double-spend and ensure correct restoration:

At booking time:
- Determine `CR` (credits_reserved), 0 ≤ CR ≤ LP
- Deduct CR from student’s available credit balance and mark it reserved for the booking.

On completion:
- Reserved credits become consumed (final).

On cancel/reschedule outcomes:
- Reserved credits are either:
  - released back to student (no-penalty cases), or
  - partially released (penalty cases), with the remainder forfeited.

### 9.3 Credit return rules (summary)
Define `credit_return_target` for student-initiated cancels:

- Cancel `>=24h` (no lock):
  - `credit_return_target = CR` (release only; no new credit)
- Cancel `12–24h` OR locked cancel `>=12h`:
  - `credit_return_target = LP`
- Cancel `<12h` (regular or locked):
  - `credit_return_target = round(0.5 * LP)`

Mechanics:
- Release `min(CR, credit_return_target)` from reservation
- Issue additional credit for any remaining `credit_return_target - CR` (if positive)
- If `CR > credit_return_target`, the difference is forfeited as the penalty.

### 9.4 Expiration
- Credits expire **1 year** from issuance date.

---

## 10. Failure Handling and Retries

### 10.1 Authorization failure at T-24h
If authorization fails at T-24:
- Set `payment_status = payment_method_required`
- Create `t24_first_failure_email_sent` event
- Send email via `notification_service.send_final_payment_warning()`
- Retry authorization every 30 minutes

**Hard deadline:** If still not authorized by **T-12h**, auto-cancel booking:
- Student receives no penalty (equivalent to `>=24h` cancel)
- Instructor is not expected to hold the slot without payment certainty

### 10.2 Capture failure at payout time
If capture fails at `lesson_end + 24h`:
- Set `payment_status = payment_method_required`
- Notify student to update payment method
- Retry capture/collection for a bounded window (recommended 48–72h)

Instructor payout policy:
- Instructor payout occurs **only after successful collection**, unless platform explicitly chooses to advance payout (business decision).

After retry window:
- Mark `payment_status = manual_review`
- Lock student account from new bookings until resolved

### 10.3 Transfer reversal failure
If transfer reversal fails (API error, insufficient balance, restrictions):
- Set `payment_status = manual_review`
- Record `reversal_failed_at`, `reversal_error`
- Freeze further automated actions on that booking
- Ops resolves (platform may eat loss or recover from instructor / future payouts)

### 10.4 Manual transfer failure (payout creation fails)
If creating a payout transfer fails:
- Set `payment_status = manual_review`
- Do not mark booking as settled
- Ops retries or resolves funding/balance issues

### 10.5 Chargebacks / disputes (bank disputes)
When a chargeback/dispute is opened:
- Immediately set `payment_status = manual_review`
- Freeze any related credits (cannot be spent)
- If credits already spent, set student balance negative and block future bookings
- If instructor has been paid, attempt to reverse payout where appropriate
- If dispute is lost:
  - permanently revoke frozen credits
  - record delinquency and restrict student account

---

## 11. Race Conditions and Idempotency (Implementation Requirements)

All money-moving operations **must be idempotent** and protected against double execution:
- Use Stripe idempotency keys for:
  - `PaymentIntent.capture`
  - `Transfer.create`
  - `Transfer.create_reversal`
  - `Refund.create`
- Use database transaction locks (or booking-level mutex) so only one “money action” runs per booking at a time.
- Store and re-use:
  - `payment_intent_id`
  - `transfer_id` (from capture)
  - `transfer_reversal_id`
  - `payout_transfer_id` (manual payout)
  - `refund_id`

---

## 12. Examples (LP=$120, SF=12%, Instructor tier=12%)

Assume:
- LP = 120.00
- SF = 14.40
- IF = 14.40
- P_full = 105.60

### 12.1 Student cancels 12–24h before (not locked)
- Capture card: student pays `LP + SF = 134.40`
- Reverse transfer: instructor gets $0
- Student credit: +120.00
- Student net loss: 14.40 (SF)

### 12.2 Student cancels <12h before (not locked) — 50/50
- Capture card: student pays 134.40
- Reverse transfer fully
- Pay instructor 50% payout: 52.80
- Issue student credit: 60.00
- Student net loss: 74.40 (60 lesson penalty + 14.40 SF)

### 12.3 Late reschedule in 12–24h window → LOCK, then cancel >=12h before new lesson
At lock time:
- Capture now + reverse transfer, set `locked`

Later cancellation:
- Student credit: +120.00
- Instructor: $0
- No card refund (credit-only)

### 12.4 Late reschedule in 12–24h window → LOCK, then cancel <12h
- Student credit: +60.00
- Instructor payout: 52.80

---

## 13. Appendix: Stripe API Calls (Mapping)

| Action | Stripe call(s) |
|---|---|
| Store payment method (recommended) | `SetupIntent.create()` + confirm on-session |
| Authorize (hold funds) | `PaymentIntent.create(capture_method="manual")` + `confirm=true` |
| Capture | `PaymentIntent.capture()` |
| Cancel auth / release hold | `PaymentIntent.cancel()` |
| Destination transfer reversal | `Transfer.create_reversal()` |
| Manual payout transfer | `Transfer.create()` |
| Refund to card (instructor fault/dispute) | `Refund.create(payment_intent=..., reverse_transfer=true, refund_application_fee=true)` |

---

## 14. Change Log (v2.0 → v2.1)

- **Strict boundary rules:** `<24h` and `>=24h` are consistent across all logic; exact 24h counts as “>24h”.
- **Reschedules:** unlimited reschedules allowed when `>=24h`; a reschedule in `12–24h` is allowed once and triggers LOCK; reschedules `<12h` are blocked.
- **Student late cancel `<12h` changed to 50/50:** student gets 50% LP credit; instructor gets 50% net payout.
- **Introduced `locked` payment status** to eliminate ambiguity of “captured but not paid.”
- **Added complete failure handling** for authorization failures, capture failures, reversals, transfers, chargebacks, and disputes.
