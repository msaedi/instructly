# InstaInstru Business Rules

*Last Updated: January 2026 (Session v129)*

This document captures all business logic, policies, and rules that govern how InstaInstru operates. These rules are enforced by the backend services and are critical for understanding platform behavior.

---

## Marketplace Economics

### Platform Fees (Student Side)

| Fee Type | Rate | Description |
|----------|------|-------------|
| **Booking Protection Fee** | 12% | Applied to base lesson price, shown as line item |

The student pays: `lesson_price + booking_protection_fee`

### Instructor Commission Tiers

Instructors pay a platform commission that decreases with volume. Tier progression is evaluated based on completed lessons in the last 30 days.

| Tier | Completed Lessons (30 days) | Commission Rate |
|------|----------------------------|-----------------|
| Entry | 1-4 lessons | 15% |
| Growth | 5-10 lessons | 12% |
| Pro | 11+ lessons | 10% |

**Tier Rules:**
- **Activity Window**: 30 days for tier calculation
- **Stepdown Max**: 1 tier at a time (no jumping tiers)
- **Inactivity Reset**: 90 days without completed lessons resets to Entry tier

### Founding Instructor Program

Founding instructors receive **permanent** benefits (no maintenance requirements):

| Benefit | Value |
|---------|-------|
| **Platform Commission** | **8%** (locked for life) |
| **Search Ranking Boost** | 1.5x multiplier |
| **Tier Immunity** | Never subject to tier changes |
| **Founding Badge** | Permanent profile badge |

**Cap:** 100 founding instructor spots total (enforced with PostgreSQL advisory locks)

**Permanence:** Once granted, founding status is **permanent**. There are no ongoing requirements—no minimum hours, no activity thresholds. The 8% rate and search boost remain for life.

### Price Floors

Minimum lesson prices protect service quality:

| Modality | Minimum (60 min) | Pro-rated |
|----------|------------------|-----------|
| **In-Person (Private)** | $80 | Yes, by duration |
| **Remote/Online (Private)** | $60 | Yes, by duration |

Example: 30-minute in-person lesson minimum = $40

### Session Duration Constraints

| Constraint | Value |
|------------|-------|
| Minimum Duration | 30 minutes |
| Maximum Duration | 240 minutes (4 hours) |

---

## Payment & Authorization Timeline

### 24-Hour Pre-Authorization Model

```
T-24hr        T (Lesson)       T+24hr
   |              |               |
   v              v               v
[AUTHORIZE]   [LESSON]       [CAPTURE]
```

| Timing | Action | Status |
|--------|--------|--------|
| >24hr before lesson | Payment scheduled for T-24hr | `scheduled` |
| T-24hr | Card authorized (hold placed) | `authorized` |
| Lesson complete | Marked complete | `authorized` |
| T+24hr after lesson | Payment captured | `captured` → `settled` |

**Immediate Authorization Trigger:**
- Booking made <24 hours before lesson
- Gaming reschedule detected (see below)

---

## Cancellation Policies

### Student Cancellation (Standard Bookings)

| Timing | Outcome | Student Refund | Instructor Payout |
|--------|---------|----------------|-------------------|
| **≥24 hours** before | Full refund | 100% card refund | $0 |
| **12-24 hours** before | Partial credit | 100% lesson credit | $0 |
| **<12 hours** before | Split penalty | 50% lesson credit | 50% payout |

### Instructor Cancellation

| Timing | Outcome |
|--------|---------|
| **Any time** | Full refund to student (card) |

Instructors face no financial penalty but cancellations affect:
- Search ranking
- Profile visibility
- Potential account review for repeated cancellations

### LOCK Mechanism (Reschedule Protection)

When a student reschedules 12-24 hours before a lesson:

1. **LOCK Activation**: Payment is captured immediately, transfer reversed
2. **Funds held** by platform pending new lesson outcome
3. **Resolution scenarios:**

| New Lesson Outcome | Student Gets | Instructor Gets |
|-------------------|--------------|-----------------|
| Completed | Lesson delivered | Payout |
| Cancelled by student ≥12hr | 100% credit | $0 |
| Cancelled by student <12hr | 50% credit | 50% payout |
| Cancelled by instructor | 100% card refund | $0 |

### Anti-Gaming Reschedule Detection

**Gaming Reschedule**: Rescheduling to avoid cancellation penalties

Detection: If original lesson was <24 hours away when reschedule was made

**Consequences:**
- Immediate authorization required
- Cancellation policy uses **original** lesson datetime
- Credit-only refunds (no card refunds)

---

## Referral Program

### Student Referrals ("Give $20, Get $20")

| Party | Reward | Form |
|-------|--------|------|
| **Referrer** (existing user) | $20 | Platform credit |
| **Referee** (new user) | $20 | Platform credit |

**Trigger:** Referee completes their first lesson

**Constraints:**
- **Hold Period**: 7 days before credit unlocks
- **Expiry**: 6 months after unlock
- **Per-Referrer Cap**: 20 student referral rewards max
- **Minimum Basket**: $80 (referral applied to bookings ≥$80)

### Instructor Referrals

| Phase | Reward | Form |
|-------|--------|------|
| **Founding Phase** (cap < 100) | $75 | Cash (Stripe transfer) |
| **Post-Founding** | $50 | Cash (Stripe transfer) |

**Trigger:** Referred instructor completes their first lesson with a student

**Requirements:**
- Referrer must be an instructor with Stripe connected account
- One-time per referred instructor

### Fraud Prevention

| Check | Action |
|-------|--------|
| **Self-Referral** | Blocked (same device fingerprint or IP) |
| **Velocity Abuse** | Daily/weekly signup limits per referrer |
| **Device Fingerprinting** | Click and signup fingerprints compared |

---

## Rate Limiting

### Bucket Policies

| Bucket | Rate | Burst | Use Case |
|--------|------|-------|----------|
| `auth_bootstrap` | 100/min | 20 | Authentication flows |
| `read` | 120/min | 20 | GET requests |
| `write` | 30/min | 10 | POST/PUT/DELETE |
| `conv_msg` | 60/min | 10 | Messages per conversation |
| `financial` | 5/min | 0 | Payments, refunds, bookings |
| `admin_mcp` | 60/min | 10 | Admin operations |
| `admin_mcp_invite` | 10/min | 2 | Admin invites |

### Financial Operation Protection

Triple protection for booking, payment, and refund operations:
- Strict rate limits (5/min, no burst)
- Always enforced (never shadow mode)
- Idempotency keys for all operations

---

## Credits & Wallet

### Platform Credits

Credits can be applied to lesson prices but **not** to platform fees.

**Credit Usage:**
```
Student pays: (lesson_price - credits) + platform_fee
Minimum card charge: platform_fee (always charged)
```

### Student Credit Cycle (Loyalty Milestones)

Recurring credits based on **lifetime** completed bookings with an 11-booking cycle:

| Booking Number | Credit | Calculation |
|----------------|--------|-------------|
| 5, 16, 27, 38... | $10 | `lifetime_count % 11 == 5` |
| 11, 22, 33, 44... | $20 | `lifetime_count % 11 == 0` |

**How it works:**
- Cycle length: 11 bookings
- Position 5 in cycle: `milestone_s5` → $10 credit
- Position 0 in cycle (i.e., every 11th): `milestone_s11` → $20 credit

**Example progression:**
```
Booking #5  → $10 credit (5 % 11 = 5)
Booking #11 → $20 credit (11 % 11 = 0)
Booking #16 → $10 credit (16 % 11 = 5)
Booking #22 → $20 credit (22 % 11 = 0)
```

**Credit Revocation:** If a triggering booking is refunded/cancelled, the milestone credit is revoked.

### Credit States

| State | Description |
|-------|-------------|
| `pending` | Credit created but not yet available |
| `available` | Ready for use |
| `reserved` | Allocated to upcoming booking |
| `applied` | Used in completed transaction |
| `forfeited` | Lost due to cancellation/policy |
| `expired` | Past expiration date |

---

## Background Checks (Checkr Integration)

### Verification Workflow

1. **Consent** collected during onboarding
2. **Check Initiated** → Status: `pending`
3. **Results Received**:
   - `clear` → Instructor approved
   - `consider` → Manual review required
   - `adverse` → Adverse action workflow triggered

### Adverse Action Workflow

1. **Pre-Adverse Notice** sent
2. **Waiting Period** for instructor dispute
3. **Final Adverse** or resolution

### Validity

Background checks may have expiration (`bgc_valid_until`) based on platform policy.

---

## Two-Factor Authentication (2FA)

### Implementation

- **Method**: TOTP (Time-based One-Time Password)
- **Backup Codes**: 10 codes generated on setup
- **Valid Window**: Configurable (default allows ±1 time step)

### Security Features

- TOTP secrets encrypted at rest (Fernet encryption)
- Backup codes hashed with Argon2id
- Setup requires TOTP verification to enable

---

## Booking Constraints

### Advance Booking

| Constraint | Value |
|------------|-------|
| Maximum Future | 365 days |
| Maximum Slots/Day | 10 time slots |

### Valid Location Types

```
student_location    - Lesson at student's address
instructor_location - Lesson at instructor's location
online              - Virtual/remote lesson
neutral_location    - Third-party location
```

### Booking Status Flow

```
PENDING → CONFIRMED → COMPLETED
    ↓         ↓
CANCELLED  CANCELLED
```

### Payment Status Flow

```
payment_method_required → scheduled → authorized → captured → settled
                              ↓           ↓
                           locked → settled (via LOCK resolution)
                              ↓
                        manual_review
```

---

## Notification Policies

### Quiet Hours

| Window | Action |
|--------|--------|
| 10 PM - 8 AM (local time) | Non-urgent notifications deferred |

### SMS Rate Limits

| Type | Limit |
|------|-------|
| Phone Verification | 3 attempts per session |

---

## Instructor Profile Requirements

### Bio Constraints

| Field | Min | Max |
|-------|-----|-----|
| Bio Length | 10 chars | 1000 chars |
| Cancellation Reason | - | 255 chars |

### Service Areas

- Instructors offering travel lessons must have at least one service area
- Cannot remove last service area while travel lessons enabled

---

## Search & Discovery

### Ranking Signals (6-Signal Model)

1. **Relevance** - Query match score
2. **Quality** - Reviews, completion rate
3. **Distance** - Proximity to search location
4. **Price** - Competitive pricing
5. **Freshness** - Recent activity
6. **Completeness** - Profile completeness

### Founding Instructor Boost

Founding instructors receive 1.5x search ranking multiplier.

### Performance Target

Search responses: <50ms with 4-layer caching

---

## Tips & Gratuity

Students can add tips after lesson completion:

- Tips processed via separate Stripe payment
- 100% of tips go to instructor
- Status tracked: `pending`, `succeeded`, `processing`, `failed`

---

## Key Service Files

| Rule Category | Primary Service |
|---------------|-----------------|
| Pricing/Fees | `pricing_service.py`, `stripe_service.py` |
| Cancellation | `booking_service.py` |
| Referrals | `referral_service.py`, `referrals_config_service.py` |
| Rate Limiting | `ratelimit/config.py` |
| Background Checks | `background_check_workflow_service.py` |
| 2FA | `two_factor_auth_service.py` |
| Credits | `credit_service.py`, `student_credit_service.py` |

---

## Configuration Sources

| Config Type | Source | Hot-Reload |
|-------------|--------|------------|
| Pricing (tiers, floors, caps) | `platform_config` table | Yes |
| Referrals | `referral_config` table | Yes (45s cache) |
| Rate Limits | Environment + Redis overrides | Yes |
| Defaults | `pricing_defaults.py` | No (code) |
