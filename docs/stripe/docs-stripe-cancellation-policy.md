# InstaInstru Cancellation & Payment Policy
*Last Updated: January 2026 (Audit updates)*
*Updates in this revision are marked with [UPDATED] or [NEW].*

## Overview

This document defines the complete cancellation, refund, and payment policies for the InstaInstru platform. These policies balance student flexibility with instructor protection while ensuring platform financial sustainability.

---

## Payment Timeline

```
T-24h              T (lesson start)        T+24h
  │                      │                    │
  ▼                      ▼                    ▼
AUTHORIZE ────────────► LESSON ────────────► CAPTURE
```

| Event | Timing | Description |
|-------|--------|-------------|
| **Authorization** | 24 hours before lesson | Payment is authorized (held on student's card) |
| **Lesson** | Scheduled time | Lesson takes place |
| **Capture** | 24 hours after lesson ends | Payment is captured and transferred to instructor |

- [UPDATED] For bookings/reschedules within 24 hours (including gaming reschedules <24h from the original lesson), authorization is triggered immediately instead of waiting for T-24h.

---

## Cancellation Policy

### Policy Summary

| Window | Policy | Student Receives |
|--------|--------|------------------|
| **More than 24 hours** | Full refund | Card refund (full amount including fees) |
| **12-24 hours** | Credit only | Platform credit for lesson price (net of credits already used; fee non-refundable) |
| **Less than 12 hours** | No refund | Nothing (instructor receives payment) |

### Instructor Cancellation [UPDATED]

If an instructor cancels at any time, the system cancels the PaymentIntent (releases the authorization) and the student is not charged. This is handled automatically by the cancellation flow.

### User-Facing Messaging

**More than 24 hours before lesson:**
> "Life happens! You can cancel your session free of charge. Would you like to reschedule instead?"

**12-24 hours before lesson:**
> "Cancellations made 12-24 hours before your lesson will receive platform credit equal to the lesson price ($X). The booking protection fee is non-refundable."

**Less than 12 hours before lesson:**
> "To respect our instructors' time, unfortunately cancellations made less than 12 hours before a lesson can't be rescheduled and will be charged in full."

---

## Cancellation Examples

### Example 1: Cancel More Than 24 Hours Before

**Scenario:**
- Student books Piano lesson with Sarah for Saturday 2:00 PM
- Lesson price: $120.00
- Platform fee: $14.40
- Total charged: $134.40
- Student cancels on Thursday 10:00 AM (>48 hours before)

**Result:**
- Payment authorization released
- Student receives full refund to card: **$134.40**
- Instructor receives: $0
- Platform receives: $0

---

### Example 2: Cancel 12-24 Hours Before

**Scenario:**
- Student books Piano lesson with Sarah for Saturday 2:00 PM
- Lesson price: $120.00
- Platform fee: $14.40
- Total charged: $134.40
- Student cancels on Friday 4:00 PM (22 hours before)

**Result:**
- Payment captured: $134.40
- Transfer to instructor reversed: $0 to instructor
- Platform credit issued: **$120.00** (lesson price only)
- Platform retains: **$14.40** (booking fee - covers Stripe costs)
- Instructor receives: $0

**Student's Credit:**
- $120.00 platform credit (expires in 1 year)
- Can be used toward any future booking

---

### Example 3: Cancel Less Than 12 Hours Before

**Scenario:**
- Student books Piano lesson with Sarah for Saturday 2:00 PM
- Lesson price: $120.00
- Platform fee: $14.40
- Total charged: $134.40
- Student cancels on Saturday 8:00 AM (6 hours before)

**Result:**
- Payment captured immediately: $134.40
- Instructor receives: **$105.60** (at T+24h)
- Platform receives: **$28.80** (student fee + instructor fee)
- Student receives: **$0**

---

## Reschedule Policy

### Policy Summary

| Condition | Allowed? | Details |
|-----------|----------|---------|
| First reschedule (>12h before) | ✅ Yes | Free, no penalty |
| First reschedule (<12h before) | ❌ No | Too close to lesson |
| Second reschedule | ❌ No | Must cancel + rebook |

### Key Rule: One Reschedule Per Booking

A booking can only be rescheduled **once**. If the student needs to change the date again, they must:
1. Cancel the rescheduled booking (receives credit per cancellation policy)
2. Book a new lesson (can use the credit)

**User-Facing Message (Attempting Second Reschedule):**
> "You've already rescheduled this booking. To change the date again, please cancel (for credit) and book a new lesson."

### Rescheduled Booking Cancellation Policy (Part 4b: Fair Policy)

**Important:** Rescheduled bookings have a **fair** modified cancellation policy that only penalizes gaming attempts.

**The key distinction:** When was the reschedule performed relative to the ORIGINAL lesson?

| Reschedule When | Cancel When | Result |
|-----------------|-------------|--------|
| **>24h from original** (legitimate) | >24h from new | Full card refund |
| **>24h from original** (legitimate) | 12-24h from new | Credit (lesson price only) |
| **<24h from original** (gaming) | >24h from new | Credit (lesson price only) |
| **<24h from original** (gaming) | 12-24h from new | Credit (lesson price only) |
| **Any** | <12h from new | No refund |

**[UPDATED] Exactly 24h from the original lesson is treated as legitimate (not gaming).**
**[UPDATED] Credits issued on cancellation are net of credits already used on the booking.**

**How it works:**
- We store `original_lesson_datetime` (previous booking's lesson time) when a booking is rescheduled
- We use `booking.created_at` as the reschedule timestamp
- [UPDATED] Gaming detection: `hours_from_original = original_lesson_datetime - created_at`; gaming if **<24h** (exactly 24h is legitimate)
- If the original lesson was **>=24h away** when rescheduled → Legitimate, normal cancellation policy applies
- If the original lesson was **<24h away** when rescheduled → Gaming attempt, credit-only policy
- [NEW] If gaming is detected, authorization is triggered immediately when the reschedule is confirmed (not at T-24h), ensuring an auth exists for any later cancellation.

**Rationale:** This closes the "reschedule loophole" (escaping 12-24h penalty by rescheduling) while NOT penalizing students who legitimately reschedule early.

---

## Reschedule Examples

### Example 4: First Reschedule (Allowed)

**Scenario:**
- Student has Piano lesson booked for Saturday 2:00 PM
- It's Thursday (>24h before)
- Student reschedules to next Wednesday 3:00 PM

**Result:**
- ✅ Reschedule successful
- Same payment authorization transferred to new date
- No charges, no credits
- Booking now marked as `rescheduled_from_booking_id`

---

### Example 4b: Reschedule When Payment Already Captured

**Scenario:**
- Student books Piano lesson for tomorrow 12:00 PM (19 hours away)
- Payment already captured: $134.40 (because <24h)
- Student reschedules to Wednesday 8:30 PM

**Result:**
- ✅ Reschedule successful
- Captured payment transfers to the new booking (no refund, no new charge)
- No new payment intent created
- Original `payment_intent_id` stays linked to the booking
- `original_lesson_datetime` set for gaming detection on future cancellation

**Why?** Student's money is already committed. Moving the lesson date doesn't require re-charging - the funds apply to the new date.

---

### Example 5: Reschedule Then Cancel - GAMING Scenario

**Scenario:**
- Original booking: Saturday 2:00 PM
- It's Friday 8 PM (**18 hours before** original = in penalty window)
- Student reschedules to next Wednesday 3:00 PM
- Student decides to cancel on Sunday (>48h before Wednesday lesson)
- Lesson price: $120.00

**Result:**
- Even though it's >24h before the NEW lesson time...
- Original lesson was **<24h away when rescheduled** → GAMING attempt detected
- Platform credit issued: **$120.00**
- Platform retains: **$14.40**
- NO card refund
- [UPDATED] Authorization is triggered immediately at reschedule confirmation for gaming cases.

**Why?** Prevents the "reschedule loophole" exploit.

---

### Example 5b: Reschedule Then Cancel - LEGITIMATE Scenario

**Scenario:**
- Original booking: Saturday 2:00 PM
- It's Monday (5 days before original = NOT in penalty window)
- Student reschedules to next Wednesday 3:00 PM (life happens!)
- Student decides to cancel on Tuesday (>24h before Wednesday lesson)
- Lesson price: $120.00

**Result:**
- Original lesson was **>24h away when rescheduled** → LEGITIMATE reschedule
- Normal >24h cancellation policy applies
- Payment authorization released
- Student receives full refund to card: **$134.40**
- NO credit issued

**Why?** Fair treatment for legitimate early reschedules.

---

### Example 6: Attempt Second Reschedule (Blocked)

**Scenario:**
- Original booking: Saturday 2:00 PM
- Student reschedules to Wednesday 3:00 PM
- Student tries to reschedule again to Friday 4:00 PM

**Result:**
- ❌ Reschedule blocked
- Message: "You've already rescheduled this booking. To change the date again, please cancel (for credit) and book a new lesson."

**Student's Options:**
1. Keep the Wednesday lesson
2. Cancel (receive $120 credit) and book Friday separately

---

## Platform Credit Policy

### Credit Application Rules

| Rule | Description |
|------|-------------|
| **Credits apply to lesson price only** | Credits cannot cover platform fees |
| **Minimum card payment** | Platform fee must always be paid by card |
| **FIFO usage** | Earliest expiring credits used first |
| **Partial usage** | Credits can be partially applied |
| **Net credit on cancellation [UPDATED]** | Credit issued = lesson price - credits already used (floored at 0) |
| **Expiration** | Credits expire 1 year from issuance |

### Why Credits Don't Cover Fees

This ensures:
1. Platform always covers Stripe processing costs
2. Prevents infinite credit cycling exploits
3. Student has "skin in the game" for every booking

### Transfer Handling [UPDATED]

When credits reduce the student charge, the instructor transfer is capped to the amount actually charged:
`transfer = min(student_pay_cents, target_payout_cents)`. Any shortfall vs the target payout is covered by a top-up transfer during capture.

---

## Credit Examples

### Example 7: Booking With Partial Credit

**Scenario:**
- Student has $50 platform credit
- Books $120 lesson (total with fee: $134.40)

**Calculation:**
```
Lesson price:           $120.00
Credit applied:         -$50.00
Remaining lesson:        $70.00
Platform fee:           +$14.40
Card charge:            $84.40
```

**Result:**
- Credit used: $50.00
- Card charged: **$84.40**

---

### Example 8: Booking With Credit Exceeding Lesson Price

**Scenario:**
- Student has $150 platform credit (from previous cancellation)
- Books $120 lesson (total with fee: $134.40)

**Calculation:**
```
Lesson price:           $120.00
Credit applied:        -$120.00 (max = lesson price)
Remaining lesson:         $0.00
Platform fee:           +$14.40
Card charge:            $14.40
Unused credit:          $30.00 (remains in account)
```

**Result:**
- Credit used: $120.00
- Card charged: **$14.40** (fee only)
- Remaining credit: **$30.00**

---

### Example 9: Credit Booking Cancelled in 12-24h Window [UPDATED]

**Scenario:**
- Student used $50 credit + $84.40 card for $120 lesson
- Cancels 18 hours before lesson

**Result:**
- Card capture: $84.40
- Credit issued: **$70.00** (net lesson price credit: $120 - $50 used)
- Platform retains: $14.40 (fee)

**Student's Total Credit:** $70.00 (credits already used on the booking are not reinstated)

---

## Fee Structure Reference

### Student Fees
| Fee Type | Amount | When Charged |
|----------|--------|--------------|
| Booking Protection Fee | 12% of lesson price | At booking |

### Instructor Fees (Tiered)
| Tier | Bookings | Platform Fee |
|------|----------|--------------|
| Founding | Any | 8% (lifetime) |
| Tier 1 | 1-4 | 15% |
| Tier 2 | 5-10 | 12% |
| Tier 3 | 11+ | 10% |

### Example Fee Calculation

**$120 lesson with Tier 2 instructor (12%):**
```
Lesson price:                    $120.00
Student fee (12%):               +$14.40
─────────────────────────────────────────
Student pays:                    $134.40

Instructor fee (12%):            -$14.40
─────────────────────────────────────────
Instructor receives:             $105.60

Platform receives:                $28.80
  └─ Student fee:    $14.40
  └─ Instructor fee: $14.40
Stripe fee (~3.1%):              -$4.20
─────────────────────────────────────────
Platform net:                     $24.60
```

---

## Edge Cases & Special Scenarios

### Instructor No-Show

**Current Process:**
1. Student reports no-show via support
2. Admin reviews case
3. If verified, admin manually releases authorization or issues refund

**Payment Protection:**
- If before capture (within 24h of lesson): Release authorization
- If after capture: Manual refund via Stripe Dashboard

### Booking Within 12 Hours of Lesson

**Scenario:** Student books at 3pm for a 5pm lesson (2 hours away)

**Cancellation:** Falls into <12h window immediately
- If they cancel at 3:30pm: No refund, instructor paid
- This is intentional - short-notice bookings carry no-refund risk

### Authorization Expiration (7+ Days)

**Scenario:** Booking created but not completed for 7+ days

**Handling:**
- System attempts to create new authorization
- If successful, continues normal flow
- If failed, marks as `auth_expired` for manual intervention

---

## Policy Change Log

| Date | Change | Reason |
|------|--------|--------|
| Dec 2025 | 12-24h credit = lesson price only (not full amount) | Cover Stripe costs, prevent abuse |
| Dec 2025 | Part 4b: Fair reschedule policy | Only penalize gaming reschedules (<24h from original), not legitimate early reschedules |
| Dec 2025 | Added `original_lesson_datetime` field | Track when reschedule happened for fair policy |
| Dec 2025 | One reschedule per booking limit | Prevent gaming |
| Dec 2025 | Credits apply to lesson price only | Ensure fee always paid by card |
| Jan 2026 | [UPDATED] Immediate auth on gaming reschedule (<24h) | Close delayed-auth loophole |
| Jan 2026 | [UPDATED] Gaming threshold clarified (<24h, exactly 24h is legitimate) | Align policy with code |
| Jan 2026 | [UPDATED] Net credit issuance on cancellation | Prevent double-crediting |
| Jan 2026 | [UPDATED] Transfer capping when credits applied | Keep transfer <= student charge; top-up handles shortfall |
| Jan 2026 | [UPDATED] UTC-only backend datetime handling | Consistent time calculations |
| Jan 2026 | [UPDATED] Deprecated confirm-payment endpoint | Use /payments/checkout |

---

## Technical Implementation Notes

### Backend Files
- Cancellation logic: `booking_service.py:1003-1452`
- Authorization scheduling + gaming immediate auth: `booking_service.py:731-900`
- Credit system: `payment_repository.py:1141-1421`
- Stripe payment intent + transfer capping/top-up: `stripe_service.py:1257-1515`
- Capture task + auth expiry handling: `payment_tasks.py:1180-1355`

### Technical Notes [UPDATED]
- UTC-only backend time handling (all service/task logic uses `timezone.utc`); frontend converts to local time for display.
- Deprecated endpoint: `/api/v1/bookings/{id}/confirm-payment` (use `/api/v1/payments/checkout`).

### Key Database Fields
- `booking.rescheduled_from_booking_id` - Tracks if booking was rescheduled
- `booking.original_lesson_datetime` - Previous booking's lesson datetime for fair reschedule policy (Part 4b)
- `booking.created_at` - Used as reschedule timestamp for gaming detection
- `platform_credits.source_booking_id` - Links credit to originating booking
- `booking.payment_status` - Tracks payment state

### Cancellation Status Values
- `released` - Authorization cancelled (>24h cancel)
- `credit_issued` - Captured and credited (12-24h cancel)
- `captured` - Captured, instructor paid (<12h cancel or completed)

---

## Summary

| Policy | Description |
|--------|-------------|
| **>24h cancel** | Full card refund |
| **12-24h cancel** | Credit for lesson price (net of used credits), fee retained |
| **<12h cancel** | No refund, instructor paid |
| **Rescheduled cancel (gaming)** | Credit-only (net of used credits) if rescheduled from <24h window |
| **Rescheduled cancel (legit)** | Normal policy if rescheduled from >24h window |
| **Reschedule limit** | Once per booking |
| **Credit usage** | Lesson price only, fee by card |
| **Credit expiration** | 1 year from issuance |
