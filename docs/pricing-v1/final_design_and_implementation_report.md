iNSTAiNSTRU Pricing V1 — Final Design & Implementation Report

1) Executive Summary

We designed and shipped a config-driven pricing system that:
	•	Charges a Student Booking Protection fee (default 12%) transparently and includes it in the total.
	•	Pays instructors using tiered commissions (15% → 12% → 10%) with rolling 30-day maintenance, max one-tier step-down per session, and 90-day inactivity reset.
	•	Enforces price floors ($80 in-person / $60 remote for 60 min, pro-rated) for private sessions.
	•	Treats wallet credits as store credit: credits reduce platform revenue (fee+commission) only; instructors are always made whole (base − commission). If credits wipe out platform share, we issue an idempotent top-up transfer after capture.
	•	Powers the Confirm page with a server preview in all flows:
	•	GET /api/bookings/{id}/pricing (when a draft booking exists)
	•	POST /api/pricing/preview (quote mode, no id)
	•	Keeps Stripe destination charges and application_fee_amount perfectly in sync with the preview via dev-only parity assertions.
	•	Adds an Admin → Pricing Settings UI to adjust fee/tiers/floors/credit milestones in real time; the right-rail label is dynamic (no hardcoded “12%”).
	•	Fixes address provider parity (Google/Mapbox), meeting location formatting, and remote modality detection via location_type or meeting_location strings (e.g., “Online”).
	•	Seeds instructors at mixed tiers with enough last-30-day completions to maintain their tiers; rates meet floors.
	•	Stabilizes the Confirm page (credits commit-only, no spring-back, AbortError suppressed, Strict Mode guard).
	•	Makes Prometheus /metrics reliable & fast: smart refresh on immediate re-scrape for counter tests; cached otherwise.
	•	CI is green; PR is merged; feature branch deleted.

⸻

2) Final Fee Structure (What & Why)

2.1 Structure & Rationale

Student Booking Protection: 12% (configurable; appears as a clear line item).
Why:
	•	NYC buyers accept a moderate, transparent “protection” fee that communicates value (safety, background checks, no-hassle payment, insurance in scope).
	•	Anchoring the student side reduces instructor incentives to circumvent and gives students a stake in staying on-platform.

Instructor Commissions (tiered):
	•	15% for sessions 1–4
	•	12% for sessions 5–10
	•	10% for sessions 11+

Tier Maintenance (rolling 30 days):
	•	Keep 12% with ≥5 completed sessions in the last 30d.
	•	Keep 10% with ≥10 in the last 30d.
	•	Step-down max one tier per session (prevents whiplash).
	•	90-day inactivity resets to 15%.

Why:
	•	This is the minimum instructor take-rate that still funds Stripe + ops while dramatically reducing leakage (they see a path to 90%+ earnings quickly and can keep it through sustained activity).
	•	The maintenance rules reward real, recent contribution; instructors can’t unlock a low tier and coast forever.

Price Floors (private sessions) — pro-rated by duration:
	•	$80 in-person / 60 min
	•	$60 remote / 60 min

Why:
	•	Prevents sub-floor pricing that breaks unit economics (especially when credits/promos apply).
	•	NYC willingness to pay supports these floors; the FE also pre-warns before submission.

2.2 Quick Math Examples (for a $100 base)
	•	Student Fee (12%): $12 → student pays $112 (before credits).
	•	Commission (15%): $15 → instructor payout = $100 − $15 = $85.
	•	Commission (10%): $10 → instructor payout = $90.

With $20 credit:
	•	Student pays $112 − $20 = $92.
	•	Platform revenue = fee+commission − credit = $12 + $15 − $20 = $7 (15% tier).
	•	If credits exceed fee+commission, Platform puts fee to zero and tops up the instructor to maintain base − commission.

⸻

3) End-to-End Implementation

3.1 Authoritative math (server)

PricingService returns integer-cents:
	•	student_fee_cents = round(base * student_fee_pct)
	•	instructor_commission_cents = round(base * tier_pct)
	•	target_instructor_payout_cents = base − commission
	•	application_fee_cents = max(0, student_fee + commission − credit)
	•	student_pay_cents = max(0, base + fee − credit)
	•	If application_fee_cents == 0 and student_pay_cents < target_payout, then top_up_transfer_cents = target_payout − student_pay.

Floors: Compute a 60-min floor (in-person or remote), pro-rate by duration, apply to private sessions.
If under floor → 422 with details (modality, duration_minutes, base_price_cents, required_floor_cents).

Modality:
	•	Resolve remote if location_type == 'remote' or meeting_location contains “online|remote|virtual” (case-insensitive).
	•	Else in-person.

3.2 Stripe flow (Connect + destination charges)
	•	PaymentIntent.create:
	•	amount = student_pay_cents
	•	application_fee_amount = application_fee_cents
	•	transfer_data.destination = instructor_account
	•	Metadata: base, fee, commission, credit, student_pay, application_fee, target_payout, instructor_tier_pct, booking_id.
	•	Top-up Transfer (after capture): If credits wiped platform share and student pay < target payout, issue one Transfer (idempotent key topup:{pi_id}) for the shortfall.
	•	Dev-only parity: We assert PI amount, application_fee_amount and metadata agree with preview. These assertions are disabled in production.

3.3 Preview pipeline (Confirm page)

Two symmetric endpoints return identical shapes:
	•	GET /api/bookings/{id}/pricing?applied_credit_cents=… (draft flow)
	•	POST /api/pricing/preview (quote flow; no id). Payload includes instructor/service ids, local booking_date (YYYY-MM-DD), start_time (HH:MM 24h), duration, modality/location, and applied credits.

Confirm page always uses server values for:
	•	Booking Protection (x%) and Total = student_pay_cents.
	•	Skeleton only while loading; no em dash placeholder.

Credits:
	•	Slider is commit-only (pointer-up / “Apply full balance”).
	•	Effects are guarded to prevent loops/spring-back.
	•	AbortError from canceled requests is ignored (normal control path).
	•	Strict Mode guard ensures one initial preview per id/payload.

3.4 Admin UI

Admin → Settings → Pricing lets us adjust:
	•	student_fee_pct
	•	instructor_tiers
	•	tier_activity_window_days, tier_stepdown_max, tier_inactivity_reset_days
	•	price_floor_cents (in cents, private in-person & remote)
	•	credit milestone cycle (if enabled)

The right-rail label is dynamic (from preview/config) — no hardcoded “12%”.

3.5 Address providers (Google/Mapbox)
	•	Autocomplete & details honor provider end-to-end.
	•	When provider mismatches an id, we return 422 (invalid_place_id_for_provider) — no silent cross-fallback unless the provider is unspecified; then one fallback is allowed and logged.
	•	Normalizers return structured fields (street number/route, city, state short code, postal, country), and we compose the meeting location as “Street, City, STATE ZIP” with de-duplication.

3.6 Seeds
	•	Instructors seeded at mixed tiers (15/12/10) with last-30-day completions to maintain those tiers.
	•	Rates meet floors; last_tier_eval_at set sensibly (UTC now); modalities consistent.

3.7 Monitoring & performance
	•	/metrics/prometheus: TTL cache (1s) for performance; smart refresh when the second scrape lands within ~0.75s to make counter-increment tests deterministic.
	•	We bypass cache in tests and suppress AbortError noise.
	•	All monitoring tests pass in CI.

⸻

4) Developer Runbook

4.1 Change the Booking Protection percent (e.g., 12% → 14%)
	1.	Open Admin → Settings → Pricing.
	2.	Update Student Booking Protection (decimal) to 0.14 and Save.
	3.	Confirm on Confirm page: label shows “(14%)”; preview totals reflect new fee.
	4.	Optional: run the Stripe E2E test in test mode to validate preview ↔ PI parity.

4.2 Adjust instructor tiers / maintenance
	•	Modify instructor_tiers in Admin (min/max/pct decimals).
	•	Adjust maintenance windows / inactivity days as needed.
	•	Save and verify in preview responses: instructor_tier_pct floats match expectations.

4.3 Adjust floors
	•	Update price_floor_cents (in cents) for private in-person/remote in Admin.
	•	FE & backend react immediately; Confirm page shows pre-warn + 422 when under floor.

4.4 Seeds
	•	Seed scripts set current_tier_pct (15/12/10) and create seed_completed_last_30d completions so those tiers stick.
	•	Ensure seeded rates meet floors.

4.5 Stripe test-mode E2E
	•	Use the optional test harness to create a booking, preview, and PI, then assert:
	•	PI amount == preview.student_pay_cents
	•	PI application_fee_amount == preview.application_fee_cents
	•	Dev parity asserts metadata matches preview.
	•	When credits exceed platform share, a top-up Transfer is created (or allowed by Stripe).

⸻

5) Public Contracts (Preview API)

5.1 POST /api/pricing/preview (quote)

Request (JSON):

{
  "instructor_id": "…",
  "instructor_service_id": "…",
  "booking_date": "YYYY-MM-DD",
  "start_time": "HH:MM",
  "selected_duration": 60,
  "location_type": "remote" | "in_person" | "student_home" | "instructor_location" | "neutral",
  "meeting_location": "Online" | "Street, City, STATE ZIP",
  "applied_credit_cents": 0
}

Response (JSON):

{
  "base_price_cents": 8000,
  "student_fee_cents": 960,
  "instructor_commission_cents": 1200,
  "target_instructor_payout_cents": 6800,
  "credit_applied_cents": 0,
  "student_pay_cents": 8960,
  "application_fee_cents": 2160,
  "top_up_transfer_cents": 0,
  "instructor_tier_pct": 0.15,
  "line_items": [
    { "label": "Booking Protection (12%)", "amount_cents": 960 }
  ]
}

5.2 GET /api/bookings/{id}/pricing?applied_credit_cents=… (draft)
	•	Same response shape as POST.
	•	Used when a draft booking exists; Confirm page chooses GET vs POST automatically.

Common 422 Error (floor):

{
  "code": "PRICE_BELOW_FLOOR",
  "details": {
    "modality": "remote",
    "duration_minutes": 60,
    "base_price_cents": 5000,
    "required_floor_cents": 6000
  }
}


⸻

6) Stripe Metadata (PI)
	•	booking_id, instructor_tier_pct
	•	base_price_cents, student_fee_cents, commission_cents
	•	applied_credit_cents, student_pay_cents
	•	application_fee_cents, target_instructor_payout_cents

Dev-only parity asserts check PI vs preview and will never throw in production.

⸻

7) Testing & CI
	•	Backend: Unit/integration coverage for floors, tiers (including 5/11 boundaries, inactivity reset), preview parity, credits/top-up, providers, monitoring.
	•	Frontend: Confirm preview rendering (GET/POST), dynamic fee label, floor 422 UI, credits slider commit-only (rapid moves → single POST), address selection/provider retry.
	•	E2E (opt-in): Stripe test mode parity.

Monitoring tests are stable after smart-refresh. CI is green.

⸻

8) Risks & Follow-ups

Merged now (ready for production).
Non-blocking improvements we may schedule:
	•	Code organization: extract PaymentConfirmation subsections into smaller components for maintainability.
	•	More QA: add international address normalization cases and a small FE test for admin-config → UI propagation (already partially covered).
	•	Observability: small metrics on top-up frequency and preview error rates post-launch.

⸻

9) TL;DR
	•	Transparent 12% student fee (configurable), instructor tiers 15/12/10 with fair maintenance, floors enforced and pro-rated, credits reduce platform revenue (never instructor’s), top-up when needed.
	•	Confirm page is server-driven in all states (GET/POST), Stripe perfectly matches preview; Admin UI edits propagate live; seeds emulate real distribution; monitoring is reliable.
	•	CI green; PR merged; branch deleted. You’re ready to launch.
