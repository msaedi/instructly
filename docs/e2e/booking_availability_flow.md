# Booking ↔ Availability E2E Flow

This scenario exercises the happy path for coordinating instructor availability with the booking system while preserving the “availability does not mutate bookings” principle. The corresponding automated test lives at `backend/tests/e2e/test_booking_availability_flow.py`.

## Sequence

1. **Seed availability**
   - Use `AvailabilityService.save_week_availability` to publish non-overlapping slots for a future week (via `future_week_start` helper).
   - Cache warming runs automatically (in-memory for tests) to populate `week_map` and composite payloads.

2. **Create bookings**
   - Two confirmed bookings are inserted with `create_booking_pg_safe` (mirrors API behaviour without race conditions).
   - Each booking uses a different slot in the same day to guarantee no overlap.

3. **Cancel one booking**
   - `BookingService.cancel_booking` is invoked with notification + Stripe dependencies stubbed.
   - Cancellation fires cache invalidation and payment repository hooks, leaving the other booking untouched.

4. **Verify invariants**
   - Fetch the availability map again — it matches the pre-booking baseline (slots intact).
   - Instructor stats show `total=2`, `cancelled=1`, `completed=0`.
   - Attempting an overlapping third booking through `BookingService.create_booking` raises `BookingConflictException` with the instructor-specific message.

```
AvailabilityService.save_week_availability ────────────────┐
                                                           │
Booking builder (slot A) ───────┐                          │
Booking builder (slot B) ───────┤──> bookings confirmed ───┤
                                │                          │
BookingService.cancel_booking ──┘──> cache invalidation ───┤
                                                           │
BookingService.get_booking_stats ───> totals/cancelled 🧮   │
                                                           │
BookingService.create_booking (overlap) ──X conflict        │
                                                           │
AvailabilityService.get_week_availability ─── baseline ✅ ──┘
```

## Assumptions & stubs

- Stripe interactions are monkeypatched with `_StubStripeService` to avoid remote calls.
- Notification emails use `_StubNotificationService`.
- `AVAILABILITY_TEST_MEMORY_CACHE=1` ensures `CacheService` runs in-memory.
- The instructor fixture provides at least one service with suitable `duration_options`.

## Running just this test

```bash
TZ=UTC pytest -q backend/tests/e2e/test_booking_availability_flow.py
```
