# Guardrails Runbook (Privacy, CI, and Trunk Dev)

## Privacy Protection Audit – how to run
- **Triggers:** push to `main`, PRs to `main`, and manual dispatch.
- **Invariants enforced by CI (Workflow Lint):**
  - Uses **Docker Compose v2** (never `docker-compose` v1).
  - **DB image pinned by digest** and guarded in the workflow.
  - Triggers (push + PR to `main`) must exist.
- **Manual run:** Actions → *Privacy Protection Audit* → *Run workflow*.
- **What it does:** GHCR login → start DB (pgvector+postgis) → health/TCP waits → migrate & seed → run privacy audit → upload artifacts.
- **Artifacts:** `backend/logs/privacy_audit_report.json` and `.md`.

## Bumping the Privacy DB image (manual, no cron)
1. Actions → *Privacy DB Image Bump* → *Run workflow* (input: `tag`, e.g. `14-postgis-pgvector`).
2. The job resolves the tag to a **digest**, updates the workflow, and opens a PR if the digest changed (no-op otherwise).
3. Merge the PR; Privacy + Workflow Lint run automatically.

## GHCR access tips
- The GHCR package is linked to this repo; default `GITHUB_TOKEN` works.
- If ever denied, either re-link the package or add a repo secret `GHCR_PAT` with `read:packages`.

## Troubleshooting (fast paths)
- **“docker-compose: not found”** → some workflow still uses v1. Fix to `docker compose`. Workflow Lint will flag it.
- **Vector/PostGIS missing** → DB image not pinned/resolved; Workflow Lint guard should catch this. Re-pin via bump workflow.
- **Flaky DB bring-up** → the workflow already does health + TCP waits. If needed, increase retries/sleep slightly.
- **Vercel build rate limit** → wait for the cooldown, then use the PR re-run button or push a docs-only no-op commit to retrigger.

## Date/Time safety (payments)
- Tests lock the 24h boundary:
  - `23h59m` → `authorizing`
  - `24h01m` → `scheduled`
- Route + service tests exist; time math is deterministic.

## Trunk-based dev (current mode)
- Push to `main` by default.
- Open PRs only for risky changes (migrations/behavior/large diffs).
- Pre-push tip: `FAST_HOOKS=1 pre-commit run --all-files`.

## Backend strictness slice playbook
- Add Pydantic strict config to DTOs in the chosen module:
  - `from pydantic import ConfigDict`
  - `model_config = ConfigDict(extra="forbid", validate_assignment=True)` on request/response models.
- Raise mypy to strict for that module only via `backend/pyproject.toml`:
  - `[[tool.mypy.overrides]] module=["backend.app.routes.<module>"] strict=true`
- Add a tiny test asserting extra field → 422 under `STRICT_SCHEMAS=true`:
  - Use `fastapi.testclient` with `reload(main)` and skip with a reason if auth blocks validation.
- Keep slices small (≤10 files) and commit directly to `main`.

### Mypy overrides (strict by default)
- We are **strict by default** for backend: `backend.app.repositories.*`, `backend.app.services.*`, `backend.app.routes.*`.
- **Last wins**: mypy merges `[[tool.mypy.overrides]]` in order. Keep the strict globs **first**, then **documented exceptions** (e.g., `services.stripe_service`, `services.base`), then any custom flags.
- **Do not add per-file `strict=true` blocks** unless you also need non-default flags; the strict globs already cover new files.
- **Schemas**: request DTOs are enforced via `StrictRequestModel (extra="forbid")` and a CI scanner; we keep only minimal `schemas.*` flags (e.g., `check_untyped_defs`, `warn_unused_ignores`).
- The **mypy baseline gate** blocks new typing debt; any increase in errors fails CI.

## Env-contract smoke: 429 UX (gated)
- Location: `frontend/e2e/env-contract.spec.ts`.
- How to run (gated): set `PLAYWRIGHT_BASE_URL` and `E2E_RATE_LIMIT_TEST=1`.
- What it asserts: making quick requests to `/ops/rate-limits/test` yields a small, bounded count of HTTP 429 responses (deduped-retry UX).
- Default runs keep it skipped to stay fast.
- Note: 429 rate-limit assertion is strict (=1). Gate with `E2E_RATE_LIMIT_TEST=1`.

### How to run env-contract

- Preview (automatic):
  - The `env-contract` workflow defaults `PLAYWRIGHT_BASE_URL` to `${{ vars.PREVIEW_BASE_URL }}` and passes `${{ secrets.PREVIEW_STAFF_CODE }}` as `GATE_CODE`.
  - Playwright uses a helper to detect the staff gate and submit the token once, then proceeds with the suite. No secrets are printed.

- Beta (manual):
  - Dispatch the workflow with `base_url=${{ vars.BETA_BASE_URL }}` and provide a one‑time beta code via the `beta_code` input.
  - The helper submits the provided code for this run only; nothing is persisted in repository secrets.

- Optional admin mint step:
  - If an admin bearer is later added as `secrets.ADMIN_BEARER`, a disabled‑by‑default step can mint an invite code via `/api/beta/invites/generate` and export `GATE_CODE` for the run.

## E2E / a11y smoke

- Local strict run (fail on serious+critical):

```bash
A11Y_IMPACTS=serious,critical npx playwright test e2e/a11y.smoke.spec.ts
```

- Looser smoke (default, fail only on critical):

```bash
A11Y_IMPACTS=critical npx playwright test e2e/a11y.smoke.spec.ts
```

- With staff/beta gate bypass:

```bash
export PLAYWRIGHT_BASE_URL=http://localhost:3100
export GATE_CODE="***"
npx playwright test e2e/a11y.smoke.spec.ts
```

Notes:
- The a11y smoke bypasses the staff gate when `GATE_CODE` is set, waits for the app shell, and scans only `<main>` (WCAG 2 A/AA). It logs a concise `[a11y]` summary and remains non-blocking in CI unless `E2E_A11Y_STRICT=1`.

## FE public env verify (diff-aware)
- Script: `frontend/scripts/verify-public-env.mjs`.
- Behavior: scans for `env.get('NEXT_PUBLIC_…')` and `process.env.NEXT_PUBLIC_…` in frontend, filters to changed files in the current diff (PR/base vs `origin/main`).
- Failure message includes a fix hint:
  - Use `getPublicEnv('FOO')` from `@/lib/publicEnv` or a helper (e.g., `withApiBase`) in client code.

## Codebase metrics snapshots (admin dashboard)
- Run `python backend/scripts/codebase_metrics.py --save` (or the Celery task) only from a full clone. A shallow checkout reports too few commits and the guardrail now refuses to append history if totals drop.
- If the collector raises `git commit total would decrease`, fetch the full history (`git fetch --unshallow`) or restore the latest `metrics_history.json` backup before retrying.
- CI runs `backend/tests/scripts/test_metrics_history.py` to ensure commit totals in `metrics_history.json` stay monotonic.
- Keep nightly backups of `metrics_history.json` (e.g. artifact/S3) so we can restore a clean baseline if a bad snapshot ever lands.

## Nightly env-contract proof
- When: every day at 09:00 UTC (GitHub Actions schedule).
- Scope: API-only preview endpoints (no staff code).
- Evidence: workflow `env-contract` uploads `env-contract-evidence` artifact containing:
  - `[headers] X-Site-Mode=… X-Phase=…`
  - `[cors] access-control-allow-credentials=… access-control-allow-origin=…`
  - `[429-triage] dedupeKey=… limited=… attempts=…`
Use the artifact to confirm nothing regressed before promoting builds.

### Evidence artifact + Job Summary
- Both preview (`env-contract-evidence`) and beta (`env-contract-evidence-beta`) runs stash `env-contract-evidence.txt` + `pw.log` and append the same proof lines to the job summary.
- Job Summary (example)
  ```text
  [headers] X-Site-Mode=preview X-Phase=instructor_only
  [cors] access-control-allow-credentials=true access-control-allow-origin=https://preview.instainstru.com
  [429-triage] dedupeKey=env-contract:rate-limit-test limited=7 attempts=10
  ```
