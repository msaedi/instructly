# Beta Rollback Procedures

This document outlines quick and full rollback options for the beta program, plus an emergency bypass.

## Quick Rollback (< 1 minute)
Use when you want to immediately open access and disable beta gating behavior without code changes.

1. Set beta phase to production-like behavior via admin:
   - Go to `Admin → Beta → Settings` and set:
     - Beta Phase: `open_beta` (or set `Disable Beta` to true)
     - Allow signup without invite: true (optional)
   - Save settings.
2. The frontend middleware reads backend headers and will stop redirecting users.

Notes:
- `Disable Beta` sets `x-beta-phase: disabled` on backend responses. Frontend treats beta like off.
- `open_beta` allows `/signup` and student browsing on beta hosts.

## Full Rollback (≈ 5 minutes)
Use when you want to fully bypass beta logic application-wide.

1. Backend setting: set `Disable Beta = true` in `Admin → Beta → Settings`.
2. Verify headers:
   - Run `bash backend/scripts/verify_beta_production.sh` and confirm `x-beta-phase: disabled`.
3. Optional: Temporarily remove or bypass beta-related dependencies on backend routes if you added additional custom gating.
4. Deploy both backend and frontend if you made code changes.

## Emergency Bypass
If beta checks cause production issues and you need an immediate hotfix:

1. Frontend middleware quick bypass:
   - In `frontend/middleware.ts`, short‑circuit for beta hosts:
     ```ts
     // Emergency: bypass beta checks
     if (process.env.NEXT_PUBLIC_BETA_BYPASS === '1') {
       return NextResponse.next();
     }
     ```
   - Set `NEXT_PUBLIC_BETA_BYPASS=1` and redeploy.

2. Backend dependency/middleware bypass:
   - In `backend/app/api/dependencies/auth.py` and any beta dependencies, return early when `settings.beta_disabled` is true.
   - Our implementation already short-circuits when disabled.

3. Validate:
   - `bash backend/scripts/verify_beta_production.sh` should show `x-beta-phase: disabled` and app paths should be accessible.

## Verification Checklist
- `bash backend/scripts/verify_beta_production.sh beta.instainstru.com` shows:
  - Valid DNS A/CNAME
  - 200/3xx from HTTPS with HSTS header present
  - `x-beta-phase: disabled` or `open_beta`
  - `x-beta-allow-signup: 1` when enabling invite-free signup
- `/signup` accessible when intended
- Student search and bookings behave as configured

## Re-enable Beta
- Revert admin settings (`Disable Beta = false`, choose desired phase)
- Remove emergency env overrides and redeploy

---

See also:
- `Admin → Beta → Settings` for runtime toggles
- `docs/beta/` for additional operational runbooks
