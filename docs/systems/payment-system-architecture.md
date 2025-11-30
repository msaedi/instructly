# Payment System Architecture

*Last Updated: November 2025 (Session v117)*

## Overview

InstaInstru uses a **24-hour pre-authorization payment model** with Stripe Connect for marketplace payments. This architecture ensures instructors get paid reliably while protecting students from no-shows.

### Key Characteristics

| Aspect | Implementation |
|--------|---------------|
| Payment Provider | Stripe Connect (Express accounts) |
| Authorization Window | T-24 hours before lesson |
| Capture Trigger | 24 hours after instructor marks complete |
| Platform Fee | 15% of lesson price |
| Retry Strategy | T-22hr, T-20hr, T-18hr, T-12hr, cancel at T-6hr |
| Credit System | Milestone rewards at S5 ($10) and S11 ($20) |

### Payment Flow Summary

```
Booking Created → T-24hr: Authorize → Lesson Occurs → Instructor Marks Complete → +24hr: Capture
                     ↓
              Auth Fails? → Retry at T-22/20/18/12hr → Cancel at T-6hr
```

---

## Architecture

### Database Models

Located in `backend/app/models/payment.py`:

| Model | Purpose | Key Fields |
|-------|---------|------------|
| `StripeCustomer` | User → Stripe customer mapping | `user_id`, `stripe_customer_id` |
| `StripeConnectedAccount` | Instructor Stripe Express accounts | `instructor_profile_id`, `stripe_account_id`, `onboarding_completed` |
| `PaymentIntent` | Tracks payment for each booking | `booking_id`, `stripe_payment_intent_id`, `amount`, `application_fee`, `status` |
| `PaymentMethod` | Saved payment methods | `stripe_payment_method_id`, `card_last4`, `card_brand`, `is_default` |
| `PaymentEvent` | Audit trail for all payment state changes | `payment_intent_id`, `event_type`, `event_data` |
| `PlatformCredit` | Platform credits for students | `user_id`, `amount_cents`, `reason`, `expires_at`, `used_at` |
| `InstructorPayoutEvent` | Instructor payout tracking | `instructor_profile_id`, `amount`, `status` |

### Service Layer

| Service | Location | Responsibility |
|---------|----------|----------------|
| `StripeService` | `app/services/stripe_service.py` | Core Stripe API integration |
| `StudentCreditService` | `app/services/student_credit_service.py` | Credit lifecycle management |
| `PricingService` | `app/services/pricing_service.py` | Fee calculations |
| `PaymentRepository` | `app/repositories/payment_repository.py` | Database operations |

### Task Layer (Celery)

Located in `backend/app/tasks/payment_tasks.py`:

| Task | Schedule | Purpose |
|------|----------|---------|
| `process_scheduled_authorizations` | Every 30 min | Authorize payments at T-24hr |
| `retry_failed_authorizations` | Every 30 min | Retry failed auths with escalating urgency |
| `capture_completed_lessons` | Every hour | Capture payments 24hr after lesson completion |
| `capture_late_cancellation` | On-demand | Immediate capture for <12hr cancellations |
| `check_authorization_health` | Every 15 min | Monitor auth pipeline health |
| `audit_and_fix_payout_schedules` | Nightly | Audit payout schedule integrity |

---

## Key Components

### 1. Stripe Connect Integration

Instructors onboard via Stripe Express accounts:

```python
# Route: POST /api/v1/payments/connect/onboard
@router.post("/connect/onboard", response_model=OnboardingResponse)
async def start_onboarding(current_user: Annotated[User, Depends(get_current_instructor)]):
    account_link = stripe_service.create_connect_account(instructor_profile.id)
    return OnboardingResponse(onboarding_url=account_link.url)
```

**Onboarding States:**
- `not_started` - No Stripe account created
- `pending` - Account created, onboarding incomplete
- `completed` - `charges_enabled=True` and `details_submitted=True`
- `restricted` - Account has limitations (requires action)

### 2. Payment Authorization (T-24hr)

The system pre-authorizes payments 24 hours before lessons:

```python
# From payment_tasks.py
def process_scheduled_authorizations() -> AuthorizationJobResults:
    """Runs every 30 minutes via Celery Beat."""

    # Find bookings needing authorization (23.5 to 24.5 hours out)
    bookings = booking_repo.get_bookings_needing_authorization(
        min_hours=23.5,
        max_hours=24.5,
        statuses=[BookingStatus.CONFIRMED]
    )

    for booking in bookings:
        try:
            # Create Stripe PaymentIntent with capture_method='manual'
            payment_intent = stripe.PaymentIntent.create(
                amount=total_cents,
                currency='usd',
                customer=stripe_customer_id,
                payment_method=default_payment_method_id,
                capture_method='manual',  # Pre-auth only
                confirm=True,
                transfer_data={'destination': instructor_stripe_account_id},
                application_fee_amount=platform_fee_cents,
                metadata={'booking_id': booking.id}
            )
            booking.payment_status = 'authorized'
        except stripe.CardError as e:
            booking.payment_status = 'auth_failed'
            # Triggers retry flow
```

### 3. Retry Strategy with Escalation

Failed authorizations follow a structured retry pattern:

| Time Until Lesson | Action | Notification |
|-------------------|--------|--------------|
| T-24hr | Initial auth attempt | None (background) |
| T-22hr | First retry | Email: "Payment issue" |
| T-20hr | Second retry | Push notification |
| T-18hr | Third retry | Email + SMS |
| T-12hr | Final retry | Final warning email |
| T-6hr | **Cancel booking** | Cancellation notification |

```python
def retry_failed_authorizations() -> RetryJobResults:
    failed_bookings = booking_repo.get_bookings_with_auth_failures()

    for booking in failed_bookings:
        hours_until = (booking.start_datetime - utc_now()).total_seconds() / 3600

        if hours_until <= 6:
            # Too late - cancel booking
            booking.status = BookingStatus.CANCELLED
            booking.payment_status = 'auth_abandoned'
            notification_service.send_booking_cancelled_payment_failure(booking)
        elif hours_until <= 12:
            # Final attempt with urgent notification
            notification_service.send_final_payment_warning(booking, hours_until)
            _attempt_authorization(booking)
```

### 4. Payment Capture (Post-Lesson)

Payments are captured 24 hours after the instructor marks the lesson complete:

```python
def capture_completed_lessons() -> CaptureJobResults:
    """Runs hourly via Celery Beat."""

    # Find lessons completed 24+ hours ago with authorized payments
    lessons = booking_repo.get_completed_bookings_ready_for_capture(
        completed_before=utc_now() - timedelta(hours=24),
        payment_status='authorized'
    )

    for booking in lessons:
        payment_intent = payment_repo.get_payment_intent(booking.id)

        # Capture the pre-authorized amount
        stripe.PaymentIntent.capture(payment_intent.stripe_payment_intent_id)

        booking.payment_status = 'captured'
        payment_repo.create_event(payment_intent.id, 'captured', {...})
```

### 5. Platform Credits System

Students earn milestone credits based on completed lessons:

```python
# From student_credit_service.py
_MILESTONE_S5_AMOUNT = 1000   # $10 at 5th lesson
_MILESTONE_S11_AMOUNT = 2000  # $20 at 11th lesson (resets cycle)

def maybe_issue_milestone_credit(self, *, student_id: str, booking_id: str):
    """Called after lesson completion."""

    lifetime_completed = self.booking_repository.count_student_completed_lifetime(student_id)
    cycle_position = lifetime_completed % 11  # Cycle every 11 lessons

    if cycle_position == 5:
        amount, reason = 1000, "milestone_s5"
    elif cycle_position == 0:  # 11th lesson (11 % 11 = 0)
        amount, reason = 2000, "milestone_s11"
    else:
        return None

    return self.issue_milestone_credit(
        student_id=student_id,
        booking_id=booking_id,
        amount_cents=amount,
        reason=reason
    )
```

**Credit Lifecycle:**
- **Issuance**: Automatic at S5/S11 milestones
- **Usage**: Applied at checkout (reduces payment amount)
- **Revocation**: If triggering booking is refunded and credit unused
- **Reinstatement**: If credit was used on a booking that's refunded

---

## Data Flow

### Checkout Flow

```
1. Student submits checkout request
   POST /api/v1/payments/checkout

2. Concurrency lock acquired (30s TTL)
   Redis key: "checkout:{user_id}:{booking_id}"

3. Idempotency check
   Redis key: "idem:POST:/api/v1/payments/checkout:user:{user_id}:booking:{booking_id}"

4. If credits requested, validate and apply
   - Check available credit balance
   - Calculate remaining amount after credits

5. Create/update PaymentIntent
   - If remaining amount > 0: Create Stripe PaymentIntent
   - Store payment_method_id for T-24hr authorization

6. Update booking status
   - status: CONFIRMED
   - payment_status: PENDING (awaiting T-24hr auth)

7. Cache response and release lock
```

### Webhook Processing

Located in `backend/app/routes/stripe_webhooks.py`:

```python
@router.post("/payment-events", response_model=WebhookResponse)
async def handle_payment_events(request: Request):
    # 1. Verify webhook signature
    payload = await request.body()
    signature = request.headers.get("stripe-signature")

    if not stripe_service.verify_webhook_signature(payload, signature):
        raise HTTPException(400, "Invalid webhook signature")

    # 2. Parse and route event
    event = json.loads(payload)
    event_type = event.get("type")

    if event_type.startswith("payment_intent."):
        return stripe_service.handle_payment_intent_webhook(event)
    elif event_type.startswith("account."):
        return _handle_account_events(event)
    elif event_type.startswith("transfer."):
        return _handle_transfer_events(event)
```

**Handled Webhook Events:**

| Event | Handler Action |
|-------|----------------|
| `payment_intent.succeeded` | Update booking payment_status to 'captured' |
| `payment_intent.payment_failed` | Mark for retry, create PaymentEvent |
| `payment_intent.canceled` | Update status, notify student |
| `account.updated` | Check onboarding completion |
| `transfer.paid` | Log instructor payout confirmation |

---

## Error Handling

### Payment Failures

| Error Type | Response | Recovery |
|------------|----------|----------|
| Card declined | 402 Payment Required | Prompt for new card |
| Insufficient funds | 402 Payment Required | Retry at next window |
| Card expired | 400 Bad Request | Require card update |
| Stripe API error | 500 Internal Error | Automatic retry with backoff |
| Webhook signature invalid | 400 Bad Request | Log and reject |

### Concurrency Protection

```python
# Checkout route uses Redis locks
lock_key = f"{current_user.id}:checkout"
if not acquire_lock(lock_key, ttl_s=30):
    raise HTTPException(
        status_code=429,
        detail="Another checkout operation is in progress"
    )
```

### Idempotency

All financial operations use idempotency keys:

```python
# Generate deterministic idempotency key
raw_key = f"POST:/api/v1/payments/checkout:user:{user_id}:booking:{booking_id}"
idempotency_key = hashlib.sha256(raw_key.encode()).hexdigest()[:32]

# Check cache before processing
cached = redis.get(f"idem:{idempotency_key}")
if cached:
    return CheckoutResponse(**json.loads(cached))
```

---

## Monitoring

### Health Checks

```python
@typed_task(name="app.tasks.payment_tasks.check_authorization_health")
def check_authorization_health():
    """Runs every 15 minutes."""

    # Check for stuck authorizations (should complete within 5 minutes)
    stuck = payment_repo.get_stuck_authorizations(older_than_minutes=30)
    if stuck:
        logger.error(f"Found {len(stuck)} stuck authorizations", extra={
            "booking_ids": [b.id for b in stuck]
        })
        # Alert ops team via notification service
```

### Key Metrics

| Metric | Alert Threshold | Source |
|--------|-----------------|--------|
| Auth success rate | < 95% | PaymentEvent counts |
| Capture success rate | < 99% | PaymentEvent counts |
| Webhook processing time | > 5s | Route timing |
| Failed auth retries | > 10/hour | Celery task results |
| Stuck authorizations | > 0 | Health check task |

### Logging

All payment operations use structured logging:

```python
logger.info(
    "payment_authorized",
    extra={
        "booking_id": booking.id,
        "student_id": booking.student_id,
        "amount_cents": amount,
        "stripe_payment_intent_id": payment_intent.id,
    }
)
```

---

## Common Operations

### Add New Payment Method

```bash
# API: POST /api/v1/payments/methods
curl -X POST /api/v1/payments/methods \
  -H "Authorization: Bearer $TOKEN" \
  -d '{"stripe_payment_method_id": "pm_xxx", "set_as_default": true}'
```

### Check Credit Balance

```bash
# API: GET /api/v1/payments/credits
curl /api/v1/payments/credits -H "Authorization: Bearer $TOKEN"

# Response:
{
  "total_available_cents": 3000,
  "credits": [
    {"id": "...", "amount_cents": 1000, "reason": "milestone_s5", "expires_at": null},
    {"id": "...", "amount_cents": 2000, "reason": "milestone_s11", "expires_at": null}
  ]
}
```

### Force Authorization Retry (Admin)

```python
# Via Django shell or admin endpoint
from app.tasks.payment_tasks import retry_single_authorization
retry_single_authorization.delay(booking_id="01K2...")
```

### Manual Capture (Emergency)

```python
# Only for stuck payments - use with caution
import stripe
stripe.PaymentIntent.capture("pi_xxx")
# Then update booking.payment_status = 'captured' in database
```

---

## Troubleshooting

### Authorization Keeps Failing

1. **Check card validity**:
   ```sql
   SELECT * FROM payment_methods
   WHERE user_id = 'xxx' AND is_default = true;
   ```

2. **Check Stripe dashboard** for decline reason

3. **Verify student has valid payment method**:
   ```bash
   curl /api/v1/payments/methods -H "Authorization: Bearer $TOKEN"
   ```

4. **Check PaymentEvent history**:
   ```sql
   SELECT * FROM payment_events
   WHERE payment_intent_id = 'xxx'
   ORDER BY created_at DESC;
   ```

### Webhook Not Received

1. **Verify webhook endpoint in Stripe Dashboard**
   - URL: `https://api.instainstru.com/webhooks/stripe/payment-events`
   - Events: `payment_intent.*`, `account.*`, `transfer.*`

2. **Check webhook signing secret** matches `STRIPE_WEBHOOK_SECRET` env var

3. **Review Stripe webhook logs** in Dashboard → Developers → Webhooks

### Credits Not Applied

1. **Check credit availability**:
   ```sql
   SELECT * FROM platform_credits
   WHERE user_id = 'xxx' AND used_at IS NULL
   ORDER BY created_at DESC;
   ```

2. **Verify credit wasn't already used**:
   ```sql
   SELECT * FROM platform_credits
   WHERE source_booking_id = 'xxx';
   ```

3. **Check checkout request** included `requested_credit_cents`

### Instructor Not Receiving Payouts

1. **Verify Connect account status**:
   ```sql
   SELECT * FROM stripe_connected_accounts
   WHERE instructor_profile_id = 'xxx';
   ```

2. **Check `onboarding_completed = true`**

3. **Verify in Stripe Dashboard** that account is not restricted

4. **Check transfer events**:
   ```sql
   SELECT * FROM instructor_payout_events
   WHERE instructor_profile_id = 'xxx'
   ORDER BY created_at DESC;
   ```

---

## Configuration

### Environment Variables

| Variable | Purpose | Example |
|----------|---------|---------|
| `STRIPE_SECRET_KEY` | API authentication | `sk_live_xxx` |
| `STRIPE_PUBLISHABLE_KEY` | Frontend token | `pk_live_xxx` |
| `STRIPE_WEBHOOK_SECRET` | Webhook verification | `whsec_xxx` |
| `STRIPE_CONNECT_WEBHOOK_SECRET` | Connect webhooks | `whsec_xxx` |
| `PLATFORM_FEE_PERCENT` | Platform fee | `15` |

### Celery Beat Schedule

```python
# In celery_config.py
beat_schedule = {
    'process-scheduled-authorizations': {
        'task': 'app.tasks.payment_tasks.process_scheduled_authorizations',
        'schedule': crontab(minute='*/30'),
    },
    'retry-failed-authorizations': {
        'task': 'app.tasks.payment_tasks.retry_failed_authorizations',
        'schedule': crontab(minute='*/30'),
    },
    'capture-completed-lessons': {
        'task': 'app.tasks.payment_tasks.capture_completed_lessons',
        'schedule': crontab(minute=0),  # Every hour
    },
    'check-authorization-health': {
        'task': 'app.tasks.payment_tasks.check_authorization_health',
        'schedule': crontab(minute='*/15'),
    },
}
```

---

## Related Documentation

- [Stripe Connect Documentation](https://stripe.com/docs/connect)
- Backend routes: `backend/app/routes/v1/payments.py`
- Task definitions: `backend/app/tasks/payment_tasks.py`
- Models: `backend/app/models/payment.py`
