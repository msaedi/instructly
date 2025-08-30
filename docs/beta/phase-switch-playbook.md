### Beta Phase Switch Playbook

Purpose: Safely change beta phases and verify effects without regressions.

Phases and toggles controlled in `Admin → Beta → Settings`:
- beta_phase: `instructor_only` | `open_beta` | `disabled`
- allow_signup_without_invite: boolean

Steps
1) Prepare
- Ensure backend is running and DB has `beta_settings` (alembic head).
- Be logged in as admin on the frontend.

2) Switch phase in Admin
- Go to `/admin/beta/settings` and update desired phase/toggles.
- Save and wait for confirmation toast.

3) Verify server headers (source of truth)
- Run: `bash backend/scripts/verify_beta_production.sh beta.instainstru.com`
- Confirm headers reflect the change: `x-beta-phase`, `x-beta-allow-signup`.

4) Validate key routes
- instructor_only + allow_signup=false
  - `/` blocked; `/instructor/join` allowed; `/signup` blocked.
- instructor_only + allow_signup=true
  - `/signup` allowed; general browsing blocked; `/instructor/join` allowed.
- open_beta
  - `/` allowed; `/signup` allowed; search and booking allowed.
- disabled
  - All routes behave as normal site.

5) Frontend middleware sanity check
- Navigate to the affected routes above on beta host. Ensure redirects match expectations.

6) Optional e2e smoke
- Run a minimal e2e flow for join/signup depending on phase.

7) Rollback if needed
- Use `docs/beta/rollback.md` for quick/full rollback steps.

Notes
- The frontend middleware fetches `/health` and relies on `x-beta-*` headers. If behavior seems stale, hard refresh the browser.
