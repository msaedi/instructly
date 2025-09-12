# Dep-cruiser: Deferred items (type-only remediation)

- Replace components → features imports:
  - `components/lessons/modals/RescheduleTimeSelectionModal.tsx`
    → Introduce a small facade export in `features/student/booking/public.ts` re-exporting `TimeDropdown`, `SummarySection`, `DurationButtons`, `Calendar` for external use, or move shared, view-agnostic bits to `features/shared/booking/ui/`.
  - `components/AvailabilityCalendar.tsx` → depends on `features/student/booking/*`. Consider a thin facade or lift neutral UI to `features/shared/booking/ui/`.

- Feature-to-feature edges remaining in payment/booking:
  - `PaymentConfirmation.tsx` uses `features/student/booking/hooks/useCreateBooking` and `.../TimeSelectionModal`. Options:
    1) DI: pass required booking actions/UI via props from the page-level (recommended)
    2) Move pure type/helpers already addressed; for UI, add public facades.

- `features/student/payment/index.ts` re-export of internal modules triggers many edges.
  - Consider narrowing `index.ts` surface or creating `features/student/payment/public.ts` with a minimal export surface for external consumers.

- `features/student/booking/index.ts` re-export of internal modules causes intra-feature edges to be seen as cross-feature. Consider scoped public surface.
