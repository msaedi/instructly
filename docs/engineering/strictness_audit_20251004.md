# Strictness & Guardrails Audit — 2025-10-04

## Request DTOs
- Existing gate (`python tools/check_request_dto_strict.py`) reports **47 request-like classes** with zero hard failures.
- Heuristic scan for classes named `*Request/Create/Update/Confirm/Reset/Verify` that do **not** inherit `StrictRequestModel` surfaced **8 schemas**:
  `PasswordResetRequest`, `PasswordResetConfirm`, `BookingRescheduleRequest`, `AvailabilityCheckRequest`, `SavePaymentMethodRequest`, `CreateCheckoutRequest`, `SpecificDateAvailabilityCreate`, `UserCreate`.
  Each copies `StrictRequestModel.model_config`, but inheritance would make intent clearer and guarantees future mixins stay strict.
- Route body bindings: **6 handlers** accept DTO parameters without `Body(...)`, so dependency overrides or query/body mixing could bypass strict parsing:
  - `backend/app/routes/password_reset.py:47` `request_password_reset`
  - `backend/app/routes/password_reset.py:84` `confirm_password_reset`
  - `backend/app/routes/payments.py:701` `save_payment_method`
  - `backend/app/routes/payments.py:856` `create_checkout`
  - `backend/app/routes/availability_windows.py:338` `add_specific_date_availability`
  - `backend/app/routes/auth.py:55` `register`
  Tightening these signatures is ~10–20 min each (validation only, no behavior changes).

## Response Models
- Auditor (`tools/audit_response_model_strict.py`) scanned **215 `response_model` references** across routes.
- **166 references (140 unique schemas)** resolve to classes that neither inherit `StrictModel` nor set `extra="forbid"` / `validate_assignment=True`.
- First ten offenders by route for triage:
  1. `backend/app/routes/account_management.py` → `AccountStatusChangeResponse`
  2. `backend/app/routes/account_management.py` → `AccountStatusResponse`
  3. `backend/app/routes/addresses.py` → `NYCZipCheckResponse`
  4. `backend/app/routes/addresses.py` → `DeleteResponse`
  5. `backend/app/routes/addresses.py` → `CoverageFeatureCollectionResponse`
  6. `backend/app/routes/addresses.py` → `NeighborhoodsListResponse`
  7. `backend/app/routes/admin_background_checks.py` → `BGCReviewCountResponse`
  8. `backend/app/routes/admin_background_checks.py` → `BGCReviewListResponse`
  9. `backend/app/routes/admin_background_checks.py` → `BGCCaseCountsResponse`
  10. `backend/app/routes/admin_background_checks.py` → `BGCCaseListResponse`
- Models built on `StandardizedModel` remain lenient. Hardening requires moving them to `StrictModel` (or equivalent `model_config`) and plumbing through any producers that currently set dynamic extras.

## Frontend Dead Code (Knip)
- `npx knip --reporter=json` captured **39 unused files**, **1 unused dependency**, **4 unused devDependencies**, **6 unlisted dependencies**, and **~150 unused exports**.
- Baseline (`.artifacts/baselines/knip.count`) is **5**, so regressions exceed the budget.
- Configuration lives in `frontend/knip.config.mjs`; there is no `frontend/knip.json`. Entries include `e2e/**`, so test assets are scanned. Ignores cover `**/__tests__/**`, `type-tests/**`, `types/generated/**`, `.next/**`, `node_modules/**`; **`types/reference/**` and `reference/dormant/**` remain in scope.**
- Top 10 unused files (from compact report):
  `components/AvailabilityCalendar.tsx`, `components/BackButton.tsx`, `components/BookingCard.tsx`, `components/BookingDetailsModal.tsx`, `components/InstructorProfileNav.tsx`, `components/ManhattanMap.tsx`, `components/booking/CheckoutFlow.tsx`, `components/errors/QueryErrorBoundary.helpers.ts`, `components/errors/QueryErrorBoundary.tsx`, `components/instructor/PayoutsDashboard.tsx`.
- Current ignores allow Husky hooks and tooling scripts to linger; expect 1–3 h to prune or relocate assets, then enable hard-fail in CI.

## Lighthouse Coverage
- Repo carries `frontend/lighthouserc.json` (warn-only thresholds, no budgets), but **no GitHub workflow references Lighthouse or `lhci`.**
- Recommendation: add a nightly or on-demand `lhci` workflow covering `/`, `/login`, `/instructor/profile` with budgets (e.g., perf ≥0.85, a11y ≥0.95, blocking time ≤200 ms). Stabilization typically costs 0.5–1 day.

## Security Scans & Allowlists
- **npm**: `npm audit --audit-level=high` reports 15 findings (5 high). `frontend/audit-allowlist.json` is empty, and no CI step currently enforces the results (`scripts/parse-npm-audit.js` exists but is unused). Fail-on-new is therefore **not** active for frontend deps.
- **pip**: `backend/scripts/run_pip_audit.sh` runs `pip-audit --strict` fed by `backend/pip-audit.ignore.json` (11 advisories; 5 triggered in current scan). Fail-on-new stays intact for backend dependencies.
- New highs/criticals beyond the allowlists were **not** detected in this audit run, but frontend needs enforcement wiring before merging fixes.

## CI Gates & Branch Protection
- `.github/workflows/ci.yml` currently provides:
  - ✅ Frontend contract drift (`contract-check` job → `node scripts/contract-check.mjs`, hard fails on drift).
  - ✅ Pin assertion (`lint-build` job → Guardrail #12, exits non-zero).
  - ✅ Public env verifier (`npm run verify:public-env`).
  - ⚠️ Missing: backend strict-by-default coverage (`tools/check_mypy_coverage.py`), request-DTO scanner, response-model auditor, mypy baseline gate, Ruff, size-limit (`npm run size`), npm audit fail-on-new, backend tests.
- Parallel workflows (`backend-ci.yml`, `db-smoke.yml`, `env-contract.yml`, `schemathesis.yml`) host critical checks but are not wired into the consolidated CI job.
- Recommended required checks for Branch Protection:
  - `contract-check`
  - `lint-build`
  - `test` (job id in `backend-ci.yml`, label “Test Backend”)
  - `security` (job id in `backend-ci.yml`, label “Security Scan”)
  - `smoke` (from `db-smoke.yml` matrix)
  - `env-contract / smoke`
  - `schemathesis (read-only) / preview`
  - `schemathesis (read-only) / beta`
  - Any new strictness auditors introduced (`request-dto-strict`, `response-model-strict`, `size-limit`, `npm-audit`) once added.

## Evidence & Historical Runs
- Latest scheduled **env-contract** and **schemathesis** workflows expose environment headers/CORS, 429 dedupe, and OpenAPI drift for preview/beta. Reuse their most recent artifacts; no re-dispatch needed during this audit.
- Frontend/Backend CI pipelines are assumed green from the last mainline run; this audit operated read-only and did not trigger reruns.

## Effort Estimate
- **Response models → strict**: ~140 offenders × 0.5–0.75 h ⇒ **70–105 h** total (break into 5–8 model PR batches; start with high-traffic routes).
- **Route Body(...) fixes**: 6 handlers × 10–20 min ⇒ **1–2 h**.
- **Knip cleanup**: 39 files + exports ⇒ **1–3 h** if mostly dead code; add 0.5–1 h if reclassifying shared libraries.
- **LHCI enablement & budgets**: **0.5–1 day** (stabilize three representative pages, tune thresholds, mitigate flake).
- **Security allowlist trim**: Frontend high vulns (5) plus backend ignored advisories (11) ⇒ **30–90 min per advisory** for upgrade or mitigation justification.
- **Residual mypy exceptions** (e.g., `services.base`, `services.stripe_service`): expect **0.5–1.5 days each** if lifting to strict typing.
